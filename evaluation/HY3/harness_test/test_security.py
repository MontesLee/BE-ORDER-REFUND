"""T15 / T16 / T17 -- user isolation and protected refund execution (I6).

The tests assert *observable* outcomes rather than one blessed HTTP code: a
cross-tenant read may be answered with 403 or 404 (the reference implementation
answers 404 on purpose, so a probe cannot confirm that a resource exists).  What
is not negotiable is that the other tenant's data does not come back and that no
money moves.
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

DENIED = (401, 403, 404)


def test_unauthorized_order_access(client):
    """T15 -- a user cannot read or act on another user's order."""
    api = Api(client)
    alice = api.create_user("t15-alice")
    bob = api.create_user("t15-bob")

    bob_order = paid_order(api, bob["id"], 7_000)

    read = api.get_order(alice["id"], bob_order)
    assert read.status_code in DENIED, read.text

    listing = api.list_orders(alice["id"], limit=100)
    assert listing.status_code == 200, listing.text
    assert all(item["id"] != bob_order for item in listing.json()["items"]), (
        "another user's order must not appear in the caller's order list"
    )

    pay = api.pay_order(alice["id"], bob_order)
    assert pay.status_code < 500

    submission = api.create_after_sale(alice["id"], bob_order, 7_000, "t15")
    assert submission.status_code >= 400, (
        "a user must not be able to file an after-sale against another user's order"
    )

    after_sales = api.list_after_sales(bob["id"], bob_order, limit=100)
    assert after_sales.status_code == 200, after_sales.text
    assert after_sales.json()["total"] == 0, "no after-sale should have been created"
    assert refunded_amount(api, bob["id"], bob_order) == 0


def test_unauthorized_after_sale_access(client):
    """T16 -- a user cannot read, approve or execute another user's after-sale."""
    api = Api(client)
    alice = api.create_user("t16-alice")
    bob = api.create_user("t16-bob")
    agent = api.create_agent("t16-agent")

    bob_order = paid_order(api, bob["id"], 9_000)
    bob_after_sale = new_after_sale(api, bob["id"], bob_order, 9_000, "t16")

    assert api.get_after_sale(alice["id"], bob_after_sale).status_code in DENIED
    assert api.list_refunds(alice["id"], bob_after_sale).status_code in DENIED

    api.approve(alice["id"], bob_after_sale)
    assert after_sale_status(api, bob["id"], bob_after_sale) == "PENDING", (
        "a normal user must not be able to approve another user's after-sale"
    )

    api.execute(alice["id"], bob_after_sale)
    assert successful_refund_amounts(api, bob["id"], bob_after_sale) == []
    assert refunded_amount(api, bob["id"], bob_order) == 0
    assert after_sale_status(api, bob["id"], bob_after_sale) == "PENDING"


def test_normal_user_cannot_execute_refund(client):
    """T17 -- refund execution is a protected step, not something a user does."""
    api = Api(client)
    owner = api.create_user("t17-owner")
    other = api.create_user("t17-other")
    agent = api.create_agent("t17-agent")

    # (a) the owner cannot push their own unapproved request to the provider
    order_id = paid_order(api, owner["id"], 10_000)
    pending = new_after_sale(api, owner["id"], order_id, 10_000, "t17-a")

    attempted = api.execute(owner["id"], pending)
    if attempted.status_code < 300:
        assert attempted.json()["after_sale"]["status"] != "REFUNDED", (
            "a normal user must not be able to bypass the review step"
        )
    else:
        assert attempted.status_code in (400, *DENIED, 409), attempted.text

    assert after_sale_status(api, owner["id"], pending) != "REFUNDED"
    assert successful_refund_amounts(api, owner["id"], pending) == []
    assert refunded_amount(api, owner["id"], order_id) == 0

    # (b) an unrelated user cannot execute someone else's approved request
    approved = approved_after_sale(api, owner["id"], agent["id"], order_id, 10_000, "t17-b")
    foreign = api.execute(other["id"], approved)
    if foreign.status_code < 300:
        assert foreign.json()["after_sale"]["status"] != "REFUNDED"
    assert successful_refund_amounts(api, owner["id"], approved) == []
    assert refunded_amount(api, owner["id"], order_id) == 0
