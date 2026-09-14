"""T01 / T02 -- refund eligibility at the level of one order.

``T01 normal refund`` and ``T02 unpaid refund`` from the golden test suite.
"""

from __future__ import annotations

from harness import (
    Api,
    after_sale_status,
    approved_after_sale,
    paid_order,
    refunded_amount,
    successful_refund_amounts,
)


def test_normal_full_refund(client):
    """T01 -- a paid order can be refunded in full, exactly once."""
    api = Api(client)
    owner = api.create_user("t01-owner")
    agent = api.create_agent("t01-agent")

    order_id = paid_order(api, owner["id"], 25_000)
    after_sale_id = approved_after_sale(api, owner["id"], agent["id"], order_id, 25_000)

    executed = api.execute(agent["id"], after_sale_id)
    assert executed.status_code == 200, executed.text
    assert executed.json()["after_sale"]["status"] == "REFUNDED"

    assert after_sale_status(api, owner["id"], after_sale_id) == "REFUNDED"
    assert successful_refund_amounts(api, owner["id"], after_sale_id) == [25_000]
    assert refunded_amount(api, owner["id"], order_id) == 25_000


def test_unpaid_order_cannot_be_refunded(client):
    """T02 -- an order that was never paid must not produce a successful refund."""
    api = Api(client)
    owner = api.create_user("t02-owner")
    agent = api.create_agent("t02-agent")

    created = api.create_order(owner["id"], 8_000)
    assert created.status_code in (200, 201), created.text
    order_id = created.json()["id"]

    submission = api.create_after_sale(owner["id"], order_id, 8_000)
    if submission.status_code < 300:
        # Accepting the request is tolerable; refunding it is not.
        after_sale_id = submission.json()["id"]
        api.approve(agent["id"], after_sale_id)
        executed = api.execute(agent["id"], after_sale_id)
        assert executed.status_code >= 400 or (
            executed.json()["after_sale"]["status"] != "REFUNDED"
        ), "an unpaid order must never reach REFUNDED"
        assert successful_refund_amounts(api, owner["id"], after_sale_id) == []
    else:
        assert submission.status_code in (400, 404, 409, 422), submission.text

    assert refunded_amount(api, owner["id"], order_id) == 0
