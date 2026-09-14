"""内存存储（线程安全）。进程重启数据即清空，便于本地演示。"""
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .models import AfterSaleStatus, OrderStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@dataclass
class AfterSale:
    order_id: str
    reason: str
    refund_amount: float
    id: str = field(default_factory=lambda: _gen_id("as"))
    status: AfterSaleStatus = AfterSaleStatus.PENDING_REVIEW
    reject_reason: str | None = None
    created_at: datetime = field(default_factory=_now)
    approved_at: datetime | None = None
    refunded_at: datetime | None = None


@dataclass
class Order:
    user_id: str
    total_amount: float
    status: OrderStatus = OrderStatus.PENDING_PAYMENT
    id: str = field(default_factory=lambda: _gen_id("ord"))
    paid_at: datetime | None = None
    refunded_at: datetime | None = None
    created_at: datetime = field(default_factory=_now)
    items: list[dict] = field(default_factory=list)
    after_sales: list[AfterSale] = field(default_factory=list)


class Store:
    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}
        self._after_sales: dict[str, AfterSale] = {}
        self._lock = threading.Lock()

    # ---- orders ----
    def add_order(self, order: Order) -> Order:
        with self._lock:
            self._orders[order.id] = order
            return order

    def get_order(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

    # ---- after sales ----
    def add_after_sale(self, after_sale: AfterSale) -> AfterSale:
        with self._lock:
            self._after_sales[after_sale.id] = after_sale
            return after_sale

    def get_after_sale(self, after_sale_id: str) -> AfterSale | None:
        return self._after_sales.get(after_sale_id)


store = Store()
