"""订单售后退款服务 FastAPI 应用。

状态流转：
  订单:  CREATED --支付--> PAID --(累计退款达全额)--> REFUNDED
  售后:  PENDING --审核--> APPROVED/REJECTED --退款--> REFUNDED

业务规则：
  - 一个订单可存在多个售后申请；
  - 支持部分退款（退款金额由调用方指定，或退剩余全部）；
  - 单次退款金额必须 > 0；
  - 同一订单所有成功退款金额累计不得超过订单实际支付金额；
  - 仅状态为 REFUNDED 的售后才计入累计退款金额。

并发安全（多 Worker）：
  数据落在共享的 SQLite 文件，退款的「幂等去重 / 资源级去重 / 额度校验 / 写回」
  全部在 store.refund_transaction 内的单个 `BEGIN IMMEDIATE` 事务中完成，
  由数据库写锁串行化并叠加条件 UPDATE，因此即便多个 Worker 进程同时处理：
    1) 同一个 AfterSale —— 至多一个成功退款；
    2) 同一 Order 下的多个 AfterSale —— 成功退款累计金额不超过订单实付金额。
  详见 store.py。
"""
from datetime import datetime, timezone
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, Query

from models import Order, AfterSale, OrderStatus, AfterSaleStatus
from schemas import (
    CreateOrderRequest,
    PayRequest,
    CreateAfterSaleRequest,
    ReviewRequest,
    RefundRequest,
)
from store import store

app = FastAPI(title="订单售后退款服务", version="0.1.0")


def _now() -> datetime:
    return datetime.now(timezone.utc)


@app.post("/orders", response_model=Order, status_code=201)
def create_order(
    req: CreateOrderRequest,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
):
    # 安全：调用方声明的身份必须与下单用户一致，防止冒用他人身份建单。
    if x_user_id is not None and x_user_id != req.user_id:
        raise HTTPException(status_code=403, detail="user_id mismatch")
    order = Order(
        id=str(uuid.uuid4()),
        user_id=req.user_id,
        amount=req.amount,
        status=OrderStatus.CREATED,
        created_at=_now(),
    )
    store.insert_order(order)
    return order


@app.get("/orders", response_model=list[Order])
def list_orders(
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    # 仅当调用方携带 X-User-Id 时，才按归属过滤；未携带（可信内网/测试）保持原行为。
    return store.list_orders(user_id=x_user_id, limit=limit, offset=offset)


@app.get("/orders/{order_id}", response_model=Order)
def get_order(
    order_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
):
    order = store.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    # 安全：用户不能访问其他用户的订单（IDOR）。
    if x_user_id is not None and order.user_id != x_user_id:
        raise HTTPException(status_code=403, detail="not allowed to access this order")
    return order


@app.post("/orders/{order_id}/pay", response_model=Order)
def pay_order(
    order_id: str,
    req: PayRequest,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
):
    order = store.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    # 安全：只能为本人订单支付。
    if x_user_id is not None and order.user_id != x_user_id:
        raise HTTPException(status_code=403, detail="not allowed to pay this order")
    if order.status != OrderStatus.CREATED:
        raise HTTPException(
            status_code=409,
            detail=f"cannot pay order in status {order.status.value}",
        )
    order.status = OrderStatus.PAID
    order.paid_at = _now()
    store.save_order(order)
    return order


@app.post("/orders/{order_id}/after-sales", response_model=AfterSale, status_code=201)
def create_after_sale(
    order_id: str,
    req: CreateAfterSaleRequest,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
):
    order = store.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    # 安全：只能为本人订单发起售后。
    if x_user_id is not None and order.user_id != x_user_id:
        raise HTTPException(
            status_code=403, detail="not allowed to create after-sale for this order"
        )
    if order.status != OrderStatus.PAID:
        raise HTTPException(
            status_code=409,
            detail="after-sale can only be created for a paid order",
        )
    after_sale = AfterSale(
        id=str(uuid.uuid4()),
        order_id=order_id,
        reason=req.reason,
        status=AfterSaleStatus.PENDING,
        created_at=_now(),
    )
    store.insert_after_sale(after_sale)
    return after_sale


@app.get("/after-sales", response_model=list[AfterSale])
def list_after_sales(
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    # 仅当携带 X-User-Id 时按归属过滤（通过 JOIN orders，无 N+1）。
    return store.list_after_sales(user_id=x_user_id, limit=limit, offset=offset)


@app.get("/after-sales/{after_sale_id}", response_model=AfterSale)
def get_after_sale(
    after_sale_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
):
    after_sale = store.get_after_sale(after_sale_id)
    if after_sale is None:
        raise HTTPException(status_code=404, detail="after-sale not found")
    # 安全：用户不能访问其他用户的 AfterSale（通过归属订单的 user_id 判断）。
    if x_user_id is not None:
        order = store.get_order(after_sale.order_id)
        if order is None or order.user_id != x_user_id:
            raise HTTPException(
                status_code=403, detail="not allowed to access this after-sale"
            )
    return after_sale


@app.post("/after-sales/{after_sale_id}/review", response_model=AfterSale)
def review_after_sale(
    after_sale_id: str,
    req: ReviewRequest,
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
):
    # 安全：审核（通过/拒绝）属于客服/审核员权限，普通用户不得自行审核，
    # 否则可「自评自批」绕过审核直接走退款。未携带角色头时保持原（可信内网）行为。
    if x_user_role is not None and x_user_role not in ("reviewer", "admin"):
        raise HTTPException(
            status_code=403, detail="review requires reviewer role"
        )
    after_sale = store.get_after_sale(after_sale_id)
    if after_sale is None:
        raise HTTPException(status_code=404, detail="after-sale not found")
    if after_sale.status != AfterSaleStatus.PENDING:
        raise HTTPException(
            status_code=409,
            detail=f"cannot review after-sale in status {after_sale.status.value}",
        )
    after_sale.status = (
        AfterSaleStatus.APPROVED if req.approve else AfterSaleStatus.REJECTED
    )
    after_sale.reviewed_at = _now()
    after_sale.reviewer_note = req.reviewer_note
    store.save_after_sale(after_sale)
    return after_sale


@app.post("/after-sales/{after_sale_id}/refund", response_model=AfterSale)
def refund_after_sale(
    after_sale_id: str,
    req: Optional[RefundRequest] = None,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
):
    """执行退款。

    并发安全由 store.refund_transaction 在数据库层保证（认领 + 预留额度 +
    条件 UPDATE + 唯一幂等键，且慢速的第三方渠道调用在写锁之外）。详见 store.py。
    """
    # 安全：只能对本人的 AfterSale 发起退款。
    if x_user_id is not None:
        after_sale = store.get_after_sale(after_sale_id)
        if after_sale is not None:
            order = store.get_order(after_sale.order_id)
            if order is None or order.user_id != x_user_id:
                raise HTTPException(
                    status_code=403, detail="not allowed to refund this after-sale"
                )
    requested = (
        req.refund_amount if (req is not None and req.refund_amount is not None) else None
    )
    status_code, body = store.refund_transaction(after_sale_id, requested, idempotency_key)
    if status_code >= 400:
        raise HTTPException(status_code=status_code, detail=body.get("detail", ""))
    return AfterSale(**body)
