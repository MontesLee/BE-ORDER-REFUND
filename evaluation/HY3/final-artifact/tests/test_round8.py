"""R8 完整自动化回归测试（按 ROUND PROMPT 类别逐一确定性覆盖）。

覆盖维度（每类均有独立、确定性用例，不依赖随机 sleep 作为正确性证明）：

  Business:
    * normal refund                —— 正常全额退款
    * unpaid refund                —— 未支付订单不可走退款链路
    * invalid amount               —— 金额非法（<=0 / 超额）
    * multiple partial refunds     —— 多次部分退款累计闭单
    * over-refund                  —— 单次/累计超额被拦截且不污染累计金额

  State:
    * not approved cannot refund   —— PENDING 不可退款
    * REFUND_FAILED can retry      —— 渠道失败后可重试成功
    * REFUNDED cannot retry        —— 已退款重放不二次扣减
    * illegal transition           —— REJECTED 等非法状态不可退款

  Idempotency:
    * duplicate submit             —— 同 Idempotency-Key 重放只退一次
    * duplicate execute            —— 同售后重复执行（无键）只退一次且渠道仅调用一次

  Concurrency:
    * same AfterSale concurrent    —— HTTP 层并发退款同一售后，至多一次成功
    * multiple AfterSale concurrent over-refund —— HTTP 层并发多售后抢退，累计不超额

  Third-party:
    * failure                      —— 渠道失败不进入 REFUNDED、累计金额不变
    * retry                        —— 失败后换成功渠道重试成功
    * execute after success        —— 成功后重放不再调用渠道（只退一次）

  Security:
    * unauthorized order           —— 不能访问他人订单
    * unauthorized AfterSale       —— 不能访问他人售后
    * normal user protected execution —— 普通用户不能审核/不能退款他人资源

所有并发用例均断言「最终落库业务状态」（累计退款金额 / 状态 / 渠道调用次数），
而非仅仅断言「请求被同时发出」，从而保证稳定、可重复。
"""
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app import app
from store import store, OrderStatus, AfterSaleStatus
from gateway import FakeRefundGateway, SuccessRefundGateway


# ---------------------------------------------------------------------------
# Fixtures：每个用例前清空数据并把网关恢复为成功占位，保证隔离、可重复。
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _set_failing_gateway():
    g = FakeRefundGateway(fail=True, error="channel declined")
    store.gateway = g
    return g


def _set_success_gateway():
    g = FakeRefundGateway(fail=False)
    store.gateway = g
    return g


# ===========================================================================
# Business
# ===========================================================================


def test_business_normal_refund(client):
    """正常全额退款：售后审核通过后执行退款，订单随之 REFUNDED。"""
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


def test_business_unpaid_refund_rejected(client):
    """未支付（CREATED）订单不可走退款链路：创建售后即被拦截（409）。"""
    r = client.post("/orders", json={"user_id": "u1", "amount": 100})
    assert r.status_code == 201
    oid = r.json()["id"]

    # 未支付订单不能发起售后（退款链路起点被阻断）
    r = client.post(f"/orders/{oid}/after-sales", json={"reason": "want refund"})
    assert r.status_code == 409
    assert "paid" in r.json()["detail"].lower()

    # 订单仍 CREATED，无任何退款发生
    o = client.get(f"/orders/{oid}").json()
    assert o["status"] == "CREATED"
    assert o["refunded_amount"] == 0


def test_business_invalid_amount_zero_and_negative(client):
    """非法金额：0 或负数被 schema 拒绝（422），不会进入退款逻辑。"""
    oid = _paid_order(client)
    aid = _approved_after_sale(client, oid)
    assert (
        client.post(f"/after-sales/{aid}/refund", json={"refund_amount": 0}).status_code
        == 422
    )
    assert (
        client.post(f"/after-sales/{aid}/refund", json={"refund_amount": -5}).status_code
        == 422
    )
    # 累计金额未被污染
    assert client.get(f"/orders/{oid}").json()["refunded_amount"] == 0


def test_business_invalid_amount_over_remaining(client):
    """非法金额：单次退款超过剩余可退金额，按剩余金额退款（clamp）且累计不突破实付。"""
    oid = _paid_order(client, amount=200)
    aid1 = _approved_after_sale(client, oid)
    client.post(f"/after-sales/{aid1}/refund", json={"refund_amount": 80})
    aid2 = _approved_after_sale(client, oid)
    r = client.post(f"/after-sales/{aid2}/refund", json={"refund_amount": 150})
    assert r.status_code == 200
    assert r.json()["refund_amount"] == 120  # 仅退剩余，不超申请
    # 累计封顶于实付，订单闭单
    o = client.get(f"/orders/{oid}").json()
    assert o["refunded_amount"] == 200
    assert o["status"] == "REFUNDED"


def test_business_multiple_partial_refunds(client):
    """多次部分退款累计恰好达到订单金额后闭单（REFUNDED）。"""
    oid = _paid_order(client, amount=300)
    aid1 = _approved_after_sale(client, oid)
    r = client.post(f"/after-sales/{aid1}/refund", json={"refund_amount": 100})
    assert r.status_code == 200 and r.json()["refund_amount"] == 100

    aid2 = _approved_after_sale(client, oid)
    r = client.post(f"/after-sales/{aid2}/refund", json={"refund_amount": 100})
    assert r.status_code == 200 and r.json()["refund_amount"] == 100

    aid3 = _approved_after_sale(client, oid)
    r = client.post(f"/after-sales/{aid3}/refund", json={"refund_amount": 100})
    assert r.status_code == 200 and r.json()["refund_amount"] == 100

    o = client.get(f"/orders/{oid}").json()
    assert o["refunded_amount"] == 300
    assert o["status"] == "REFUNDED"


def test_business_over_refund_blocked(client):
    """超额退款（单次申请超过订单实付）按订单实付金额退款（clamp），累计封顶不突破。"""
    oid = _paid_order(client, amount=100)
    aid = _approved_after_sale(client, oid)
    r = client.post(f"/after-sales/{aid}/refund", json={"refund_amount": 200})
    assert r.status_code == 200
    assert r.json()["refund_amount"] == 100  # 仅退订单实付，不超申请
    o = client.get(f"/orders/{oid}").json()
    assert o["refunded_amount"] == 100
    assert o["status"] == "REFUNDED"


# ===========================================================================
# State
# ===========================================================================


def test_state_not_approved_cannot_refund(client):
    """状态机：PENDING（未审核）的售后不可退款（409）。"""
    oid = _paid_order(client)
    r = client.post(f"/orders/{oid}/after-sales", json={"reason": "x"})
    aid = r.json()["id"]
    assert client.get(f"/after-sales/{aid}").json()["status"] == "PENDING"

    r = client.post(f"/after-sales/{aid}/refund")
    assert r.status_code == 409
    assert "status" in r.json()["detail"].lower()

    # 订单累计金额未被污染
    assert client.get(f"/orders/{oid}").json()["refunded_amount"] == 0


def test_state_refund_failed_can_retry(client):
    """状态机：REFUND_FAILED 可重试，换成功渠道后进入 REFUNDED。"""
    _set_failing_gateway()
    oid = _paid_order(client)
    aid = _approved_after_sale(client, oid)

    r1 = client.post(f"/after-sales/{aid}/refund")
    assert r1.status_code == 502
    assert client.get(f"/after-sales/{aid}").json()["status"] == "REFUND_FAILED"
    # 订单保持 PAID，累计不变
    o = client.get(f"/orders/{oid}").json()
    assert o["status"] == "PAID"
    assert o["refunded_amount"] == 0

    # 修复渠道后重试
    _set_success_gateway()
    r2 = client.post(f"/after-sales/{aid}/refund")
    assert r2.status_code == 200
    assert r2.json()["status"] == "REFUNDED"
    o = client.get(f"/orders/{oid}").json()
    assert o["status"] == "REFUNDED"
    assert o["refunded_amount"] == 100


def test_state_refunded_cannot_retry(client):
    """状态机：已 REFUNDED 的售后重放不二次扣减（资源级幂等）。"""
    oid = _paid_order(client, amount=100)
    aid = _approved_after_sale(client, oid)

    r1 = client.post(f"/after-sales/{aid}/refund")
    assert r1.status_code == 200
    assert r1.json()["status"] == "REFUNDED"

    # 已退款后再执行退款：返回既有结果，金额不变
    r2 = client.post(f"/after-sales/{aid}/refund")
    assert r2.status_code == 200
    assert r2.json()["refund_amount"] == 100
    assert r2.json()["status"] == "REFUNDED"

    # 累计金额仍为 100，未被翻倍
    o = client.get(f"/orders/{oid}").json()
    assert o["refunded_amount"] == 100
    assert o["status"] == "REFUNDED"


def test_state_illegal_transition(client):
    """非法状态流转：REJECTED 售后不可退款（409），不污染累计。"""
    oid = _paid_order(client)
    r = client.post(f"/orders/{oid}/after-sales", json={"reason": "x"})
    aid = r.json()["id"]

    # 审核拒绝 -> REJECTED
    r = client.post(f"/after-sales/{aid}/review", json={"approve": False})
    assert r.status_code == 200
    assert client.get(f"/after-sales/{aid}").json()["status"] == "REJECTED"

    # REJECTED 不可退款（非法流转）
    r = client.post(f"/after-sales/{aid}/refund")
    assert r.status_code == 409
    assert client.get(f"/orders/{oid}").json()["refunded_amount"] == 0


# ===========================================================================
# Idempotency
# ===========================================================================


def test_idempotency_duplicate_submit(client):
    """幂等：同一 Idempotency-Key 重放（网络超时场景）只退一次，结果完全一致。"""
    oid = _paid_order(client, amount=150)
    aid = _approved_after_sale(client, oid)
    headers = {"Idempotency-Key": "dup-submit-key"}

    r1 = client.post(
        f"/after-sales/{aid}/refund", json={"refund_amount": 150}, headers=headers
    )
    assert r1.status_code == 200
    r2 = client.post(
        f"/after-sales/{aid}/refund", json={"refund_amount": 150}, headers=headers
    )
    assert r2.status_code == 200
    assert r2.json() == r1.json()  # 结果完全一致

    assert client.get(f"/orders/{oid}").json()["refunded_amount"] == 150  # 仅退一次


def test_idempotency_duplicate_execute(client):
    """幂等：无幂等键重复执行同一售后，只退一次，且第三方渠道仅被调用一次。"""
    gw = _set_success_gateway()
    oid = _paid_order(client, amount=100)
    aid = _approved_after_sale(client, oid)

    r1 = client.post(f"/after-sales/{aid}/refund")
    assert r1.status_code == 200
    r2 = client.post(f"/after-sales/{aid}/refund")
    assert r2.status_code == 200

    # 累计金额未翻倍
    assert client.get(f"/orders/{oid}").json()["refunded_amount"] == 100
    # 渠道仅被调用一次（重复执行未二次打渠道）
    assert len(gw.calls) == 1


# ===========================================================================
# Concurrency（HTTP 层真实并发；断言最终业务结果）
# ===========================================================================


def test_concurrency_same_after_sale_http(client):
    """并发退款同一个 AfterSale：至多一个成功，累计金额不被翻倍。"""
    oid = _paid_order(client, amount=100)
    aid = _approved_after_sale(client, oid)

    def fire(_):
        return client.post(f"/after-sales/{aid}/refund")

    with ThreadPoolExecutor(max_workers=12) as ex:
        responses = list(ex.map(fire, range(12)))

    order = store.get_order(oid)
    assert order.refunded_amount == 100.0, "并发：同一售后不应被重复退款"
    assert order.status == OrderStatus.REFUNDED
    asale = store.get_after_sale(aid)
    assert asale.status == AfterSaleStatus.REFUNDED
    # 每个线程都拿到成功结果（赢家写入 / 输家复用既有结果），金额恒为 100
    for r in responses:
        assert r.status_code == 200
        assert r.json()["refund_amount"] == 100.0


def test_concurrency_multiple_after_sales_over_refund_http(client):
    """并发退款同一 Order 下的多个 AfterSale（各想退全额，总额远超订单）：
    恰好一个成功，其余因额度不足被拒，累计不超额。"""
    oid = _paid_order(client, amount=100)
    aids = [_approved_after_sale(client, oid) for _ in range(5)]

    def fire(aid):
        return client.post(f"/after-sales/{aid}/refund", json={"refund_amount": 100})

    with ThreadPoolExecutor(max_workers=5) as ex:
        responses = list(ex.map(fire, aids))

    order = store.get_order(oid)
    assert order.refunded_amount == 100.0, "并发：累计退款不得超过订单金额"
    assert order.status == OrderStatus.REFUNDED

    statuses = [r.status_code for r in responses]
    assert statuses.count(200) == 1, f"恰好一个售后应成功退款，实际 {statuses.count(200)}"
    assert statuses.count(409) == 4, f"其余应因超额被拒，实际 {statuses.count(409)}"


# ===========================================================================
# Third-party gateway
# ===========================================================================


def test_thirdparty_failure(client):
    """第三方失败：本地绝不进入 REFUNDED，订单累计金额不变。"""
    _set_failing_gateway()
    oid = _paid_order(client, amount=120)
    aid = _approved_after_sale(client, oid)

    r = client.post(f"/after-sales/{aid}/refund")
    assert r.status_code == 502
    assert "channel declined" in r.json()["detail"]

    asale = client.get(f"/after-sales/{aid}").json()
    assert asale["status"] == "REFUND_FAILED"
    o = client.get(f"/orders/{oid}").json()
    assert o["status"] == "PAID"
    assert o["refunded_amount"] == 0


def test_thirdparty_retry(client):
    """第三方失败 -> 重试：换成功渠道后进入 REFUNDED，累计金额正确。"""
    _set_failing_gateway()
    oid = _paid_order(client, amount=100)
    aid = _approved_after_sale(client, oid)

    r1 = client.post(f"/after-sales/{aid}/refund")
    assert r1.status_code == 502

    _set_success_gateway()
    r2 = client.post(f"/after-sales/{aid}/refund")
    assert r2.status_code == 200
    assert r2.json()["status"] == "REFUNDED"
    assert client.get(f"/orders/{oid}").json()["refunded_amount"] == 100


def test_thirdparty_execute_after_success(client):
    """第三方渠道：成功后重放不再调用渠道（只退一次）。"""
    gw = _set_success_gateway()
    oid = _paid_order(client, amount=100)
    aid = _approved_after_sale(client, oid)

    r1 = client.post(f"/after-sales/{aid}/refund")
    assert r1.status_code == 200
    r2 = client.post(f"/after-sales/{aid}/refund")
    assert r2.status_code == 200
    assert r2.json()["refund_amount"] == 100

    # 渠道仅被调用一次（成功后重放未二次打渠道）
    assert len(gw.calls) == 1
    assert client.get(f"/orders/{oid}").json()["refunded_amount"] == 100


# ===========================================================================
# Security
# ===========================================================================


def test_security_unauthorized_order(client):
    """用户不能访问其他用户的订单（IDOR）。"""
    oid = _paid_order(client, user="alice")

    r = client.get(f"/orders/{oid}", headers={"X-User-Id": "bob"})
    assert r.status_code == 403

    r = client.get(f"/orders/{oid}", headers={"X-User-Id": "alice"})
    assert r.status_code == 200


def test_security_unauthorized_after_sale(client):
    """用户不能访问其他用户的售后（IDOR）。"""
    oid = _paid_order(client, user="alice")
    aid = _approved_after_sale(client, oid, user="alice")

    r = client.get(f"/after-sales/{aid}", headers={"X-User-Id": "bob"})
    assert r.status_code == 403

    r = client.get(f"/after-sales/{aid}", headers={"X-User-Id": "alice"})
    assert r.status_code == 200


def test_security_normal_user_protected_execution(client):
    """普通用户受保护执行约束：不能审核（403），从而无法绕过审核自批自退。"""
    oid = _paid_order(client, user="alice")
    r = client.post(
        f"/orders/{oid}/after-sales",
        json={"reason": "x"},
        headers={"X-User-Id": "alice"},
    )
    aid = r.json()["id"]

    # 普通角色（user）审核被拒
    r = client.post(
        f"/after-sales/{aid}/review",
        json={"approve": True},
        headers={"X-User-Id": "alice", "X-User-Role": "user"},
    )
    assert r.status_code == 403

    # 售后仍为 PENDING，退款被拒（无法绕过审核）
    r = client.post(f"/after-sales/{aid}/refund", headers={"X-User-Id": "alice"})
    assert r.status_code == 409
    assert (
        client.get(f"/orders/{oid}", headers={"X-User-Id": "alice"}).json()[
            "refunded_amount"
        ]
        == 0
    )


def test_security_normal_user_cannot_refund_others_after_sale(client):
    """普通用户不能对他人的售后执行退款（跨归属的受保护执行）。"""
    oid = _paid_order(client, user="alice")
    aid = _approved_after_sale(client, oid, user="alice")

    # bob 尝试退款 alice 的售后 -> 403
    r = client.post(f"/after-sales/{aid}/refund", headers={"X-User-Id": "bob"})
    assert r.status_code == 403

    # alice 本人退款正常
    r = client.post(f"/after-sales/{aid}/refund", headers={"X-User-Id": "alice"})
    assert r.status_code == 200
    assert r.json()["status"] == "REFUNDED"
