# TRACE_R4 — 对 Review Comment 的复核

## 本轮目标（ROUND PROMPT）
Review Comment：
> 退款执行前会先读取售后状态，再决定是否退款。如果两个 Worker 同时读取到相同状态，
> 是否可能重复退款？累计退款金额的检查是否也存在类似问题？

要求：判断该评论是否成立；若成立则定位根因、最小化修复、加 regression test、跑测试；
不要无关重构。

## 结论
**该 Review Comment 在「当前实现」下不成立（NOT 成立）。**

## 判断依据（读代码）
`store.refund_transaction`（store.py:236-377）已经把"读状态 → 判断是否可退 → 写回"
全部包裹在**单个 `BEGIN IMMEDIATE` 事务**（store.py:258）中，而非评论假设的那种
"先 SELECT 读状态、再单独发 UPDATE"的脱锁两步：

1. **串行化来源**：`BEGIN IMMEDIATE` 在事务一开始就向 SQLite 申请写锁（WAL 模式下为
   RESERVED 锁），配合 `busy_timeout=15000`（store.py:116），多个 Worker 的退款被
   数据库层串行化。因此"读状态"这一步并不独立于锁之外，两个 Worker 不可能在都读到
   APPROVED 之后还各自穿插地写回。
2. **双重条件 UPDATE 做二次保护**（即便将来串行化被绕过也不会破坏不变量）：
   - 售后级：`UPDATE after_sales SET status='REFUNDED' ... WHERE id=? AND status='APPROVED'`
     （store.py:319-331）。只有真正把 APPROVED 翻成 REFUNDED 的那个 Worker 的
     `rowcount==1`；输家 `rowcount==0`，回滚后读回已 REFUNDED 的行、返回既有结果，
     不产生第二个有效退款。
   - 累计额度级：`UPDATE orders SET refunded_amount=? ... WHERE id=? AND refunded_amount + ? <= amount`
     （store.py:340-353）。这是 SQL 层的"原子校验并写回"；`rowcount==0`（额度已不够）
     时整体回滚，Order 的累计值不被污染。

结论：评论担心的"同时读到相同状态 → 重复退款 / 突破累计上限"在当前代码中不会发生。
R3 引入的 IMMEDIATE 事务已关闭该 TOCTOU 竞态。

## 文件变更
- **新增** `tests/test_review_comment_r4.py`：针对评论原话的 4 个 regression test，
  直接复现"两个 Worker 同时读到相同状态"的场景：
  - `test_review_comment_simultaneous_read_same_after_sale_no_duplicate_refund`：
    线程级 + `threading.Barrier(N=8)`，让 8 个线程在同一时刻同时发起退款同一售后，
    断言累计金额恒为 100（不翻倍）。
  - `test_review_comment_cumulative_cap_under_simultaneous_reads`：
    两个线程同时按"剩余全额"各自退款一个售后，断言累计金额 == 100、恰好一个成功。
  - `test_review_comment_two_workers_same_after_sale_no_double`：
    进程级（派生 2 个真实进程连同一 SQLite 文件）同时退款同一售后，断言不重复退款。
  - `test_review_comment_two_workers_cumulative_cap_no_breach`：
    进程级两个 Worker 各自退款一个售后、都按剩余全额申请，断言累计不超过订单金额。
- **未修改** `app.py` / `store.py` / `models.py` / `schemas.py`：评论不成立，无需修复，
  也未做任何无关重构。

## 关键设计决策
- 判定评论"不成立"后，没有强行制造修复（避免无关重构/过度改动），而是补上一组
  最能还原评论原话（"两个 Worker 同时读到相同状态"）的并发回归测试，用证据固化结论，
  并防止未来有人把"读状态/写回"拆出事务而重新引入竞态。
- 线程级用例用 `threading.Barrier` 对齐线程起点，最大化"同时读到 APPROVED"的概率；
  进程级用例用派生进程模拟真正的多 Worker（各自独立连接、共享同一 SQLite 文件）。

## 问题与修复
- 无代码 bug 需要修复。
- 运行环境注意：`python -m pytest tests` 必须在项目根目录执行（cwd 决定 `app`/`store`
  能否被 import，因为 `python -m` 会把 cwd 加入 sys.path）。Bash 工具在本机 PATH 损坏，
  统一用 PowerShell + 绝对解释器路径运行。

## 测试运行结果
`python -m pytest tests -v` → **34 passed（含 4 个新增 R4 用例）**，2 个第三方弃用告警
（fastapi/starlette testclient，与本次无关）。

## 不确定 / 已知限制
- 当前安全性**依赖**"读状态 + 判断 + 写回"始终位于同一个 `BEGIN IMMEDIATE` 事务内。
  若将来有人在事务外新增"先 SELECT 读状态再调退款"的预检（例如单独的 GET 端点或
  app.py 中的防御性提前读取），就会重新引入评论担心的 TOCTOU。代码注释
  （store.py / app.py）已写明该约束，可作为后续 Code Review 的关注点，但本轮未改动。
- 进程级用例仅在测试进程内验证；SQLite WAL + IMMEDIATE 的多进程串行化行为在不同
  文件系统/挂载选项下理论上仍受 `busy_timeout` 保护，本机测试通过。
