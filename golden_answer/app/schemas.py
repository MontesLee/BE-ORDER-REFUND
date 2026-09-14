"""Request and response models.

Money fields are declared as ``int`` on purpose.  A ``float`` body such as
``10.5`` is rejected with ``422`` instead of being silently truncated, because
a truncated amount is exactly how the cumulative-refund invariant gets broken.
"""

from __future__ import annotations

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field

CENTS_DESCRIPTION = "金额，单位：分 (integer cents)"


class CreateUserIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    role: Literal["USER", "AGENT"] = "USER"


class CreateOrderIn(BaseModel):
    amount: int = Field(gt=0, description=f"订单金额，单位：分 (cents)")


class CreateAfterSaleIn(BaseModel):
    refund_amount: int = Field(gt=0, description=CENTS_DESCRIPTION)
    idempotency_key: Optional[str] = Field(default=None, max_length=200)


class UserOut(BaseModel):
    id: int
    name: str
    role: str


class OrderOut(BaseModel):
    id: int
    user_id: int
    total_amount: int
    paid_amount: int
    refunded_amount: int
    payment_status: str


class AfterSaleOut(BaseModel):
    id: int
    order_id: int
    user_id: int
    refund_amount: int
    status: str
    idempotency_key: Optional[str] = None


class RefundOut(BaseModel):
    id: int
    after_sale_id: int
    order_id: int
    amount: int
    status: str
    attempt: int
    third_party_ref: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class OrderPage(BaseModel):
    items: List[OrderOut]
    total: int
    limit: int
    offset: int


class AfterSalePage(BaseModel):
    items: List[AfterSaleOut]
    total: int
    limit: int
    offset: int


class RefundPage(BaseModel):
    items: List[RefundOut]
    total: int
    limit: int
    offset: int


class RefundExecutionOut(BaseModel):
    after_sale: AfterSaleOut
    refund: Optional[RefundOut] = None
    replayed: bool = False


class RefundSummaryOut(BaseModel):
    order_id: int
    payment_status: str
    paid_amount: int
    refunded_amount: int
    successful_refund_total: int
    consistent: bool


class ErrorOut(BaseModel):
    error: str
    code: str
