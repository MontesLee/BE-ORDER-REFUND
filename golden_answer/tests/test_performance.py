"""T18 -- basic performance and data-access discipline.

R7 asks for "obvious N+1 / repeated queries / degradation as refunds grow /
unbounded loading" to be fixed.  Turning that into a stable automated check means
asserting things that are deterministic:

* the query plans for the hot lookups use an **index**, not a table scan;
* list endpoints are **paged**, so a caller cannot ask for the whole table
  (``limit=5`` must return five rows, not three hundred);
* a paged response over 300 rows stays far below the 500 ms budget.

No QPS benchmark and no timing-sensitive assertions beyond a generous bound.
"""

from __future__ import annotations

import time

from app import repository
from harness import Api, paid_order

SEEDED_REFUNDS = 300
PAID_AMOUNT = 1_000_000
LATENCY_BUDGET_SECONDS = 0.5


def _seed_ledger(order_id: int, user_id: int, count: int) -> None:
    """Insert ``count`` settled refunds straight into the schema.

    Seeding through the API would take ~900 calls and would measure the test
    client rather than the query path, which is what T18 is about.
    """
    conn = repository.connect()
    try:
        now = repository.utcnow()
        with repository.write_tx(conn):
            for index in range(count):
                after_sale_id = repository.insert_after_sale(
                    conn, order_id, user_id, 1, f"perf-{index}", now
                )
                refund_id = repository.insert_refund(
                    conn, after_sale_id, order_id, 1, 1, f"perf-refund-{index}", now
                )
                repository.mark_refund_settled(
                    conn, refund_id, "REFUNDED", f"TP-{index}", None, None, now
                )
                repository.update_after_sale_status(conn, after_sale_id, "REFUNDED", now)
                repository.reserve_refund_quota(conn, order_id, 1)
    finally:
        conn.close()


def _query_plan(conn, sql: str, params=()) -> str:
    rows = conn.execute(f"EXPLAIN QUERY PLAN {sql}", params).fetchall()
    return " | ".join(str(row["detail"]) for row in rows)


def test_indexed_queries_and_bounded_loading(client, db_file):
    api = Api(client)
    owner = api.create_user("t18-owner")
    agent = api.create_agent("t18-agent")
    order_id = paid_order(api, owner["id"], PAID_AMOUNT)

    _seed_ledger(order_id, owner["id"], SEEDED_REFUNDS)

    conn = repository.connect()
    try:
        plan = _query_plan(conn, "SELECT * FROM orders WHERE user_id = ?", (owner["id"],))
        assert "SCAN orders" not in plan, f"orders.user_id lookup scans: {plan}"

        plan = _query_plan(
            conn, "SELECT * FROM after_sales WHERE order_id = ? ORDER BY id", (order_id,)
        )
        assert "SCAN after_sales" not in plan, f"after_sales.order_id lookup scans: {plan}"

        plan = _query_plan(
            conn, "SELECT * FROM refunds WHERE order_id = ? ORDER BY id", (order_id,)
        )
        assert "SCAN refunds" not in plan, f"refunds.order_id lookup scans: {plan}"

        plan = _query_plan(
            conn,
            "SELECT * FROM refunds WHERE after_sale_id = ? AND status = 'REFUNDED'",
            (1,),
        )
        assert "SCAN refunds" not in plan, f"successful-refund lookup scans: {plan}"
    finally:
        conn.close()

    # Pagination is enforced: asking for 5 rows returns 5 rows.
    first_page = api.list_after_sales(owner["id"], order_id, limit=5)
    assert first_page.status_code == 200, first_page.text
    payload = first_page.json()
    assert payload["total"] == SEEDED_REFUNDS, payload["total"]
    assert len(payload["items"]) == 5, (
        f"limit=5 returned {len(payload['items'])} rows: unbounded loading"
    )

    last_page = api.list_after_sales(
        owner["id"], order_id, limit=5, offset=SEEDED_REFUNDS - 5
    )
    assert last_page.status_code == 200, last_page.text
    assert len(last_page.json()["items"]) == 5, last_page.text

    # A paged read over 300 rows must stay well inside the latency budget.
    samples = []
    for _ in range(5):
        started = time.perf_counter()
        response = api.list_after_sales(owner["id"], order_id, limit=50)
        samples.append(time.perf_counter() - started)
        assert response.status_code == 200, response.text

    best = min(samples)
    assert best < LATENCY_BUDGET_SECONDS, (
        f"paged listing took {best:.3f}s, budget {LATENCY_BUDGET_SECONDS}s"
    )
