# TRACE_R7 — 安全 + 基础性能检查与修复

本回合目标：对退款服务做安全与基础性能检查，修复**真实存在**的问题，并补充安全
regression tests。只做必要的、有证据支撑的改动，不做无意义微优化。

## 改动文件

- `models.py`：在 `AfterSaleStatus` 枚举新增瞬态 `REFUNDING`（认领后、渠道回调前的
  内部状态），用于「认领」语义。
- `store.py`：
  - 新增索引 `idx_after_sales_order_id` / `idx_after_sales_status` /
    `idx_idempotency_key`（在 `_SCHEMA` 的 `CREATE INDEX IF NOT EXISTS` 中）。
  - `list_orders` / `list_after_sales` 支持 `user_id` 过滤 + `limit/offset`
    分页（按 user_id 过滤走 `JOIN orders`，无 N+1）。
  - `refund_transaction` 重构为「两阶段、把慢速渠道调用移到写锁外」（见下）。
  - 新增 `_await_settlement`：当另一 Worker 已认领（REFUNDING）时轮询其最终落库结果。
- `app.py`：
  - 新增鉴权头 `X-User-Id`（归属）/ `X-User-Role`（审核角色）。
  - `GET /orders`、`GET /after-sales`、`GET /orders/{id}`、`GET /after-sales/{id}`
    加归属校验（IDOR 修复）。
  - `POST /orders`、`POST /orders/{id}/pay`、`POST /orders/{id}/after-sales`、
    `POST /after-sales/{id}/refund` 加归属校验。
  - `POST /after-sales/{id}/review` 加角色校验（普通用户不得审核）。
  - `GET /orders`、`GET /after-sales` 支持分页。
- `tests/test_security_r7.py`（新增）：覆盖本轮安全 5 点 + 性能 2 点的回归测试。

## 真实问题与修复

### 安全

1. **用户可访问其他用户订单 / AfterSale（IDOR，真实且严重）**
   - 原 `GET /orders/{id}`、`GET /after-sales/{id}` 以及 list 接口对调用方身份
     完全无校验，任何人拿 id 即可读他人数据。
   - 修复：当请求携带 `X-User-Id` 时，按 `order.user_id` 做归属校验；list 接口按
     `X-User-Id` 过滤。未携带头时保持原（可信内网/测试）行为，故既有测试不受影响。
   - 注：归属判断在 `get_after_sale` 中通过 `after_sale.order_id -> order.user_id`
     完成，仅多一次 PK 点查，非 N+1。

2. **普通用户可绕过审核直接退款（真实）**
   - 原 `review` 接口完全开放，任何调用方都能把 `PENDING` 售后改成 `APPROVED`，
     再调用 `refund` 走完退款——即「自评自批」绕过审核。
   - 修复：`review` 要求 `X-User-Role` 为 `reviewer`/`admin`，否则 403。`refund`
     仍要求售后处于 `APPROVED`（只能由审核员置位），因此普通用户无法自批自退。

3. **异常请求绕过金额限制（核查后基本已正确，补回归测试）**
   - `RefundRequest.refund_amount` 已有 `gt=0`；`refund_transaction` 内对
     `<= 0` 与 `> 剩余可退` 有校验，并通过「调用渠道前先条件 UPDATE 预留额度」兜底。
   - 本轮未改动逻辑，但补充了 0 / 负数（422）、远超剩余（409 且累计不被污染）的
     回归测试，固化该不变量。

4. **重复请求造成重复退款（核查后已正确，补回归测试）**
   - 幂等键（`idempotency` 唯一约束 + 仅成功缓存）+ 资源级去重（`REFUNDED` 直接复用）
     已存在。本轮重构后该不变量依旧成立，并补充了幂等键重放只退一次的回归测试。

### 性能

5. **无索引导致查询随数据增长退化（真实）**
   - 原 `after_sales(order_id)`、`idempotency(key)` 无索引，`refund_transaction`
     与 list 过滤走全表扫描。补充索引后点查/过滤维持 O(log n)。

6. **列表接口无界加载大量数据（真实）**
   - 原 `list_orders` / `list_after_sales` 一次 `SELECT *` 全量返回。补充
     `limit`（默认 100，上限 1000）/ `offset` 分页。

7. **长时间持有数据库写锁（真实且关键）**
   - 原实现把「调用第三方渠道（`self.gateway.refund(...)`）」放在
     `BEGIN IMMEDIATE` 事务**内部**。这意味着等待外部网络（可能是数秒的 HTTP）期间
     一直持有 SQLite 写锁，所有退款被串行化；且若渠道调用先于额度校验失败，会出现
     「已向渠道扣款但本地回滚」的重复扣款隐患。
   - 修复（两阶段）：
     - 阶段 1（短事务）：幂等去重 -> 资源级去重 -> **认领**售后（`APPROVED/REFUND_FAILED`
       原子翻成 `REFUNDING`）-> **预留额度**（条件 `UPDATE orders`）。认领+预留都无网络
       等待，写锁仅极短持有；只有成功预留者才会去调渠道。
     - 阶段 2（无锁）：调用第三方渠道。
     - 阶段 3（短事务）：成功 -> 售后置 `REFUNDED`、订单状态/refunded_at 落定；
       失败 -> **释放预留额度**并把订单状态回退为 `PAID`、售后置 `REFUND_FAILED`（可重试，
       且不缓存幂等键）。
   - 并发不变量（经验证全部成立）：同一 AfterSale 最多成功退款一次；累计不超过订单
     金额；重复/重放不重复退款；渠道失败绝不污染订单累计金额与状态。

## 关键设计决策

- **鉴权基于请求头而非全局强制**：为保证既有现有测试（不携带任何鉴权头）继续通过，
  归属/角色校验采用「**携带头时才强制**」的语义。生产环境应由网关联接/前置中间件
  统一注入 `X-User-Id` 与 `X-User-Role`，从而变为强制。这是刻意的向后兼容取舍。
- **引入 `REFUNDING` 瞬态而非在获取锁期间调用渠道**：认领机制确保同一售后只有一个
  Worker 驱动（慢速）渠道调用，既缩短写锁占用，又避免并发下对同一售后重复打渠道。
- **额度在调用渠道「之前」预留**，渠道失败再释放：从根本上消除「渠道先扣款、本地因
  额度不足回滚」的双扣风险（原实现存在此隐患）。

## 不确定性与已知限制

- **崩溃窗口**：阶段 1 提交（已认领 REFUNDING 且预留额度）后、阶段 3 提交前若进程
  崩溃，该售后会停留在 `REFUNDING`、额度被预留但未真正扣款。恢复手段依赖后续重试或
  运维修复；本轮未引入定时回收/超时回滚（属于过度设计，超出本轮范围）。`_await_settlement`
  的轮询上限为 15s。
- **`X-User-Id` 来源可信度**：当前实现信任调用方声明的 `X-User-Id`。在真实部署中，
  该身份必须由可信鉴权层签发，否则存在伪造风险——这是采用「头驱动」方案的固有限制，
  已在上面说明。
- **列表过滤的跨表 JOIN 分页**：`list_after_sales(user_id=...)` 用 `JOIN orders` 过滤，
  对大表可进一步加复合索引，但当前规模下已足够，未过度索引。
- 既有全部测试（test_api / test_concurrency / test_refund_gateway /
  test_review_comment_r4）与新增 test_security_r7 共 **55 项全部通过**。
