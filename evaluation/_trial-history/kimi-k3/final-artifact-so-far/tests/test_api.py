"""API 全流程与状态机测试。"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _create_paid_order() -> str:
    r = client.post("/orders", json={"item_name": "测试商品", "amount": "99.90"})
    assert r.status_code == 201
    order_id = r.json()["id"]
    r = client.post(f"/orders/{order_id}/pay")
    assert r.status_code == 200
    return order_id


def test_create_order():
    r = client.post("/orders", json={"item_name": "书", "amount": "12.50"})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "CREATED"
    assert body["amount"] == "12.50"


def test_create_order_invalid_amount():
    r = client.post("/orders", json={"item_name": "书", "amount": "-1"})
    assert r.status_code == 422


def test_pay_order():
    r = client.post("/orders", json={"item_name": "书", "amount": "10"})
    order_id = r.json()["id"]
    r = client.post(f"/orders/{order_id}/pay")
    assert r.status_code == 200
    assert r.json()["status"] == "PAID"
    assert r.json()["paid_at"] is not None


def test_pay_twice_rejected():
    order_id = _create_paid_order()
    r = client.post(f"/orders/{order_id}/pay")
    assert r.status_code == 409


def test_refund_cannot_apply_before_pay():
    r = client.post("/orders", json={"item_name": "书", "amount": "10"})
    order_id = r.json()["id"]
    r = client.post(f"/orders/{order_id}/refunds", json={"refund_amount": "10", "reason": "不想要了"})
    assert r.status_code == 409


def test_full_refund_flow():
    order_id = _create_paid_order()

    # 创建售后
    r = client.post(f"/orders/{order_id}/refunds", json={"refund_amount": "99.90", "reason": "质量问题"})
    assert r.status_code == 201
    refund = r.json()
    assert refund["status"] == "PENDING"
    assert refund["refund_amount"] == "99.90"  # 全额退款
    refund_id = refund["id"]

    # 审核通过
    r = client.post(f"/refunds/{refund_id}/review", json={"approve": True, "comment": "同意"})
    assert r.status_code == 200
    assert r.json()["status"] == "APPROVED"

    # 执行退款
    r = client.post(f"/refunds/{refund_id}/execute")
    assert r.status_code == 200
    assert r.json()["status"] == "REFUNDED"

    # 订单状态联动
    r = client.get(f"/orders/{order_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["order"]["status"] == "REFUNDED"
    assert len(body["refunds"]) == 1
    assert body["refunds"][0]["status"] == "REFUNDED"


def test_reject_refund():
    order_id = _create_paid_order()
    r = client.post(f"/orders/{order_id}/refunds", json={"refund_amount": "30", "reason": "拍错了"})
    refund_id = r.json()["id"]

    r = client.post(f"/refunds/{refund_id}/review", json={"approve": False, "comment": "不符合条件"})
    assert r.status_code == 200
    assert r.json()["status"] == "REJECTED"

    # 拒绝后不能执行退款
    r = client.post(f"/refunds/{refund_id}/execute")
    assert r.status_code == 409


def test_execute_before_approve_rejected():
    order_id = _create_paid_order()
    r = client.post(f"/orders/{order_id}/refunds", json={"refund_amount": "30", "reason": "七天无理由"})
    refund_id = r.json()["id"]
    r = client.post(f"/refunds/{refund_id}/execute")
    assert r.status_code == 409


def test_multiple_pending_refunds_allowed():
    # 一个订单可同时存在多个售后申请
    order_id = _create_paid_order()
    r1 = client.post(f"/orders/{order_id}/refunds", json={"refund_amount": "30", "reason": "第一次"})
    assert r1.status_code == 201
    r2 = client.post(f"/orders/{order_id}/refunds", json={"refund_amount": "30", "reason": "第二次"})
    assert r2.status_code == 201

    r = client.get(f"/orders/{order_id}")
    assert len(r.json()["refunds"]) == 2


def test_reapply_after_reject_allowed():
    order_id = _create_paid_order()
    r = client.post(f"/orders/{order_id}/refunds", json={"refund_amount": "10", "reason": "第一次"})
    refund_id = r.json()["id"]
    client.post(f"/refunds/{refund_id}/review", json={"approve": False})

    r = client.post(f"/orders/{order_id}/refunds", json={"refund_amount": "10", "reason": "重新申请"})
    assert r.status_code == 201


def test_not_found():
    assert client.get("/orders/ord_none").status_code == 404
    assert client.post("/orders/ord_none/pay").status_code == 404
    assert client.get("/refunds/rfd_none").status_code == 404
    assert client.post("/refunds/rfd_none/review", json={"approve": True}).status_code == 404
    assert client.post("/refunds/rfd_none/execute").status_code == 404


def test_cannot_pay_refunded_order():
    order_id = _create_paid_order()
    r = client.post(f"/orders/{order_id}/refunds", json={"refund_amount": "99.90", "reason": "退款"})
    refund_id = r.json()["id"]
    client.post(f"/refunds/{refund_id}/review", json={"approve": True})
    client.post(f"/refunds/{refund_id}/execute")

    r = client.post(f"/orders/{order_id}/pay")
    assert r.status_code == 409
    # 已全额退款的订单不能再发起售后
    r = client.post(f"/orders/{order_id}/refunds", json={"refund_amount": "1", "reason": "再次退款"})
    assert r.status_code == 409


# ---------- 本轮新增：部分退款 / 累计退款金额 ----------

def _review_and_execute(refund_id: str):
    r = client.post(f"/refunds/{refund_id}/review", json={"approve": True})
    assert r.status_code == 200
    r = client.post(f"/refunds/{refund_id}/execute")
    assert r.status_code == 200


def test_partial_refund_keeps_order_paid():
    order_id = _create_paid_order()  # 支付 99.90
    r = client.post(f"/orders/{order_id}/refunds", json={"refund_amount": "30", "reason": "部分退货"})
    refund_id = r.json()["id"]
    _review_and_execute(refund_id)

    r = client.get(f"/orders/{order_id}")
    body = r.json()
    # 部分退款：订单仍为 PAID，未整体置为 REFUNDED
    assert body["order"]["status"] == "PAID"
    assert body["refunds"][0]["status"] == "REFUNDED"


def test_refund_amount_zero_rejected():
    order_id = _create_paid_order()
    r = client.post(f"/orders/{order_id}/refunds", json={"refund_amount": "0", "reason": "x"})
    assert r.status_code == 422


def test_refund_amount_exceeds_remaining_rejected():
    order_id = _create_paid_order()  # 支付 99.90
    # 先成功退 60
    r = client.post(f"/orders/{order_id}/refunds", json={"refund_amount": "60", "reason": "a"})
    _review_and_execute(r.json()["id"])
    # 再申请退 60 → 剩余可退 39.90，超出
    r = client.post(f"/orders/{order_id}/refunds", json={"refund_amount": "60", "reason": "b"})
    assert r.status_code == 409


def test_cumulative_refund_capped_at_paid():
    # 订单支付 100
    r = client.post("/orders", json={"item_name": "套票", "amount": "100"})
    order_id = r.json()["id"]
    client.post(f"/orders/{order_id}/pay")

    # 分三次：40 + 40 + 30，第三次应被拒（剩余仅 20）
    r1 = client.post(f"/orders/{order_id}/refunds", json={"refund_amount": "40", "reason": "a"})
    _review_and_execute(r1.json()["id"])
    r2 = client.post(f"/orders/{order_id}/refunds", json={"refund_amount": "40", "reason": "b"})
    _review_and_execute(r2.json()["id"])

    r3 = client.post(f"/orders/{order_id}/refunds", json={"refund_amount": "30", "reason": "c"})
    assert r3.status_code == 409  # 累计将达 110 > 100

    # 精确退剩余 20 成功，订单整体置 REFUNDED
    r4 = client.post(f"/orders/{order_id}/refunds", json={"refund_amount": "20", "reason": "d"})
    assert r4.status_code == 201
    _review_and_execute(r4.json()["id"])
    assert client.get(f"/orders/{order_id}").json()["order"]["status"] == "REFUNDED"


def test_rejected_refund_not_counted_in_cumulative():
    order_id = _create_paid_order()  # 99.90
    # 一笔被拒 50
    r1 = client.post(f"/orders/{order_id}/refunds", json={"refund_amount": "50", "reason": "被拒"})
    rid1 = r1.json()["id"]
    client.post(f"/refunds/{rid1}/review", json={"approve": False})
    # 仍可成功申请 99.90（被拒的不计入累计）
    r2 = client.post(f"/orders/{order_id}/refunds", json={"refund_amount": "99.90", "reason": "重提"})
    assert r2.status_code == 201
    assert client.get(f"/orders/{order_id}").json()["order"]["status"] == "PAID"
