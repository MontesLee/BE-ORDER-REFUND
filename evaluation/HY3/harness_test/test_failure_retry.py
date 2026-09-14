"""T05 / T09 / T11 / T12 -- third-party failure semantics (I4) and retry.

All four tests inject a deterministic gateway instead of breaking a real
network, so a failure is reproduced on every run rather than "sometimes in
production".

Failure mode under test: the provider rejects the refund while the local record
is nevertheless marked ``REFUNDED``.
"""

from __future__ import annotations

from harness import (
    Api,
    after_sale_status,
    approved_after_sale,
    ledger_successful_total,
    paid_order,
    refunded_amount,
    successful_refund_amounts,
)


def test_third_party_failure_is_not_marked_success(client, gateway):
    """T11 -- provider failure must never become a local REFUNDED."""
    api = Api(client)
    owner = api.create_user("t11-owner")
    agent = api.create_agent("t11-agent")

    order_id = paid_order(api, owner["id"], 10_000)
    after_sale_id = approved_after_sale(api, owner["id"], agent["id"], order_id, 10_000)

    gateway.fail_always = True
    executed = api.execute(agent["id"], after_sale_id)
    assert executed.status_code < 500, executed.text

    status = after_sale_status(api, owner["id"], after_sale_id)
    assert status != "REFUNDED", "a refused provider refund must not be REFUNDED"
    assert status == "REFUND_FAILED", (
        f"the after-sale should land in REFUND_FAILED, got {status}"
    )
    assert successful_refund_amounts(api, owner["id"], after_sale_id) == []
    assert refunded_amount(api, owner["id"], order_id) == 0


def test_failed_refund_does_not_consume_quota(client, gateway):
    """T05 -- a refused refund must not permanently burn the order's quota."""
    api = Api(client)
    owner = api.create_user("t05-owner")
    agent = api.create_agent("t05-agent")

    order_id = paid_order(api, owner["id"], 10_000)

    gateway.fail_first_n = 1
    failing = approved_after_sale(api, owner["id"], agent["id"], order_id, 6_000, "t05-a")
    assert api.execute(agent["id"], failing).status_code < 500
    assert after_sale_status(api, owner["id"], failing) == "REFUND_FAILED"
    assert refunded_amount(api, owner["id"], order_id) == 0

    # The whole 10000 is still available, which is only possible if the failed
    # attempt gave its reservation back.
    succeeding = approved_after_sale(api, owner["id"], agent["id"], order_id, 10_000, "t05-b")
    assert api.execute(agent["id"], succeeding).status_code == 200
    assert after_sale_status(api, owner["id"], succeeding) == "REFUNDED"
    assert refunded_amount(api, owner["id"], order_id) == 10_000
    assert ledger_successful_total(api, owner["id"], order_id) == 10_000


def test_failed_refund_can_be_retried(client, gateway):
    """T09 -- REFUND_FAILED is retryable and a successful retry ends in REFUNDED."""
    api = Api(client)
    owner = api.create_user("t09-owner")
    agent = api.create_agent("t09-agent")

    order_id = paid_order(api, owner["id"], 10_000)
    after_sale_id = approved_after_sale(api, owner["id"], agent["id"], order_id, 10_000)

    gateway.fail_first_n = 1
    first = api.execute(agent["id"], after_sale_id)
    assert first.status_code < 500, first.text
    assert after_sale_status(api, owner["id"], after_sale_id) == "REFUND_FAILED"

    second = api.execute(agent["id"], after_sale_id)
    assert second.status_code == 200, second.text
    assert after_sale_status(api, owner["id"], after_sale_id) == "REFUNDED"
    assert successful_refund_amounts(api, owner["id"], after_sale_id) == [10_000]
    assert refunded_amount(api, owner["id"], order_id) == 10_000


def test_incident_regression_provider_failure(client, gateway):
    """T12 -- the R6 incident, reproduced deterministically.

    Reported symptom: "the provider failed but the order shows the refund
    succeeded".  This regression test fails on the buggy implementation and
    passes once the provider verdict decides the local state.
    """
    api = Api(client)
    owner = api.create_user("t12-owner")
    agent = api.create_agent("t12-agent")

    order_id = paid_order(api, owner["id"], 10_000)
    after_sale_id = approved_after_sale(api, owner["id"], agent["id"], order_id, 10_000)

    gateway.fail_first_n = 1

    # 1. Provider refuses -> local must not claim success.
    api.execute(agent["id"], after_sale_id)
    assert after_sale_status(api, owner["id"], after_sale_id) == "REFUND_FAILED"
    assert refunded_amount(api, owner["id"], order_id) == 0
    assert ledger_successful_total(api, owner["id"], order_id) == 0

    # 2. Retry succeeds -> exactly one successful refund.
    assert api.execute(agent["id"], after_sale_id).status_code == 200
    assert after_sale_status(api, owner["id"], after_sale_id) == "REFUNDED"

    # 3. Further retries must not refund again.
    api.execute(agent["id"], after_sale_id)
    assert successful_refund_amounts(api, owner["id"], after_sale_id) == [10_000]
    assert refunded_amount(api, owner["id"], order_id) == 10_000
    assert ledger_successful_total(api, owner["id"], order_id) == 10_000
