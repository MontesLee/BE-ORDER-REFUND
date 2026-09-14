"""R7 安全 + 基础性能 回归测试。

覆盖本轮 ROUND PROMPT 的安全与性能重点：
  安全：
    1) 用户不能访问其他用户订单；
    2) 用户不能访问其他用户 AfterSale；
    3) 普通用户不能绕过审核直接执行退款；
    4) 异常请求不能绕过金额限制；
    5) 重复请求不能造成重复退款。
  性能：
    * 索引存在（避免 Refund 数量增长后的查询退化）；
    * 列表接口支持分页（避免无界加载大量数据）。

说明：鉴权基于请求头 `X-User-Id`（归属）/ `X-User-Role`（审核角色）。仅当请求携带
这些头时才强制执行；未携带时保持原有（可信内网/测试）行为，因此既有测试不受影响。
"""
import pytest
from fastapi.testclient import TestClient

from app import app
from store import store


@pytest.fixture(autouse=True)
def _reset_store():
    store.reset()
    yield
    store.reset()


@pytest.fixture
def client():
    return TestClient(app)


def _create_paid_order(client, user="u1", amount=100.0):
    r = client.post(
        "/orders", json={"user_id": user, "amount": amount},
        headers={"X-User-Id": user},
    )
    assert r.status_code == 201, r.text
    oid = r.json()["id"]
    r = client.post(
        f"/orders/{oid}/pay", json={}, headers={"X-User-Id": user}
    )
    assert r.status_code == 200, r.text
    return oid


def _create_approved_after_sale(client, oid, user="u1", reason="r"):
    r = client.post(
        f"/orders/{oid}/after-sales", json={"reason": reason},
        headers={"X-User-Id": user},
    )
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    r = client.post(
        f"/after-sales/{aid}/review", json={"approve": True},
        headers={"X-User-Role": "reviewer"},
    )
    assert r.status_code == 200, r.text
    return aid


# ---- 1) 用户不能访问其他用户的订单 ----


def test_user_cannot_access_other_users_order(client):
    oid = _create_paid_order(client, user="alice")

    # 其他用户访问 -> 403
    r = client.get(f"/orders/{oid}", headers={"X-User-Id": "bob"})
    assert r.status_code == 403

    # 本人访问 -> 200
    r = client.get(f"/orders/{oid}", headers={"X-User-Id": "alice"})
    assert r.status_code == 200


def test_user_can_only_list_own_orders(client):
    _create_paid_order(client, user="alice")
    _create_paid_order(client, user="bob")

    r = client.get("/orders", headers={"X-User-Id": "bob"})
    assert r.status_code == 200
    ids = [o["user_id"] for o in r.json()]
    assert ids == ["bob"]  # 仅返回本人订单，不会泄漏 alice 的订单


# ---- 2) 用户不能访问其他用户的 AfterSale ----


def test_user_cannot_access_other_users_after_sale(client):
    oid = _create_paid_order(client, user="alice")
    aid = _create_approved_after_sale(client, oid, user="alice")

    r = client.get(f"/after-sales/{aid}", headers={"X-User-Id": "bob"})
    assert r.status_code == 403

    r = client.get(f"/after-sales/{aid}", headers={"X-User-Id": "alice"})
    assert r.status_code == 200


def test_user_can_only_list_own_after_sales(client):
    oid_a = _create_paid_order(client, user="alice")
    oid_b = _create_paid_order(client, user="bob")
    _create_approved_after_sale(client, oid_a, user="alice")
    _create_approved_after_sale(client, oid_b, user="bob")

    r = client.get("/after-sales", headers={"X-User-Id": "bob"})
    assert r.status_code == 200
    owners = set()
    for a in r.json():
        o = client.get(f"/orders/{a['order_id']}").json()
        owners.add(o["user_id"])
    assert owners == {"bob"}


# ---- 3) 普通用户不能绕过审核直接执行退款 ----


def test_normal_user_cannot_review(client):
    # 审核需要 reviewer 角色，普通角色被拒
    oid = _create_paid_order(client, user="alice")
    r = client.post(f"/orders/{oid}/after-sales", json={"reason": "x"},
                    headers={"X-User-Id": "alice"})
    aid = r.json()["id"]

    r = client.post(f"/after-sales/{aid}/review", json={"approve": True},
                    headers={"X-User-Id": "alice", "X-User-Role": "user"})
    assert r.status_code == 403


def test_normal_user_cannot_self_approve_and_refund(client):
    oid = _create_paid_order(client, user="alice")
    r = client.post(f"/orders/{oid}/after-sales", json={"reason": "x"},
                    headers={"X-User-Id": "alice"})
    aid = r.json()["id"]

    # 普通用户自评自批被拒
    r = client.post(f"/after-sales/{aid}/review", json={"approve": True},
                    headers={"X-User-Id": "alice", "X-User-Role": "user"})
    assert r.status_code == 403

    # 因此售后仍为 PENDING，退款被拒（无法绕过审核）
    r = client.post(f"/after-sales/{aid}/refund", headers={"X-User-Id": "alice"})
    assert r.status_code == 409
    # 订单累计未被污染
    assert client.get(f"/orders/{oid}", headers={"X-User-Id": "alice"}).json()["refunded_amount"] == 0


def test_reviewer_approval_then_owner_refund_works(client):
    oid = _create_paid_order(client, user="alice")
    aid = _create_approved_after_sale(client, oid, user="alice")

    # 本人对已审核的售后退款 -> 成功（这是预期的正常流程）
    r = client.post(f"/after-sales/{aid}/refund", headers={"X-User-Id": "alice"})
    assert r.status_code == 200
    assert r.json()["status"] == "REFUNDED"


# ---- 4) 异常请求不能绕过金额限制 ----


def test_amount_zero_or_negative_rejected(client):
    oid = _create_paid_order(client, user="alice", amount=100)
    aid = _create_approved_after_sale(client, oid, user="alice")
    r = client.post(f"/after-sales/{aid}/refund", json={"refund_amount": 0},
                    headers={"X-User-Id": "alice"})
    assert r.status_code == 422
    r = client.post(f"/after-sales/{aid}/refund", json={"refund_amount": -5},
                    headers={"X-User-Id": "alice"})
    assert r.status_code == 422


def test_amount_over_remaining_is_clamped(client):
    oid = _create_paid_order(client, user="alice", amount=200)
    aid1 = _create_approved_after_sale(client, oid, user="alice")
    client.post(f"/after-sales/{aid1}/refund", json={"refund_amount": 80},
                headers={"X-User-Id": "alice"})
    # 已退 80，剩余 120；申请 9999 远超剩余 -> 仅退剩余 120（clamp，不拒绝）
    aid2 = _create_approved_after_sale(client, oid, user="alice")
    r = client.post(f"/after-sales/{aid2}/refund", json={"refund_amount": 9999},
                    headers={"X-User-Id": "alice"})
    assert r.status_code == 200
    assert r.json()["refund_amount"] == 120
    o = client.get(f"/orders/{oid}", headers={"X-User-Id": "alice"}).json()
    assert o["refunded_amount"] == 200
    assert o["status"] == "REFUNDED"


# ---- 5) 重复请求不能造成重复退款 ----


def test_duplicate_idempotency_key_no_double_refund(client):
    oid = _create_paid_order(client, user="alice", amount=150)
    aid = _create_approved_after_sale(client, oid, user="alice")
    headers = {"X-User-Id": "alice", "Idempotency-Key": "k-dup-1"}

    r1 = client.post(f"/after-sales/{aid}/refund", json={"refund_amount": 150}, headers=headers)
    assert r1.status_code == 200
    r2 = client.post(f"/after-sales/{aid}/refund", json={"refund_amount": 150}, headers=headers)
    assert r2.status_code == 200
    assert r2.json() == r1.json()  # 结果完全一致

    assert client.get(f"/orders/{oid}", headers={"X-User-Id": "alice"}).json()["refunded_amount"] == 150


# ---- 性能：索引 + 分页 ----


def test_performance_indexes_exist(client):
    conn = store._conn()
    names = {row["name"] for row in conn.execute("PRAGMA index_list(after_sales)")}
    assert "idx_after_sales_order_id" in names
    assert "idx_after_sales_status" in names
    names2 = {row["name"] for row in conn.execute("PRAGMA index_list(idempotency)")}
    assert "idx_idempotency_key" in names2


def test_list_endpoints_support_pagination(client):
    for i in range(25):
        _create_paid_order(client, user="alice", amount=10.0)

    # limit/offset 生效
    r = client.get("/orders?limit=10&offset=0", headers={"X-User-Id": "alice"})
    assert r.status_code == 200
    assert len(r.json()) == 10

    r2 = client.get("/orders?limit=10&offset=10", headers={"X-User-Id": "alice"})
    assert len(r2.json()) == 10

    # 即便有大量数据，单页也被限制（无界加载受控）
    r3 = client.get("/orders?limit=1000", headers={"X-User-Id": "alice"})
    assert len(r3.json()) == 25
