"""订单售后退款服务 API 入口。"""
from fastapi import FastAPI, HTTPException

from . import service
from .models import AfterSaleCreate, OrderCreate, RejectRequest

app = FastAPI(title="订单售后退款服务", version="0.1.0")


def _handle(fn, *args):
    """统一异常转换：KeyError -> 404，BizError -> 409。"""
    try:
        return fn(*args)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e.args[0] if e.args else e))
    except service.BizError as e:
        raise HTTPException(status_code=409, detail=e.message)


# ---- 订单 ----

@app.post("/orders", status_code=201)
def create_order(req: OrderCreate):
    return service.create_order(req)


@app.post("/orders/{order_id}/pay")
def pay_order(order_id: str):
    return _handle(service.pay_order, order_id)


@app.get("/orders/{order_id}")
def get_order(order_id: str):
    return _handle(service.get_order, order_id)


# ---- 售后 ----

@app.post("/orders/{order_id}/after-sales", status_code=201)
def create_after_sale(order_id: str, req: AfterSaleCreate):
    return _handle(service.create_after_sale, order_id, req)


@app.post("/after-sales/{after_sale_id}/approve")
def approve_after_sale(after_sale_id: str):
    return _handle(service.approve_after_sale, after_sale_id)


@app.post("/after-sales/{after_sale_id}/reject")
def reject_after_sale(after_sale_id: str, req: RejectRequest):
    return _handle(service.reject_after_sale, after_sale_id, req.reason)


@app.post("/after-sales/{after_sale_id}/refund")
def execute_refund(after_sale_id: str):
    return _handle(service.execute_refund, after_sale_id)


@app.get("/after-sales/{after_sale_id}")
def get_after_sale(after_sale_id: str):
    return _handle(service.get_after_sale, after_sale_id)


@app.get("/health")
def health():
    return {"status": "ok"}
