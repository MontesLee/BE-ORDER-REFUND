# TRACE_R5 — 基于当前真实代码的说明

> 本文件的所有结论均来自本工作区当前代码：
> `app.py`、`store.py`、`models.py`、`schemas.py`、`tests/`。
> 未参考任何外部/评测材料，全部以代码为准。
> 运行 `pytest tests -v` 结果：**34 passed**。

---

## 1. 请求处理流程

整体是 FastAPI 单应用 + 一个 SQLite 存储单例 `store = Store()`（`store.py:381`）。

入口（`app.py`）：
- `POST /orders` → `create_order`：生成 `uuid` 订单，状态置 `CREATED`，落库。
- `GET /orders`、`GET /orders/{id}`：只读查询。
- `POST /orders/{id}/pay` → `pay_order`：仅在 `CREATED` 时把订单翻成 `PAID`，写 `paid_at`。
- `POST /orders/{id}/after-sales` → `create_after_sale`：仅当订单 `PAID` 时可建售后，初始 `PENDING`。
- `POST /after-sales/{id}/review` → `review_after_sale`：仅当 `PENDING` 时翻成 `APPROVED`/`REJECTED`。
- `POST /after-sales/{id}/refund` → `refund_after_sale`：核心写操作。

退款入口的细节（`app.py:140-157`）：
1. 从请求头读 `Idempotency-Key`（`Header(None, alias="Idempotency-Key")`），缺省为 `None`。
2. 解析可选 `RefundRequest`，取其 `refund_amount`（`None` 表示退剩余全部）。
3. 调用 `store.refund_transaction(after_sale_id, requested, idempotency_key)`，返回一个 `(status_code, body)` 元组。
4. 若 `status_code >= 400`，抛 `HTTPException(status_code, detail)`；否则把 `body` 反序列化成 `AfterSale` 返回。

其余写操作（建单/支付/审核）都比较薄，直接 `get_*` 校验后 `save_*` 落库，并发校验仅依赖状态前置判断，**没有**像退款那样放进 `BEGIN IMMEDIATE` 事务。这意味着"重复支付""重复审核"等并发问题在代码里只用"状态 != 期望"的 409 拦截，而未做数据库层条件更新——这是与退款不一致的一处实现（见第 7 点）。

---

## 2. 状态机

两个实体各自有状态枚举（`models.py:13-23`）。

**Order**：`CREATED → PAID → REFUNDED`
- `CREATED` 由 `create_order` 赋予。
- `PAID` 由 `pay_order` 在 `CREATED` 时翻转（非 `CREATED` 返回 409，`app.py:76-80`）。
- `REFUNDED` 由退款逻辑在"累计成功退款金额达到订单全额"时翻转（`store.py:335-339`：`new_refunded >= amount - 1e-9` 时置 `REFUNDED`，否则保持 `PAID`）。

**AfterSale**：`PENDING → APPROVED/REJECTED → REFUNDED`
- `PENDING` 由 `create_after_sale` 赋予，且仅当订单 `PAID`（`app.py:92-96`，非 `PAID` 返回 409）。
- `APPROVED`/`REJECTED` 由 `review_after_sale` 在 `PENDING` 时翻转（`app.py:126-133`，非 `PENDING` 返回 409；且 `REJECTED` 不可再 review/refund）。
- `REFUNDED` 由 `refund_transaction` 中条件 `UPDATE ... WHERE status='APPROVED'` 成功时翻转（见第 4、5 点）。

状态转换全部由"**先读状态、校验期望、再写状态**"完成；退款这条链路把"读+校验+写"整体包进一个 `BEGIN IMMEDIATE` 事务，因此状态机在并发下不会被撕裂（见第 6 点）。

⚠️ **与预期不一致之处（需明确指出）**：
`app.py:3-5` 注释写的状态流转是"已支付 --(累计退款达全额)--> REFUNDED"，这与实现一致；但 `models.py:1-5` 的模块 docstring 仍写着"本服务只考虑「全额退款」，因此退款金额恒等于订单金额"——**这是过时/错误的描述**。实际代码（`store.py:300-315`、`tests/test_partial_refunds_accumulate_and_close_order.py` 及 `test_api.py::test_partial_refunds_accumulate_and_close_order`）完整支持部分退款、多次退款累计、累计达全额才关单。请以代码行为准，不要被 `models.py` 的旧注释误导。

---

## 3. 什么条件下允许退款

退款是否被允许，全部由 `store.refund_transaction`（`store.py:236-377`）内的顺序判断决定：

1. 售后不存在 → `404`（`store.py:273-275`）。
2. 售后已 `REFUNDED` → 直接返回既有结果，视为"允许但幂等命中"，**不再累加**（资源级幂等，`store.py:280-282`）。
3. 售后状态不是 `APPROVED`（即仍 `PENDING` 或 `REJECTED`）→ `409`（`store.py:284-288`）。这是"不允许退款"的核心条件：必须先审核通过。
4. 关联订单不存在 → `404`（`store.py:294-296`）。
5. 退款金额必须 `> 0`：
   - 入参层：`schemas.py:28-30` 的 `RefundRequest.refund_amount` 带 `gt=0`，传 0/负数直接 `422`（见 `test_api.py::test_refund_amount_must_be_positive`）。
   - 代码层：`store.py:304-306` 又对计算后的 `refund_amount <= 0` 返回 `400`（例如默认退剩余金额时剩余已为 0 的情况）。
6. 退款金额不得超过"剩余可退金额" `remaining = round(amount - refunded, 2)`：
   - `requested is None` 时退 `remaining`（全额退剩余），否则退 `requested`（`store.py:300-301`）。
   - `refund_amount > remaining + 1e-9` → `409`（`store.py:307-315`）。
7. 真正写回还需通过"条件 UPDATE 的 rowcount"二次校验（见第 5 点），失败则整体回滚。

补充：订单一旦 `REFUNDED`（退满），因为其状态不再是 `PAID`，再 `create_after_sale` 会被 `app.py:92-96` 的 `PAID` 守卫拦截返回 `409`（`test_api.py::test_cannot_create_after_sale_on_fully_refunded_order`）。这条"退满后不能再开新售后"是**隐式**由 `PAID` 守卫实现的，并非显式写"若 REFUNDED 禁止"。

---

## 4. 幂等如何保证

有两层幂等保护，均在 `store.refund_transaction` 内：

**(A) 幂等键（请求级，跨 Worker 共享）** — `store.py:261-268` 与 `367-372`
- 进入事务后先查 `idempotency` 表（`key` 为 `PRIMARY KEY`，`store.py:62-66`）。若同一 `Idempotency-Key` 已存在，直接 `commit` 并返回**已缓存的结果**，不重复执行退款。
- 仅当退款**成功（200）**时才把结果写入 `idempotency` 表（`INSERT OR IGNORE ... status_code=200`，`store.py:367-372`）。
- **失败（404/409/400）不缓存**，因此客户端可用同一幂等键修正（如先审核）后重试并拿到成功结果（`test_api.py::test_idempotency_key_not_cached_on_failure` 验证）。
- 该查表动作在 `BEGIN IMMEDIATE` 持有写锁期间进行，所以并发同键请求被数据库串行化，先到者写入、后到者命中缓存，不会双退。

**(B) 资源级幂等（同一 AfterSale 至多一次成功退款）** — `store.py:280-282` 与 `318-331`
- 若售后已 `REFUNDED`，返回既有结果，不二次累加（即使没带幂等键也安全，`test_api.py::test_refund_same_after_sale_only_one_successful_refund`）。
- 写售后时用**条件 UPDATE**：`UPDATE after_sales SET status='REFUNDED', ... WHERE id=? AND status='APPROVED'`（`store.py:319-323`）。只有把 `APPROVED` 翻成 `REFUNDED` 的那个 Worker 的 `rowcount == 1`；并发输家 `rowcount == 0`，回滚后读回赢家已写好的结果返回（`store.py:325-331`）。

两层叠加：幂等键解决"客户端网络超时重放同一请求"，资源级守卫解决"即使换了幂等键、或根本不带键，对同一已退售后仍不会双退"。`test_idempotency_key_does_not_double_when_key_reused_after_success` 验证了后者。

---

## 5. 累计退款金额如何保证

累计退款金额存在 `orders.refunded_amount` 列（默认 0，`store.py:49`；`models.py:34`），**仅 REFUNDED 的售后才计入**。

保证机制是"**SQL 层原子的校验+写回**"，位于 `store.py:333-353`：

```sql
UPDATE orders SET refunded_amount=?, refunded_at=?, status=?
WHERE id=? AND refunded_amount + ? <= amount
```

- `?` 分别为 `new_refunded = round(refunded + refund_amount, 2)` 与本次 `refund_amount`。
- 该 UPDATE 在数据库层一次性完成"剩余额度是否够 + 写入新累计值"，不可被并发穿插。
- 若 `rowcount == 0`：说明在并发下额度已被别的退款消耗（`refunded_amount + refund_amount > amount`），此时 `conn.rollback()`，**连前面已更新的 after_sales 状态也一并撤销**，累计值不被污染（`test_api.py::test_refund_exceeds_remaining_returns_409` 中 `refunded_amount` 保持 80 不被污染）。
- 事务整体提交前，after_sales 的状态翻转（`store.py:319-323`）与 orders 的累计更新（`store.py:340-343`）在同一个 `BEGIN IMMEDIATE` 事务里，要么都成功、要么都回滚，保证一致性。
- 订单状态联动：`new_refunded >= amount - 1e-9` 时置 `REFUNDED`，否则保持 `PAID`（`store.py:335-339`）。

⚠️ **金额类型限制（设计取舍 / 与"教科书"差异）**：金额用 `REAL`（浮点）存储，靠 `round(..., 2)` 和 `1e-9` 容差规避误差（`store.py:300, 334, 337, 308`）。教科书/金融规范做法通常用整数分或 `Decimal` 避免浮点；当前实现在常规精度下通过测试，但浮点并非货币的最佳表示。

---

## 6. 多 Worker 如何保证

多 Worker 安全的核心思路：**把数据落到所有 Worker 共享的 SQLite 文件，由数据库层的写锁 + 条件 UPDATE 保证不变量**，而不是依赖进程内锁。

具体做法（`store.py`）：
- 共享存储：默认库为 `tempfile.gettempdir()/hy3_refund.db`，可用环境变量 `REFUND_DB_PATH` 指定独立文件（`store.py:69-71`）。多个 Worker 连同一文件即共享同一份数据。
- 并发友好的连接配置：`PRAGMA journal_mode=WAL` + `PRAGMA busy_timeout=15000`（`store.py:115-116`）。WAL 让读写更友好，写冲突时自动等待而非立即报错。
- 每线程一条连接：`threading.local()` + `check_same_thread=False`（`store.py:103-120`），让真正的并发发生在数据库层，而不被单把 Python 锁串行化。
- **`BEGIN IMMEDIATE` 写锁**：`refund_transaction` 一开头就 `cur.execute("BEGIN IMMEDIATE")`（`store.py:258`），事务开始即抢占 SQLite 写锁，把多个 Worker 的并发退款**串行化**。
- **条件 UPDATE 作二次保护**：即使将来去掉写锁/锁被绕过，`WHERE status='APPROVED'`（`store.py:319-323`）与 `WHERE refunded_amount + ? <= amount`（`store.py:340-343`）的 `rowcount` 校验仍能保证"同售后只退一次""累计不超额"。

测试覆盖两种真实并发（验证的是**最终落库业务结果**，而非请求是否同时发出）：
- 线程级：同进程多线程各自独立连接，`test_concurrency.py` 中 10 线程抢同一售后、5 个售后各退全额（共 500 > 100）等，断言累计恒为订单金额、恰一个成功。
- 进程级：`multiprocessing` 派生多个进程各自连同一 SQLite 文件，模拟真正的多 Worker（`test_multiprocess_same_after_sale_only_one_refund`、`test_multiprocess_multiple_after_sales_over_budget`，以及 R4 的 `test_review_comment_two_workers_*`）。
- 同步屏障强化：R4 测试用 `threading.Barrier` 让 N 个线程同一时刻发起，最大化"同时读到 APPROVED"的概率，仍不重复退款、不破额度。

结论：当前实现下 R4 那条"两个 Worker 同时读到相同状态是否会重复退款/破额度"的评论**不成立**，因为读+判断+写在单一 `BEGIN IMMEDIATE` 事务内，且叠加条件 UPDATE。

---

## 7. 当前方案有什么限制

1. **SQLite 不适合高并发写**。虽用 WAL + `busy_timeout`，但 `BEGIN IMMEDIATE` 仍有全局写锁，同一时刻只有一个 Writer 能提交；高吞吐/大量并发退款场景下，未抢到锁的 Worker 会等待直至 `busy_timeout`（15s）超时。生产级需要 PostgreSQL/Redis 等带更高并发写能力的存储（教科书常用 `SELECT ... FOR UPDATE` 或分布式锁）。

2. **仅限同机共享文件**。SQLite 的锁是文件级，要求所有 Worker 能访问同一份磁盘文件。若 Worker 分布在不同主机（网络文件系统），SQLite 的并发/持久性不可靠。当前多进程测试只是在同一台机器上共享 `tempfile` 文件，并未验证跨主机。

3. **金额用浮点（REAL）**。见第 5 点，浮点并非货币的理想类型，存在理论上的舍入风险（虽靠 `round`+`1e-9` 容差通过测试）。

4. **非退款写操作缺少数据库层原子保护**。只有 `refund_transaction` 用了 `BEGIN IMMEDIATE` + 条件 UPDATE。建单/支付/审核（`save_order`、`save_after_sale`）只是"读状态→判断→普通 UPDATE"，靠状态码 409 拦截。例如重复支付：两个 Worker 同时读到 `CREATED` 理论上都可能通过 `order.status != CREATED` 判断（该判断在各自连接里、非事务内），存在极小概率双写 `PAID`——虽然后写只是把 `PAID` 再写成 `PAID`（幂等无害），但这与退款的"硬保证"层级不一致。这是一致性保证不完全对称的一处薄弱点。

5. **幂等键全局唯一、跨售后共享**。`idempotency.key` 是表级主键（`store.py:62-66`）。按 REST 惯例幂等键应绑定"某类操作"，这里只有一个退款端点用它，所以可接受；但**若客户端把同一 `Idempotency-Key` 复用到不同 after_sale 上，会拿到第一个 after_sale 的缓存结果**——这属于误用，但实现不会报错，是个潜在 footgun。

6. **缺少显式的"订单已退满禁止再开售后"状态**。`test_can_create_after_sale_on_fully_refunded_order` 通过是因为订单退满后状态变 `REFUNDED`、不再是 `PAID`，被 `create_after_sale` 的 `PAID` 守卫顺带拦截。这是隐式约束，依赖"退满即 REFUNDED"的联动，可读性上不如显式写"REFUNDED 订单禁止新建售后"。

7. **无重试/退避骨架**。`busy_timeout` 是 SQLite 内置等待；代码没有对 `SQLITE_BUSY` 做应用层重试或指数退避。极端高竞争下直接以 409/超时体现，不会自愈。

8. **无真正的"部分退款"业务字段回查审计**。每次退款把 `refund_amount` 存到对应 after_sale 行，累计存到 order 行，但没有独立的"退款流水/ ledger"表。要审计"某次退款对应哪个幂等键、哪笔订单金额变动"需反查 `idempotency` 表与 after_sales 行，粒度有限。

---

### 一句话总结
退款链路通过"**共享 SQLite 文件 + `BEGIN IMMEDIATE` 写锁串行化 + 条件 UPDATE(rowcount 校验) + 幂等键表**"四重机制，在单文件、同机多 Worker 下保证"同一售后只退一次、累计不破订单金额"；但代价是 SQLite 写吞吐受限、金额用浮点、且仅退款操作有此硬保证（建单/支付/审核为非事务级软保证）。`models.py` 旧注释称"只考虑全额退款"与实际的部分退款实现不符，应以代码为准。
