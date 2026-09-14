"""Adapted harness for the Hy3 candidate artifact.

This is the ONLY interface-adaptation layer for running the Golden test suite
(``golden_answer/tests/test_*.py``, assertions unchanged) against Hy3's
implementation in ``D:\\Workspace\\trial-workspaces\\hy3``.

Contract differences between the canonical contract (harness.py in
golden_answer) and Hy3, and how this adapter bridges them:

1. Identity: Hy3 has NO ``/users`` registry. Identity is carried by the
   ``X-User-Id`` header (opaque string) and, for review, ``X-User-Role``.
   -> ``create_user`` / ``create_agent`` mint a local numeric id; the tests only
      ever need the id back.
2. Order creation requires ``user_id`` in the BODY and checks it equals the
   ``X-User-Id`` header. -> body carries ``user_id``; header carries the same.
3. ``pay_order`` requires a body. -> send ``{"payment_method": "balance"}``.
4. Refund AMOUNT lives on the EXECUTE call (``POST /after-sales/{id}/refund``,
   optional ``refund_amount``), NOT on after-sale creation (which only takes
   ``reason``). The canonical tests pass the amount at creation time, so this
   adapter remembers it per after-sale id and replays it on execute.
5. Idempotency key (``Idempotency-Key``) is consumed at EXECUTE, not create.
6. Responses are flat (``AfterSale`` directly; ``status`` not ``payment_status``;
   lists are bare arrays, not ``{items,total}``); there is NO refunds-listing
   endpoint. -> a thin ``Resp`` wrapper re-shapes responses so the unchanged
   assertions see the shapes they expect. ``successful_refund_amounts`` is
   reconstructed from ``get_after_sale`` (an after-sale has at most one
   successful refund per FD-05).
7. ``review`` (approve/reject) is NOT ownership-checked in Hy3 — only role-gated
   when ``X-User-Role`` is present. The harness deliberately does NOT inject a
   role header (matching the canonical caller), so this genuine gap is exercised
   by T16/T17 rather than masked.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

# Hy3 authorizes the ORDER OWNER (not an independent agent) to execute a refund.
# The canonical suite executes as the reviewer/agent. When this is "owner" (the
# default), execute() uses the tracked order owner so the suite exercises Hy3's
# actual 2-role model for FUNCTIONAL invariants. Set HY3_EXECUTOR=caller to pass
# the caller through verbatim and verify Hy3's real authz (security tests).
_OWNER_EXECUTOR = os.environ.get("HY3_EXECUTOR", "owner") == "owner"


class Resp:
    """Minimal response wrapper so unchanged assertions read expected shapes."""

    def __init__(self, status_code: int, text: str, body: Any):
        self.status_code = status_code
        self._text = text
        self._body = body

    def json(self):
        return self._body

    @property
    def text(self) -> str:
        return self._text


class Api:
    def __init__(self, client, base_url: str = "", user_header: str = "X-User-Id") -> None:
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.user_header = user_header
        self._uid = 0
        # after_sale_id -> requested refund amount (bridges create->execute split)
        self._amounts: Dict[str, float] = {}
        # after_sale_id -> order owner id (Hy3 authorizes the OWNER to execute)
        self._owners: Dict[str, int] = {}

    # -- helpers ---------------------------------------------------------

    def url(self, path: str) -> str:
        return f"{self.base_url}{path}" if self.base_url else path

    def headers(self, user_id: Optional[int] = None, extra: Optional[Dict[str, str]] = None):
        h: Dict[str, str] = dict(extra or {})
        if user_id is not None:
            h[self.user_header] = str(user_id)
        return h

    def _params(self, limit=None, offset=None):
        p = {}
        if limit is not None:
            p["limit"] = limit
        if offset is not None:
            p["offset"] = offset
        return p

    def _wrap(self, r, order_norm=False, list_norm=False, refund_norm=False):
        try:
            body = r.json()
        except Exception:
            body = {}
        text = getattr(r, "text", "") or ""
        if order_norm and isinstance(body, dict):
            body = dict(body)
            body.setdefault("payment_status", body.get("status"))
            body.setdefault("paid_amount", body.get("amount"))
        if list_norm and isinstance(body, list):
            body = {"items": body, "total": len(body)}
        if refund_norm and isinstance(body, dict):
            # Hy3 returns the AfterSale flat; tests read ["after_sale"]["status"].
            if "after_sale" not in body and "status" in body:
                body = {"after_sale": body}
        return Resp(r.status_code, text, body)

    # -- users (no registry in Hy3) -------------------------------------

    def create_user(self, name: str, role: str = "USER") -> Dict[str, Any]:
        self._uid += 1
        return {"id": self._uid, "name": name, "role": role}

    def create_agent(self, name: str = "agent") -> Dict[str, Any]:
        return self.create_user(name, "AGENT")

    # -- orders ----------------------------------------------------------

    def create_order(self, user_id: int, amount: int):
        return self._wrap(
            self.client.post(
                self.url("/orders"),
                json={"user_id": str(user_id), "amount": float(amount)},
                headers=self.headers(user_id),
            ),
            order_norm=True,
        )

    def pay_order(self, user_id: int, order_id: int):
        return self._wrap(
            self.client.post(
                self.url(f"/orders/{order_id}/pay"),
                json={"payment_method": "balance"},
                headers=self.headers(user_id),
            ),
            order_norm=True,
        )

    def get_order(self, user_id: int, order_id: int):
        return self._wrap(
            self.client.get(
                self.url(f"/orders/{order_id}"), headers=self.headers(user_id)
            ),
            order_norm=True,
        )

    def list_orders(self, user_id: int, limit=None, offset=None):
        return self._wrap(
            self.client.get(
                self.url("/orders"),
                headers=self.headers(user_id),
                params=self._params(limit, offset),
            ),
            list_norm=True,
        )

    # -- after-sales -----------------------------------------------------

    def create_after_sale(
        self,
        user_id: int,
        order_id: int,
        amount: int,
        idempotency_key: Optional[str] = None,
    ):
        extra: Dict[str, str] = {}
        if idempotency_key:
            # Hy3 consumes idempotency at EXECUTE; header kept for completeness.
            extra["Idempotency-Key"] = idempotency_key
        r = self.client.post(
            self.url(f"/orders/{order_id}/after-sales"),
            json={"reason": f"refund request for {amount}"},
            headers=self.headers(user_id, extra),
        )
        wr = self._wrap(r)
        if wr.status_code in (200, 201):
            try:
                aid = wr.json()["id"]
                self._amounts[aid] = float(amount)
                self._owners[aid] = user_id  # order owner, for owner-executor mode
            except Exception:
                pass
        return wr

    def get_after_sale(self, user_id: int, after_sale_id: int):
        return self._wrap(
            self.client.get(
                self.url(f"/after-sales/{after_sale_id}"),
                headers=self.headers(user_id),
            )
        )

    def list_after_sales(self, user_id: int, order_id: int, limit=None, offset=None):
        # Hy3 exposes GET /after-sales (owner-filtered via X-User-Id), NOT a
        # per-order endpoint. Fetch the owner's after-sales and filter by order.
        r = self._wrap(
            self.client.get(
                self.url("/after-sales"),
                headers=self.headers(user_id),
                params=self._params(limit, offset),
            ),
            list_norm=False,
        )
        if r.status_code != 200:
            return r
        items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        items = [a for a in items if a.get("order_id") == order_id]
        return Resp(200, "", {"items": items, "total": len(items)})

    def approve(self, user_id: int, after_sale_id: int):
        # Hy3 review endpoint: gated by X-User-Role when present; this adapter
        # sends only X-User-Id (canonical caller) so the real authz is exercised.
        return self._wrap(
            self.client.post(
                self.url(f"/after-sales/{after_sale_id}/review"),
                json={"approve": True},
                headers=self.headers(user_id),
            )
        )

    def execute(self, user_id: int, after_sale_id: int):
        # Hy3 authorizes the ORDER OWNER to execute a refund (its 2-role model:
        # owner executes, reviewer approves). The canonical suite calls execute as
        # the reviewer/agent. Two evaluation modes:
        #   HY3_EXECUTOR=owner  (default): rebind to the tracked owner so the
        #     FUNCTIONAL invariants are exercised (the canonical "agent" caller is
        #     the authorized executor in Hy3's model).
        #   HY3_EXECUTOR=caller : pass the caller through verbatim, so the SECURITY
        #     tests can verify Hy3's real authz (a foreign/non-owner user must be
        #     denied). Running security tests in this mode exposes FD-08 honestly.
        if _OWNER_EXECUTOR:
            executor = self._owners.get(after_sale_id, user_id)
        else:
            executor = user_id
        amount = self._amounts.get(after_sale_id)
        body = {"refund_amount": amount} if amount is not None else {}
        return self._wrap(
            self.client.post(
                self.url(f"/after-sales/{after_sale_id}/refund"),
                json=body,
                headers=self.headers(executor),
            ),
            refund_norm=True,
        )

    def list_refunds(self, user_id: int, after_sale_id: int, limit=None, offset=None):
        # Hy3 exposes no refunds-listing endpoint; derive from the after-sale.
        r = self.get_after_sale(user_id, after_sale_id)
        if r.status_code != 200:
            return Resp(r.status_code, r.text, {"items": [], "total": 0})
        b = r.json()
        items = []
        if b.get("status") == "REFUNDED" and b.get("refund_amount") is not None:
            items = [{"amount": b["refund_amount"], "status": "REFUNDED"}]
        return Resp(200, "", {"items": items, "total": len(items)})


# --------------------------------------------------------------------------
# Scenario helpers (reimplemented for Hy3's shapes)
# --------------------------------------------------------------------------


def paid_order(api: Api, owner_id: int, amount: int) -> int:
    response = api.create_order(owner_id, amount)
    assert response.status_code in (200, 201), response.text
    order_id = response.json()["id"]
    payment = api.pay_order(owner_id, order_id)
    assert payment.status_code == 200, payment.text
    assert payment.json()["status"] == "PAID", payment.text
    return order_id


def new_after_sale(
    api: Api, owner_id: int, order_id: int, amount: int, idempotency_key=None
) -> int:
    response = api.create_after_sale(owner_id, order_id, amount, idempotency_key)
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def approved_after_sale(
    api: Api, owner_id: int, agent_id: int, order_id: int, amount: int, idempotency_key=None
) -> int:
    after_sale_id = new_after_sale(api, owner_id, order_id, amount, idempotency_key)
    approval = api.approve(agent_id, after_sale_id)
    assert approval.status_code == 200, approval.text
    return after_sale_id


def successful_refund_amounts(api: Api, viewer_id: int, after_sale_id: int) -> List[int]:
    r = api.get_after_sale(viewer_id, after_sale_id)
    if r.status_code != 200:
        return []
    b = r.json()
    if b.get("status") == "REFUNDED" and b.get("refund_amount") is not None:
        return [int(b["refund_amount"])]
    return []


def refunded_amount(api: Api, viewer_id: int, order_id: int) -> int:
    r = api.get_order(viewer_id, order_id)
    assert r.status_code == 200, r.text
    return int(r.json()["refunded_amount"])


def ledger_successful_total(api: Api, viewer_id: int, order_id: int) -> int:
    r = api.list_after_sales(viewer_id, order_id, limit=100)
    assert r.status_code == 200, r.text
    body = r.json()
    items = body["items"] if isinstance(body, dict) else body
    total = 0
    for item in items:
        if item.get("status") == "REFUNDED":
            total += int(item.get("refund_amount") or 0)
    return total


def after_sale_status(api: Api, viewer_id: int, after_sale_id: int) -> str:
    r = api.get_after_sale(viewer_id, after_sale_id)
    assert r.status_code == 200, r.text
    return r.json()["status"]


def pair_of_users(api: Api):
    owner = api.create_user("owner")
    agent = api.create_agent("agent")
    return owner["id"], agent["id"]
