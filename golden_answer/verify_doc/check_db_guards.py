"""Deterministic proof that the database itself enforces the invariants.

The multi-worker tests (T13/T14) assert the business outcome under real
concurrency, but a race is by nature a timing event: on a given machine a
broken implementation *can* slip through by luck.  This script removes the luck.
It probes the storage layer directly and checks that the guarantees are
structural, not behavioural:

* a second successful refund for one after-sale is rejected by a partial
  UNIQUE index, whatever the application code does;
* ``refunded_amount`` can never exceed ``paid_amount`` thanks to a CHECK
  constraint;
* the write lock taken by ``BEGIN IMMEDIATE`` is genuinely exclusive **across
  connections/processes** -- a second writer is refused rather than allowed to
  interleave a check-then-write pair.

Every assertion is an expected *error*: the point is that the database says no.

Usage::

    python verify_doc/check_db_guards.py
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

WORKDIR = Path(tempfile.mkdtemp(prefix="refund-guards-"))
os.environ["REFUND_DB_PATH"] = str(WORKDIR / "guards.db")

from app import repository  # noqa: E402

RESULTS: list = []


def check(name: str, action, expect: str) -> None:
    try:
        action()
        outcome = "NO_ERROR_RAISED"
    except sqlite3.IntegrityError as exc:
        outcome = f"IntegrityError: {exc}"
    except sqlite3.OperationalError as exc:
        outcome = f"OperationalError: {exc}"
    ok = outcome.startswith(expect)
    RESULTS.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    print(f"         expected : {expect}")
    print(f"         observed : {outcome}")


def seed():
    repository.init_schema()
    conn = repository.connect()
    now = repository.utcnow()
    with repository.write_tx(conn):
        user_id = repository.insert_user(conn, "guard-owner", "USER", now)
        order_id = repository.insert_order(conn, user_id, 10_000, now)
        repository.mark_order_paid(conn, order_id, now)
        first = repository.insert_after_sale(conn, order_id, user_id, 10_000, "g-1", now)
        second = repository.insert_after_sale(conn, order_id, user_id, 1, "g-2", now)
        refund_id = repository.insert_refund(conn, first, order_id, 10_000, 1, "g-r1", now)
        repository.mark_refund_settled(
            conn, refund_id, "REFUNDED", "TP-1", None, None, now
        )
        repository.reserve_refund_quota(conn, order_id, 10_000)
    conn.close()
    return order_id, first, second


def main() -> int:
    order_id, first_after_sale, second_after_sale = seed()
    print(f"== database: {os.environ['REFUND_DB_PATH']}\n")

    # 1. I2 -- partial unique index: at most one REFUNDED row per after-sale.
    def duplicate_success():
        conn = repository.connect()
        try:
            with repository.write_tx(conn):
                repository.insert_refund(conn, first_after_sale, order_id, 5, 2, "g-r2", "x")
                conn.execute(
                    "UPDATE refunds SET status='REFUNDED' WHERE idempotency_key='g-r2'"
                )
        finally:
            conn.close()

    check(
        "I2  a second successful refund for one after-sale is rejected",
        duplicate_success,
        "IntegrityError",
    )

    # 2. I1 -- CHECK constraint: cumulative refunds cannot exceed paid_amount.
    def over_refund():
        conn = repository.connect()
        try:
            with repository.write_tx(conn):
                conn.execute(
                    "UPDATE orders SET refunded_amount = paid_amount + 1 WHERE id = ?",
                    (order_id,),
                )
        finally:
            conn.close()

    check(
        "I1  orders.refunded_amount > paid_amount is rejected",
        over_refund,
        "IntegrityError",
    )

    # 3. Negative money is equally impossible.
    def negative_amount():
        conn = repository.connect()
        try:
            with repository.write_tx(conn):
                conn.execute(
                    "UPDATE orders SET refunded_amount = -1 WHERE id = ?", (order_id,)
                )
        finally:
            conn.close()

    check("I1  negative refunded_amount is rejected", negative_amount, "IntegrityError")

    # 4. A non-positive refund request can never be persisted.
    def non_positive_request():
        conn = repository.connect()
        try:
            with repository.write_tx(conn):
                repository.insert_after_sale(conn, order_id, 1, 0, "g-zero", "x")
        finally:
            conn.close()

    check(
        "R1  after_sales.refund_amount > 0 is enforced by the schema",
        non_positive_request,
        "IntegrityError",
    )

    # 5. I5 -- BEGIN IMMEDIATE takes a real, cross-connection write lock.
    def concurrent_writer():
        holder = repository.connect()
        intruder = sqlite3.connect(os.environ["REFUND_DB_PATH"], timeout=0.5, isolation_level=None)
        try:
            holder.execute("BEGIN IMMEDIATE")
            intruder.execute("PRAGMA busy_timeout = 300")
            intruder.execute("BEGIN IMMEDIATE")
        finally:
            try:
                intruder.execute("ROLLBACK")
            except sqlite3.OperationalError:
                pass
            intruder.close()
            try:
                holder.execute("ROLLBACK")
            except sqlite3.OperationalError:
                pass
            holder.close()

    check(
        "I5  a second BEGIN IMMEDIATE writer is refused while one holds the lock",
        concurrent_writer,
        "OperationalError",
    )

    # 6. ... and the lock really is released afterwards.
    def writer_after_release():
        holder = repository.connect()
        holder.execute("BEGIN IMMEDIATE")
        holder.execute("ROLLBACK")
        holder.close()
        follower = repository.connect()
        try:
            with repository.write_tx(follower):
                follower.execute("SELECT 1")
        finally:
            follower.close()

    check(
        "I5  the write lock is released after the holder commits",
        writer_after_release,
        "NO_ERROR_RAISED",
    )

    print()
    if all(RESULTS):
        print(f"== all {len(RESULTS)} storage-level guards hold")
        return 0
    print(f"== {RESULTS.count(False)} of {len(RESULTS)} guards FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
