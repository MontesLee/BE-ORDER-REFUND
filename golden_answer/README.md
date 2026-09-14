# Order After-Sale Refund Service — Golden Answer

参考实现（reference solution），用于 **BE-ORDER-REFUND** 多轮后端 Agent 评测题的
baseline 与测试套件来源。

- 技术栈：Python 3.11+ / FastAPI / SQLite（标准库 `sqlite3`，无 ORM）/ pytest
- 金额单位：**分（integer cents）**，全程不使用 `float`
- 调用方身份：`X-User-Id` 请求头
- 无 Redis / MQ / 微服务 / 分布式事务

---

## 1. 快速开始

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload          # http://127.0.0.1:8000/docs
```

认一个用户、拿它的 id，再带上请求头调用：

```bash
curl -s -X POST localhost:8000/users -H 'Content-Type: application/json' \
     -d '{"name":"alice","role":"USER"}'
curl -s -X POST localhost:8000/users -H 'Content-Type: application/json' \
     -d '{"name":"support","role":"AGENT"}'
```

环境变量：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `REFUND_DB_PATH` | `<repo>/data/refund.db` | SQLite 文件路径；每个连接按需读取，便于测试隔离 |
| `REFUND_GATEWAY_MODE` | `ok` | `ok` / `fail` / `fail_first`，用于给真实进程注入第三方渠道故障 |
| `REFUND_GATEWAY_FAIL_N` | `1` | `fail_first` 模式下前 N 次调用失败 |

---

## 2. 运行验证

```bash
./verify.sh
```

`verify.sh` 会：挑选解释器 → 建立干净 venv → 安装 `requirements.txt` →
指向一次性 SQLite 文件 → 跑完整测试套件（含 2 个真实 uvicorn 进程的并发用例）→
把原始输出写入 `verify_doc/test-result.txt` → 用 pytest 的退出码退出。

环境变量开关：`VERIFY_PYTHON=/path/to/python`（跳过建 venv）、
`VERIFY_SKIP_VENV=1`（复用当前解释器）。

---

## 3. 领域模型

```
User(id, name, role)                       role ∈ {USER, AGENT}
Order(id, user_id, total_amount, paid_amount, refunded_amount, payment_status)
AfterSale(id, order_id, user_id, refund_amount, status, idempotency_key)
Refund(id, after_sale_id, order_id, amount, status, attempt,
       third_party_ref, error_code, error_message, idempotency_key)
```

`Order.refunded_amount` 是本系统唯一的“已退金额”权威计数器：它在**认领**退款时
自增（预留额度），第三方失败时回退。任何时刻它与 `refunds` 中成功流水之和一致。

### 状态机

```
PENDING --approve--> APPROVED --execute--> REFUNDING
                                              |  ^
                               third-party OK |  | third-party failed
                                              v  |  (retry)
                                          REFUNDED   REFUND_FAILED
```

`REFUNDED` 是终态。`PENDING → REFUNDED`、`REFUNDED → *` 一律非法。

---

## 4. 六条不变量与落地点

| 不变量 | 语义 | 落地点（不是靠“记得写对”） |
| --- | --- | --- |
| **I1** 金额 | `sum(成功退款) <= paid_amount` | `orders` 表 `CHECK (refunded_amount <= paid_amount)` + 单条 `UPDATE ... WHERE refunded_amount + ? <= paid_amount` 守卫，二者都在 `BEGIN IMMEDIATE` 内 |
| **I2** 幂等 | 同一 AfterSale 至多一条成功退款 | 部分唯一索引 `ux_refunds_one_success ON refunds(after_sale_id) WHERE status='REFUNDED'`；认领阶段用 `expect_status` CAS 抢占 |
| **I3** 状态 | 只允许合法迁移，`REFUNDED` 终态 | `app/state_machine.py` 单一转换表；所有状态写入都必须过它 |
| **I4** 第三方失败 | 渠道失败时本地不得为 `REFUNDED` | 第三方裁决在事务外取得，`_settle()` 按裁决二选一；失败分支回退预留额度 |
| **I5** 多 worker | 多个进程并发下 I1/I2 仍成立 | `BEGIN IMMEDIATE` + `busy_timeout=30s` + 上述数据库级约束（**不是** `threading.Lock`） |
| **I6** 权限隔离 | 不能访问他人订单/售后，不能绕过审核 | `auth.assert_can_view` 归属校验（跨租户返回 404，不泄露存在性）+ `approve/execute` 仅 `AGENT` |

### 为什么并发控制放在数据库里

`threading.Lock` 是进程内对象。单进程测试会通过，多 worker 生产环境会失效——
这正是本题要抓的失效模式之一。因此：

1. **写锁**：所有 read-modify-write 都用 `BEGIN IMMEDIATE`，在第一次读之前就拿到
   数据库写锁，杜绝 check-then-write 交错；`busy_timeout` 让竞争方排队而不是报错。
2. **约束兜底**：即便应用逻辑写错，`CHECK` 与部分唯一索引也会拒绝非法写入。
3. **连接复用但事务不跨越第三方调用**：第三方调用放在两个短事务之间，
   慢渠道不会长时间持有数据库锁。

`connect()` 里的 `PRAGMA journal_mode = WAL` 是**尽力而为**的：WAL 是文件级持久
属性，只需成功一次；多个 worker 同时启动时可能撞上它需要的排他锁，这种碰撞无害，
不能因此让 worker 起不来（见 `repository.enable_wal` 的重试与容错）。

---

## 5. HTTP 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 存活探针 |
| POST | `/users` | `{name, role}` → 用户 |
| GET | `/users/me` | 当前调用方 |
| POST | `/orders` | `{amount}` → 订单（`UNPAID`，`paid_amount=0`） |
| GET | `/orders` | 当前用户的订单，分页 |
| GET | `/orders/{id}` | 订单详情（仅归属者或 `AGENT`） |
| POST | `/orders/{id}/pay` | 支付，幂等 |
| GET | `/orders/{id}/refund-summary` | 计数器/流水一致性对账（运维用，非题目要求） |
| POST | `/orders/{id}/after-sales` | `{refund_amount, idempotency_key?}`；同 key 重放返回 200 + 原记录 |
| GET | `/orders/{id}/after-sales` | 分页列表 |
| GET | `/after-sales/{id}` | 售后详情 |
| POST | `/after-sales/{id}/approve` | 仅 `AGENT`；重复审核是 no-op |
| POST | `/after-sales/{id}/execute` | 仅 `AGENT`；已成功则重放返回 200，进行中返回 409 |
| GET | `/after-sales/{id}/refunds` | 退款尝试流水，分页 |
| POST | `/maintenance/reconcile` | 释放卡死的 `REFUNDING` 预留额度（运维用） |

分页：`?limit=&offset=`，`limit` 默认 50、上限 100（单次请求不可能拉全表）。

错误码：`400` 参数问题 / `401` 身份缺失 / `403` 角色不足 / `404` 不存在**或不可见**
（跨租户一律 404，避免探测资源是否存在）/ `409` 状态或额度冲突。

---

## 6. 测试套件

```bash
pytest tests -v
```

| 文件 | 覆盖的 golden test |
| --- | --- |
| `test_order.py` | R0 基线：可运行、订单/售后/审核/退款主流程 |
| `test_refund.py` | T01 正常退款、T02 未支付不可退 |
| `test_amount.py` | T03 多笔部分退款、T04 超额退款被拒 |
| `test_idempotency.py` | T06 重复提交、T07 重复执行 |
| `test_state_machine.py` | T08 非法流转、T10 `REFUNDED` 终态 |
| `test_failure_retry.py` | T05 失败不占额度、T09 失败可重试、T11 第三方失败不得标记成功、T12 事故回归 |
| `test_concurrency.py` | T13 同一售后并发、T14 多售后并发超额（**2 个真实 uvicorn 进程**共享一个 SQLite 文件） |
| `test_security.py` | T15 越权订单、T16 越权售后、T17 普通用户不可执行退款 |
| `test_performance.py` | T18 索引命中 + 分页有界 + 延迟预算 |

设计约定：

- 断言**可观测业务结果**（成功退款笔数、累计金额、终态），不绑定某种实现机制；
  重复执行返回 `200` 还是 `409` 都接受，只要不产生第二次退款。
- 并发用例必须跨进程，且必须校验数据，而不是“请求确实并发发出去了”。
- 第三方失败由可注入网关确定性制造，不依赖随机 `sleep`，也不依赖“偶现”。
- 所有 HTTP 客户端使用 `trust_env=False`：**回环地址不应该走环境里的 HTTP 代理**，
  否则代理会让复用连接以绝对形式请求行发出，服务端会正确地判为未知路径。

---

## 7. 已知限制（有意保留，未隐藏）

1. **崩溃窗口**：进程在“认领成功、第三方调用未回写”之间挂掉，会留下 `REFUNDING`
   流水与一笔被预留的额度。本实现没有分布式事务、没有 outbox，因此用显式的
   `POST /maintenance/reconcile` 释放超时未结算的尝试。这是 SQLite 单机方案的
   真实边界，而不是缺陷。
2. **SQLite 写入是串行的**：`BEGIN IMMEDIATE` 让写事务排队，吞吐上限受单文件写锁
   限制。适用中小规模；换成 PostgreSQL 时同一套约束可以平移（`CHECK` + 部分唯一索引）。
3. **身份机制极简**：`X-User-Id` 只是为了让评测聚焦授权*语义*，它本身不是认证方案。
4. `refund-summary` 与 `maintenance/reconcile` 是给评测者/运维的对账与恢复入口，
   题目并未要求模型实现，模型未实现不扣分。
