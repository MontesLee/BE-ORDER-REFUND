# evidence — Hy3（BE-ORDER-REFUND 真实 Model Trial）

> 逐条对照 `rubric.md` §1 的 22 条命题判定：`PASS` / `FAIL`（本评测无 N/A）。
> 证据优先级：`TEST > CODE > TRACE > DOC > REVIEW`；客观 Rubric 必有自动化证据。
> **模型自报数字不采信**（协议 §6）：以评测方对冻结产物（`final-artifact/`，store.py @ 18:41:28）的独立复跑为准。本文件覆盖 18:37–39 一份对带 NameError 中间态产物的过期结论。

## 1. 判定表

| Rubric | Round | Result | Evidence type | Evidence path | Reason |
| --- | --- | --- | --- | --- | --- |
| IF-01 | R0 | PASS | TEST | `G-test_order.py::test_project_runs_and_basic_flow`（冻结产物 200）；`M-` 90/90 | 服务可启动、端点可服务、干净环境可跑 |
| IF-02 | R9 | PASS | TRACE/REVIEW | `_eval_progress/baseline_hy3_before_R9.txt`；`final-artifact/TRACE_R2.md…R9.md` | 逐文件增量演进（R2–R9 mtime/哈希快照），无大规模重写 |
| IF-03 | R9 | PASS | TEST+DOC | `r9_pytest.txt`(90 passed)；`final-artifact/README.md` | 全量套件绿；含实现+测试+README+requirements |
| FD-01 | R0 | PASS | TEST+CODE | `G-test_refund.py::test_unpaid_order_cannot_be_refunded`；`C-store.py` 卡 `status != PAID` | 未支付/未审核不退款 |
| FD-02 | R1 | PASS | TEST | `G-test_amount.py::test_multiple_partial_refunds` | 多售后部分退款累加正确 |
| FD-03 | R3 | PASS⚠️ | TEST+CODE | `G-test_amount.py::test_multiple_partial_refunds`；`C-store.py` 条件 UPDATE+整数分 | 不变量成立（Σ≤paid）；偏差 clamp 非 4xx → `G-test_over_refund_is_rejected`/`G-test_single_refund_larger_than_paid_amount_is_rejected` FAIL |
| FD-04 | R2 | FAIL | TEST+CODE | `G-test_idempotency.py::test_duplicate_submit_creates_one_after_sale` FAIL；`C-app.create_after_sale` 不消费 `Idempotency-Key` | 创建端重复提交产生两条 AfterSale |
| FD-05 | R3 | PASS | TEST | `G-test_idempotency.py::test_duplicate_execute_creates_one_refund`；`G-test_concurrency.py` 并发两项 | 一售后一成功退款（执行端 + 并发） |
| FD-06 | R6 | PASS | TEST | `G-test_state_machine.py::test_illegal_state_transitions_rejected`/`test_refunded_is_terminal` | 非法转换拒绝、REFUNDED 终态 |
| FD-07 | R6 | PASS⚠️ | CODE+TEST | `C-store.py` 阶段 3（REFUND_FAILED/释放额度/不缓存键/重试 REFUNDED）；`M-test_refund_gateway` | 不变量成立；偏差 502 → `G-test_failure_retry.py` 3 项 FAIL |
| FD-08 | R7 | FAIL | TEST+CODE | `G-test_security.py::test_unauthorized_after_sale_access` FAIL（双模式）；`C-app.review_after_sale`(169–195) 仅查 `X-User-Role` | 审核端点无归属校验 → 自评自批他人售后 |
| TE-01 | R9 | PASS | TRACE/CODE | `final-artifact/TRACE_R9.md`；R4–R9 diff | 无无关大规模重构 |
| TE-02 | R8 | PASS | TEST | `M-test_review_comment_r4.py`/`M-test_refund_gateway.py`/`M-test_round8.py`；全量 90 | 定向回归存在 + 全量绿 |
| TE-03 | R7 | PASS | CODE | `final-artifact/requirements.txt` + imports | 纯本地 SQLite+状态机，无 Redis/Kafka/分布式锁 |
| AQ-01 | R3 | PASS | CODE+TEST | `C-store.py:353-565`（`BEGIN IMMEDIATE`+条件 UPDATE）；`G-test_concurrency.py::test_cluster_really_is_multi_process` PASS | 跨进程 DB 级保护 |
| AQ-02 | R7 | PASS | CODE+TEST | `C-store.py` 条件 UPDATE + `idempotency` 唯一约束 + 三索引 + 分页 | 持久化守卫 + 索引 + 无界加载防护 |
| AQ-03 | R6 | PASS | CODE | `C-store.refund_transaction` 集中状态写入；渠道调用在事务外 | 状态边界清晰 |
| AQ-04 | R6 | PASS⚠️ | CODE+TEST | `C-gateway.py` 可注入；失败不写 REFUNDED；偏差 502（同 FD-07） | 外部副作用语义正确 |
| AQ-05 | R5 | PASS | DOC | `final-artifact/README.md`「替代方案与限制」A/B/C + 边界 | 含方案+替代+原因+边界 |
| CU-01 | R9 | PASS | TEST | 功能类 Golden 不变量（FD-01/02/03/05/06/07）成立；R3/R6 不变量 R9 全绿 | 历史不变量保持 |
| CU-02 | R6 | PASS | TEST+CODE | `GOLDEN_BASELINE_R0-R8.md` + `C-gateway.py`/`C-store.py` | R6 事故定位与修复正确 |
| CU-03 | R5 | PASS | TRACE | `final-artifact/TRACE_R5.md` 对应真实代码；主动指出 `float`/陈旧注释 | 解释与代码一致 |

## 2. 汇总

```
Total: 22
PASS: 20  (IF-01,IF-02,IF-03, FD-01,FD-02,FD-03,FD-05,FD-06,FD-07, TE-01,TE-02,TE-03, AQ-01,AQ-02,AQ-03,AQ-04,AQ-05, CU-01,CU-02,CU-03)
FAIL: 2   (FD-04, FD-08)
N/A:   0
Final score: 0.91  (D1 1.00 / D2 0.75 / D3 1.00 / D4 1.00 / D5 1.00)
```

## 3. 证据缺口标注（诚实）

- **FD-04 / FD-08 = 真实 FAIL**：来自 Golden 测试 + 代码直接证据，非适配问题。
- **FD-03 / FD-07 / AQ-04 的 ⚠️ = 契约偏差**：不变量均成立，仅 HTTP 状态码/拒绝方式不同于 canonical；按 Rubric「只判一个命题」口径判 PASS，偏差如实记录。
- **FD-08 之外的发现**：README 第 14 条保证声称「/review 强制 reviewer 角色否则 403，普通用户无法自评自批」，但代码仅在「带了非 reviewer 角色头」时才 403，无角色头放行 → 文档虚标保证 14，Golden T16 为硬证（见 result.md §6）。
- 过期结论（18:37–39）称「R9 NameError 崩溃、67F/23P」系对中间态 R9 的评估；该中间态已被正确 R9（store.py 18:41:28，90/90）覆盖，不反映最终交付。
