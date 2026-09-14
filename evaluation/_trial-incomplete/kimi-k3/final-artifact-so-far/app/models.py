"""数据模型与状态定义。"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class OrderStatus(str, enum.Enum):
    CREATED = "CREATED"      # 已创建，未支付
    PAID = "PAID"            # 已支付，可申请售后
    REFUNDED = "REFUNDED"    # 已全额退款
    CLOSED = "CLOSED"        # 已关闭（未支付时取消）


class RefundStatus(str, enum.Enum):
    PENDING = "PENDING"      # 待审核
    APPROVED = "APPROVED"    # 审核通过，待执行退款
    REJECTED = "REJECTED"    # 审核拒绝
    REFUNDED = "REFUNDED"    # 退款完成


class Order(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("ord"))
    item_name: str
    amount: Decimal
    status: OrderStatus = OrderStatus.CREATED
    created_at: datetime = Field(default_factory=_now)
    paid_at: datetime | None = None
    refunded_at: datetime | None = None


class Refund(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("rfd"))
    order_id: str
    refund_amount: Decimal  # 本次退款金额，可部分退款，必须 > 0
    reason: str
    status: RefundStatus = RefundStatus.PENDING
    created_at: datetime = Field(default_factory=_now)
    reviewed_at: datetime | None = None
    refunded_at: datetime | None = None
    review_comment: str | None = None


# ---------- 请求 / 响应 schema ----------

class CreateOrderRequest(BaseModel):
    item_name: str = Field(min_length=1, max_length=100)
    amount: Decimal = Field(gt=0, decimal_places=2)


class CreateRefundRequest(BaseModel):
    refund_amount: Decimal = Field(gt=0, decimal_places=2)
    reason: str = Field(min_length=1, max_length=500)


class ReviewRefundRequest(BaseModel):
    approve: bool
    comment: str | None = Field(default=None, max_length=500)


class OrderDetailResponse(BaseModel):
    order: Order
    refunds: list[Refund] = []
