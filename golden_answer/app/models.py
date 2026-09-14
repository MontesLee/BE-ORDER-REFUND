"""Domain enums and value objects.

Deliberately free of I/O so that business vocabulary is shared by the
repository, the service layer and the tests.

Money
-----
Every monetary value in this project is an ``int`` expressed in **分 (cents)**.
``float`` is never used for money: binary floating point cannot represent
``0.01`` exactly and silently breaks the cumulative-amount invariant.
"""

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class UserRole(str, Enum):
    USER = "USER"
    AGENT = "AGENT"


class PaymentStatus(str, Enum):
    UNPAID = "UNPAID"
    PAID = "PAID"


class AfterSaleStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REFUNDING = "REFUNDING"
    REFUNDED = "REFUNDED"
    REFUND_FAILED = "REFUND_FAILED"


class RefundStatus(str, Enum):
    REFUNDING = "REFUNDING"
    REFUNDED = "REFUNDED"
    REFUND_FAILED = "REFUND_FAILED"


# --------------------------------------------------------------------------
# Value objects (read-mostly views over database rows)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class User:
    id: int
    name: str
    role: str


@dataclass(frozen=True)
class Order:
    id: int
    user_id: int
    total_amount: int
    paid_amount: int
    refunded_amount: int
    payment_status: str


@dataclass(frozen=True)
class AfterSale:
    id: int
    order_id: int
    user_id: int
    refund_amount: int
    status: str
    idempotency_key: Optional[str]


@dataclass(frozen=True)
class Refund:
    id: int
    after_sale_id: int
    order_id: int
    amount: int
    status: str
    attempt: int
    third_party_ref: Optional[str]
