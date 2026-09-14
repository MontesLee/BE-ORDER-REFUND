"""T13 / T14 -- multi-worker correctness (I5).

These tests run against **two real uvicorn processes** that share one SQLite
file (see the ``cluster`` fixture).  That detail is the point of the round:

* an in-process test would happily pass a ``threading.Lock``, which is a
  process-local object and therefore useless in production;
* a test that only asserts "the requests were issued concurrently" proves
  nothing about the observable business result.

Both tests therefore assert the *data*: how many refunds succeeded and how much
money left the order.  Requests are spread across both workers.
"""

from __future__ import annotations

import concurrent.futures
import threading

from harness import (
    Api,
    after_sale_status,
    approved_after_sale,
    ledger_successful_total,
    paid_order,
    refunded_amount,
    successful_refund_amounts,
)

#: How many independent after-sales are attacked in T13. Repeating the race
#: matters: a single round can be won by luck (the attacker threads simply miss
#: each other's critical section), and a test that only sometimes reproduces the
#: bug is not a regression test.
T13_ROUNDS = 3


def test_cluster_really_is_multi_process(cluster):
    """Guard: the fixture must be running two distinct worker processes."""
    pids = cluster.get("worker_pids") or []
    assert len(pids) == 2, "the cluster fixture must start exactly two workers"
    assert len(set(pids)) == 2, "the two workers must be distinct processes"
    assert len(set(cluster["urls"])) == 2


def test_concurrent_same_after_sale(cluster, cluster_apis):
    """T13 -- N workers race on one after-sale; at most one refund succeeds.

    Every attacker is released from the same barrier so the requests actually
    overlap, and the scenario is repeated over several after-sales so the race
    is reproduced rather than hoped for.
    """
    setup = cluster_apis[0]
    owner = setup.create_user("t13-owner")
    agent = setup.create_agent("t13-agent")
    order_id = paid_order(setup, owner["id"], 30_000)

    def hammer(api: Api, after_sale_id: int, gate: threading.Barrier) -> int:
        gate.wait()
        return api.execute(agent["id"], after_sale_id).status_code

    for round_index in range(T13_ROUNDS):
        after_sale_id = approved_after_sale(
            setup, owner["id"], agent["id"], order_id, 10_000, f"t13-{round_index}"
        )
        gate = threading.Barrier(len(cluster_apis))
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(cluster_apis)) as pool:
            statuses = [
                future.result()
                for future in [
                    pool.submit(hammer, api, after_sale_id, gate) for api in cluster_apis
                ]
            ]
        assert all(status < 500 for status in statuses), statuses

        settled = successful_refund_amounts(cluster_apis[0], owner["id"], after_sale_id)
        assert len(settled) == 1, (
            f"round {round_index}: exactly one refund must succeed, got {settled}"
        )
        assert after_sale_status(cluster_apis[0], owner["id"], after_sale_id) == "REFUNDED"

    total = ledger_successful_total(cluster_apis[0], owner["id"], order_id)
    assert total == T13_ROUNDS * 10_000
    assert refunded_amount(cluster_apis[0], owner["id"], order_id) == total


def test_concurrent_multiple_after_sales(cluster, cluster_apis):
    """T14 -- workers race on several after-sales of the same order.

    Five 3000 refunds against a 10000 order: the cap, not the clock, decides how
    many may succeed.
    """
    setup = cluster_apis[0]
    owner = setup.create_user("t14-owner")
    agent = setup.create_agent("t14-agent")
    order_id = paid_order(setup, owner["id"], 10_000)

    after_sale_ids = [
        approved_after_sale(setup, owner["id"], agent["id"], order_id, 3_000, f"t14-{i}")
        for i in range(5)
    ]

    def hammer(pair, gate: threading.Barrier) -> int:
        api, after_sale_id = pair
        gate.wait()
        return api.execute(agent["id"], after_sale_id).status_code

    workers = cluster_apis[:5]
    gate = threading.Barrier(len(workers))
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(workers)) as pool:
        statuses = [
            future.result()
            for future in [
                pool.submit(hammer, pair, gate) for pair in zip(workers, after_sale_ids)
            ]
        ]

    assert all(status < 500 for status in statuses), statuses

    verify = cluster_apis[0]
    counter = refunded_amount(verify, owner["id"], order_id)
    ledger = ledger_successful_total(verify, owner["id"], order_id)
    successes = sum(
        len(successful_refund_amounts(verify, owner["id"], after_sale_id))
        for after_sale_id in after_sale_ids
    )

    assert counter <= 10_000, f"cumulative refunds exceeded paid_amount: {counter}"
    assert ledger == counter, f"ledger ({ledger}) disagrees with the order counter ({counter})"
    assert ledger <= 10_000
    assert successes <= 3, f"at most 3x3000 fits into 10000, got {successes}"
    assert successes >= 1
