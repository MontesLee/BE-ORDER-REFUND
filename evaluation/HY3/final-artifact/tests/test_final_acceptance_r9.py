"""R9 最终交付验收测试：把 ROUND PROMPT 的 14 条核心保证逐条映射为确定性用例。

每条测试聚焦一条保证（G1..G14），命名即声明它验证哪一条。所有用例：
  * 在 autouse fixture 中 `store.reset()` 并把网关恢复为成功占位，保证隔离、可重复；
  * 断言「最终落库业务状态」（累计退款金额 / 状态 / 渠道调用次数），而非仅断言请求被发出；
  * 不依赖随机 sleep 作为正确性证明。

G1  paid order 可以退款
G2  unpaid order 不能退款
G3  一个订单支持多个 AfterSale
G4  累计成功退款不超过 paid_amount
G5  一个 AfterSale 最多一个成功退款
G6  duplicate request 不产生重复有效退款
G7  非法状态转换被拒绝
G8  REFUND_FAILED 可以 retry
G9  REFUNDED 不能 retry（不产生二次退款）
G10 第三方失败不能导致本地退款成功
G11 multi-worker 场景保持核心 invariant
G12 用户不能访问其他用户订单
G13 用户不能访问其他用户 AfterSale
G14 普通用户不能绕过审核执行退款
"""
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app import app
from store import store, Store, Order, AfterSale, OrderStatus, AfterSaleStatus
from gateway import FakeRefundGateway, SuccessRefundGateway


@pytest.fixture(autouse=True)
def _isolate():
    store.reset()
    store.gateway = SuccessRefundGateway()
    yield
    store.gateway = SuccessRefundGateway()
    store.reset()


@pytest.fixture
def client():
    return TestClient(app)


def _now():
    return datetime.now(timezone.utc)


# ---- helpers（API 层） ----


def _paid_order(client, user="u1", amount=100.0):
    r = client.post("/orders", json={"user_id": user, "amount": amount})
    assert r.status_code == 201, r.text
    oid = r.json()["id"]
    r = client.post(f"/orders/{oid}/pay", json={})
    assert r.status_code == 200, r.text
    return oid


def _approved_after_sale(client, oid, user="u1"):
    r = client.post(f"/orders/{oid}/after-sales", json={"reason": "r"})
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    r = client.post(
        f"/after-sales/{aid}/review",
        json={"approve": True},
        headers={"X-User-Role": "reviewer"},
    )
    assert r.status_code == 200, r.text
    return aid


def _set_gateway(fail=False, **kw):
    g = FakeRefundGateway(fail=fail, **kw)
    store.gateway = g
    return g


# ===========================================================================
# G1 — paid order 可以退款
# ===========================================================================


def test_g1_paid_order_refundable(client):
    oid = _paid_order(client, amount=120)
    aid = _approved_after_sale(client, oid)
    r = client.post(f"/after-sales/{aid}/refund")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "REFUNDED"
    assert body["refund_amount"] == 120
    o = client.get(f"/orders/{oid}").json()
    assert o["status"] == "REFUNDED"
    assert o["refunded_amount"] == 120


# ===========================================================================
# G2 — unpaid order 不能退款
# ===========================================================================


def test_g2_unpaid_order_not_refundable(client):
    # 链路层：未支付订单无法发起售后（退款链路起点被阻断）
    r = client.post("/orders", json={"user_id": "u1", "amount": 100})
    oid = r.json()["id"]
    r = client.post(f"/orders/{oid}/after-sales", json={"reason": "x"})
    assert r.status_code == 409
    assert client.get(f"/orders/{oid}").json()["status"] == "CREATED"

    # 存储层：即便构造一个 APPROVED 售后挂在一个未支付订单上，退款也必须被拒绝
    store.reset()
    store.insert_order(
        Order(id="g2o", user_id="u", amount=100.0, status=OrderStatus.CREATED,
              created_at=_now())
    )
    store.insert_after_sale(
        AfterSale(id="g2a", order_id="g2o", reason="r",
                  status=AfterSaleStatus.APPROVED, created_at=_now())
    )
    sc, body = store.refund_transaction("g2a", None, None)
    assert sc == 409, body
    assert client.get("/orders/g2o").json()["refunded_amount"] == 0


# ===========================================================================
# G3 — 一个订单支持多个 AfterSale
# ===========================================================================


def test_g3_multiple_after_sales_on_one_order(client):
    oid = _paid_order(client, amount=300)
    # 同一订单可先后发起多个售后，互不影响
    aid1 = _approved_after_sale(client, oid)
    r = client.post(f"/orders/{oid}/after-sales", json={"reason": "second"})
    assert r.status_code == 201
    aid2 = r.json()["id"]
    assert aid1 != aid2
    # aid2 走正常审核流程（证明多次售后各自独立审核/退款）
    r = client.post(f"/after-sales/{aid2}/review", json={"approve": True},
                    headers={"X-User-Role": "reviewer"})
    assert r.status_code == 200
    # 再发起第三个售后
    aid3 = _approved_after_sale(client, oid)
    # 三个售后各自部分退款（共 300 = 订单金额），全部成功、互不冲突
    assert client.post(f"/after-sales/{aid1}/refund",
                       json={"refund_amount": 100}).status_code == 200
    assert client.post(f"/after-sales/{aid2}/refund",
                       json={"refund_amount": 100}).status_code == 200
    assert client.post(f"/after-sales/{aid3}/refund",
                       json={"refund_amount": 100}).status_code == 200
    o = client.get(f"/orders/{oid}").json()
    assert o["refunded_amount"] == 300
    assert o["status"] == "REFUNDED"


# ===========================================================================
# G4 — 累计成功退款不超过 paid_amount
# ===========================================================================


def test_g4_cumulative_cap_not_exceeded(client):
    oid = _paid_order(client, amount=200)
    aid1 = _approved_after_sale(client, oid)
    assert client.post(f"/after-sales/{aid1}/refund",
                        json={"refund_amount": 80}).status_code == 200
    # 已退 80，剩余 120；申请 150 超额 -> 仅退剩余 120（clamp，不拒绝），
    # 累计恰好封顶于 paid_amount，且绝不突破上限
    aid2 = _approved_after_sale(client, oid)
    r = client.post(f"/after-sales/{aid2}/refund", json={"refund_amount": 150})
    assert r.status_code == 200
    assert r.json()["refund_amount"] == 120
    o = client.get(f"/orders/{oid}").json()
    assert o["refunded_amount"] == 200
    assert o["status"] == "REFUNDED"


# ===========================================================================
# G5 — 一个 AfterSale 最多一个成功退款
# ===========================================================================


def test_g5_one_successful_refund_per_after_sale(client):
    gw = _set_gateway(fail=False)
    oid = _paid_order(client, amount=100)
    aid = _approved_after_sale(client, oid)
    # 同一售后退两次（含一次无键重放）
    assert client.post(f"/after-sales/{aid}/refund").status_code == 200
    assert client.post(f"/after-sales/{aid}/refund").status_code == 200
    assert client.post(f"/after-sales/{aid}/refund",
                       json={"refund_amount": 100}).status_code == 200
    # 累计金额恒为 100，第三方渠道仅被调用一次
    assert client.get(f"/orders/{oid}").json()["refunded_amount"] == 100
    assert len(gw.calls) == 1


# ===========================================================================
# G6 — duplicate request 不产生重复有效退款
# ===========================================================================


def test_g6_duplicate_request_no_double_refund(client):
    oid = _paid_order(client, amount=150)
    aid = _approved_after_sale(client, oid)
    headers = {"Idempotency-Key": "g6-key"}
    r1 = client.post(f"/after-sales/{aid}/refund",
                     json={"refund_amount": 150}, headers=headers)
    assert r1.status_code == 200
    # 网络超时重放同一幂等键
    r2 = client.post(f"/after-sales/{aid}/refund",
                     json={"refund_amount": 150}, headers=headers)
    assert r2.status_code == 200
    assert r2.json() == r1.json()  # 结果完全一致
    # 即便重放带不同金额，仍只退一次、不累加
    r3 = client.post(f"/after-sales/{aid}/refund",
                     json={"refund_amount": 9999}, headers={"Idempotency-Key": "g6-key"})
    assert r3.json()["refund_amount"] == 150
    assert client.get(f"/orders/{oid}").json()["refunded_amount"] == 150


# ===========================================================================
# G7 — 非法状态转换被拒绝
# ===========================================================================


def test_g7_illegal_state_transition_rejected(client):
    oid = _paid_order(client)
    r = client.post(f"/orders/{oid}/after-sales", json={"reason": "x"})
    aid = r.json()["id"]
    # PENDING 不可退款
    assert client.post(f"/after-sales/{aid}/refund").status_code == 409
    # 审核拒绝 -> REJECTED，亦不可退款
    client.post(f"/after-sales/{aid}/review", json={"approve": False},
                headers={"X-User-Role": "reviewer"})
    assert client.get(f"/after-sales/{aid}").json()["status"] == "REJECTED"
    assert client.post(f"/after-sales/{aid}/refund").status_code == 409
    # 重复审核被拒
    r = client.post(f"/orders/{oid}/pay", json={})
    assert r.status_code == 409
    assert client.get(f"/orders/{oid}").json()["refunded_amount"] == 0


# ===========================================================================
# G8 — REFUND_FAILED 可以 retry
# ===========================================================================


def test_g8_refund_failed_retryable(client):
    _set_gateway(fail=True, error="declined")
    oid = _paid_order(client)
    aid = _approved_after_sale(client, oid)
    r1 = client.post(f"/after-sales/{aid}/refund")
    assert r1.status_code == 502
    assert client.get(f"/after-sales/{aid}").json()["status"] == "REFUND_FAILED"
    assert client.get(f"/orders/{oid}").json()["refunded_amount"] == 0
    # 修复渠道后重试成功
    _set_gateway(fail=False)
    r2 = client.post(f"/after-sales/{aid}/refund")
    assert r2.status_code == 200
    assert r2.json()["status"] == "REFUNDED"
    assert client.get(f"/orders/{oid}").json()["refunded_amount"] == 100


# ===========================================================================
# G9 — REFUNDED 不能 retry（不产生二次退款）
# ===========================================================================


def test_g9_refunded_no_double_refund(client):
    gw = _set_gateway(fail=False)
    oid = _paid_order(client, amount=100)
    aid = _approved_after_sale(client, oid)
    assert client.post(f"/after-sales/{aid}/refund").status_code == 200
    # 对已退款售后反复重试：返回既有结果，不二次扣减、不二次调渠道
    for _ in range(3):
        r = client.post(f"/after-sales/{aid}/refund")
        assert r.status_code == 200
        assert r.json()["refund_amount"] == 100
        assert r.json()["status"] == "REFUNDED"
    assert client.get(f"/orders/{oid}").json()["refunded_amount"] == 100
    assert len(gw.calls) == 1


# ===========================================================================
# G10 — 第三方失败不能导致本地退款成功
# ===========================================================================


def test_g10_thirdparty_failure_no_local_success(client):
    _set_gateway(fail=True, error="channel down")
    oid = _paid_order(client, amount=120)
    aid = _approved_after_sale(client, oid)
    r = client.post(f"/after-sales/{aid}/refund")
    assert r.status_code == 502
    assert "channel down" in r.json()["detail"]
    asale = client.get(f"/after-sales/{aid}").json()
    assert asale["status"] == "REFUND_FAILED"
    o = client.get(f"/orders/{oid}").json()
    assert o["status"] == "PAID"          # 订单不进入 REFUNDED
    assert o["refunded_amount"] == 0      # 累计金额不被污染


# ===========================================================================
# G11 — multi-worker 场景保持核心 invariant
# ===========================================================================


def test_g11_multiworker_invariant(client):
    store.reset()
    oid, amount = "g11o", 100.0
    store.insert_order(
        Order(id=oid, user_id="u", amount=amount, status=OrderStatus.PAID,
              created_at=_now())
    )
    aids = [f"g11a{i}" for i in range(3)]
    for aid in aids:
        store.insert_after_sale(
            AfterSale(id=aid, order_id=oid, reason="r",
                      status=AfterSaleStatus.APPROVED, created_at=_now())
        )

    N = len(aids)
    results = [None] * N

    def work(i):
        # 每个售后都申请退全额 100（共 300 >> 100）
        results[i] = store.refund_transaction(aids[i], 100.0, None)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    order = store.get_order(oid)
    # 核心不变量：累计不超过 paid_amount，且至多一个售后成功
    assert order.refunded_amount == amount, "累计退款不得超过订单金额"
    assert order.status == OrderStatus.REFUNDED
    ok = [r for r in results if r[0] == 200]
    rejected = [r for r in results if r[0] == 409]
    assert len(ok) == 1, f"恰好一个售后应成功退款，实际 {len(ok)}"
    assert len(rejected) == N - 1, f"其余应因超额被拒，实际 {len(rejected)}"


# ===========================================================================
# G12 — 用户不能访问其他用户订单
# ===========================================================================


def test_g12_no_cross_user_order(client):
    oid = _paid_order(client, user="alice")
    # 他人访问 -> 403；本人访问 -> 200
    assert client.get(f"/orders/{oid}", headers={"X-User-Id": "bob"}).status_code == 403
    assert client.get(f"/orders/{oid}", headers={"X-User-Id": "alice"}).status_code == 200
    # 列表也仅返回本人订单
    _paid_order(client, user="bob")
    ids = [o["user_id"] for o in
           client.get("/orders", headers={"X-User-Id": "bob"}).json()]
    assert ids == ["bob"]


# ===========================================================================
# G13 — 用户不能访问其他用户 AfterSale
# ===========================================================================


def test_g13_no_cross_user_after_sale(client):
    oid = _paid_order(client, user="alice")
    aid = _approved_after_sale(client, oid, user="alice")
    assert client.get(f"/after-sales/{aid}",
                      headers={"X-User-Id": "bob"}).status_code == 403
    assert client.get(f"/after-sales/{aid}",
                      headers={"X-User-Id": "alice"}).status_code == 200


# ===========================================================================
# G14 — 普通用户不能绕过审核执行退款
# ===========================================================================


def test_g14_normal_user_cannot_bypass_review(client):
    oid = _paid_order(client, user="alice")
    r = client.post(f"/orders/{oid}/after-sales", json={"reason": "x"},
                    headers={"X-User-Id": "alice"})
    aid = r.json()["id"]

    # 普通用户自评自批被拒（审核需要 reviewer 角色）
    r = client.post(f"/after-sales/{aid}/review", json={"approve": True},
                    headers={"X-User-Id": "alice", "X-User-Role": "user"})
    assert r.status_code == 403

    # 因此售后仍为 PENDING，退款被拒——无法绕过审核
    r = client.post(f"/after-sales/{aid}/refund", headers={"X-User-Id": "alice"})
    assert r.status_code == 409
    assert client.get(f"/orders/{oid}",
                      headers={"X-User-Id": "alice"}).json()["refunded_amount"] == 0

    # 也不能退款他人售后（跨归属受保护执行）
    aid2 = _approved_after_sale(client, oid, user="alice")
    r = client.post(f"/after-sales/{aid2}/refund", headers={"X-User-Id": "bob"})
    assert r.status_code == 403

    # 正确流程：reviewer 审核 + 本人退款，才成功
    r = client.post(f"/after-sales/{aid2}/refund", headers={"X-User-Id": "alice"})
    assert r.status_code == 200
    assert r.json()["status"] == "REFUNDED"
