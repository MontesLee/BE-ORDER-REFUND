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
"""
from datetime import datetime, timezone
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException

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
def create_order(req: CreateOrderRequest):
    order = Order(
        id=str(uuid.uuid4()),
        user_id=req.user_id,
        amount=req.amount,
        created_at=_now(),
    )
    store.orders[order.id] = order
    return order


@app.get("/orders", response_model=list[Order])
def list_orders():
    return list(store.orders.values())


@app.get("/orders/{order_id}", response_model=Order)
def get_order(order_id: str):
    order = store.orders.get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    return order


@app.post("/orders/{order_id}/pay", response_model=Order)
def pay_order(order_id: str, req: PayRequest):
    order = store.orders.get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    if order.status != OrderStatus.CREATED:
        raise HTTPException(
            status_code=409,
            detail=f"cannot pay order in status {order.status.value}",
        )
    order.status = OrderStatus.PAID
    order.paid_at = _now()
    return order


@app.post("/orders/{order_id}/after-sales", response_model=AfterSale, status_code=201)
def create_after_sale(order_id: str, req: CreateAfterSaleRequest):
    order = store.orders.get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    if order.status != OrderStatus.PAID:
        raise HTTPException(
            status_code=409,
            detail="after-sale can only be created for a paid order",
        )
    after_sale = AfterSale(
        id=str(uuid.uuid4()),
        order_id=order_id,
        reason=req.reason,
        created_at=_now(),
    )
    store.after_sales[after_sale.id] = after_sale
    return after_sale


@app.get("/after-sales", response_model=list[AfterSale])
def list_after_sales():
    return list(store.after_sales.values())


@app.get("/after-sales/{after_sale_id}", response_model=AfterSale)
def get_after_sale(after_sale_id: str):
    after_sale = store.after_sales.get(after_sale_id)
    if after_sale is None:
        raise HTTPException(status_code=404, detail="after-sale not found")
    return after_sale


@app.post("/after-sales/{after_sale_id}/review", response_model=AfterSale)
def review_after_sale(after_sale_id: str, req: ReviewRequest):
    after_sale = store.after_sales.get(after_sale_id)
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
    return after_sale


@app.post("/after-sales/{after_sale_id}/refund", response_model=AfterSale)
def refund_after_sale(after_sale_id: str, req: Optional[RefundRequest] = None):
    after_sale = store.after_sales.get(after_sale_id)
    if after_sale is None:
        raise HTTPException(status_code=404, detail="after-sale not found")
    if after_sale.status != AfterSaleStatus.APPROVED:
        raise HTTPException(
            status_code=409,
            detail=f"cannot refund after-sale in status {after_sale.status.value}",
        )
    order = store.orders.get(after_sale.order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")

    # 计算本次退款金额：未指定则退「剩余可退金额」
    requested = req.refund_amount if (req is not None and req.refund_amount is not None) else None
    remaining = order.amount - order.refunded_amount
    refund_amount = remaining if requested is None else requested

    # 规则3：退款金额必须大于 0（schema 的 gt=0 已约束传入值；此处兜底剩余为 0 的情况）
    if refund_amount <= 0:
        raise HTTPException(status_code=400, detail="refund_amount must be greater than 0")
    # 规则4：累计成功退款金额不得超过订单实际支付金额
    if refund_amount > remaining + 1e-9:
        raise HTTPException(
            status_code=409,
            detail=(
                f"refund amount {refund_amount} exceeds remaining payable {round(remaining, 2)}"
            ),
        )

    now = _now()
    after_sale.status = AfterSaleStatus.REFUNDED
    after_sale.refund_amount = round(refund_amount, 2)
    if after_sale.reviewed_at is None:
        after_sale.reviewed_at = now
    order.refunded_amount = round(order.refunded_amount + refund_amount, 2)  # 规则5：仅成功退款计入
    order.refunded_at = now
    # 退满后才将订单置为 REFUNDED，否则保持 PAID（部分退款）
    order.status = (
        OrderStatus.REFUNDED if order.refunded_amount >= order.amount - 1e-9 else OrderStatus.PAID
    )
    return after_sale
