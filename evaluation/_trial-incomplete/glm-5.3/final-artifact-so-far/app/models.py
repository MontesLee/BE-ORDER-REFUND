"""数据模型：订单与售后退款申请。"""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class OrderStatus(str, Enum):
    PENDING_PAYMENT = "PENDING_PAYMENT"  # 待支付
    PAID = "PAID"                        # 已支付
    REFUNDING = "REFUNDING"              # 售后审核/退款进行中
    REFUNDED = "REFUNDED"                # 已全额退款


class AfterSaleStatus(str, Enum):
    PENDING_REVIEW = "PENDING_REVIEW"    # 待客服审核
    APPROVED = "APPROVED"                # 审核通过，待执行退款
    REJECTED = "REJECTED"                # 审核驳回
    REFUNDED = "REFUNDED"                # 退款完成


class OrderItem(BaseModel):
    sku_id: str
    name: str
    price: float = Field(gt=0)
    quantity: int = Field(gt=0)


class OrderCreate(BaseModel):
    user_id: str
    items: list[OrderItem] = Field(min_length=1)


class AfterSaleCreate(BaseModel):
    reason: str = Field(min_length=1)


class RejectRequest(BaseModel):
    reason: str = Field(min_length=1)


class OrderItemOut(OrderItem):
    pass


class AfterSaleBrief(BaseModel):
    id: str
    status: AfterSaleStatus
    reason: str
    refund_amount: float
    reject_reason: str | None = None
    created_at: datetime
    approved_at: datetime | None = None
    refunded_at: datetime | None = None


class OrderOut(BaseModel):
    id: str
    user_id: str
    status: OrderStatus
    total_amount: float
    items: list[OrderItemOut]
    paid_at: datetime | None = None
    refunded_at: datetime | None = None
    created_at: datetime
    after_sales: list[AfterSaleBrief] = []


class AfterSaleOut(AfterSaleBrief):
    order_id: str
    order_status: OrderStatus
