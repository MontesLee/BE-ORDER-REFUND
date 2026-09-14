"""第三方渠道退款网关测试（本轮 R6 新增）。

目标：稳定复现「第三方支付渠道成功 / 失败」两种场景，并验证：
  1) 第三方成功时，本地最终进入 REFUNDED（订单随之 REFUNDED）；
  2) 第三方失败时，本地不得进入 REFUNDED（订单保持 PAID，累计金额不变）；
  3) REFUND_FAILED 可以重试（失败后换成功网关可进入 REFUNDED）；
  4) 成功后不能重复退款（资源级幂等 + 唯一幂等键，且渠道仅被调用一次）；
  5) 失败不缓存幂等键，可用同一 Idempotency-Key 重试；
  6) 并发失败不会误标 REFUNDED；
  7) 间歇性失败（首调失败、后调成功）场景下，最终一致性正确。

通过 `store.gateway` 注入 `FakeRefundGateway` 实现确定性模拟（不再依赖真实网络，
也不依赖随机失败），因此用例稳定可复现。
"""
import threading

import pytest
from fastapi.testclient import TestClient

from app import app
from store import store, Order, AfterSale, OrderStatus, AfterSaleStatus
from gateway import FakeRefundGateway, RefundResult

CLIENT = TestClient(app)


@pytest.fixture
def client():
    return CLIENT


@pytest.fixture(autouse=True)
def _isolate():
    """清空数据，并把网关恢复为成功占位，保证用例间隔离。"""
    store.reset()
    original = store.gateway
    yield
    store.gateway = original
    store.reset()


def _paid_order(amount=100.0, user="u1"):
    r = CLIENT.post("/orders", json={"user_id": user, "amount": amount})
    assert r.status_code == 201, r.text
    oid = r.json()["id"]
    r = CLIENT.post(f"/orders/{oid}/pay", json={})
    assert r.status_code == 200, r.text
    return oid


def _approved_after_sale(oid, reason="r"):
    r = CLIENT.post(f"/orders/{oid}/after-sales", json={"reason": reason})
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    r = CLIENT.post(f"/after-sales/{aid}/review", json={"approve": True})
    assert r.status_code == 200, r.text
    return aid


def _gw(fail=False, **kw):
    g = FakeRefundGateway(fail=fail, **kw)
    store.gateway = g
    return g


# 1) 第三方成功 -> 本地 REFUNDED -------------------------------------------------


def test_third_party_success_marks_refunded(client):
    gw = _gw(fail=False)
    oid = _paid_order(amount=120)
    aid = _approved_after_sale(oid)

    r = client.post(f"/after-sales/{aid}/refund")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "REFUNDED"
    assert body["refund_amount"] == 120

    # 订单随之 REFUNDED，且渠道恰好被调用一次
    o = client.get(f"/orders/{oid}").json()
    assert o["status"] == "REFUNDED"
    assert o["refunded_amount"] == 120
    assert len(gw.calls) == 1
    assert gw.calls[0] == (oid, aid, 120.0)


# 2) 第三方失败 -> 本地不得 REFUNDED ---------------------------------------------


def test_third_party_failure_marks_refund_failed_not_refunded(client):
    gw = _gw(fail=True, error="channel timeout")
    oid = _paid_order(amount=120)
    aid = _approved_after_sale(oid)

    r = client.post(f"/after-sales/{aid}/refund")
    # 失败返回 502，绝不进入 REFUNDED
    assert r.status_code == 502
    assert "channel timeout" in r.json()["detail"]

    asale = client.get(f"/after-sales/{aid}").json()
    assert asale["status"] == "REFUND_FAILED"
    assert asale["refund_amount"] == 120  # 记录的是本次尝试金额

    # 订单保持 PAID，累计退款金额不被污染
    o = client.get(f"/orders/{oid}").json()
    assert o["status"] == "PAID"
    assert o["refunded_amount"] == 0
    assert len(gw.calls) == 1


# 3) REFUND_FAILED 可重试 -> 换成功网关后进入 REFUNDED ----------------------------


def test_failure_then_retry_with_success_enters_refunded(client):
    gw_fail = _gw(fail=True, error="temporary decline")
    oid = _paid_order(amount=100)
    aid = _approved_after_sale(oid)

    # 第一次：渠道失败
    r1 = client.post(f"/after-sales/{aid}/refund")
    assert r1.status_code == 502
    assert client.get(f"/after-sales/{aid}").json()["status"] == "REFUND_FAILED"

    # 修复渠道后重试（同一售后，未换幂等键）
    gw_ok = _gw(fail=False)
    r2 = client.post(f"/after-sales/{aid}/refund")
    assert r2.status_code == 200
    assert r2.json()["status"] == "REFUNDED"
    assert r2.json()["refund_amount"] == 100

    o = client.get(f"/orders/{oid}").json()
    assert o["status"] == "REFUNDED"
    assert o["refunded_amount"] == 100
    # 失败那次与成功那次各调用一次渠道
    assert len(gw_fail.calls) == 1 and len(gw_ok.calls) == 1


# 4) 失败不缓存幂等键，可同键重试 ------------------------------------------------


def test_failure_idempotency_key_not_cached(client):
    _gw(fail=True, error="boom")
    oid = _paid_order(amount=100)
    aid = _approved_after_sale(oid)
    headers = {"Idempotency-Key": "k-retry"}

    r1 = client.post(f"/after-sales/{aid}/refund", headers=headers)
    assert r1.status_code == 502

    # 同键重试：因失败未缓存，应重新执行并成功
    _gw(fail=False)
    r2 = client.post(f"/after-sales/{aid}/refund", headers=headers)
    assert r2.status_code == 200
    assert r2.json()["refund_amount"] == 100


# 5) 成功后不能重复退款（渠道仅调用一次） ----------------------------------------


def test_success_no_double_refund_retry(client):
    gw = _gw(fail=False)
    oid = _paid_order(amount=100)
    aid = _approved_after_sale(oid)

    r1 = client.post(f"/after-sales/{aid}/refund")
    assert r1.status_code == 200
    # 重复退款（资源级幂等）：不应二次调用渠道
    r2 = client.post(f"/after-sales/{aid}/refund")
    assert r2.status_code == 200
    assert r2.json()["refund_amount"] == 100

    o = client.get(f"/orders/{oid}").json()
    assert o["refunded_amount"] == 100  # 未翻倍
    assert len(gw.calls) == 1  # 渠道仅被调用一次


def test_success_idempotency_key_dedupes_and_single_channel_call(client):
    gw = _gw(fail=False)
    oid = _paid_order(amount=150)
    aid = _approved_after_sale(oid)
    headers = {"Idempotency-Key": "k-dedup"}

    r1 = client.post(f"/after-sales/{aid}/refund", json={"refund_amount": 150}, headers=headers)
    assert r1.status_code == 200
    r2 = client.post(f"/after-sales/{aid}/refund", json={"refund_amount": 150}, headers=headers)
    assert r2.status_code == 200
    assert r2.json() == r1.json()  # 幂等结果完全一致
    assert client.get(f"/orders/{oid}").json()["refunded_amount"] == 150
    assert len(gw.calls) == 1  # 重放未再次打渠道


# 6) 部分退款失败不污染累计，补齐后仍可关闭订单 --------------------------------


def test_partial_refund_failure_then_complete(client):
    gw = _gw(fail=True, error="declined")
    oid = _paid_order(amount=200)
    aid1 = _approved_after_sale(oid)
    # 第一次部分退款（80）渠道失败
    r = client.post(f"/after-sales/{aid1}/refund", json={"refund_amount": 80})
    assert r.status_code == 502
    o = client.get(f"/orders/{oid}").json()
    assert o["status"] == "PAID" and o["refunded_amount"] == 0

    # 渠道恢复，重试 aid1 退 80 成功
    _gw(fail=False)
    r = client.post(f"/after-sales/{aid1}/refund", json={"refund_amount": 80})
    assert r.status_code == 200
    assert client.get(f"/orders/{oid}").json()["refunded_amount"] == 80

    # 补齐剩余 120
    aid2 = _approved_after_sale(oid)
    r = client.post(f"/after-sales/{aid2}/refund", json={"refund_amount": 120})
    assert r.status_code == 200
    o = client.get(f"/orders/{oid}").json()
    assert o["status"] == "REFUNDED"
    assert o["refunded_amount"] == 200


# 7) 并发失败不会误标 REFUNDED ------------------------------------------------


def test_concurrent_failure_never_refunded():
    gw = _gw(fail=True, error="concurrent decline")
    store.reset()
    oid, aid = "cg-o", "cg-a"
    store.insert_order(
        Order(id=oid, user_id="u", amount=100.0, status=OrderStatus.PAID,
              created_at=_now())
    )
    store.insert_after_sale(
        AfterSale(id=aid, order_id=oid, reason="r", status=AfterSaleStatus.APPROVED,
                  created_at=_now())
    )

    N = 10
    barrier = threading.Barrier(N)
    results = [None] * N

    def work(i):
        barrier.wait()
        results[i] = store.refund_transaction(aid, None, None)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 全部因渠道失败返回 502，本地绝无 REFUNDED
    for sc, _ in results:
        assert sc == 502
    assert store.get_after_sale(aid).status == AfterSaleStatus.REFUND_FAILED
    o = store.get_order(oid)
    assert o.status == OrderStatus.PAID
    assert o.refunded_amount == 0.0


# 8) 间歇性失败（首调失败、后调成功）最终一致 ---------------------------------


class FlakyGateway:
    """模拟间歇性失败：前 fail_times 次失败，之后成功。"""

    def __init__(self, fail_times: int = 1):
        self.fail_times = fail_times
        self.calls = 0

    def refund(self, *, payment_ref, after_sale_id, amount):
        self.calls += 1
        if self.calls <= self.fail_times:
            return RefundResult(success=False, error="transient network error")
        return RefundResult(success=True, channel_refund_id=f"flaky-{after_sale_id}")


def test_intermittent_failure_then_success(client):
    flaky = FlakyGateway(fail_times=1)
    store.gateway = flaky
    oid = _paid_order(amount=100)
    aid = _approved_after_sale(oid)

    r1 = client.post(f"/after-sales/{aid}/refund")
    assert r1.status_code == 502  # 首次渠道失败
    assert client.get(f"/after-sales/{aid}").json()["status"] == "REFUND_FAILED"

    r2 = client.post(f"/after-sales/{aid}/refund")
    assert r2.status_code == 200  # 渠道恢复后成功
    assert r2.json()["status"] == "REFUNDED"
    assert client.get(f"/orders/{oid}").json()["refunded_amount"] == 100


def _now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)
