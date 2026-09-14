"""R0 -- the project must actually run and cover the happy path.

This is the baseline round. It deliberately checks nothing about partial
refunds, idempotency, concurrency, provider failure, security or performance:
those requirements do not exist yet at R0 and scoring them early would be
unfair (see the round scoring boundaries in ``instruction.md``).
"""

from __future__ import annotations

from harness import Api, paid_order


def test_project_runs_and_basic_flow(client):
    api = Api(client)
    owner = api.create_user("r0-owner")
    agent = api.create_agent("r0-agent")

    order_id = paid_order(api, owner["id"], 10_000)

    fetched = api.get_order(owner["id"], order_id)
    assert fetched.status_code == 200, fetched.text
    body = fetched.json()
    assert body["payment_status"] == "PAID"
    assert body["paid_amount"] == 10_000

    created = api.create_after_sale(owner["id"], order_id, 10_000)
    assert created.status_code in (200, 201), created.text
    after_sale_id = created.json()["id"]
    assert created.json()["status"] == "PENDING"

    approved = api.approve(agent["id"], after_sale_id)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"

    executed = api.execute(agent["id"], after_sale_id)
    assert executed.status_code == 200, executed.text
    assert executed.json()["after_sale"]["status"] == "REFUNDED"

    after = api.get_after_sale(owner["id"], after_sale_id)
    assert after.status_code == 200, after.text
    assert after.json()["status"] == "REFUNDED"
