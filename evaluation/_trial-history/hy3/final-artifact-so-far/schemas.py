"""请求体 Schema（入参校验）。"""
from typing import Optional

from pydantic import BaseModel, Field


class CreateOrderRequest(BaseModel):
    user_id: str = Field(..., min_length=1, description="下单用户标识")
    amount: float = Field(..., gt=0, description="订单金额，必须大于 0")


class PayRequest(BaseModel):
    payment_method: str = Field("balance", description="支付方式，仅作留痕")


class CreateAfterSaleRequest(BaseModel):
    reason: str = Field(..., min_length=1, description="退款原因")


class ReviewRequest(BaseModel):
    approve: bool = Field(..., description="是否审核通过")
    reviewer_note: Optional[str] = Field(None, description="审核备注")


class RefundRequest(BaseModel):
    # 不传则退「剩余可退金额」（订单金额 - 已成功退款金额）。
    # 传值必须 > 0（gt 约束），且最终累计不得超过订单金额（在接口内校验）。
    refund_amount: Optional[float] = Field(
        None, gt=0, description="本次退款金额；不传则退剩余全部"
    )
