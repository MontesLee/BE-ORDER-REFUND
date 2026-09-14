"""T06 / T07 -- idempotency (I2).

A duplicated business request must not create a second effect.  The tests assert
the *observable business result*, not a specific mechanism: a model may use a
unique index, an upsert, a replay table or anything else that works.
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


def test_duplicate_submit_creates_one_after_sale(client):
    """T06 -- the same idempotency key resubmitted twice yields one after-sale."""
    api = Api(client)
    owner = api.create_user("t06-owner")
    agent = api.create_agent("t06-agent")

    order_id = paid_order(api, owner["id"], 10_000)

    first = api.create_after_sale(owner["id"], order_id, 4_000, "submit-once")
    second = api.create_after_sale(owner["id"], order_id, 4_000, "submit-once")

    assert first.status_code in (200, 201), first.text
    assert second.status_code in (200, 201), second.text
    assert first.json()["id"] == second.json()["id"], (
        "a repeated idempotency key must not create a second after-sale"
    )

    listing = api.list_after_sales(owner["id"], order_id, limit=100)
    assert listing.status_code == 200, listing.text
    assert listing.json()["total"] == 1, listing.text

    # ... and the single after-sale still behaves normally.
    after_sale_id = first.json()["id"]
    assert api.approve(agent["id"], after_sale_id).status_code == 200
    assert api.execute(agent["id"], after_sale_id).status_code == 200
    assert successful_refund_amounts(api, owner["id"], after_sale_id) == [4_000]


def test_duplicate_execute_creates_one_refund(client):
    """T07 -- executing the same after-sale twice refunds at most once."""
    api = Api(client)
    owner = api.create_user("t07-owner")
    agent = api.create_agent("t07-agent")

    order_id = paid_order(api, owner["id"], 10_000)
    after_sale_id = approved_after_sale(api, owner["id"], agent["id"], order_id, 10_000)

    first = api.execute(agent["id"], after_sale_id)
    assert first.status_code == 200, first.text

    second = api.execute(agent["id"], after_sale_id)
    # Refusing the duplicate (409) and replaying the original (200) are both
    # legitimate designs; producing a second refund is not.
    assert second.status_code < 500, second.text

    assert successful_refund_amounts(api, owner["id"], after_sale_id) == [10_000]
    assert refunded_amount(api, owner["id"], order_id) == 10_000
    assert after_sale_status(api, owner["id"], after_sale_id) == "REFUNDED"


def test_duplicate_submit_does_not_break_the_amount_cap(client):
    """A replayed submission must not silently consume quota twice."""
    api = Api(client)
    owner = api.create_user("t06b-owner")
    agent = api.create_agent("t06b-agent")

    order_id = paid_order(api, owner["id"], 10_000)

    for _ in range(3):
        response = api.create_after_sale(owner["id"], order_id, 10_000, "same-key")
        assert response.status_code in (200, 201), response.text
        after_sale_id = response.json()["id"]

    assert api.approve(agent["id"], after_sale_id).status_code == 200
    assert api.execute(agent["id"], after_sale_id).status_code == 200
    assert refunded_amount(api, owner["id"], order_id) == 10_000
