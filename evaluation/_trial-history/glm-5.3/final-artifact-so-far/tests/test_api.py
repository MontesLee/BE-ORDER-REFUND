"""API 集成测试：订单支付 -> 售后申请 -> 审核 -> 退款的完整流程及异常分支。"""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def make_paid_order(client, user_id="u1"):
    resp = client.post(
        "/orders",
        json={
            "user_id": user_id,
            "items": [
                {"sku_id": "sku-1", "name": "机械键盘", "price": 299.0, "quantity": 1},
                {"sku_id": "sku-2", "name": "鼠标垫", "price": 39.9, "quantity": 2},
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    order = resp.json()
    assert order["status"] == "PENDING_PAYMENT"
    assert order["total_amount"] == pytest.approx(378.8)

    resp = client.post(f"/orders/{order['id']}/pay")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "PAID"
    return order


class TestFullFlow:
    def test_happy_path(self, client):
        """创建 -> 支付 -> 售后申请 -> 审核通过 -> 退款 -> 查询状态。"""
        order = make_paid_order(client)

        # 发起售后
        resp = client.post(
            f"/orders/{order['id']}/after-sales", json={"reason": "商品质量问题"}
        )
        assert resp.status_code == 201, resp.text
        after_sale = resp.json()
        assert after_sale["status"] == "PENDING_REVIEW"
        assert after_sale["refund_amount"] == pytest.approx(378.8)  # 全额退款
        assert after_sale["order_status"] == "REFUNDING"

        # 订单进入售后中
        resp = client.get(f"/orders/{order['id']}")
        assert resp.json()["status"] == "REFUNDING"
        assert len(resp.json()["after_sales"]) == 1

        # 审核通过
        resp = client.post(f"/after-sales/{after_sale['id']}/approve")
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "APPROVED"

        # 执行退款
        resp = client.post(f"/after-sales/{after_sale['id']}/refund")
        assert resp.status_code == 200, resp.text
        refunded = resp.json()
        assert refunded["status"] == "REFUNDED"
        assert refunded["refunded_at"] is not None

        # 订单终态
        resp = client.get(f"/orders/{order['id']}")
        assert resp.json()["status"] == "REFUNDED"
        assert resp.json()["refunded_at"] is not None

    def test_reject_then_reapply(self, client):
        """驳回后订单回到已支付，可再次发起售后。"""
        order = make_paid_order(client, user_id="u2")
        resp = client.post(
            f"/orders/{order['id']}/after-sales", json={"reason": "不想要了"}
        )
        after_sale = resp.json()

        resp = client.post(
            f"/after-sales/{after_sale['id']}/reject", json={"reason": "超过售后期"}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "REJECTED"
        assert resp.json()["reject_reason"] == "超过售后期"
        assert resp.json()["order_status"] == "PAID"

        # 再次发起售后并完成退款
        resp = client.post(
            f"/orders/{order['id']}/after-sales", json={"reason": "商品有划痕"}
        )
        assert resp.status_code == 201, resp.text
        after_sale2 = resp.json()
        client.post(f"/after-sales/{after_sale2['id']}/approve")
        resp = client.post(f"/after-sales/{after_sale2['id']}/refund")
        assert resp.json()["status"] == "REFUNDED"


class TestValidation:
    def test_pay_twice_fails(self, client):
        order = make_paid_order(client)
        resp = client.post(f"/orders/{order['id']}/pay")
        assert resp.status_code == 409

    def test_after_sale_before_payment_fails(self, client):
        resp = client.post(
            "/orders", json={"user_id": "u3", "items": [{"sku_id": "s", "name": "x", "price": 10, "quantity": 1}]}
        )
        order = resp.json()
        resp = client.post(
            f"/orders/{order['id']}/after-sales", json={"reason": "质量问题"}
        )
        assert resp.status_code == 409

    def test_duplicate_after_sale_fails(self, client):
        order = make_paid_order(client, user_id="u4")
        client.post(f"/orders/{order['id']}/after-sales", json={"reason": "第一次"})
        resp = client.post(f"/orders/{order['id']}/after-sales", json={"reason": "第二次"})
        assert resp.status_code == 409

    def test_refund_without_approval_fails(self, client):
        order = make_paid_order(client, user_id="u5")
        after_sale = client.post(
            f"/orders/{order['id']}/after-sales", json={"reason": "未审核"}
        ).json()
        resp = client.post(f"/after-sales/{after_sale['id']}/refund")
        assert resp.status_code == 409

    def test_review_twice_fails(self, client):
        order = make_paid_order(client, user_id="u6")
        after_sale = client.post(
            f"/orders/{order['id']}/after-sales", json={"reason": "重复审核"}
        ).json()
        client.post(f"/after-sales/{after_sale['id']}/approve")
        resp = client.post(f"/after-sales/{after_sale['id']}/approve")
        assert resp.status_code == 409

    def test_refund_after_rejected_fails(self, client):
        order = make_paid_order(client, user_id="u7")
        after_sale = client.post(
            f"/orders/{order['id']}/after-sales", json={"reason": "已驳回"}
        ).json()
        client.post(f"/after-sales/{after_sale['id']}/reject", json={"reason": "不符合条件"})
        resp = client.post(f"/after-sales/{after_sale['id']}/refund")
        assert resp.status_code == 409

    def test_refunded_order_cannot_pay_or_apply(self, client):
        order = make_paid_order(client, user_id="u8")
        after_sale = client.post(
            f"/orders/{order['id']}/after-sales", json={"reason": "退款"}
        ).json()
        client.post(f"/after-sales/{after_sale['id']}/approve")
        client.post(f"/after-sales/{after_sale['id']}/refund")
        assert client.post(f"/orders/{order['id']}/pay").status_code == 409
        assert client.post(
            f"/orders/{order['id']}/after-sales", json={"reason": "再来一次"}
        ).status_code == 409

    def test_unknown_ids_return_404(self, client):
        assert client.get("/orders/nope").status_code == 404
        assert client.post("/orders/nope/pay").status_code == 404
        assert client.get("/after-sales/nope").status_code == 404
        assert client.post("/after-sales/nope/refund").status_code == 404

    def test_invalid_order_payload(self, client):
        # 空商品列表 / 非法价格
        assert client.post("/orders", json={"user_id": "u", "items": []}).status_code == 422
        resp = client.post(
            "/orders",
            json={"user_id": "u", "items": [{"sku_id": "s", "name": "x", "price": -1, "quantity": 1}]},
        )
        assert resp.status_code == 422
