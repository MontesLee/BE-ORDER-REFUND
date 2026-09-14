"""Persistence layer: SQLite connection handling, schema DDL, SQL statements.

Why this file carries so much weight
------------------------------------
The benchmark's hardest invariants (I1 amount cap, I2 one successful refund per
AfterSale, I5 multi-worker correctness) cannot be guaranteed in Python alone.
They are pushed down to the database, where they hold **across processes**:

============================  ==========================================
Guarantee                     Mechanism
============================  ==========================================
I1 ``refunded_amount <=        ``CHECK`` constraint on ``orders`` plus an
   paid_amount``               ``UPDATE ... WHERE refunded_amount + ? <=
                               paid_amount`` guard executed inside a
                               ``BEGIN IMMEDIATE`` write transaction
I2 at most one ``REFUNDED``    partial ``UNIQUE INDEX`` on
   refund per AfterSale        ``refunds(after_sale_id) WHERE status='REFUNDED'``
I5 multi-worker                ``BEGIN IMMEDIATE`` (real write lock in the
                               database file, not a process-local
                               ``threading.Lock``) + ``busy_timeout`` retry
============================  ==========================================

A ``threading.Lock`` would pass a single-process test and fail in production;
that is exactly failure mode #7 in the benchmark specification.

Money is stored as ``INTEGER`` 分 (cents) everywhere. No ``float``.
"""

from __future__ import annotations

import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

# --------------------------------------------------------------------------
# Connections
# --------------------------------------------------------------------------

DEFAULT_DB_FILENAME = "refund.db"


def default_db_path() -> str:
    return str(Path(__file__).resolve().parent.parent / "data" / DEFAULT_DB_FILENAME)


def db_path() -> str:
    """Resolved database file.

    Read from the environment on every call so that a test can point the whole
    application at a throw-away file without re-importing modules.
    """
    return os.environ.get("REFUND_DB_PATH") or default_db_path()


def connect() -> sqlite3.Connection:
    path = db_path()
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path, timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    # Wait (instead of raising SQLITE_BUSY) when another worker holds the
    # write lock. This is what makes concurrent writers queue up safely.
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA foreign_keys = ON")
    if path != ":memory:":
        enable_wal(conn)
    return conn


def enable_wal(conn: sqlite3.Connection, attempts: int = 5) -> bool:
    """Switch the database file to WAL mode, best effort.

    WAL is a *persistent property of the file*, so it only has to be applied
    once; afterwards every connection picks it up automatically.  Applying it
    needs an exclusive lock, so several workers booting in the same instant can
    collide -- and that collision is harmless.  Losing the race must not take a
    worker down, otherwise a rolling restart turns into an outage.
    """
    for attempt in range(attempts):
        try:
            mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()[0]
            return str(mode).lower() == "wal"
        except sqlite3.OperationalError:
            if attempt == attempts - 1:
                return False
            time.sleep(0.2 * (attempt + 1))
    return False


@contextmanager
def write_tx(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Serialise a read-modify-write section as a write transaction.

    ``BEGIN IMMEDIATE`` takes the database write lock *before* the first read,
    so no two workers can interleave a check-then-write pair. Plain
    ``BEGIN DEFERRED`` would allow exactly the race the benchmark targets.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        _safe_rollback(conn)
        raise
    conn.execute("COMMIT")


@contextmanager
def read_tx(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    conn.execute("BEGIN")
    try:
        yield conn
    finally:
        _safe_rollback(conn)


def _safe_rollback(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("ROLLBACK")
    except sqlite3.OperationalError:
        pass


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    role       TEXT NOT NULL DEFAULT 'USER',
    created_at TEXT NOT NULL,
    CHECK (role IN ('USER', 'AGENT'))
);

CREATE TABLE IF NOT EXISTS orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    total_amount    INTEGER NOT NULL,
    paid_amount     INTEGER NOT NULL DEFAULT 0,
    refunded_amount INTEGER NOT NULL DEFAULT 0,
    payment_status  TEXT    NOT NULL DEFAULT 'UNPAID',
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    CHECK (total_amount > 0),
    CHECK (paid_amount >= 0),
    CHECK (paid_amount <= total_amount),
    CHECK (refunded_amount >= 0),
    -- I1 enforced by the database itself, for every worker:
    CHECK (refunded_amount <= paid_amount),
    CHECK (payment_status IN ('UNPAID', 'PAID'))
);

CREATE TABLE IF NOT EXISTS after_sales (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id        INTEGER NOT NULL REFERENCES orders(id),
    user_id         INTEGER NOT NULL REFERENCES users(id),
    refund_amount   INTEGER NOT NULL,
    status          TEXT    NOT NULL,
    idempotency_key TEXT,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    CHECK (refund_amount > 0),
    CHECK (status IN ('PENDING', 'APPROVED', 'REFUNDING', 'REFUNDED', 'REFUND_FAILED'))
);

-- Idempotent client submission: a repeated key can never create a second row.
CREATE UNIQUE INDEX IF NOT EXISTS ux_after_sales_idempotency
    ON after_sales(idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_after_sales_order ON after_sales(order_id, id);
CREATE INDEX IF NOT EXISTS ix_after_sales_user  ON after_sales(user_id, id);

-- Listing an order must not scan the table once a user has some history.
CREATE INDEX IF NOT EXISTS ix_orders_user ON orders(user_id, id);

CREATE TABLE IF NOT EXISTS refunds (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    after_sale_id   INTEGER NOT NULL REFERENCES after_sales(id),
    order_id        INTEGER NOT NULL REFERENCES orders(id),
    amount          INTEGER NOT NULL,
    status          TEXT    NOT NULL,
    attempt         INTEGER NOT NULL DEFAULT 1,
    third_party_ref TEXT,
    error_code      TEXT,
    error_message   TEXT,
    idempotency_key TEXT,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    CHECK (amount > 0),
    CHECK (status IN ('REFUNDING', 'REFUNDED', 'REFUND_FAILED'))
);

-- I2 enforced by the database itself: at most one successful refund per
-- AfterSale, no matter how many workers race.
CREATE UNIQUE INDEX IF NOT EXISTS ux_refunds_one_success
    ON refunds(after_sale_id) WHERE status = 'REFUNDED';
CREATE UNIQUE INDEX IF NOT EXISTS ux_refunds_idempotency
    ON refunds(idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_refunds_after_sale ON refunds(after_sale_id, id);
CREATE INDEX IF NOT EXISTS ix_refunds_order      ON refunds(order_id, id);
"""


def init_schema() -> None:
    """Create the schema if it does not exist yet. Safe to call from every worker."""
    conn = connect()
    try:
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.executescript(SCHEMA)
    finally:
        conn.close()


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    return dict(row) if row is not None else None


def rows_to_dicts(rows: List[sqlite3.Row]) -> List[Dict[str, Any]]:
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# users
# --------------------------------------------------------------------------


def get_user(conn: sqlite3.Connection, user_id: int) -> Optional[Dict[str, Any]]:
    return row_to_dict(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


def insert_user(conn: sqlite3.Connection, name: str, role: str, now: str) -> int:
    cur = conn.execute(
        "INSERT INTO users (name, role, created_at) VALUES (?, ?, ?)", (name, role, now)
    )
    return int(cur.lastrowid)


# --------------------------------------------------------------------------
# orders
# --------------------------------------------------------------------------


def get_order(conn: sqlite3.Connection, order_id: int) -> Optional[Dict[str, Any]]:
    return row_to_dict(conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone())


def insert_order(
    conn: sqlite3.Connection, user_id: int, total_amount: int, now: str
) -> int:
    cur = conn.execute(
        """
        INSERT INTO orders (user_id, total_amount, paid_amount, refunded_amount,
                            payment_status, created_at, updated_at)
        VALUES (?, ?, 0, 0, 'UNPAID', ?, ?)
        """,
        (user_id, total_amount, now, now),
    )
    return int(cur.lastrowid)


def mark_order_paid(conn: sqlite3.Connection, order_id: int, now: str) -> None:
    conn.execute(
        """
        UPDATE orders
           SET paid_amount = total_amount, payment_status = 'PAID', updated_at = ?
         WHERE id = ? AND payment_status = 'UNPAID'
        """,
        (now, order_id),
    )


def list_orders_for_user(
    conn: sqlite3.Connection, user_id: int, limit: int, offset: int
) -> List[Dict[str, Any]]:
    return rows_to_dicts(
        conn.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY id LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        ).fetchall()
    )


def count_orders_for_user(conn: sqlite3.Connection, user_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM orders WHERE user_id = ?", (user_id,)
    ).fetchone()
    return int(row["c"])


def reserve_refund_quota(conn: sqlite3.Connection, order_id: int, amount: int) -> bool:
    """Atomically reserve ``amount`` of the order's refundable quota.

    Returns ``False`` when the reservation would push the cumulative amount
    above ``paid_amount``.  The ``WHERE`` clause makes check-and-reserve a
    single statement, so it is safe under concurrency; the table ``CHECK``
    constraint is the independent backstop.
    """
    cur = conn.execute(
        """
        UPDATE orders
           SET refunded_amount = refunded_amount + ?, updated_at = ?
         WHERE id = ?
           AND payment_status = 'PAID'
           AND refunded_amount + ? <= paid_amount
        """,
        (amount, utcnow(), order_id, amount),
    )
    return cur.rowcount == 1


def release_refund_quota(conn: sqlite3.Connection, order_id: int, amount: int) -> None:
    """Give the reserved quota back when the provider refused the refund."""
    conn.execute(
        """
        UPDATE orders
           SET refunded_amount = refunded_amount - ?, updated_at = ?
         WHERE id = ? AND refunded_amount >= ?
        """,
        (amount, utcnow(), order_id, amount),
    )


# --------------------------------------------------------------------------
# after_sales
# --------------------------------------------------------------------------

_AFTER_SALE_COLS = (
    "id, order_id, user_id, refund_amount, status, idempotency_key, "
    "created_at, updated_at"
)


def get_after_sale(
    conn: sqlite3.Connection, after_sale_id: int
) -> Optional[Dict[str, Any]]:
    return row_to_dict(
        conn.execute(
            f"SELECT {_AFTER_SALE_COLS} FROM after_sales WHERE id = ?", (after_sale_id,)
        ).fetchone()
    )


def get_after_sale_by_idempotency_key(
    conn: sqlite3.Connection, idempotency_key: str
) -> Optional[Dict[str, Any]]:
    return row_to_dict(
        conn.execute(
            f"SELECT {_AFTER_SALE_COLS} FROM after_sales WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
    )


def insert_after_sale(
    conn: sqlite3.Connection,
    order_id: int,
    user_id: int,
    refund_amount: int,
    idempotency_key: Optional[str],
    now: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO after_sales (order_id, user_id, refund_amount, status,
                                 idempotency_key, created_at, updated_at)
        VALUES (?, ?, ?, 'PENDING', ?, ?, ?)
        """,
        (order_id, user_id, refund_amount, idempotency_key, now, now),
    )
    return int(cur.lastrowid)


def list_after_sales_for_order(
    conn: sqlite3.Connection, order_id: int, limit: int, offset: int
) -> List[Dict[str, Any]]:
    return rows_to_dicts(
        conn.execute(
            f"SELECT {_AFTER_SALE_COLS} FROM after_sales WHERE order_id = ? "
            "ORDER BY id LIMIT ? OFFSET ?",
            (order_id, limit, offset),
        ).fetchall()
    )


def count_after_sales_for_order(conn: sqlite3.Connection, order_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM after_sales WHERE order_id = ?", (order_id,)
    ).fetchone()
    return int(row["c"])


def update_after_sale_status(
    conn: sqlite3.Connection,
    after_sale_id: int,
    new_status: str,
    now: str,
    expected_status: Optional[str] = None,
) -> bool:
    """Compare-and-set the AfterSale status.

    ``expected_status`` turns the update into an optimistic guard: the row is
    only touched if it is still in the state we validated.  Returns whether a
    row was actually updated.
    """
    if expected_status is None:
        cur = conn.execute(
            "UPDATE after_sales SET status = ?, updated_at = ? WHERE id = ?",
            (new_status, now, after_sale_id),
        )
    else:
        cur = conn.execute(
            "UPDATE after_sales SET status = ?, updated_at = ? "
            "WHERE id = ? AND status = ?",
            (new_status, now, after_sale_id, expected_status),
        )
    return cur.rowcount == 1


# --------------------------------------------------------------------------
# refunds
# --------------------------------------------------------------------------


def next_refund_attempt(conn: sqlite3.Connection, after_sale_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(attempt), 0) AS m FROM refunds WHERE after_sale_id = ?",
        (after_sale_id,),
    ).fetchone()
    return int(row["m"]) + 1


def insert_refund(
    conn: sqlite3.Connection,
    after_sale_id: int,
    order_id: int,
    amount: int,
    attempt: int,
    idempotency_key: str,
    now: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO refunds (after_sale_id, order_id, amount, status, attempt,
                             idempotency_key, created_at, updated_at)
        VALUES (?, ?, ?, 'REFUNDING', ?, ?, ?, ?)
        """,
        (after_sale_id, order_id, amount, attempt, idempotency_key, now, now),
    )
    return int(cur.lastrowid)


def get_refund(conn: sqlite3.Connection, refund_id: int) -> Optional[Dict[str, Any]]:
    return row_to_dict(conn.execute("SELECT * FROM refunds WHERE id = ?", (refund_id,)).fetchone())


def get_settled_refund(
    conn: sqlite3.Connection, after_sale_id: int
) -> Optional[Dict[str, Any]]:
    return row_to_dict(
        conn.execute(
            "SELECT * FROM refunds WHERE after_sale_id = ? AND status = 'REFUNDED' "
            "ORDER BY id LIMIT 1",
            (after_sale_id,),
        ).fetchone()
    )


def mark_refund_settled(
    conn: sqlite3.Connection,
    refund_id: int,
    status: str,
    third_party_ref: Optional[str],
    error_code: Optional[str],
    error_message: Optional[str],
    now: str,
) -> bool:
    cur = conn.execute(
        """
        UPDATE refunds
           SET status = ?, third_party_ref = ?, error_code = ?, error_message = ?,
               updated_at = ?
         WHERE id = ? AND status = 'REFUNDING'
        """,
        (status, third_party_ref, error_code, error_message, now, refund_id),
    )
    return cur.rowcount == 1


def list_refunds_for_after_sale(
    conn: sqlite3.Connection, after_sale_id: int, limit: int, offset: int
) -> List[Dict[str, Any]]:
    return rows_to_dicts(
        conn.execute(
            "SELECT * FROM refunds WHERE after_sale_id = ? ORDER BY id LIMIT ? OFFSET ?",
            (after_sale_id, limit, offset),
        ).fetchall()
    )


def count_refunds_for_after_sale(conn: sqlite3.Connection, after_sale_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM refunds WHERE after_sale_id = ?", (after_sale_id,)
    ).fetchone()
    return int(row["c"])


def successful_refund_total(conn: sqlite3.Connection, order_id: int) -> int:
    """Authoritative sum used to cross-check ``orders.refunded_amount``."""
    row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM refunds "
        "WHERE order_id = ? AND status = 'REFUNDED'",
        (order_id,),
    ).fetchone()
    return int(row["total"])


def count_successful_refunds_for_after_sale(
    conn: sqlite3.Connection, after_sale_id: int
) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM refunds WHERE after_sale_id = ? AND status = 'REFUNDED'",
        (after_sale_id,),
    ).fetchone()
    return int(row["c"])


def stale_refunding_refunds(
    conn: sqlite3.Connection, older_than_iso: str
) -> List[Dict[str, Any]]:
    return rows_to_dicts(
        conn.execute(
            "SELECT * FROM refunds WHERE status = 'REFUNDING' AND updated_at < ? "
            "ORDER BY id",
            (older_than_iso,),
        ).fetchall()
    )
