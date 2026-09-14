"""FastAPI application: HTTP surface and error mapping.

Identity is ``X-User-Id``.  Endpoints are synchronous ``def`` functions so the
threadpool handles them; each request opens its own SQLite connection and every
invariant-critical read-modify-write goes through ``BEGIN IMMEDIATE``.

Run locally::

    uvicorn app.main:app --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Header, Query, Response
from fastapi.responses import JSONResponse

from . import auth, refund_gateway, repository, service
from .schemas import (
    AfterSaleOut,
    AfterSalePage,
    CreateAfterSaleIn,
    CreateOrderIn,
    CreateUserIn,
    ErrorOut,
    OrderOut,
    OrderPage,
    RefundExecutionOut,
    RefundPage,
    RefundSummaryOut,
    UserOut,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    repository.init_schema()
    injected = getattr(app.state, "gateway", None)
    if injected is not None:
        refund_gateway.set_gateway(injected)
    else:
        refund_gateway.set_gateway(refund_gateway.gateway_from_env())
    yield


app = FastAPI(
    title="Order After-Sale Refund Service",
    version="1.0.0",
    description=(
        "多轮后端评测题参考实现：订单售后退款。金额单位为分 (integer cents)。"
        "调用方身份通过 X-User-Id 头传递。"
    ),
    lifespan=lifespan,
)


def current_user(
    x_user_id: Optional[int] = Header(default=None, alias=auth.HEADER_NAME),
) -> dict:
    return auth.resolve_user(x_user_id)


# --------------------------------------------------------------------------
# Error mapping
# --------------------------------------------------------------------------


def _error(status_code: int, message: str, code: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorOut(error=message, code=code).model_dump(),
    )


@app.exception_handler(service.ServiceError)
async def _service_error_handler(request, exc: service.ServiceError):
    return _error(exc.status_code, exc.message, exc.code)


@app.exception_handler(auth.Unauthorized)
async def _unauthorized_handler(request, exc: auth.Unauthorized):
    return _error(401, str(exc) or "unauthorized", "unauthorized")


@app.exception_handler(auth.Forbidden)
async def _forbidden_handler(request, exc: auth.Forbidden):
    return _error(403, str(exc) or "forbidden", "forbidden")


@app.exception_handler(auth.NotFound)
async def _not_found_handler(request, exc: auth.NotFound):
    return _error(404, str(exc) or "not found", "not_found")


# --------------------------------------------------------------------------
# Health / identity
# --------------------------------------------------------------------------


@app.get("/health", tags=["ops"])
def health():
    return {"status": "ok", "version": app.version}


@app.post("/users", response_model=UserOut, status_code=201, tags=["users"])
def create_user(payload: CreateUserIn):
    return service.create_user(payload.name, payload.role)


@app.get("/users/me", response_model=UserOut, tags=["users"])
def read_me(user: dict = Depends(current_user)):
    return user


# --------------------------------------------------------------------------
# Orders
# --------------------------------------------------------------------------


@app.post("/orders", response_model=OrderOut, status_code=201, tags=["orders"])
def create_order(payload: CreateOrderIn, user: dict = Depends(current_user)):
    return service.create_order(user, payload.amount)


@app.get("/orders", response_model=OrderPage, tags=["orders"])
def list_orders(
    limit: Optional[int] = Query(default=None, ge=1),
    offset: Optional[int] = Query(default=None, ge=0),
    user: dict = Depends(current_user),
):
    return service.list_orders(user, limit, offset)


@app.get("/orders/{order_id}", response_model=OrderOut, tags=["orders"])
def read_order(order_id: int, user: dict = Depends(current_user)):
    return service.get_order(user, order_id)


@app.post("/orders/{order_id}/pay", response_model=OrderOut, tags=["orders"])
def pay_order(order_id: int, user: dict = Depends(current_user)):
    return service.pay_order(user, order_id)


@app.get(
    "/orders/{order_id}/refund-summary",
    response_model=RefundSummaryOut,
    tags=["orders", "ops"],
)
def order_refund_summary(order_id: int, user: dict = Depends(current_user)):
    return service.order_refund_summary(user, order_id)


# --------------------------------------------------------------------------
# After-sales
# --------------------------------------------------------------------------


@app.post(
    "/orders/{order_id}/after-sales", response_model=AfterSaleOut, tags=["after-sales"]
)
def create_after_sale(
    order_id: int,
    payload: CreateAfterSaleIn,
    response: Response,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    user: dict = Depends(current_user),
):
    key = payload.idempotency_key or idempotency_key
    after_sale, replayed = service.create_after_sale(
        user, order_id, payload.refund_amount, key
    )
    response.status_code = 200 if replayed else 201
    return after_sale


@app.get(
    "/orders/{order_id}/after-sales", response_model=AfterSalePage, tags=["after-sales"]
)
def list_after_sales(
    order_id: int,
    limit: Optional[int] = Query(default=None, ge=1),
    offset: Optional[int] = Query(default=None, ge=0),
    user: dict = Depends(current_user),
):
    return service.list_after_sales(user, order_id, limit, offset)


@app.get("/after-sales/{after_sale_id}", response_model=AfterSaleOut, tags=["after-sales"])
def read_after_sale(after_sale_id: int, user: dict = Depends(current_user)):
    return service.get_after_sale(user, after_sale_id)


@app.post(
    "/after-sales/{after_sale_id}/approve", response_model=AfterSaleOut, tags=["after-sales"]
)
def approve_after_sale(after_sale_id: int, user: dict = Depends(current_user)):
    return service.approve_after_sale(user, after_sale_id)


@app.post(
    "/after-sales/{after_sale_id}/execute",
    response_model=RefundExecutionOut,
    tags=["after-sales"],
)
def execute_refund(after_sale_id: int, user: dict = Depends(current_user)):
    return service.execute_refund(user, after_sale_id)


@app.get(
    "/after-sales/{after_sale_id}/refunds", response_model=RefundPage, tags=["after-sales"]
)
def list_refunds(
    after_sale_id: int,
    limit: Optional[int] = Query(default=None, ge=1),
    offset: Optional[int] = Query(default=None, ge=0),
    user: dict = Depends(current_user),
):
    return service.list_refunds(user, after_sale_id, limit, offset)


# --------------------------------------------------------------------------
# Maintenance
# --------------------------------------------------------------------------


@app.post("/maintenance/reconcile", tags=["ops"])
def reconcile(
    timeout_seconds: int = Query(default=300, ge=0),
    user: dict = Depends(current_user),
):
    return service.reconcile_stale(user, timeout_seconds)
