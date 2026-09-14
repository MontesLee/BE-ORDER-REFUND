"""业务逻辑：订单与售后退款的状态机。"""
from .models import (
    AfterSaleCreate,
    AfterSaleOut,
    AfterSaleStatus,
    OrderCreate,
    OrderOut,
    OrderStatus,
)
from .store import AfterSale, Order, _now, store


class BizError(Exception):
    """业务规则冲突（API 层转换为 409）。"""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def _require_order(order_id: str) -> Order:
    order = store.get_order(order_id)
    if order is None:
        raise KeyError(f"订单不存在: {order_id}")
    return order


def _require_after_sale(after_sale_id: str) -> tuple[AfterSale, Order]:
    after_sale = store.get_after_sale(after_sale_id)
    if after_sale is None:
        raise KeyError(f"售后申请不存在: {after_sale_id}")
    return after_sale, _require_order(after_sale.order_id)


# ---- 订单 ----

def create_order(req: OrderCreate) -> OrderOut:
    total = sum(item.price * item.quantity for item in req.items)
    order = Order(
        user_id=req.user_id,
        total_amount=round(total, 2),
        items=[item.model_dump() for item in req.items],
    )
    store.add_order(order)
    return _to_order_out(order)


def pay_order(order_id: str) -> OrderOut:
    order = _require_order(order_id)
    if order.status != OrderStatus.PENDING_PAYMENT:
        raise BizError(f"订单当前状态 {order.status.value}，不可支付")
    order.status = OrderStatus.PAID
    order.paid_at = _now()
    return _to_order_out(order)


def get_order(order_id: str) -> OrderOut:
    return _to_order_out(_require_order(order_id))


# ---- 售后 ----

def create_after_sale(order_id: str, req: AfterSaleCreate) -> AfterSaleOut:
    order = _require_order(order_id)
    if order.status != OrderStatus.PAID:
        raise BizError(f"订单当前状态 {order.status.value}，仅已支付订单可发起售后退款")
    # 全额退款：存在待审核/已通过/已退款的售后时，不允许重复申请
    for existing in order.after_sales:
        if existing.status in (
            AfterSaleStatus.PENDING_REVIEW,
            AfterSaleStatus.APPROVED,
            AfterSaleStatus.REFUNDED,
        ):
            raise BizError("该订单已存在生效的售后申请，不允许重复发起")
    after_sale = AfterSale(
        order_id=order.id,
        reason=req.reason,
        refund_amount=order.total_amount,
    )
    store.add_after_sale(after_sale)
    order.after_sales.append(after_sale)
    order.status = OrderStatus.REFUNDING
    return _to_after_sale_out(after_sale, order)


def approve_after_sale(after_sale_id: str) -> AfterSaleOut:
    after_sale, order = _require_after_sale(after_sale_id)
    if after_sale.status != AfterSaleStatus.PENDING_REVIEW:
        raise BizError(f"售后申请当前状态 {after_sale.status.value}，不可审核")
    after_sale.status = AfterSaleStatus.APPROVED
    after_sale.approved_at = _now()
    return _to_after_sale_out(after_sale, order)


def reject_after_sale(after_sale_id: str, reason: str) -> AfterSaleOut:
    after_sale, order = _require_after_sale(after_sale_id)
    if after_sale.status != AfterSaleStatus.PENDING_REVIEW:
        raise BizError(f"售后申请当前状态 {after_sale.status.value}，不可审核")
    after_sale.status = AfterSaleStatus.REJECTED
    after_sale.reject_reason = reason
    # 驳回后订单回到已支付状态，用户可再次发起售后
    if order.status == OrderStatus.REFUNDING:
        order.status = OrderStatus.PAID
    return _to_after_sale_out(after_sale, order)


def execute_refund(after_sale_id: str) -> AfterSaleOut:
    after_sale, order = _require_after_sale(after_sale_id)
    if after_sale.status != AfterSaleStatus.APPROVED:
        raise BizError(f"售后申请当前状态 {after_sale.status.value}，仅审核通过的申请可执行退款")
    after_sale.status = AfterSaleStatus.REFUNDED
    after_sale.refunded_at = _now()
    order.status = OrderStatus.REFUNDED
    order.refunded_at = after_sale.refunded_at
    return _to_after_sale_out(after_sale, order)


def get_after_sale(after_sale_id: str) -> AfterSaleOut:
    after_sale, order = _require_after_sale(after_sale_id)
    return _to_after_sale_out(after_sale, order)


# ---- 序列化 ----

def _to_after_sale_brief(a: AfterSale):
    from .models import AfterSaleBrief

    return AfterSaleBrief(
        id=a.id,
        status=a.status,
        reason=a.reason,
        refund_amount=a.refund_amount,
        reject_reason=a.reject_reason,
        created_at=a.created_at,
        approved_at=a.approved_at,
        refunded_at=a.refunded_at,
    )


def _to_order_out(order: Order) -> OrderOut:
    return OrderOut(
        id=order.id,
        user_id=order.user_id,
        status=order.status,
        total_amount=order.total_amount,
        items=order.items,
        paid_at=order.paid_at,
        refunded_at=order.refunded_at,
        created_at=order.created_at,
        after_sales=[_to_after_sale_brief(a) for a in order.after_sales],
    )


def _to_after_sale_out(a: AfterSale, order: Order) -> AfterSaleOut:
    return AfterSaleOut(
        id=a.id,
        status=a.status,
        reason=a.reason,
        refund_amount=a.refund_amount,
        reject_reason=a.reject_reason,
        created_at=a.created_at,
        approved_at=a.approved_at,
        refunded_at=a.refunded_at,
        order_id=order.id,
        order_status=order.status,
    )
