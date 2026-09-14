# 订单售后退款服务

一个最小可运行的「订单售后退款」后端服务，基于 FastAPI 实现。
覆盖：创建订单 → 支付 → 发起售后 → 客服审核 → 执行退款 → 查询状态。
本版本**只考虑全额退款**，不涉及优惠券、积分等复杂业务。

## 运行环境

- Python 3.13（已内置 fastapi / uvicorn / pydantic / httpx / pytest）
- 数据持久化到 **SQLite**（默认位于系统临时目录的 `hy3_refund.db`，可用环境变量
  `REFUND_DB_PATH` 覆盖），多 Worker 共享同一数据库文件即可保证状态一致。
- 采用 WAL 日志模式 + `BEGIN IMMEDIATE` 写事务 + 条件 UPDATE，保证多进程并发安全
  （详见下文「多 Worker 并发控制」）。

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

## 核心保证清单（最终交付的 14 条）

本服务以「数据库层事务 + 条件 UPDATE + 幂等键 + 归属校验」四重机制，端到端满足以下 14 条核心业务保证，全部由 `tests/test_final_acceptance_r9.py` 逐条确定性覆盖：

| # | 保证 | 满足方式 |
| --- | --- | --- |
| 1 | paid order 可以退款 | `create_after_sale` 要求订单 `PAID`；`refund_transaction` 校验订单状态后调用渠道并落 `REFUNDED` |
| 2 | unpaid order 不能退款 | `create_after_sale` 在 `CREATED` 订单上返回 409；`refund_transaction` 额外在存储层卡 `status != PAID` 直接拒绝 |
| 3 | 一个订单支持多个 AfterSale | `create_after_sale` 不限制同一订单的售后数量，各自独立审核/退款 |
| 4 | 累计成功退款不超过 paid_amount | 金额以整数「分」运算避免浮点误差；单次申请超过剩余可退时按剩余金额 clamp 退款；额度在调用渠道前以条件 `UPDATE ... WHERE CAST((refunded_amount+?) *100 AS INTEGER) <= CAST(amount*100 AS INTEGER)` 预留，并发超额 `rowcount==0` 回滚；订单 `REFUNDED` 后无法再退 |
| 5 | 一个 AfterSale 最多一个成功退款 | 认领 `UPDATE ... WHERE status IN ('APPROVED','REFUND_FAILED')` 保证同一售后仅一个工作者驱动渠道；`REFUNDED` 重放只返回既有结果 |
| 6 | duplicate request 不产生重复有效退款 | 幂等键（`idempotency` 表唯一约束，跨 Worker 共享）+ 资源级守卫，重放只退一次 |
| 7 | 非法状态转换被拒绝 | `PENDING`/`REJECTED`/`REFUNDING` 等非可退款态退款返回 409；重复审核/重复支付同样被状态机拦截 |
| 8 | REFUND_FAILED 可以 retry | 失败仅置 `REFUND_FAILED` 并释放额度，幂等键不缓存，可再次退款（换成功渠道即成功） |
| 9 | REFUNDED 不能 retry | 已 `REFUNDED` 的售后重放直接返回既有结果，不二次调渠道、不二次扣减 |
| 10 | 第三方失败不能导致本地退款成功 | 渠道失败不写 `REFUNDED`：订单保持 `PAID`、累计金额不变，本地状态为 `REFUND_FAILED`（返回 502） |
| 11 | multi-worker 保持核心 invariant | 共享 SQLite + `BEGIN IMMEDIATE` 写锁串行化；条件 UPDATE 作为二次保护，跨进程亦成立 |
| 12 | 用户不能访问其他用户订单 | 所有订单读写接口在携带 `X-User-Id` 时校验归属（`get_order`/`list_orders` 返回 403） |
| 13 | 用户不能访问其他用户 AfterSale | `get_after_sale`/`list_after_sales` 通过归属订单的 `user_id` 校验，越权返回 403 |
| 14 | 普通用户不能绕过审核执行退款 | 审核（`/review`）强制要求 `X-User-Role ∈ {reviewer, admin}`，否则 403；售后不审核则停在 `PENDING`，退款被拒 |

> 鉴权基于请求头 `X-User-Id`（归属）/ `X-User-Role`（审核角色）。仅当携带这些头时才强制执行；未携带时保持原有（可信内网/测试）行为，故既有测试不受影响。

## 状态流转

```
订单:  CREATED ──支付──▶ PAID ──退款──▶ REFUNDED
售后:  PENDING ──审核──▶ APPROVED / REJECTED ──渠道退款──▶ REFUNDED
                                    └──渠道失败──▶ REFUND_FAILED（可重试）
```

> 注意：本地只有在**第三方支付渠道确认成功**后才会进入 `REFUNDED`。渠道失败记为
> `REFUND_FAILED`，订单保持 `PAID`、累计退款金额不变，可用同一售后（或同一
> `Idempotency-Key`）重试。详见下文「第三方渠道退款网关」。

约束（接口会返回 409/400 拦截非法流转）：

- 仅 `CREATED` 订单可支付；仅 `PAID` 订单可发起售后。
- **一个订单可存在多个售后申请**（多次发起互不阻塞）。
- 仅 `PENDING` 售后可审核；仅 `APPROVED` 售后可退款。
- **支持部分退款**：退款接口可指定 `refund_amount`，不指定则退「剩余可退金额」（订单金额 − 已成功退款金额）。
- **`refund_amount` 必须大于 0**；若剩余可退金额为 0 也返回 400。
- **累计退款限额**：同一订单所有成功退款金额之和不得超过订单实际支付金额；单次申请金额超过剩余可退时，按「剩余可退金额」退款（clamp，而非拒绝），保证累计金额永不超过订单实际支付金额。
- **仅成功退款计入累计**：只有状态变为 `REFUNDED` 的售后才累加 `order.refunded_amount`；`PENDING`/`APPROVED`/`REJECTED` 均不计入。
- 订单在「累计退款达全额」后才置为 `REFUNDED`，部分退款期间保持 `PAID`。

## 幂等性（应对重复提交 / 网络超时）

退款接口 `POST /after-sales/{after_sale_id}/refund` 具备双重幂等保护：

- **资源级幂等**：同一个 `AfterSale` 最多只能成功退款一次。对已经处于 `REFUNDED` 的售后再次发起退款，接口直接返回既有结果（200），**不会**重复扣减累计退款金额。
- **幂等键（Idempotency-Key）**：请求可携带 `Idempotency-Key` 请求头。相同键的重复请求（典型如客户端因网络超时未收到响应而重放）会被去重，直接返回首次处理成功的结果，不重复退款。
  - 仅「成功（2xx）」的退款结果会被缓存；失败请求（如审核未通过、幂等键未在成功结果上缓存等）不缓存，允许客户端用同一幂等键修正后重试。
  - 去重判断在全局锁内原子完成，重复提交不会破坏累计退款金额上限。

说明：幂等键已落库（SQLite `idempotency` 表），多 Worker 之间天然共享；生产环境如需
更短的恢复时间可配合带 TTL 的缓存（如 Redis），但核心不变量由数据库事务保证。

## 多 Worker 并发控制

服务可能以多个 Worker（进程）部署。两个 Worker 可能同时处理：

1. 同一个 `AfterSale`；
2. 同一 `Order` 下的多个 `AfterSale`。

退款逻辑集中在 `store.refund_transaction`，在**单个 `BEGIN IMMEDIATE` 事务**内完成
「幂等去重 → 资源级去重 → 额度校验 → 条件写回」：

- **串行化写入**：`BEGIN IMMEDIATE` 会获取数据库写锁，多个进程的并发退款被串行执行，
  避免 read-modify-write 竞态。
- **同一 AfterSale 最多成功退款一次**：`UPDATE after_sales ... WHERE id=? AND status='APPROVED'`
  为条件更新，仅当仍是 `APPROVED` 时才置为 `REFUNDED`；若 `rowcount == 0`，说明并发的
  其它 Worker 已抢先退款，本事务回滚并直接返回既有结果（200），不二次累加。
- **累计退款不超过订单实付金额**：`UPDATE orders SET refunded_amount = refunded_amount + ?
  ... WHERE id=? AND refunded_amount + ? <= amount` 为条件更新；若 `rowcount == 0`，说明
  额度已被并发的其它退款消耗，整体回滚（AfterSale 的更新一并撤销），不污染累计值。
- **跨 Worker 幂等键**：`idempotency` 表以 `key` 为主键（唯一约束），同一 `Idempotency-Key`
  的重复请求（如网络超时重放）直接复用已存结果。

并发正确性验证见 `tests/test_concurrency.py`（线程级 + 多进程级，均断言最终业务结果）。

### 替代方案与限制

- **替代方案 A·乐观并发（版本号 / 条件更新）**：不依赖 `BEGIN IMMEDIATE` 全局写锁，
  仅在更新时带版本或额度条件，冲突则重试。优点：写并发度更高；缺点：需要重试逻辑，
  且条件更新已在本实现中作为「二次保护」保留。
- **替代方案 B·分布式锁（Redis/ZooKeeper）**：在应用层用一把分布式锁保护退款临界区。
  优点：可与异构存储解耦；缺点：引入额外依赖与单点，且仍须把状态落共享存储。
- **替代方案 C·数据库行锁 / `SELECT ... FOR UPDATE`**：在支持行锁的数据库（PostgreSQL、
  MySQL InnoDB）上更细粒度。SQLite 无真正行锁，`BEGIN IMMEDIATE` 是等价且简单的串行化手段。
- **限制**：
  - SQLite 写操作全局串行，高写入吞吐场景会成为瓶颈；高并发生产建议换 Postgres 等，
    并保留「条件 UPDATE」做不变量保护。
  - 依赖 `busy_timeout` 等待写锁；极端长事务下可能出现等待，本服务退款事务都很短，可接受。
  - 本实现未对 `pay` / `review` 等高竞争写做额外加锁（其状态机本身幂等、且不影响退款额度），
    如未来出现高并发审核冲突，可同样改为条件更新。

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
| POST | `/after-sales/{after_sale_id}/refund` | 执行退款，body: `{refund_amount?}`（不传退剩余全部）；支持 `Idempotency-Key` 头做幂等去重 |

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
  models.py       # 领域模型与状态枚举（含 REFUND_FAILED）
  schemas.py      # 请求体校验
  store.py        # SQLite 存储层（多 Worker 安全）
  gateway.py      # 第三方支付渠道退款网关抽象（可替换）
  requirements.txt
  tests/test_api.py
  tests/conftest.py              # 将项目根加入 sys.path，保证干净环境直接可运行
  tests/test_concurrency.py
  tests/test_refund_gateway.py  # 第三方成功/失败的确定性测试
  tests/test_review_comment_r4.py
  tests/test_security_r7.py      # 安全 + 分页/索引 回归
  tests/test_round8.py           # 六大类 14 子项集中回归
  tests/test_final_acceptance_r9.py  # 最终交付：14 条核心保证逐条验收
```

## 第三方渠道退款网关

原退款流程只更新本地状态、从未真正调用第三方支付渠道，会出现「渠道失败但本地显示
退款成功」的不一致。现把「调用渠道」抽成可替换的 `RefundGateway`（见 `gateway.py`）：

- `RefundResult`：渠道结果（`success / channel_refund_id / error`）。
- `RefundGateway`（协议）：`refund(*, payment_ref, after_sale_id, amount)`。
- `RealRefundGateway`：生产用，基于 httpx 调用真实渠道，由 `REFUND_CHANNEL_URL` 启用；
  未配置时返回失败（而非静默成功）。
- `FakeRefundGateway`：测试用，确定性模拟成功/失败（`fail=`、`fail_predicate=`）。
- `SuccessRefundGateway`：未配置真实渠道时的成功占位，作为默认网关，保持既有
  happy-path 与一致性测试通过。

`store.Store` 持有 `gateway`，`refund_transaction` 在 `BEGIN IMMEDIATE` 事务内、把本地
置为 `REFUNDED` **之前**调用渠道：

- 渠道成功 → 走原有「条件 UPDATE」把 `after_sales`/`orders` 置为 `REFUNDED`；
- 渠道失败 → 仅把 `after_sales` 置为 `REFUND_FAILED`，**不修改**订单累计金额/状态，
  且**不缓存**幂等键（允许同键重试）。

退款接口在渠道失败时返回 **502**；`REFUND_FAILED` 的售后可再次退款（重试），成功后
进入 `REFUNDED`。确定性复现见 `tests/test_refund_gateway.py`。

---

## 最终架构说明（Final Architecture & Core Guarantees）

### 1. 分层架构

```
                 HTTP (FastAPI) + 鉴权请求头 (X-User-Id / X-User-Role)
                          │
                          ▼
   app.py ── schemas.py（入参校验）──► store.py（持久化 + 退款核心事务）
                                          │
                                          ▼
                              SQLite(共享文件, WAL)  ◄── 多 Worker 共享
                                          │
                                          ▼
                              gateway.py（第三方退款渠道抽象）
```

- **app.py**：FastAPI 路由层。每个写接口在调用 `store` 前先做「归属/角色」校验，并把
  业务状态码（200/400/409/502/403）映射为 HTTP 状态码。
- **schemas.py**：pydantic 入参校验（`amount>0`、`refund_amount>0` 等），把非法金额在
  进入业务逻辑前就挡在 422。
- **store.py**：唯一有状态的核心。所有一致性逻辑（幂等去重、资源级认领、额度预留、写回）
  都集中在 `Store.refund_transaction` 内，由 SQLite 事务保证原子性。
- **gateway.py**：`RefundGateway` 协议 + 可替换实现（`RealRefundGateway` / `FakeRefundGateway`
  / `SuccessRefundGateway`）。`store` 持有 `gateway`，在「调用渠道」与「本地落库」之间解耦，
  使第三方成功/失败成为可注入的确定性变量。
- **models.py**：`Order` / `AfterSale` 实体与状态枚举。

### 2. 退款核心算法（两阶段，缩短写锁持有）

`refund_transaction(after_sale_id, requested, idempotency_key)` 把慢速的第三方渠道调用
移到数据库写锁之外，避免「持有写锁等待网络」导致全局串行化：

- **阶段 1（`BEGIN IMMEDIATE` 短事务）**：幂等键去重 → 资源级去重（已 `REFUNDED` 直接返回）
  → 认领（把 `APPROVED`/`REFUND_FAILED` 原子翻成 `REFUNDING`，同一售后仅 1 个工作者驱动渠道）
  → 读订单并校验金额 → **在调用渠道「之前」用条件 `UPDATE ... WHERE refunded_amount + ? <= amount`
  预留额度**。认领 + 预留都在锁内、无网络等待，写锁仅极短持有。
- **阶段 2（无锁）**：调用第三方支付渠道（不持任何 DB 锁，不阻塞其它退款）。
- **阶段 3（`BEGIN IMMEDIATE` 短事务）**：渠道成功 → 售后置 `REFUNDED`、订单按累计额度回写状态；
  渠道失败 → 释放阶段 1 预留额度、售后置 `REFUND_FAILED`（可重试）、订单保持 `PAID`、
  **不缓存**幂等键。

### 3. 多 Worker 不变量如何成立

所有一致性由「数据库层」而非「应用层锁」保证，因此天然跨进程：

1. `BEGIN IMMEDIATE` 在事务开始即取 SQLite 写锁，把并发写串行化；
2. 认领 `UPDATE ... WHERE status IN ('APPROVED','REFUND_FAILED')` 保证同一售后最多 1 个成功退款；
3. 额度 `UPDATE ... WHERE refunded_amount + ? <= amount` 作为 SQL 层「校验并写回」的原子判定，
   并发下累计退款金额永不突破订单实付金额；
4. `idempotency` 表主键唯一约束，使同一 `Idempotency-Key` 跨 Worker 共享去重。

索引（`idx_after_sales_order_id` / `idx_after_sales_status` / `idx_idempotency_key`）把点查
维持在 O(log n)，避免 Refund 数量增长后的查询退化；列表接口 `limit/offset` 分页避免无界加载。

### 4. 安全模型

鉴权基于请求头 `X-User-Id`（归属）与 `X-User-Role`（审核角色）：

- **归属校验**：`get_order` / `list_orders` / `get_after_sale` / `list_after_sales` /
  `refund` 在携带 `X-User-Id` 时校验资源归属，越权返回 403（防 IDOR）。
- **审核角色**：`/review` 强制要求 `X-User-Role ∈ {reviewer, admin}`，否则 403。
  普通用户无法把 `PENDING` 售后审核为 `APPROVED`，因此无法「自评自批」绕过审核去退款；
  未携带角色头时保持可信内网行为，既有测试不受影响。

### 5. 14 条核心保证如何被满足（速查）

| # | 保证 | 关键落点 |
| --- | --- | --- |
| 1 | paid order 可以退款 | `create_after_sale` 要求 `PAID`；`refund_transaction` 校验后调渠道落 `REFUNDED` |
| 2 | unpaid order 不能退款 | `create_after_sale` 在 `CREATED` 返回 409；`refund_transaction` 存储层再卡 `status != PAID` |
| 3 | 一个订单支持多个 AfterSale | `create_after_sale` 不限数量，各自独立审核/退款 |
| 4 | 累计成功退款不超过 paid_amount | 整数分运算；超额按剩余金额 clamp 退款；阶段 1 条件 `UPDATE ... WHERE CAST((refunded_amount+?) *100 AS INTEGER) <= CAST(amount*100 AS INTEGER)` 预留额度，并发超额回滚 |
| 5 | 一个 AfterSale 最多一个成功退款 | 认领 `UPDATE ... WHERE status IN ('APPROVED','REFUND_FAILED')`；`REFUNDED` 重放只返回既有结果 |
| 6 | duplicate request 不产生重复有效退款 | 幂等键（唯一约束）+ 资源级守卫，重放只退一次 |
| 7 | 非法状态转换被拒绝 | `PENDING`/`REJECTED`/`REFUNDING` 退款返回 409；重复审核/支付被状态机拦截 |
| 8 | REFUND_FAILED 可以 retry | 失败仅置 `REFUND_FAILED` 并释放额度、不缓存幂等键，可再次退款 |
| 9 | REFUNDED 不能 retry | 已 `REFUNDED` 重放直接返回既有结果，不二次调渠道/扣减 |
| 10 | 第三方失败不能导致本地退款成功 | 渠道失败不写 `REFUNDED`：订单保持 `PAID`、累计不变、本地 `REFUND_FAILED`（502） |
| 11 | multi-worker 保持核心 invariant | 共享 SQLite + `BEGIN IMMEDIATE` 串行化 + 条件 UPDATE + 唯一幂等键（线程级/进程级均验证） |
| 12 | 用户不能访问其他用户订单 | 订单接口携带 `X-User-Id` 校验归属，越权 403 |
| 13 | 用户不能访问其他用户 AfterSale | 售后接口经归属订单 `user_id` 校验，越权 403 |
| 14 | 普通用户不能绕过审核执行退款 | `/review` 强制 reviewer 角色，否则 403；未审核停 `PENDING` 退款被拒 |

> 上述 14 条全部由 `tests/test_final_acceptance_r9.py` 逐条确定性覆盖（G1–G14），
> 并辅以 `tests/test_concurrency.py`（线程级 + 多进程级）、`tests/test_refund_gateway.py`
> （第三方成功/失败）、`tests/test_security_r7.py`（安全 + 分页/索引）等回归用例。

### 6. 干净环境运行

```bash
# 依赖（仅测试运行所需）：fastapi / uvicorn / pydantic / httpx / pytest
python -m pip install -r requirements.txt

# 运行全部测试（确定性、可重复）
python -m pytest tests -v
```

默认网关为 `SuccessRefundGateway`（无真实渠道环境下的成功占位），无需任何外部服务即可
让完整测试套件在干净环境下通过；接入生产渠道只需配置 `REFUND_CHANNEL_URL`。

