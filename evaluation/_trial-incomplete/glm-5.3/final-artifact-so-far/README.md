# 订单售后退款服务

一个最小可运行的订单售后退款服务：用户创建订单并支付后，可针对订单发起售后退款申请，客服审核通过后系统执行退款。只支持**全额退款**，不涉及优惠券、积分等复杂业务。

## 技术栈

- Python 3.10+ / FastAPI / Pydantic v2
- 数据存储：内存（进程重启后清空，仅用于演示）
- 测试：pytest + FastAPI TestClient

## 运行

```bash
# 安装依赖（如使用虚拟环境请先激活）
pip install -r requirements.txt

# 启动服务（默认 http://127.0.0.1:8000）
uvicorn app.main:app --reload

# 交互式 API 文档
# http://127.0.0.1:8000/docs
```

## 运行测试

```bash
python -m pytest -q
```

## 状态机

### 订单（Order）

```
PENDING_PAYMENT --支付--> PAID --发起售后--> REFUNDING --退款完成--> REFUNDED
                              ^                    |
                              +------- 驳回 -------+
```

### 售后申请（AfterSale）

```
PENDING_REVIEW --审核通过--> APPROVED --执行退款--> REFUNDED
      |
      +--审核驳回--> REJECTED（订单回到 PAID，可再次发起售后）
```

规则要点：

- 全额退款：`refund_amount` 恒等于订单实付总额 `total_amount`。
- 仅 `PAID` 状态的订单可发起售后；存在待审核/已通过/已退款的售后时不可重复发起。
- 仅 `APPROVED` 状态的售后可执行退款；驳回后订单回到 `PAID`。
- 状态冲突返回 `409`，资源不存在返回 `404`。

## API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/orders` | 创建订单（待支付） |
| POST | `/orders/{order_id}/pay` | 支付订单 |
| GET | `/orders/{order_id}` | 查询订单（含售后列表） |
| POST | `/orders/{order_id}/after-sales` | 创建售后退款申请 |
| POST | `/after-sales/{id}/approve` | 审核通过 |
| POST | `/after-sales/{id}/reject` | 审核驳回（body: `{"reason": "..."}`） |
| POST | `/after-sales/{id}/refund` | 执行退款 |
| GET | `/after-sales/{id}` | 查询售后申请 |
| GET | `/health` | 健康检查 |

### 示例：完整流程

```bash
# 1. 创建订单
curl -X POST http://127.0.0.1:8000/orders -H "Content-Type: application/json" -d '{
  "user_id": "u1",
  "items": [{"sku_id": "sku-1", "name": "机械键盘", "price": 299.0, "quantity": 1}]
}'
# => {"id":"ord-xxxx","status":"PENDING_PAYMENT","total_amount":299.0,...}

# 2. 支付
curl -X POST http://127.0.0.1:8000/orders/ord-xxxx/pay
# => {"status":"PAID",...}

# 3. 发起售后
curl -X POST http://127.0.0.1:8000/orders/ord-xxxx/after-sales -H "Content-Type: application/json" -d '{"reason":"商品质量问题"}'
# => {"id":"as-xxxx","status":"PENDING_REVIEW","refund_amount":299.0,...}

# 4. 审核通过
curl -X POST http://127.0.0.1:8000/after-sales/as-xxxx/approve
# => {"status":"APPROVED",...}

# 5. 执行退款
curl -X POST http://127.0.0.1:8000/after-sales/as-xxxx/refund
# => {"status":"REFUNDED",...}

# 6. 查询订单
curl http://127.0.0.1:8000/orders/ord-xxxx
# => {"status":"REFUNDED","refunded_at":"...","after_sales":[...],...}
```

## 项目结构

```
app/
  main.py     # FastAPI 路由与异常转换
  service.py  # 业务逻辑与状态机
  store.py    # 内存存储（线程安全）
  models.py   # Pydantic 请求/响应模型与枚举
tests/
  test_api.py # 完整流程与异常分支测试
smoke_test.py # 本地启动冒烟脚本（拉起 uvicorn 走完整流程）
```

## 设计说明

- 单进程内存存储，`Store` 内置锁保证基本线程安全；未做持久化（需求为最小可运行版本）。
- "执行退款"为同步模拟：直接将售后与订单置为 `REFUNDED` 并记录时间戳，不对接真实支付网关。
- 业务规则冲突（非法状态流转）统一抛 `BizError`，在 API 层映射为 `409`；资源不存在映射为 `404`。
- 金额计算使用浮点数并对合计做两位小数取整，足够满足演示场景（生产环境建议用整数分存储）。
