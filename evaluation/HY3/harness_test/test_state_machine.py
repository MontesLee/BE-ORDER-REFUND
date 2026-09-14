"""T08 / T10 -- the AfterSale state machine (I3).

``PENDING -> REFUNDED`` and ``REFUNDED -> *`` are both illegal.  ``REFUNDED`` is
terminal.
"""

from __future__ import annotations

from harness import (
    Api,
    after_sale_status,
    approved_after_sale,
    new_after_sale,
    paid_order,
    refunded_amount,
    successful_refund_amounts,
)


def test_illegal_state_transitions_rejected(client):
    """T08 -- an unapproved after-sale can never be refunded."""
    api = Api(client)
    owner = api.create_user("t08-owner")
    agent = api.create_agent("t08-agent")

    order_id = paid_order(api, owner["id"], 10_000)
    after_sale_id = new_after_sale(api, owner["id"], order_id, 10_000, "t08")

    assert after_sale_status(api, owner["id"], after_sale_id) == "PENDING"

    executed = api.execute(agent["id"], after_sale_id)
    if executed.status_code < 300:
        assert executed.json()["after_sale"]["status"] != "REFUNDED", (
            "PENDING -> REFUNDED must be impossible"
        )
    else:
        assert executed.status_code in (400, 403, 404, 409), executed.text

    assert after_sale_status(api, owner["id"], after_sale_id) != "REFUNDED"
    assert successful_refund_amounts(api, owner["id"], after_sale_id) == []
    assert refunded_amount(api, owner["id"], order_id) == 0


def test_refunded_is_terminal(client):
    """T10 -- after success, no path may start another refund."""
    api = Api(client)
    owner = api.create_user("t10-owner")
    agent = api.create_agent("t10-agent")

    order_id = paid_order(api, owner["id"], 10_000)
    after_sale_id = approved_after_sale(api, owner["id"], agent["id"], order_id, 10_000)

    assert api.execute(agent["id"], after_sale_id).status_code == 200
    assert after_sale_status(api, owner["id"], after_sale_id) == "REFUNDED"

    # Approving again must not reopen the request.
    reopened = api.approve(agent["id"], after_sale_id)
    assert reopened.status_code < 500, reopened.text
    assert after_sale_status(api, owner["id"], after_sale_id) == "REFUNDED"

    # Retrying must not move money a second time.
    retried = api.execute(agent["id"], after_sale_id)
    assert retried.status_code < 500, retried.text
    assert after_sale_status(api, owner["id"], after_sale_id) == "REFUNDED"

    assert successful_refund_amounts(api, owner["id"], after_sale_id) == [10_000]
    assert refunded_amount(api, owner["id"], order_id) == 10_000
