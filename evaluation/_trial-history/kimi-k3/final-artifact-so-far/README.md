# 订单售后退款服务

最小可运行的订单售后退款服务。用户支付订单后可发起全额售后退款，客服审核通过后执行退款。

## 技术栈

- Python 3 + FastAPI + Pydantic v2
- 进程内内存存储（重启数据丢失，仅用于演示）
- pytest + httpx（TestClient）做 API 测试

## 状态机

订单：`CREATED` → `PAID` → `REFUNDED`（`CLOSED` 为预留状态，未实现取消入口）

售后单：`PENDING` → `APPROVED` → `REFUNDED`，或 `PENDING` → `REJECTED`

规则：

- 一个订单可存在多个售后申请；仅 `PAID` 状态（未全额退款）的订单可申请售后
- 支持部分退款：`refund_amount` 可小于订单金额，但必须 `> 0`
- 累计成功退款金额不得超过订单实际支付金额；超过可退余额的申请返回 409
- 仅成功退款（`REFUNDED`）计入累计；被审核拒绝的售后单不计入
- 退款累计达到支付金额时，订单整体置为 `REFUNDED`；部分退款时订单保持 `PAID`
- 仅 `APPROVED` 状态售后单可执行退款
- 状态冲突返回 409，资源不存在返回 404，参数校验失败返回 422

## 运行

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

启动后访问 `http://127.0.0.1:8000/docs` 查看 Swagger 文档。

## 测试

```bash
python -m pytest -q
```

## API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/orders` | 创建订单，body: `{item_name, amount}` |
| POST | `/orders/{order_id}/pay` | 支付订单 |
| GET | `/orders/{order_id}` | 查询订单及其售后单 |
| POST | `/orders/{order_id}/refunds` | 创建售后申请，body: `{refund_amount, reason}` |
| POST | `/refunds/{refund_id}/review` | 审核售后，body: `{approve, comment?}` |
| POST | `/refunds/{refund_id}/execute` | 执行退款 |
| GET | `/refunds/{refund_id}` | 查询售后单 |

## 示例

```bash
# 创建并支付订单
curl -X POST localhost:8000/orders -H 'Content-Type: application/json' \
  -d '{"item_name": "机械键盘", "amount": "299.00"}'
curl -X POST localhost:8000/orders/ord_xxx/pay

# 申请售后 → 审核通过 → 执行退款（可多次、部分退款）
curl -X POST localhost:8000/orders/ord_xxx/refunds -H 'Content-Type: application/json' \
  -d '{"refund_amount": "99.00", "reason": "七天无理由退货"}'
curl -X POST localhost:8000/refunds/rfd_xxx/review -H 'Content-Type: application/json' \
  -d '{"approve": true, "comment": "同意退款"}'
curl -X POST localhost:8000/refunds/rfd_xxx/execute

# 查询
curl localhost:8000/orders/ord_xxx
```

## 目录结构

```
app/
  __init__.py
  models.py     # Pydantic 模型、状态枚举、请求/响应 schema
  service.py    # 业务逻辑与状态机，内存存储
  main.py       # FastAPI 路由与异常映射
tests/
  test_api.py   # 全流程与非法状态迁移测试
requirements.txt
pytest.ini
```

## 已知限制

- 内存存储，无持久化、无跨进程一致性（仅用线程锁保证单进程并发安全）
- 无鉴权、无用户体系
- 支付与退款均为模拟，未对接真实支付渠道
- 仅支持全额退款，不考虑部分退款、优惠券、积分
