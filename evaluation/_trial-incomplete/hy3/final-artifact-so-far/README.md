# 订单售后退款服务

一个最小可运行的「订单售后退款」后端服务，基于 FastAPI 实现。
覆盖：创建订单 → 支付 → 发起售后 → 客服审核 → 执行退款 → 查询状态。
本版本**只考虑全额退款**，不涉及优惠券、积分等复杂业务。

## 运行环境

- Python 3.13（已内置 fastapi / uvicorn / pydantic / httpx / pytest）
- 数据存放在进程内存（字典），**重启服务后数据丢失**，用于演示最小实现

## 安装与启动

```bash
# 依赖已预装；如需重装：
python -m pip install -r requirements.txt

# 启动服务（默认 http://127.0.0.1:8000）
python -m uvicorn app:app --reload

# 交互式文档：
#   http://127.0.0.1:8000/docs
```

## 运行测试

```bash
python -m pytest -q
```

## 状态流转

```
订单:  CREATED ──支付──▶ PAID ──退款──▶ REFUNDED
售后:  PENDING ──审核──▶ APPROVED / REJECTED ──退款──▶ REFUNDED
```

约束（接口会返回 409/400 拦截非法流转）：

- 仅 `CREATED` 订单可支付；仅 `PAID` 订单可发起售后。
- **一个订单可存在多个售后申请**（多次发起互不阻塞）。
- 仅 `PENDING` 售后可审核；仅 `APPROVED` 售后可退款。
- **支持部分退款**：退款接口可指定 `refund_amount`，不指定则退「剩余可退金额」（订单金额 − 已成功退款金额）。
- **`refund_amount` 必须大于 0**；若剩余可退金额为 0 也返回 400。
- **累计退款限额**：同一订单所有成功退款金额之和不得超过订单实际支付金额，超额返回 409。
- **仅成功退款计入累计**：只有状态变为 `REFUNDED` 的售后才累加 `order.refunded_amount`；`PENDING`/`APPROVED`/`REJECTED` 均不计入。
- 订单在「累计退款达全额」后才置为 `REFUNDED`，部分退款期间保持 `PAID`。

## API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/orders` | 创建订单，body: `{user_id, amount}` |
| GET  | `/orders` | 列出全部订单 |
| GET  | `/orders/{order_id}` | 查询订单状态 |
| POST | `/orders/{order_id}/pay` | 支付订单，body: `{payment_method?}` |
| POST | `/orders/{order_id}/after-sales` | 发起售后，body: `{reason}` |
| GET  | `/after-sales` | 列出全部售后 |
| GET  | `/after-sales/{after_sale_id}` | 查询售后状态 |
| POST | `/after-sales/{after_sale_id}/review` | 审核，body: `{approve, reviewer_note?}` |
| POST | `/after-sales/{after_sale_id}/refund` | 执行退款，body: `{refund_amount?}`（不传退剩余全部） |

## 典型调用流程

```bash
# 1. 创建订单
curl -X POST http://127.0.0.1:8000/orders -H 'Content-Type: application/json' \
  -d '{"user_id":"u1","amount":100}'

# 2. 支付
curl -X POST http://127.0.0.1:8000/orders/{order_id}/pay -H 'Content-Type: application/json' -d '{}'

# 3. 发起售后
curl -X POST http://127.0.0.1:8000/orders/{order_id}/after-sales -H 'Content-Type: application/json' \
  -d '{"reason":"不想要了"}'

# 4. 客服审核通过
curl -X POST http://127.0.0.1:8000/after-sales/{after_sale_id}/review -H 'Content-Type: application/json' \
  -d '{"approve":true}'

# 5. 执行退款
curl -X POST http://127.0.0.1:8000/after-sales/{after_sale_id}/refund

# 6. 查询
curl http://127.0.0.1:8000/orders/{order_id}
curl http://127.0.0.1:8000/after-sales/{after_sale_id}
```

## 目录结构

```
hy3/
  app.py          # FastAPI 应用与路由
  models.py       # 领域模型与状态枚举
  schemas.py      # 请求体校验
  store.py        # 内存存储层（线程安全）
  requirements.txt
  tests/test_api.py
```
