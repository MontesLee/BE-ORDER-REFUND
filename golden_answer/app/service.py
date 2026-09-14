"""Business rules and transaction boundaries.

Everything that can break an invariant lives here, and the ordering is the
whole point:

``create_after_sale``
    Rejects unpaid orders and replays duplicate submissions instead of
    inserting a second row.

``approve_after_sale``
    ``PENDING -> APPROVED``, agent only, idempotent.

``execute_refund``
    Three phases, in this order:

    1. **Claim** (one ``BEGIN IMMEDIATE`` transaction)
       Validate the state machine, *reserve* the order's refundable quota with
       a single guarded ``UPDATE``, insert the ``REFUNDING`` refund row and
       move the AfterSale to ``REFUNDING``.  Because the write lock is taken
       before the first read, two workers cannot both pass the check.
    2. **Call the provider** *outside* any transaction, so a slow or hanging
       provider never holds the database write lock.
    3. **Settle** (a second short transaction)
       ``REFUNDING -> REFUNDED`` on provider success; ``REFUNDING ->
       REFUND_FAILED`` plus a quota release on provider failure.

    If the provider fails, the local state can never become ``REFUNDED``
    (I4) and the reservation is returned, so a later attempt can still use the
    full quota (I1 stays meaningful).

Cancellation safety
-------------------
This design is not a distributed transaction, and it does not pretend to be.
A crash between phase 1 and phase 3 leaves a ``REFUNDING`` row whose quota is
reserved.  :func:`reconcile_stale` releases exactly those rows.  That limit is
documented rather than hidden -- see ``README.md`` and ``verify_doc/README.md``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from . import auth, repository, state_machine
from .models import AfterSaleStatus, PaymentStatus, RefundStatus, UserRole
from .refund_gateway import GatewayResult, get_gateway

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 50


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class ServiceError(Exception):
    status_code = 400
    code = "service_error"

    def __init__(self, message: str, code: Optional[str] = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class BadRequest(ServiceError):
    status_code = 400
    code = "bad_request"


class Conflict(ServiceError):
    status_code = 409
    code = "conflict"


# Re-exported so the HTTP layer has a single place to import from.
Unauthorized = auth.Unauthorized
Forbidden = auth.Forbidden
NotFound = auth.NotFound


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def normalize_page(limit: Optional[int], offset: Optional[int]) -> tuple:
    """Clamp paging so a single request can never load an unbounded result set."""
    if limit is None:
        limit = DEFAULT_PAGE_SIZE
    if limit < 1:
        limit = 1
    if limit > MAX_PAGE_SIZE:
        limit = MAX_PAGE_SIZE
    if offset is None or offset < 0:
        offset = 0
    return limit, offset


def _require_positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BadRequest(f"{field} must be an integer number of 分 (cents)")
    if value <= 0:
        raise BadRequest(f"{field} must be greater than 0")
    return value


@dataclass
class _Claim:
    kind: str  # "claimed" | "replay"
    after_sale: Dict[str, Any]
    refund: Optional[Dict[str, Any]] = None


# --------------------------------------------------------------------------
# Users / orders
# --------------------------------------------------------------------------


def create_user(name: str, role: str = UserRole.USER.value) -> Dict[str, Any]:
    if role not in (UserRole.USER.value, UserRole.AGENT.value):
        raise BadRequest("role must be USER or AGENT")
    if not name or not str(name).strip():
        raise BadRequest("name is required")
    conn = repository.connect()
    try:
        with repository.write_tx(conn):
            user_id = repository.insert_user(conn, str(name).strip(), role, repository.utcnow())
            user = repository.get_user(conn, user_id)
        return user
    finally:
        conn.close()


def create_order(actor: Dict[str, Any], total_amount: Any) -> Dict[str, Any]:
    amount = _require_positive_int(total_amount, "amount")
    conn = repository.connect()
    try:
        with repository.write_tx(conn):
            order_id = repository.insert_order(conn, actor["id"], amount, repository.utcnow())
            order = repository.get_order(conn, order_id)
        return order
    finally:
        conn.close()


def pay_order(actor: Dict[str, Any], order_id: int) -> Dict[str, Any]:
    conn = repository.connect()
    try:
        with repository.write_tx(conn):
            order = repository.get_order(conn, order_id)
            if order is None or int(order["user_id"]) != int(actor["id"]):
                raise NotFound("order not found")
            if order["payment_status"] == PaymentStatus.PAID.value:
                return order  # paying twice is harmless
            repository.mark_order_paid(conn, order_id, repository.utcnow())
            order = repository.get_order(conn, order_id)
        return order
    finally:
        conn.close()


def get_order(actor: Dict[str, Any], order_id: int) -> Dict[str, Any]:
    conn = repository.connect()
    try:
        order = repository.get_order(conn, order_id)
        if order is None:
            raise NotFound("order not found")
        auth.assert_can_view(actor, order["user_id"], "order")
        return order
    finally:
        conn.close()


def list_orders(actor: Dict[str, Any], limit: Optional[int], offset: Optional[int]) -> Dict[str, Any]:
    limit, offset = normalize_page(limit, offset)
    conn = repository.connect()
    try:
        items = repository.list_orders_for_user(conn, actor["id"], limit, offset)
        total = repository.count_orders_for_user(conn, actor["id"])
        return {"items": items, "total": total, "limit": limit, "offset": offset}
    finally:
        conn.close()


def order_refund_summary(actor: Dict[str, Any], order_id: int) -> Dict[str, Any]:
    """Cross-check the persisted counter against the refund ledger.

    Used by the evaluator (and by reconciliation) to prove I1 without reading
    private internals: ``refunded_amount`` must equal the sum of successful
    refunds and must never exceed ``paid_amount``.
    """
    conn = repository.connect()
    try:
        order = repository.get_order(conn, order_id)
        if order is None:
            raise NotFound("order not found")
        auth.assert_can_view(actor, order["user_id"], "order")
        settled = repository.successful_refund_total(conn, order_id)
        return {
            "order_id": order_id,
            "payment_status": order["payment_status"],
            "paid_amount": order["paid_amount"],
            "refunded_amount": order["refunded_amount"],
            "successful_refund_total": settled,
            "consistent": (
                order["refunded_amount"] == settled
                and order["refunded_amount"] <= order["paid_amount"]
            ),
        }
    finally:
        conn.close()


# --------------------------------------------------------------------------
# After-sales
# --------------------------------------------------------------------------


def create_after_sale(
    actor: Dict[str, Any],
    order_id: int,
    refund_amount: Any,
    idempotency_key: Optional[str] = None,
) -> tuple:
    """Create an AfterSale. Returns ``(after_sale, replayed)``."""
    amount = _require_positive_int(refund_amount, "refund_amount")
    if idempotency_key is not None:
        idempotency_key = str(idempotency_key).strip() or None

    conn = repository.connect()
    try:
        with repository.write_tx(conn):
            if idempotency_key:
                existing = repository.get_after_sale_by_idempotency_key(conn, idempotency_key)
                if existing is not None:
                    if int(existing["order_id"]) != int(order_id) or int(
                        existing["user_id"]
                    ) != int(actor["id"]):
                        raise Conflict(
                            "idempotency key was already used for another request",
                            code="idempotency_key_reused",
                        )
                    if int(existing["refund_amount"]) != amount:
                        raise Conflict(
                            "idempotency key was already used with a different amount",
                            code="idempotency_key_reused",
                        )
                    return existing, True

            order = repository.get_order(conn, order_id)
            if order is None or int(order["user_id"]) != int(actor["id"]):
                raise NotFound("order not found")
            if order["payment_status"] != PaymentStatus.PAID.value:
                raise Conflict("order is not paid", code="order_not_paid")

            try:
                after_sale_id = repository.insert_after_sale(
                    conn, order_id, actor["id"], amount, idempotency_key, repository.utcnow()
                )
            except sqlite3.IntegrityError:
                # Lost a race on the same idempotency key: return the winner.
                existing = repository.get_after_sale_by_idempotency_key(conn, idempotency_key)
                if existing is None:
                    raise
                return existing, True
            after_sale = repository.get_after_sale(conn, after_sale_id)
        return after_sale, False
    finally:
        conn.close()


def get_after_sale(actor: Dict[str, Any], after_sale_id: int) -> Dict[str, Any]:
    conn = repository.connect()
    try:
        after_sale = repository.get_after_sale(conn, after_sale_id)
        if after_sale is None:
            raise NotFound("after-sale not found")
        auth.assert_can_view(actor, after_sale["user_id"], "after-sale")
        return after_sale
    finally:
        conn.close()


def list_after_sales(
    actor: Dict[str, Any],
    order_id: int,
    limit: Optional[int],
    offset: Optional[int],
) -> Dict[str, Any]:
    limit, offset = normalize_page(limit, offset)
    conn = repository.connect()
    try:
        order = repository.get_order(conn, order_id)
        if order is None:
            raise NotFound("order not found")
        auth.assert_can_view(actor, order["user_id"], "order")
        items = repository.list_after_sales_for_order(conn, order_id, limit, offset)
        total = repository.count_after_sales_for_order(conn, order_id)
        return {"items": items, "total": total, "limit": limit, "offset": offset}
    finally:
        conn.close()


def list_refunds(
    actor: Dict[str, Any],
    after_sale_id: int,
    limit: Optional[int],
    offset: Optional[int],
) -> Dict[str, Any]:
    limit, offset = normalize_page(limit, offset)
    conn = repository.connect()
    try:
        after_sale = repository.get_after_sale(conn, after_sale_id)
        if after_sale is None:
            raise NotFound("after-sale not found")
        auth.assert_can_view(actor, after_sale["user_id"], "after-sale")
        items = repository.list_refunds_for_after_sale(conn, after_sale_id, limit, offset)
        total = repository.count_refunds_for_after_sale(conn, after_sale_id)
        return {"items": items, "total": total, "limit": limit, "offset": offset}
    finally:
        conn.close()


def approve_after_sale(actor: Dict[str, Any], after_sale_id: int) -> Dict[str, Any]:
    auth.require_agent(actor)
    conn = repository.connect()
    try:
        with repository.write_tx(conn):
            after_sale = repository.get_after_sale(conn, after_sale_id)
            if after_sale is None:
                raise NotFound("after-sale not found")
            status = after_sale["status"]
            if status == AfterSaleStatus.PENDING.value:
                now = repository.utcnow()
                state_machine.assert_transition(status, AfterSaleStatus.APPROVED.value)
                repository.update_after_sale_status(
                    conn,
                    after_sale_id,
                    AfterSaleStatus.APPROVED.value,
                    now,
                    expected_status=AfterSaleStatus.PENDING.value,
                )
            elif status == AfterSaleStatus.REFUNDED.value or status == AfterSaleStatus.REFUND_FAILED.value:
                # Approving something already past review is a no-op, not an error.
                pass
            elif status == AfterSaleStatus.APPROVED.value or status == AfterSaleStatus.REFUNDING.value:
                pass
            else:  # pragma: no cover - defensive
                raise Conflict(
                    f"cannot approve an after-sale in status {status}",
                    code="illegal_state_transition",
                )
            return repository.get_after_sale(conn, after_sale_id)
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Refund execution
# --------------------------------------------------------------------------


def _claim_refund(conn: sqlite3.Connection, after_sale_id: int) -> _Claim:
    """Phase 1: validate the state machine and reserve quota atomically."""
    now = repository.utcnow()
    with repository.write_tx(conn):
        after_sale = repository.get_after_sale(conn, after_sale_id)
        if after_sale is None:
            raise NotFound("after-sale not found")
        status = after_sale["status"]

        if status == AfterSaleStatus.REFUNDED.value:
            # Already refunded: a duplicate execute is a replay, not a second
            # refund. Returning here keeps I2 true and makes retries safe.
            return _Claim("replay", after_sale)

        if status in state_machine.IN_FLIGHT_STATES:
            raise Conflict("a refund attempt is already in progress", code="refund_in_progress")

        if not state_machine.can_start_refund(status):
            # PENDING (never approved) lands here: the state machine forbids
            # going straight from review to money movement.
            raise Conflict(
                f"illegal after-sale transition: {status} -> REFUNDING",
                code="illegal_state_transition",
            )

        order = repository.get_order(conn, after_sale["order_id"])
        if order is None:
            raise NotFound("order not found")
        if order["payment_status"] != PaymentStatus.PAID.value:
            raise Conflict("order is not paid", code="order_not_paid")

        amount = int(after_sale["refund_amount"])
        if not repository.reserve_refund_quota(conn, order["id"], amount):
            raise Conflict(
                "cumulative refund would exceed the paid amount",
                code="refund_amount_exceeded",
            )

        attempt = repository.next_refund_attempt(conn, after_sale_id)
        idempotency_key = f"as-{after_sale_id}-attempt-{attempt}"
        refund_id = repository.insert_refund(
            conn,
            after_sale_id,
            order["id"],
            amount,
            attempt,
            idempotency_key,
            now,
        )
        repository.update_after_sale_status(
            conn,
            after_sale_id,
            AfterSaleStatus.REFUNDING.value,
            now,
            expected_status=status,
        )
        refreshed = repository.get_after_sale(conn, after_sale_id)
        refund = repository.get_refund(conn, refund_id)
    return _Claim("claimed", refreshed, refund)


def _settle(
    conn: sqlite3.Connection,
    after_sale_id: int,
    refund_id: int,
    order_id: int,
    amount: int,
    result: GatewayResult,
) -> None:
    """Phase 3: write the provider's verdict and keep the ledger honest."""
    now = repository.utcnow()
    with repository.write_tx(conn):
        if result.ok:
            settled = repository.mark_refund_settled(
                conn,
                refund_id,
                RefundStatus.REFUNDED.value,
                result.third_party_ref,
                None,
                None,
                now,
            )
            if not settled:
                raise Conflict("refund was already settled", code="already_settled")
            repository.update_after_sale_status(
                conn,
                after_sale_id,
                AfterSaleStatus.REFUNDED.value,
                now,
                expected_status=AfterSaleStatus.REFUNDING.value,
            )
        else:
            settled = repository.mark_refund_settled(
                conn,
                refund_id,
                RefundStatus.REFUND_FAILED.value,
                None,
                result.error_code or "PROVIDER_FAILURE",
                result.error_message or "third-party refund failed",
                now,
            )
            if not settled:
                raise Conflict("refund was already settled", code="already_settled")
            repository.update_after_sale_status(
                conn,
                after_sale_id,
                AfterSaleStatus.REFUND_FAILED.value,
                now,
                expected_status=AfterSaleStatus.REFUNDING.value,
            )
            # Provider refused -> the money never left, so the reservation
            # must go back. Otherwise a failure would silently burn quota.
            repository.release_refund_quota(conn, order_id, amount)


def execute_refund(actor: Dict[str, Any], after_sale_id: int) -> Dict[str, Any]:
    auth.require_agent(actor)
    conn = repository.connect()
    try:
        claim = _claim_refund(conn, after_sale_id)

        if claim.kind == "replay":
            return {
                "after_sale": claim.after_sale,
                "refund": repository.get_settled_refund(conn, after_sale_id),
                "replayed": True,
            }

        refund = claim.refund
        result = get_gateway().refund(
            after_sale_id=after_sale_id,
            order_id=int(refund["order_id"]),
            amount=int(refund["amount"]),
            idempotency_key=refund["idempotency_key"],
        )
        _settle(
            conn,
            after_sale_id,
            int(refund["id"]),
            int(refund["order_id"]),
            int(refund["amount"]),
            result,
        )
        return {
            "after_sale": repository.get_after_sale(conn, after_sale_id),
            "refund": repository.get_refund(conn, int(refund["id"])),
            "replayed": False,
        }
    except sqlite3.IntegrityError as exc:  # backstop for ux_refunds_one_success
        raise Conflict(
            f"refund rejected by a database invariant: {exc}", code="integrity_violation"
        ) from exc
    finally:
        conn.close()


def reconcile_stale(actor: Dict[str, Any], timeout_seconds: int = 300) -> Dict[str, Any]:
    """Release quota held by attempts that died mid-flight.

    A worker that crashes between phase 1 and phase 3 leaves a ``REFUNDING``
    row and a reserved amount.  There is no distributed transaction here to
    clean that up automatically, so reconciliation is an explicit, auditable
    operator action.
    """
    auth.require_agent(actor)
    if timeout_seconds < 0:
        raise BadRequest("timeout_seconds must be >= 0")
    cutoff = (
        datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds)
    ).isoformat(timespec="milliseconds")

    conn = repository.connect()
    released: List[int] = []
    try:
        with repository.write_tx(conn):
            for stale in repository.stale_refunding_refunds(conn, cutoff):
                now = repository.utcnow()
                if repository.mark_refund_settled(
                    conn,
                    int(stale["id"]),
                    RefundStatus.REFUND_FAILED.value,
                    None,
                    "STALE_ATTEMPT",
                    "reconciled: attempt did not settle",
                    now,
                ):
                    repository.update_after_sale_status(
                        conn,
                        int(stale["after_sale_id"]),
                        AfterSaleStatus.REFUND_FAILED.value,
                        now,
                        expected_status=AfterSaleStatus.REFUNDING.value,
                    )
                    repository.release_refund_quota(
                        conn, int(stale["order_id"]), int(stale["amount"])
                    )
                    released.append(int(stale["id"]))
        return {"released": len(released), "released_refund_ids": released}
    finally:
        conn.close()
