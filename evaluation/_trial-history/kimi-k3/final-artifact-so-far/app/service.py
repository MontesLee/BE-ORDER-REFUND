"""业务逻辑层：订单与售后退款的状态机。

存储为进程内内存字典，重启即丢，仅用于最小可运行演示。
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from decimal import Decimal

from .models import Order, OrderStatus, Refund, RefundStatus


class BizError(Exception):
    """业务规则冲突（如非法状态迁移）。对应 HTTP 409。"""


class NotFoundError(Exception):
    """资源不存在。对应 HTTP 404。"""


class OrderService:
    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}
        self._refunds: dict[str, Refund] = {}
        self._lock = threading.Lock()

    # ---------- 订单 ----------

    def create_order(self, item_name: str, amount) -> Order:
        order = Order(item_name=item_name, amount=amount)
        with self._lock:
            self._orders[order.id] = order
        return order

    def pay_order(self, order_id: str) -> Order:
        with self._lock:
            order = self._get_order(order_id)
            if order.status == OrderStatus.PAID:
                raise BizError("订单已支付，请勿重复支付")
            if order.status != OrderStatus.CREATED:
                raise BizError(f"当前状态 {order.status} 不允许支付")
            order.status = OrderStatus.PAID
            order.paid_at = datetime.now(timezone.utc)
            return order

    def get_order(self, order_id: str) -> Order:
        return self._get_order(order_id)

    def get_order_detail(self, order_id: str) -> tuple[Order, list[Refund]]:
        order = self._get_order(order_id)
        refunds = [r for r in self._refunds.values() if r.order_id == order_id]
        return order, refunds

    # ---------- 售后退款 ----------

    def create_refund(self, order_id: str, refund_amount, reason: str) -> Refund:
        with self._lock:
            order = self._get_order(order_id)
            if order.status != OrderStatus.PAID:
                raise BizError("只有已支付且未全额退款的订单才能申请售后")
            if refund_amount <= 0:
                raise BizError("退款金额必须大于 0")
            remaining = order.amount - self._refunded_amount(order_id)
            if refund_amount > remaining:
                raise BizError(
                    f"退款金额超出可退余额，订单已支付 {order.amount}，已成功退款 "
                    f"{order.amount - remaining}，剩余可退 {remaining}"
                )
            refund = Refund(order_id=order_id, refund_amount=refund_amount, reason=reason)
            self._refunds[refund.id] = refund
            return refund

    def review_refund(self, refund_id: str, approve: bool, comment: str | None) -> Refund:
        with self._lock:
            refund = self._get_refund(refund_id)
            if refund.status != RefundStatus.PENDING:
                raise BizError(f"售后单当前状态 {refund.status} 不允许审核")
            refund.status = RefundStatus.APPROVED if approve else RefundStatus.REJECTED
            refund.review_comment = comment
            refund.reviewed_at = datetime.now(timezone.utc)
            return refund

    def execute_refund(self, refund_id: str) -> Refund:
        with self._lock:
            refund = self._get_refund(refund_id)
            if refund.status != RefundStatus.APPROVED:
                raise BizError("只有审核通过的售后单才能执行退款")
            order = self._get_order(refund.order_id)
            now = datetime.now(timezone.utc)
            refund.status = RefundStatus.REFUNDED
            refund.refunded_at = now
            # 只有成功退款才计入累计；累计达到支付金额时订单整体置为已退款
            if self._refunded_amount(order.id) >= order.amount:
                order.status = OrderStatus.REFUNDED
                order.refunded_at = now
            return refund

    def get_refund(self, refund_id: str) -> Refund:
        return self._get_refund(refund_id)

    # ---------- 内部 ----------

    def _get_order(self, order_id: str) -> Order:
        order = self._orders.get(order_id)
        if order is None:
            raise NotFoundError(f"订单不存在: {order_id}")
        return order

    def _get_refund(self, refund_id: str) -> Refund:
        refund = self._refunds.get(refund_id)
        if refund is None:
            raise NotFoundError(f"售后单不存在: {refund_id}")
        return refund

    def _refunded_amount(self, order_id: str) -> Decimal:
        """累计该订单已成功退款（REFUNDED）的金额，未成功的退款不计入。"""
        from decimal import Decimal

        total = Decimal(0)
        for r in self._refunds.values():
            if r.order_id == order_id and r.status == RefundStatus.REFUNDED:
                total += r.refund_amount
        return total
