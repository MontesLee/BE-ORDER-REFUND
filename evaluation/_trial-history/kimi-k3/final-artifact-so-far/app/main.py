"""订单售后退款服务 API 入口。"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .models import (
    CreateOrderRequest,
    CreateRefundRequest,
    Order,
    OrderDetailResponse,
    Refund,
    ReviewRefundRequest,
)
from .service import BizError, NotFoundError, OrderService

app = FastAPI(title="订单售后退款服务", version="0.1.0")
service = OrderService()


@app.exception_handler(NotFoundError)
async def not_found_handler(_: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(BizError)
async def biz_error_handler(_: Request, exc: BizError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


# ---------- 订单 ----------

@app.post("/orders", response_model=Order, status_code=201)
def create_order(req: CreateOrderRequest) -> Order:
    return service.create_order(req.item_name, req.amount)


@app.post("/orders/{order_id}/pay", response_model=Order)
def pay_order(order_id: str) -> Order:
    return service.pay_order(order_id)


@app.get("/orders/{order_id}", response_model=OrderDetailResponse)
def get_order(order_id: str) -> OrderDetailResponse:
    order, refunds = service.get_order_detail(order_id)
    return OrderDetailResponse(order=order, refunds=refunds)


# ---------- 售后退款 ----------

@app.post("/orders/{order_id}/refunds", response_model=Refund, status_code=201)
def create_refund(order_id: str, req: CreateRefundRequest) -> Refund:
    return service.create_refund(order_id, req.refund_amount, req.reason)


@app.post("/refunds/{refund_id}/review", response_model=Refund)
def review_refund(refund_id: str, req: ReviewRefundRequest) -> Refund:
    return service.review_refund(refund_id, req.approve, req.comment)


@app.post("/refunds/{refund_id}/execute", response_model=Refund)
def execute_refund(refund_id: str) -> Refund:
    return service.execute_refund(refund_id)


@app.get("/refunds/{refund_id}", response_model=Refund)
def get_refund(refund_id: str) -> Refund:
    return service.get_refund(refund_id)
