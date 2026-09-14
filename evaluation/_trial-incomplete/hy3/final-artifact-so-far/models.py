"""领域数据模型。

使用 pydantic 定义持久化实体与状态枚举。
本服务只考虑「全额退款」，因此退款金额恒等于订单金额。
"""
from enum import Enum
from typing import Optional

from pydantic import BaseModel
from datetime import datetime


class OrderStatus(str, Enum):
    CREATED = "CREATED"      # 已创建，未支付
    PAID = "PAID"            # 已支付，可发起售后
    REFUNDED = "REFUNDED"    # 已退款


class AfterSaleStatus(str, Enum):
    PENDING = "PENDING"      # 待客服审核
    APPROVED = "APPROVED"    # 审核通过，可退款
    REJECTED = "REJECTED"    # 审核拒绝
    REFUNDED = "REFUNDED"    # 已退款


class Order(BaseModel):
    id: str
    user_id: str
    amount: float
    status: OrderStatus = OrderStatus.CREATED
    created_at: datetime
    paid_at: Optional[datetime] = None
    # 累计成功退款金额（仅 REFUNDED 的售后才计入）
    refunded_amount: float = 0.0
    refunded_at: Optional[datetime] = None


class AfterSale(BaseModel):
    id: str
    order_id: str
    reason: str
    status: AfterSaleStatus = AfterSaleStatus.PENDING
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    refund_amount: Optional[float] = None
    reviewer_note: Optional[str] = None
