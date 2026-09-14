"""基础 API 测试。

使用 FastAPI TestClient（基于 httpx）在进程内驱动接口，不启动真实端口。
每个用例前自动清空内存存储，保证相互隔离。
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


def _create_paid_order(client, amount=100.0, user="u1"):
    r = client.post("/orders", json={"user_id": user, "amount": amount})
    assert r.status_code == 201, r.text
    oid = r.json()["id"]
    r = client.post(f"/orders/{oid}/pay", json={"payment_method": "balance"})
    assert r.status_code == 200, r.text
    return oid


def test_create_order(client):
    r = client.post("/orders", json={"user_id": "u1", "amount": 50})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "CREATED"
    assert body["amount"] == 50
    assert body["id"]


def test_create_order_invalid_amount(client):
    r = client.post("/orders", json={"user_id": "u1", "amount": -1})
    assert r.status_code == 422
    r = client.post("/orders", json={"user_id": "u1", "amount": 0})
    assert r.status_code == 422


def test_pay_order_happy_path(client):
    r = client.post("/orders", json={"user_id": "u1", "amount": 50})
    oid = r.json()["id"]
    r = client.post(f"/orders/{oid}/pay", json={})
    assert r.status_code == 200
    assert r.json()["status"] == "PAID"
    assert r.json()["paid_at"]


def test_pay_missing_order(client):
    r = client.post("/orders/nope/pay", json={})
    assert r.status_code == 404


def test_pay_twice_fails(client):
    oid = _create_paid_order(client)
    r = client.post(f"/orders/{oid}/pay", json={})
    assert r.status_code == 409


def test_after_sale_on_unpaid_order_fails(client):
    r = client.post("/orders", json={"user_id": "u1", "amount": 50})
    oid = r.json()["id"]
    r = client.post(f"/orders/{oid}/after-sales", json={"reason": "x"})
    assert r.status_code == 409


def test_after_sale_missing_order(client):
    r = client.post("/orders/nope/after-sales", json={"reason": "x"})
    assert r.status_code == 404


def test_full_refund_flow(client):
    oid = _create_paid_order(client, amount=120)
    r = client.post(f"/orders/{oid}/after-sales", json={"reason": "want money back"})
    assert r.status_code == 201
    aid = r.json()["id"]
    assert r.json()["status"] == "PENDING"

    # 审核前不能退款
    r = client.post(f"/after-sales/{aid}/refund")
    assert r.status_code == 409

    # 审核通过
    r = client.post(f"/after-sales/{aid}/review", json={"approve": True})
    assert r.status_code == 200
    assert r.json()["status"] == "APPROVED"

    # 已审核后不能重复审核
    r = client.post(f"/after-sales/{aid}/review", json={"approve": False})
    assert r.status_code == 409

    # 执行退款
    r = client.post(f"/after-sales/{aid}/refund")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "REFUNDED"
    assert body["refund_amount"] == 120

    # 订单随之变为 REFUNDED
    r = client.get(f"/orders/{oid}")
    assert r.json()["status"] == "REFUNDED"
    assert r.json()["refunded_at"]


def test_reject_flow(client):
    oid = _create_paid_order(client)
    r = client.post(f"/orders/{oid}/after-sales", json={"reason": "x"})
    aid = r.json()["id"]
    r = client.post(
        f"/after-sales/{aid}/review",
        json={"approve": False, "reviewer_note": "no"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "REJECTED"
    assert body["reviewer_note"] == "no"

    # 拒绝后不能退款
    r = client.post(f"/after-sales/{aid}/refund")
    assert r.status_code == 409

    # 订单仍为 PAID
    r = client.get(f"/orders/{oid}")
    assert r.json()["status"] == "PAID"


def test_review_missing_after_sale(client):
    r = client.post("/after-sales/nope/review", json={"approve": True})
    assert r.status_code == 404


def test_get_not_found(client):
    assert client.get("/orders/nope").status_code == 404
    assert client.get("/after-sales/nope").status_code == 404


def _create_approved_after_sale(client, oid, reason="r"):
    r = client.post(f"/orders/{oid}/after-sales", json={"reason": reason})
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    r = client.post(f"/after-sales/{aid}/review", json={"approve": True})
    assert r.status_code == 200, r.text
    return aid


# ---- 业务规则：多售后 / 部分退款 / 累计限额 ----


def test_multiple_after_sales_allowed_on_same_order(client):
    oid = _create_paid_order(client)
    aid1 = _create_approved_after_sale(client, oid, "reason-1")
    # 同一订单可再次发起售后，不应被拦截
    r = client.post(f"/orders/{oid}/after-sales", json={"reason": "reason-2"})
    assert r.status_code == 201, r.text
    aid2 = r.json()["id"]
    assert aid1 != aid2


def test_partial_refunds_accumulate_and_close_order(client):
    oid = _create_paid_order(client, amount=200)
    aid1 = _create_approved_after_sale(client, oid)
    r = client.post(f"/after-sales/{aid1}/refund", json={"refund_amount": 80})
    assert r.status_code == 200
    assert r.json()["refund_amount"] == 80
    assert r.json()["status"] == "REFUNDED"

    # 部分退款后订单仍 PAID
    r = client.get(f"/orders/{oid}")
    assert r.json()["status"] == "PAID"
    assert r.json()["refunded_amount"] == 80

    # 第二次部分退款，补齐剩余 120
    aid2 = _create_approved_after_sale(client, oid)
    r = client.post(f"/after-sales/{aid2}/refund", json={"refund_amount": 120})
    assert r.status_code == 200
    assert r.json()["refund_amount"] == 120

    # 累计达全额，订单变为 REFUNDED
    r = client.get(f"/orders/{oid}")
    body = r.json()
    assert body["status"] == "REFUNDED"
    assert body["refunded_amount"] == 200


def test_refund_defaults_to_remaining(client):
    oid = _create_paid_order(client, amount=200)
    aid1 = _create_approved_after_sale(client, oid)
    client.post(f"/after-sales/{aid1}/refund", json={"refund_amount": 50})
    # 不传 refund_amount，应退剩余 150
    aid2 = _create_approved_after_sale(client, oid)
    r = client.post(f"/after-sales/{aid2}/refund")
    assert r.status_code == 200
    assert r.json()["refund_amount"] == 150


def test_refund_amount_must_be_positive(client):
    oid = _create_paid_order(client, amount=100)
    aid = _create_approved_after_sale(client, oid)
    # 传 0 或负数 -> schema gt=0 校验，返回 422
    r = client.post(f"/after-sales/{aid}/refund", json={"refund_amount": 0})
    assert r.status_code == 422
    r = client.post(f"/after-sales/{aid}/refund", json={"refund_amount": -10})
    assert r.status_code == 422


def test_cannot_create_after_sale_on_fully_refunded_order(client):
    # 退满后订单变为 REFUNDED，不能再发起新的售后（无法再退任何金额）
    oid = _create_paid_order(client, amount=100)
    aid = _create_approved_after_sale(client, oid)
    client.post(f"/after-sales/{aid}/refund")  # 退剩余全部 100
    r = client.get(f"/orders/{oid}")
    assert r.json()["status"] == "REFUNDED"
    r = client.post(f"/orders/{oid}/after-sales", json={"reason": "again"})
    assert r.status_code == 409


def test_refund_exceeds_remaining_is_clamped(client):
    oid = _create_paid_order(client, amount=200)
    aid1 = _create_approved_after_sale(client, oid)
    client.post(f"/after-sales/{aid1}/refund", json={"refund_amount": 80})
    # 已退 80，剩余 120，再申请退 150 -> 超额部分按剩余金额退款（clamp，不拒绝）
    aid2 = _create_approved_after_sale(client, oid)
    r = client.post(f"/after-sales/{aid2}/refund", json={"refund_amount": 150})
    assert r.status_code == 200
    # 实际退款金额为剩余可退上限 120，而非申请的 150
    assert r.json()["refund_amount"] == 120.0
    # 累计严格不超过订单实付，且订单闭单为 REFUNDED
    r = client.get(f"/orders/{oid}")
    assert r.json()["refunded_amount"] == 200.0
    assert r.json()["status"] == "REFUNDED"


def test_rejected_after_sale_does_not_count(client):
    oid = _create_paid_order(client, amount=100)
    # 创建后直接拒绝（不占用累计额度）
    r = client.post(f"/orders/{oid}/after-sales", json={"reason": "x"})
    aid_rej = r.json()["id"]
    r = client.post(f"/after-sales/{aid_rej}/review", json={"approve": False})
    assert r.status_code == 200
    # 拒绝状态不可退款
    r = client.post(f"/after-sales/{aid_rej}/refund")
    assert r.status_code == 409
    # 真正退款一个全额售后，累计应为 100
    aid_ok = _create_approved_after_sale(client, oid)
    client.post(f"/after-sales/{aid_ok}/refund")
    r = client.get(f"/orders/{oid}")
    assert r.json()["refunded_amount"] == 100
    assert r.json()["status"] == "REFUNDED"


def test_approved_but_unrefunded_does_not_count(client):
    oid = _create_paid_order(client, amount=100)
    # 审核通过但未退款，不占用累计额度
    _create_approved_after_sale(client, oid)
    r = client.get(f"/orders/{oid}")
    assert r.json()["refunded_amount"] == 0
    # 仍可全额退款
    aid2 = _create_approved_after_sale(client, oid)
    r = client.post(f"/after-sales/{aid2}/refund")
    assert r.status_code == 200
    assert r.json()["refund_amount"] == 100


# ---- 幂等性：重复提交 / 网络超时重放 ----
# 目标：1) 重复提交不产生多个有效退款；2) 同一 AfterSale 最多一个成功退款；
#      3) 幂等机制不破坏累计退款金额限制。


def test_refund_same_after_sale_only_one_successful_refund(client):
    # 资源级幂等：已 REFUNDED 的售后再次退款，返回既有结果，不计第二次
    oid = _create_paid_order(client, amount=100)
    aid = _create_approved_after_sale(client, oid)
    r1 = client.post(f"/after-sales/{aid}/refund")
    assert r1.status_code == 200
    assert r1.json()["refund_amount"] == 100
    assert r1.json()["status"] == "REFUNDED"

    # 重复调用（无幂等键）——不应产生第二个有效退款
    r2 = client.post(f"/after-sales/{aid}/refund")
    assert r2.status_code == 200
    assert r2.json()["refund_amount"] == 100
    assert r2.json()["status"] == "REFUNDED"

    # 累计金额仅 100，未翻倍
    r = client.get(f"/orders/{oid}")
    assert r.json()["refunded_amount"] == 100
    assert r.json()["status"] == "REFUNDED"


def test_idempotency_key_dedupes_duplicate_request(client):
    # 同一 Idempotency-Key 重放（典型网络超时场景）返回完全相同的结果，只退一次
    oid = _create_paid_order(client, amount=150)
    aid = _create_approved_after_sale(client, oid)
    headers = {"Idempotency-Key": "req-abc-001"}

    r1 = client.post(f"/after-sales/{aid}/refund", json={"refund_amount": 150}, headers=headers)
    assert r1.status_code == 200
    first_body = r1.json()

    # 客户端因超时未收到响应而重放同一请求
    r2 = client.post(f"/after-sales/{aid}/refund", json={"refund_amount": 150}, headers=headers)
    assert r2.status_code == 200
    assert r2.json() == first_body  # 结果完全一致

    r = client.get(f"/orders/{oid}")
    assert r.json()["refunded_amount"] == 150  # 仅退一次


def test_idempotency_key_does_not_double_when_key_reused_after_success(client):
    # 即便用「不同」幂等键重复针对同一 AfterSale，资源级守卫仍保证只退一次
    oid = _create_paid_order(client, amount=100)
    aid = _create_approved_after_sale(client, oid)

    r1 = client.post(f"/after-sales/{aid}/refund", headers={"Idempotency-Key": "k-1"})
    assert r1.status_code == 200
    r2 = client.post(f"/after-sales/{aid}/refund", headers={"Idempotency-Key": "k-2"})
    assert r2.status_code == 200
    assert r2.json()["refund_amount"] == 100

    r = client.get(f"/orders/{oid}")
    assert r.json()["refunded_amount"] == 100  # 累计未被破坏


def test_idempotency_key_not_cached_on_failure(client):
    # 失败请求（如未审核）不缓存幂等键，允许客户端用同一键修正后重试
    oid = _create_paid_order(client, amount=100)
    r = client.post(f"/orders/{oid}/after-sales", json={"reason": "x"})
    aid = r.json()["id"]
    headers = {"Idempotency-Key": "retry-key"}

    # 未审核 -> 409，不应缓存
    r1 = client.post(f"/after-sales/{aid}/refund", headers=headers)
    assert r1.status_code == 409

    # 审核通过后用同一幂等键重试，应当成功（证明失败未被缓存）
    client.post(f"/after-sales/{aid}/review", json={"approve": True})
    r2 = client.post(f"/after-sales/{aid}/refund", headers=headers)
    assert r2.status_code == 200
    assert r2.json()["refund_amount"] == 100


def test_idempotent_refund_keeps_cumulative_limit(client):
    # 重复提交不会让累计退款突破订单金额上限
    oid = _create_paid_order(client, amount=200)
    aid1 = _create_approved_after_sale(client, oid)
    # 第一次成功部分退款 80
    r = client.post(f"/after-sales/{aid1}/refund", json={"refund_amount": 80}, headers={"Idempotency-Key": "p1"})
    assert r.status_code == 200
    assert r.json()["refund_amount"] == 80

    # 对该已退款售后反复重放退 9999（远超剩余），都只返回原 80，不累加
    for _ in range(3):
        rr = client.post(f"/after-sales/{aid1}/refund", json={"refund_amount": 9999}, headers={"Idempotency-Key": "p1"})
        assert rr.status_code == 200
        assert rr.json()["refund_amount"] == 80

    r = client.get(f"/orders/{oid}")
    assert r.json()["refunded_amount"] == 80  # 首次仅 80，未受重放影响

    # 剩余额度仍受正常约束：再申请 150 时超额部分按剩余 120 退款（clamp），
    # 累计封顶于订单实付金额，绝不突破上限
    aid2 = _create_approved_after_sale(client, oid)
    rr = client.post(f"/after-sales/{aid2}/refund", json={"refund_amount": 150}, headers={"Idempotency-Key": "p2"})
    assert rr.status_code == 200
    assert rr.json()["refund_amount"] == 120
    r = client.get(f"/orders/{oid}")
    assert r.json()["refunded_amount"] == 200  # 累计封顶于实付金额，不超上限
    assert r.json()["status"] == "REFUNDED"


