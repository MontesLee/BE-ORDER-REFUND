"""Thin adapter over the canonical HTTP contract.

The whole evaluation suite talks to the service through this object only, and
``Api`` accepts either a ``TestClient`` or an ``httpx.Client``.  That is what
makes the suite reusable against a candidate model's implementation: adapting to
a different endpoint spelling or a different identity header means editing this
one file, not eighteen tests.

Canonical contract (see ``test/README.md``)
-------------------------------------------
Identity: ``X-User-Id: <int>``
New after-sale submissions may also carry ``Idempotency-Key`` (or a
``idempotency_key`` body field); the harness sends both so either choice works.

======================  ==================================================
POST /orders            ``{"amount": <cents>}``
POST /orders/{id}/pay   no body
GET  /orders/{id}       returns ``refunded_amount`` and ``payment_status``
POST /orders/{id}/after-sales
                        ``{"refund_amount": <cents>}``
POST /after-sales/{id}/approve
POST /after-sales/{id}/execute
GET  /after-sales/{id}/refunds
                        paged ``{"items": [...], "total": n}``
======================  ==================================================
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

CENTS = 1  # amounts are integer 分


class Api:
    """Adapter over the canonical HTTP contract.

    ``base_url`` is prepended by this class instead of relying on
    ``httpx.Client(base_url=...)``: that merge produced absolute-form request
    lines on some httpx builds, which the server correctly rejected as unknown
    paths.  Building the URL here keeps the suite portable across clients.
    """

    def __init__(self, client, base_url: str = "", user_header: str = "X-User-Id") -> None:
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.user_header = user_header

    # -- helpers ---------------------------------------------------------

    def url(self, path: str) -> str:
        return f"{self.base_url}{path}" if self.base_url else path

    def headers(self, user_id: Optional[int] = None, extra: Optional[Dict[str, str]] = None):
        headers: Dict[str, str] = dict(extra or {})
        if user_id is not None:
            headers[self.user_header] = str(user_id)
        return headers

    def _params(self, limit=None, offset=None):
        params = {}
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        return params

    # -- users -----------------------------------------------------------

    def create_user(self, name: str, role: str = "USER") -> Dict[str, Any]:
        response = self.client.post(
            self.url("/users"), json={"name": name, "role": role}
        )
        assert response.status_code in (200, 201), f"create_user: {response.status_code} {response.text}"
        return response.json()

    def create_agent(self, name: str = "agent") -> Dict[str, Any]:
        return self.create_user(name, "AGENT")

    # -- orders ----------------------------------------------------------

    def create_order(self, user_id: int, amount: int):
        return self.client.post(
            self.url("/orders"), json={"amount": amount}, headers=self.headers(user_id)
        )

    def pay_order(self, user_id: int, order_id: int):
        return self.client.post(
            self.url(f"/orders/{order_id}/pay"), headers=self.headers(user_id)
        )

    def get_order(self, user_id: int, order_id: int):
        return self.client.get(
            self.url(f"/orders/{order_id}"), headers=self.headers(user_id)
        )

    def list_orders(self, user_id: int, limit=None, offset=None):
        return self.client.get(
            self.url("/orders"),
            headers=self.headers(user_id),
            params=self._params(limit, offset),
        )

    # -- after-sales -----------------------------------------------------

    def create_after_sale(
        self,
        user_id: int,
        order_id: int,
        amount: int,
        idempotency_key: Optional[str] = None,
    ):
        body: Dict[str, Any] = {"refund_amount": amount}
        extra: Dict[str, str] = {}
        if idempotency_key:
            # Send it both ways so the suite accepts either design choice.
            body["idempotency_key"] = idempotency_key
            extra["Idempotency-Key"] = idempotency_key
        return self.client.post(
            self.url(f"/orders/{order_id}/after-sales"),
            json=body,
            headers=self.headers(user_id, extra),
        )

    def get_after_sale(self, user_id: int, after_sale_id: int):
        return self.client.get(
            self.url(f"/after-sales/{after_sale_id}"), headers=self.headers(user_id)
        )

    def list_after_sales(self, user_id: int, order_id: int, limit=None, offset=None):
        return self.client.get(
            self.url(f"/orders/{order_id}/after-sales"),
            headers=self.headers(user_id),
            params=self._params(limit, offset),
        )

    def approve(self, user_id: int, after_sale_id: int):
        return self.client.post(
            self.url(f"/after-sales/{after_sale_id}/approve"),
            headers=self.headers(user_id),
        )

    def execute(self, user_id: int, after_sale_id: int):
        return self.client.post(
            self.url(f"/after-sales/{after_sale_id}/execute"),
            headers=self.headers(user_id),
        )

    def list_refunds(self, user_id: int, after_sale_id: int, limit=None, offset=None):
        return self.client.get(
            self.url(f"/after-sales/{after_sale_id}/refunds"),
            headers=self.headers(user_id),
            params=self._params(limit, offset),
        )


# --------------------------------------------------------------------------
# Scenario helpers
# --------------------------------------------------------------------------


def paid_order(api: Api, owner_id: int, amount: int) -> int:
    response = api.create_order(owner_id, amount)
    assert response.status_code in (200, 201), f"create_order: {response.text}"
    order_id = response.json()["id"]
    payment = api.pay_order(owner_id, order_id)
    assert payment.status_code == 200, f"pay_order: {payment.status_code} {payment.text}"
    assert payment.json()["payment_status"] == "PAID", payment.text
    return order_id


def new_after_sale(
    api: Api, owner_id: int, order_id: int, amount: int, idempotency_key=None
) -> int:
    response = api.create_after_sale(owner_id, order_id, amount, idempotency_key)
    assert response.status_code in (200, 201), f"create_after_sale: {response.text}"
    return response.json()["id"]


def approved_after_sale(
    api: Api, owner_id: int, agent_id: int, order_id: int, amount: int, idempotency_key=None
) -> int:
    after_sale_id = new_after_sale(api, owner_id, order_id, amount, idempotency_key)
    approval = api.approve(agent_id, after_sale_id)
    assert approval.status_code == 200, f"approve: {approval.status_code} {approval.text}"
    return after_sale_id


def successful_refund_amounts(api: Api, viewer_id: int, after_sale_id: int) -> List[int]:
    response = api.list_refunds(viewer_id, after_sale_id, limit=100)
    assert response.status_code == 200, f"list_refunds: {response.status_code} {response.text}"
    return [
        int(item["amount"])
        for item in response.json()["items"]
        if item["status"] == "REFUNDED"
    ]


def refunded_amount(api: Api, viewer_id: int, order_id: int) -> int:
    response = api.get_order(viewer_id, order_id)
    assert response.status_code == 200, f"get_order: {response.status_code} {response.text}"
    return int(response.json()["refunded_amount"])


def ledger_successful_total(api: Api, viewer_id: int, order_id: int) -> int:
    """Sum of successful refunds, read from the public API only.

    Independent of ``orders.refunded_amount`` so a mismatch between the counter
    and the ledger is observable.
    """
    response = api.list_after_sales(viewer_id, order_id, limit=100)
    assert response.status_code == 200, response.text
    total = 0
    for item in response.json()["items"]:
        total += sum(successful_refund_amounts(api, viewer_id, int(item["id"])))
    return total


def after_sale_status(api: Api, viewer_id: int, after_sale_id: int) -> str:
    response = api.get_after_sale(viewer_id, after_sale_id)
    assert response.status_code == 200, response.text
    return response.json()["status"]


def pair_of_users(api: Api):
    owner = api.create_user("owner")
    agent = api.create_agent("agent")
    return owner["id"], agent["id"]
