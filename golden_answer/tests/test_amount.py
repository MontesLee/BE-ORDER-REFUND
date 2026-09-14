"""T03 / T04 -- the cumulative amount invariant (I1).

``sum(successful_refund.amount) <= order.paid_amount`` at every instant.
"""

from __future__ import annotations

from harness import (
    Api,
    approved_after_sale,
    ledger_successful_total,
    paid_order,
    refunded_amount,
    successful_refund_amounts,
)


def test_multiple_partial_refunds(client):
    """T03 -- several after-sales on one order, each partial, each counted once."""
    api = Api(client)
    owner = api.create_user("t03-owner")
    agent = api.create_agent("t03-agent")

    order_id = paid_order(api, owner["id"], 10_000)

    parts = [3_000, 3_000, 4_000]
    for index, amount in enumerate(parts):
        after_sale_id = approved_after_sale(
            api, owner["id"], agent["id"], order_id, amount, f"t03-{index}"
        )
        executed = api.execute(agent["id"], after_sale_id)
        assert executed.status_code == 200, executed.text
        assert executed.json()["after_sale"]["status"] == "REFUNDED"

    assert refunded_amount(api, owner["id"], order_id) == sum(parts) == 10_000
    assert ledger_successful_total(api, owner["id"], order_id) == 10_000


def test_over_refund_is_rejected(client):
    """T04 -- cumulative successful refunds may never exceed paid_amount."""
    api = Api(client)
    owner = api.create_user("t04-owner")
    agent = api.create_agent("t04-agent")

    order_id = paid_order(api, owner["id"], 10_000)

    first = approved_after_sale(api, owner["id"], agent["id"], order_id, 6_000, "t04-a")
    second = approved_after_sale(api, owner["id"], agent["id"], order_id, 6_000, "t04-b")

    assert api.execute(agent["id"], first).status_code == 200

    overflow = api.execute(agent["id"], second)
    assert overflow.status_code >= 400, (
        "executing a second 6000 refund on a 10000 order must be refused"
    )
    assert overflow.status_code in (400, 409), overflow.text

    assert refunded_amount(api, owner["id"], order_id) == 6_000
    assert ledger_successful_total(api, owner["id"], order_id) == 6_000
    assert successful_refund_amounts(api, owner["id"], second) == []


def test_single_refund_larger_than_paid_amount_is_rejected(client):
    """I1 corner case: one after-sale asking for more than the order ever paid."""
    api = Api(client)
    owner = api.create_user("t04b-owner")
    agent = api.create_agent("t04b-agent")

    order_id = paid_order(api, owner["id"], 5_000)
    created = api.create_after_sale(owner["id"], order_id, 9_000, "t04b")

    if created.status_code >= 400:
        assert created.status_code in (400, 409, 422), created.text
        assert refunded_amount(api, owner["id"], order_id) == 0
        return

    after_sale_id = created.json()["id"]
    api.approve(agent["id"], after_sale_id)
    executed = api.execute(agent["id"], after_sale_id)
    assert executed.status_code >= 400, "9000 must not be refunded from a 5000 order"
    assert refunded_amount(api, owner["id"], order_id) == 0
