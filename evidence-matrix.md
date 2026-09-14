# BE-ORDER-REFUND — Evidence Matrix

Rubric → Evidence 的完整追溯。`Result` 为 **Golden Answer 基线**判定
（`PASS` / `FAIL` / `NOT_APPLICABLE`），实测时按同一链路替换为被测模型的判定。

Evidence 优先级：`TEST > CODE > TRACE > DOC > REVIEW`。

---

## 1. Rubric → Evidence

| Rubric | Trigger | Evidence | Type | Automated | Result |
| --- | --- | --- | --- | --- | --- |
| IF-01 | R0 | R0-E01 / R0-E04 | TEST / DOC | Yes | PASS |
| IF-02 | R1–R9 | R1..R9 Trace + REVIEW | TRACE / REVIEW | No | NOT_APPLICABLE |
| IF-03 | R9 | R9-E01 / R9-E02 / R9-E03 / R8-E01 | TEST / DOC | Yes | PASS |
| FD-01 | R0 | R0-E02 / R0-E03 | TEST | Yes | PASS |
| FD-02 | R1 | R1-E01 | TEST | Yes | PASS |
| FD-03 | R1/R3 | R1-E01 / R1-E02 / R1-E03 / R3-E02 | TEST | Yes | PASS |
| FD-04 | R2 | R2-E01 / R2-E02 | TEST | Yes | PASS |
| FD-05 | R2/R3 | R2-E03 / R3-E01 | TEST | Yes | PASS |
| FD-06 | R2/R6 | R2-E04 / R2-E05 / R2-E06 / R6-E03 | TEST / CODE | Mixed | PASS |
| FD-07 | R6 | R6-E01 / R6-E02 | TEST | Yes | PASS |
| FD-08 | R7 | R7-E01 / R7-E02 / R7-E03 / R7-E05 | TEST / CODE | Mixed | PASS |
| TE-01 | R4–R9 | R4..R9 diff + REVIEW | TRACE / REVIEW | No | NOT_APPLICABLE |
| TE-02 | R4/R6/R8 | R4-E02 / R4-E03 / R6-E04 / R8-E01 / R8-E02 | TEST | Yes | PASS |
| TE-03 | R3/R6/R7 | R3-E05 | CODE | No | PASS |
| AQ-01 | R3 | R3-E01 / R3-E03 / R3-E04 / R5-E03 | TEST / CODE | Mixed | PASS |
| AQ-02 | R3 | R3-E04 / R3-E05 / R7-E04 | TEST / CODE | Mixed | PASS |
| AQ-03 | R5/R6 | R5-E01 / R5-E02 / R6-E03 | CODE / TEST | Mixed | PASS |
| AQ-04 | R6 | R6-E01 / R6-E05 | TEST / CODE | Mixed | PASS |
| AQ-05 | R3/R5 | R3-E05 / R5-E04 | CODE / DOC | No | PASS |
| CU-01 | R3–R9 | R3-E02 / R6-E02 / R9-E01 | TEST | Yes | PASS |
| CU-02 | R6 | R6-E02 / R6-E03 | TEST | Mixed | PASS |
| CU-03 | R5 | R5-E01 / R5-E02 / R5-E03 / R5-E04 | CODE / DOC | No | PASS |

---

## 2. Evidence 明细

| Evidence | Type | 来源（可复现） | 支撑 Rubric | Result |
| --- | --- | --- | --- | --- |
| R0-E01 | TEST | `pytest tests/test_order.py::test_project_runs_and_basic_flow` | IF-01 | PASS |
| R0-E02 | TEST | `pytest tests/test_refund.py::test_normal_full_refund` | FD-01 | PASS |
| R0-E03 | TEST | `pytest tests/test_refund.py::test_unpaid_order_cannot_be_refunded` | FD-01 | PASS |
| R0-E04 | DOC | `golden_answer/README.md` §1 快速开始 | IF-01 | PASS |
| R1-E01 | TEST | `pytest tests/test_amount.py::test_multiple_partial_refunds` | FD-02, FD-03 | PASS |
| R1-E02 | TEST | `pytest tests/test_amount.py::test_over_refund_is_rejected` | FD-03 | PASS |
| R1-E03 | TEST | `pytest tests/test_amount.py::test_single_refund_larger_than_paid_amount_is_rejected` | FD-03 | PASS |
| R2-E01 | TEST | `pytest tests/test_idempotency.py::test_duplicate_submit_creates_one_after_sale` | FD-04 | PASS |
| R2-E02 | TEST | `pytest tests/test_idempotency.py::test_duplicate_submit_does_not_break_the_amount_cap` | FD-04 | PASS |
| R2-E03 | TEST | `pytest tests/test_idempotency.py::test_duplicate_execute_creates_one_refund` | FD-05 | PASS |
| R2-E04 | TEST | `pytest tests/test_state_machine.py::test_illegal_state_transitions_rejected` | FD-06 | PASS |
| R2-E05 | TEST | `pytest tests/test_state_machine.py::test_refunded_is_terminal` | FD-06 | PASS |
| R2-E06 | CODE | `app/state_machine.py` 单一转换表 | FD-06 | PASS |
| R3-E01 | TEST | `pytest tests/test_concurrency.py::test_concurrent_same_after_sale` | FD-05, AQ-01 | PASS |
| R3-E02 | TEST | `pytest tests/test_concurrency.py::test_concurrent_multiple_after_sales` | FD-03, CU-01 | PASS |
| R3-E03 | TEST | `pytest tests/test_concurrency.py::test_cluster_really_is_multi_process` | AQ-01 | PASS |
| R3-E04 | TEST | `python verify_doc/check_db_guards.py`（6 项存储级保护） | AQ-01, AQ-02 | PASS |
| R3-E05 | CODE | `app/repository.py`（`BEGIN IMMEDIATE`、部分唯一索引、索引定义） | TE-03, AQ-02, AQ-05 | PASS |
| R4-E01 | TEST | `pytest tests/test_concurrency.py::test_concurrent_same_after_sale` | FD-05, AQ-01 | PASS |
| R4-E02 | TEST | `pytest tests/test_concurrency.py::test_concurrent_multiple_after_sales` | FD-03, TE-02 | PASS |
| R4-E03 | TEST | `pytest tests/test_amount.py::test_over_refund_is_rejected` | TE-02 | PASS |
| R4-E04 | REVIEW | `round-evidence/R4/reviewer.md` | TE-01 | NOT_APPLICABLE |
| R5-E01 | CODE | `app/state_machine.py` 转换表 + `REFUND_START_STATES` | CU-03, AQ-03 | PASS |
| R5-E02 | CODE | `app/service.py` `_claim_refund` / `_settle` | CU-03, AQ-03 | PASS |
| R5-E03 | CODE | `app/repository.py` `reserve_refund_quota` / `write_tx` | CU-03, AQ-01, AQ-02 | PASS |
| R5-E04 | DOC | `golden_answer/README.md` §4 §7（方案、替代方案、限制） | CU-03, AQ-05 | PASS |
| R6-E01 | TEST | `pytest tests/test_failure_retry.py::test_third_party_failure_is_not_marked_success` | FD-07, AQ-04 | PASS |
| R6-E02 | TEST | `pytest tests/test_failure_retry.py::test_failed_refund_can_be_retried` | FD-07, CU-01, CU-02 | PASS |
| R6-E03 | TEST | `pytest tests/test_failure_retry.py::test_incident_regression_provider_failure` | FD-06, CU-02, AQ-03 | PASS |
| R6-E04 | TEST | `pytest tests/test_failure_retry.py::test_failed_refund_does_not_consume_quota` | TE-02 | PASS |
| R6-E05 | CODE | `app/refund_gateway.py`（`RefundGateway` 协议 + 可编程实现） | AQ-04 | PASS |
| R7-E01 | TEST | `pytest tests/test_security.py::test_unauthorized_order_access` | FD-08 | PASS |
| R7-E02 | TEST | `pytest tests/test_security.py::test_unauthorized_after_sale_access` | FD-08 | PASS |
| R7-E03 | TEST | `pytest tests/test_security.py::test_normal_user_cannot_execute_refund` | FD-08 | PASS |
| R7-E04 | TEST | `pytest tests/test_performance.py::test_indexed_queries_and_bounded_loading` | AQ-02 | PASS |
| R7-E05 | CODE | `app/auth.py`（归属校验 + 角色校验） | FD-08 | PASS |
| R8-E01 | TEST | `pytest tests -rA`（22 passed） | IF-03, TE-02 | PASS |
| R8-E02 | TEST | `python verify_doc/check_coverage_matrix.py`（18/18 + 6/6 分类） | TE-02 | PASS |
| R9-E01 | TEST | `pytest tests -rA`（全量历史回归） | IF-03, CU-01, FD-01…FD-08 | PASS |
| R9-E02 | TEST | `bash verify.sh`（退出码 0） | IF-03 | PASS |
| R9-E03 | DOC | `golden_answer/README.md`（含验证方式与已知限制） | IF-03 | PASS |

---

## 3. Test → Evidence → Rubric 反向链路

| Test | Evidence | Rubric | 维度 |
| --- | --- | --- | --- |
| R0-T01 / R0-T02 / R0-T03 | R0-E01…E03 | IF-01, FD-01 | D1 / D2 |
| R1-T01 / R1-T02 / R1-T03 | R1-E01…E03 | FD-02, FD-03 | D2 |
| R2-T01…R2-T05 | R2-E01…E05 | FD-04, FD-05, FD-06 | D2 |
| R3-T01 / R3-T03 / R3-T04 | R3-E01, R3-E03, R3-E04 | AQ-01, AQ-02, FD-05 | D4 / D2 |
| R3-T02 | R3-E02 | FD-03, CU-01 | D2 / D5 |
| R4-T01…R4-T03 | R4-E01…E03 | TE-02, AQ-01, FD-03 | D3 / D4 |
| R5-T01（代码检视） | R5-E01…E04 | CU-03, AQ-03, AQ-05 | D5 / D4 |
| R6-T01…R6-T04 | R6-E01…E04 | FD-07, AQ-04, CU-02, TE-02 | D2 / D4 / D5 / D3 |
| R7-T01…R7-T03 | R7-E01…E03 | FD-08 | D2 |
| R7-T04 | R7-E04 | AQ-02 | D4 |
| R8-T01 / R8-T02 | R8-E01, R8-E02 | IF-03, TE-02 | D1 / D3 |
| R9-T01 / R9-T02 | R9-E01, R9-E02 | IF-03, CU-01 | D1 / D5 |

每个核心 Test 至少支撑一条 Rubric；每条 Must Rubric 至少有一条 Evidence（`IF-02`、`TE-01` 的 Evidence 位置已预留为 Trace/REVIEW，基线记 `NOT_APPLICABLE`，实测时填写）。不存在无法追溯的评分。

---

## 4. 覆盖度自检

| 检查项 | 结果 |
| --- | --- |
| 22 条 Rubric 均有 Evidence 位置 | 是（20 条 PASS，2 条 NOT_APPLICABLE 已注明原因） |
| 客观 Rubric 均有自动化证据 | 是（Objective 11 条全部由 TEST 支撑） |
| Subjective Rubric 均有 CODE/DOC/REVIEW | 是（TE-03/AQ-05/CU-03 由 CODE+DOC 支撑） |
| 每条核心 Test 至少支撑一条 Rubric | 是（见 §3） |
| 无重复计分 | 是（每条只判断一个命题，见 `rubric.md` §2） |
