# TRACE_R3 — 多 Worker 并发控制（Round 3）

## 1. 本轮任务

服务可能以多 Worker（多进程）部署。两个 Worker 可能同时处理：
1. 同一个 AfterSale；
2. 同一 Order 下的多个 AfterSale。

需要确认并加固两条业务不变量：
- 同一个 AfterSale 最多一个成功退款；
- 成功退款累计金额不超过订单实际支付金额。

当前数据库：SQLite（提示语所述；但实际上一版代码是进程内存字典，见下「问题发现」）。

## 2. 分析当前实现（问题发现）

读 `store.py` / `app.py` 后发现：

- 上一版存储层是**进程内存字典** + 一把 `threading.Lock`。代码注释声称「在持有
  全局锁的前提下完成」幂等与额度校验。
- 关键缺陷：`threading.Lock` 是**进程内**的。多 Worker = 多个进程，每个进程各持一份
  内存数据与各自的锁，锁**无法跨进程**保护。因此：
  - 两 Worker 同时处理同一 AfterSale：都读到 `APPROVED` → 都执行退款 → **重复退款**；
  - 两 Worker 同时处理同 Order 的多个 AfterSale：都按同一 `remaining` 累加 →
    **累计退款突破订单金额**。
- 另外，提示语说「当前数据库使用 SQLite」，但代码实际是内存字典。内存字典在跨进程下
  连「同一份数据」都没有，根本无法满足多 Worker 场景——所以必须先落一个**共享、事务一致**
  的存储，SQLite 正是提示语给出的目标。

结论：原实现在多 Worker 下**不满足**两条不变量，必须重构存储与并发控制。

## 3. 选择的并发控制方案

**共享 SQLite + `BEGIN IMMEDIATE` 写事务 + 条件 UPDATE（+ 幂等键唯一约束）。**

理由：
- 多 Worker 场景首要条件是「共享且事务一致」的存储，SQLite 文件被所有 Worker 进程
  共享，零额外依赖，契合提示语。
- SQLite 没有真正的行级锁，`BEGIN IMMEDIATE` 会获取数据库**写锁**，从而把并发写入
  **串行化**，从根本上消除 read-modify-write 竞态。
- 再叠加「条件 UPDATE」做数据库层二次保护，即便将来去掉全局锁也不变量仍成立：
  - 同一 AfterSale：`UPDATE ... WHERE id=? AND status='APPROVED'`，`rowcount==0` 即已被
    并发方抢先退款，回滚并返回既有结果。
  - 累计额度：`UPDATE orders SET refunded_amount = refunded_amount + ? ... WHERE ... AND
    refunded_amount + ? <= amount`，`rowcount==0` 即额度不足，整体回滚。
- 幂等键落表并以 `key` 为主键（唯一约束），跨 Worker 去重天然一致。
- 连接策略：每线程一条连接（线程本地），`check_same_thread=False`，WAL 模式 +
  `busy_timeout=15s`，使并发真正发生在数据库层、而非被单把 Python 锁串行化。

## 4. 修改的文件

- `store.py`（重写）：
  - 新增 `Store`，底层为 SQLite（`_DEFAULT_DB` 取 `REFUND_DB_PATH` 或系统临时目录
    `hy3_refund.db`）；WAL + busy_timeout；线程本地连接；`executescript(_SCHEMA)` 建表。
  - 提供 `insert_*` / `save_*` / `get_*` / `list_*` 以及 `reset()`（兼容旧测试）。
  - 核心 `refund_transaction(after_sale_id, requested, idempotency_key)`：单事务内完成
    幂等去重 → 资源级去重 → 额度校验 → 条件 UPDATE（AfterSale）→ 条件 UPDATE（Order）
    → 写入幂等键。所有分支都正确 `COMMIT`/`ROLLBACK`。
  - 删除旧的进程内 `threading.Lock`、`IdempotencyRecord`、内存字典。
- `app.py`（改写）：各端点改为调用 store 的 load/save；退款端点委托 `store.refund_transaction`。
  业务规则、HTTP 状态码（200/400/404/409）与之前完全一致，保证旧测试不回归。
- `tests/test_concurrency.py`（新增）：见第 5 节。
- `README.md`：更新运行环境（SQLite）、幂等说明，新增「多 Worker 并发控制」章节
  （方案 / 替代方案 / 限制）。
- 注：`models.py` / `schemas.py` 未改动。

## 5. 并发测试（验证实际业务结果，而非只发请求）

`tests/test_concurrency.py`，全部断言读取**最终落库状态**：

- `test_thread_concurrent_same_after_sale_only_one_refund`：同进程 10 线程并发退同一
  AfterSale（全额）→ `refunded_amount == 100`、订单 `REFUNDED`、该售后仅一次退款。
- `test_thread_concurrent_multiple_after_sales_over_budget`：5 个 AfterSale 各退全额 100
  （共 500 >> 100）→ `refunded_amount == 100`、恰好 1 个成功（200）、其余 4 个 409。
- `test_thread_concurrent_multiple_after_sales_exact_fill`：退 60 + 40 正好凑满 100 →
  两个都 200、累计恰 100。
- `test_http_concurrent_same_after_sale_only_one_refund`：经 TestClient HTTP 接口并发退同一
  AfterSale（10 并发）→ 同样 `refunded_amount == 100`。
- `test_multiprocess_same_after_sale_only_one_refund`：派生 6 个进程共享同一 SQLite 文件，
  并发退同一 AfterSale → `refunded_amount == 100`（真正跨进程验证）。
- `test_multiprocess_multiple_after_sales_over_budget`：5 个进程各退全额 100 →
  `refunded_amount == 100`、恰好 1 个售后成功。

运行结果：`pytest tests -v` → **30 passed**（原 24 + 新增 6），无失败。

## 6. 遇到的问题与修复

- 初始 `cd` / `ls` 在 Bash 工具中不可用（MSYS 环境 PATH 问题）。改用 PowerShell 排查后，
  最终统一用绝对路径 Python 解释器 + `PYTHONPATH=<项目目录>` 跑 pytest，输出重定向到文件再 Read。
- 写 `store.py` 时 Write 工具首次因参数顺序报错，重发后成功。
- 退款事务中「AfterSale 条件 UPDATE 失败（被并发方抢先）」的分支：先 `ROLLBACK` 再在
  自动提交模式下 `SELECT` 读回赢家结果返回 200——确保不残留打开事务、且返回的是正确既有结果。
- 多进程测试最初想用 `multiprocessing.Barrier`/`Queue` 做精确同步，考虑到 Windows `spawn`
  下 pickle 复杂性与「不变量本身与时机无关」的特性，改为：仅把 db 路径与简单参数传给子进程，
  父进程在 `join` 后读取最终落库状态断言。既稳定又不依赖时序，仍能真实触发跨进程并发。

## 7. 不确定性与已知限制

- SQLite 写操作全局串行（`BEGIN IMMEDIATE` 写锁），极高写入吞吐会成为瓶颈；生产高并发
  建议迁移到 PostgreSQL/MySQL 并保留「条件 UPDATE」作为不变量保护（已是本实现的二次防线）。
- 依赖 `busy_timeout` 等待写锁；本服务退款事务都很短，可接受。若未来出现长事务需注意。
- `pay` / `review` 等写操作未额外加并发保护：其状态机本身幂等（重复 pay 返回 409、重复
  review 返回 409），且不影响退款额度，故未改动；如未来出现高并发审核冲突可同样改为条件更新。
- 默认数据库文件位于系统临时目录（`REFUND_DB_PATH` 可覆盖）；多 Worker 必须指向**同一个**
  文件路径才共享状态，这是部署前提。
- 测试进程内用全局 `store`（默认 temp 库），多进程测试用独立临时库，二者互不干扰。
