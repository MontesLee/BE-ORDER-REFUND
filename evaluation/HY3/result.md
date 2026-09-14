# Hy3 — Model Trial Result（22 Rubric 判定）

> 评测对象：`evaluation/HY3/final-artifact/`（hy3 模型 R0–R9 真实产物冻结快照，store.py @ 18:41:28）
> 评测方：主 Agent（evaluator），未向被测模型泄露参考答案 / 评测标准
> 判定日期：2026-09-14
> 统一 Golden 测试：对冻结产物实跑 `golden_answer/tests/test_*.py`（断言字不变，仅适配 hy3 契约），结果 **14 passed / 7 failed**（排除 `test_performance.py`：hy3 无 `refunds` 表）
> 注：本目录早先存在一份 18:37–39 的 `result.md`/`evidence.md`/`trace.md`，系 18:01 并行自动化对一份**带 NameError 的中间态 R9** 产物做出的过期结论（67F/23P、Golden 4–6 passed）。该中间态已被后续正确的 R9（90/90，store.py 18:41:28）覆盖，故以本文件（独立复跑核验）为准。

## 1. 模型与环境

| 字段 | 值 |
| --- | --- |
| model name | `hy3`（账号权威清单确认有效） |
| model version | `POWERED-BY: Hy3`（与 `hy3` 一致） |
| environment | Windows / Python 3.13（托管 venv `…\python\envs\default`）/ FastAPI + SQLite |
| 被测日期 | 2026-09-14 |
| 起始工作区 | `init/` |
| rounds completed | **R0–R9 全部完成**（R0–R8 前序会话落地；R9 本会话派发 `agent-d00735d3` 落地，独立复跑 90/90） |

## 2. final test result

```
命令（模型自带）：cd final-artifact && pytest tests -v
结果：90 passed   （评测方用托管解释器独立复跑确认，非模型自报）

命令（Golden 统一套件 / owner 模式，功能类）：harness_test/ + 冻结产物
结果：12 passed / 6 failed

命令（Golden 统一套件 / caller 模式，安全类）：HY3_EXECUTOR=caller
结果：2 passed / 1 failed

合计 Golden：14 passed / 7 failed
```

> 沿用 `golden_answer/tests/` 断言，仅 `harness.py` 适配 hy3 接口（无 `/users` 本地生成 id、金额在执行端指定、扁平响应包装 `status`↔`payment_status`、列表→paged、幂等键在执行端消费、refund 鉴权强制 owner）。

## 3. rubric result

| 维度（权重） | 适用条数 | PASS | FAIL | NA | 维度得分 |
| --- | --- | --- | --- | --- | --- |
| D1 Instruction Following (15%) | 3 | 3 | 0 | 0 | 1.00 |
| D2 Feature Delivery (35%) | 8 | 6 | 2 | 0 | 0.75 |
| D3 Task Efficiency (15%) | 3 | 3 | 0 | 0 | 1.00 |
| D4 Architecture Quality (20%) | 5 | 5 | 0 | 0 | 1.00 |
| D5 Context Understanding (15%) | 3 | 3 | 0 | 0 | 1.00 |
| **Final** | **22** | **20** | **2** | **0** | **0.91** |

> 计分：`1.00×0.15 + 0.75×0.35 + 1.00×0.15 + 1.00×0.20 + 1.00×0.15 = 0.9125 ≈ 0.91`。

## 4. 逐条判定

### D1 Instruction Following（3/3）

| ID | 命题 | 判定 | 依据 |
| --- | --- | --- | --- |
| IF-01 | clean env 按 README 启动运行 | **PASS** | Golden `test_order.py::test_project_runs_and_basic_flow` 对冻结产物 200；模型 90/90；README 含安装/启动/测试命令 |
| IF-02 | 后续轮次增量演进，无大规模重写 | **PASS** | `TRACE_R2`…`TRACE_R9` + 逐轮 diff：每轮仅增量修改 `store.py`/`app.py`/`gateway.py`，无删改重来 |
| IF-03 | 最终 source/tests/README/requirements/verification 完整可运行 | **PASS** | R9 含实现 + 7 测试文件 + README + requirements；`pytest tests -v` 全绿（90 passed） |

### D2 Feature Delivery（6/8）

| ID | 命题 | 判定 | 依据 |
| --- | --- | --- | --- |
| FD-01 | 仅满足支付与审核条件的 AfterSale 可退款 | **PASS** | Golden `test_unpaid_order_cannot_be_refunded` 通过；`store.refund_transaction` 卡 `status != PAID` 拒绝（存储层双保险） |
| FD-02 | 一订单支持多 AfterSale 与部分退款 | **PASS** | Golden `test_multiple_partial_refunds` 通过 |
| FD-03 | 成功退款累计 ≤ `paid_amount` | **PASS** ⚠️ | 不变量成立：整数分 + 条件 `UPDATE ... WHERE CAST((refunded_amount+?)×100 AS INTEGER) <= CAST(amount×100 AS INTEGER)` 预留额度。**偏差**：超额请求被 clamp（退剩余）而非 4xx 拒绝 → Golden `test_over_refund_is_rejected`/`test_single_refund_larger_than_paid_amount_is_rejected` 失败（200），不变量本身满足 |
| FD-04 | 重复业务请求不产生多个有效退款结果 | **FAIL** | Golden `test_duplicate_submit_creates_one_after_sale` **失败**：相同 `Idempotency-Key` 在「创建」端不消费，重复提交产生两条不同 id 的 AfterSale（`create_after_sale` 不读幂等键）。执行端幂等正确，但创建端缺去重 → 变异体 M3 行为，被 T06 杀死 |
| FD-05 | 一个 AfterSale 最多一条成功 Refund | **PASS** | Golden `test_duplicate_execute_creates_one_refund` + 多进程并发 `test_concurrent_same_after_sale`/`test_concurrent_multiple_after_sales` 通过 |
| FD-06 | 非法状态转换拒绝，`REFUNDED` 终态 | **PASS** | Golden `test_illegal_state_transitions_rejected` + `test_refunded_is_terminal` 通过 |
| FD-07 | 第三方失败进可重试态，重试成功进 `REFUNDED` | **PASS** ⚠️ | 不变量成立：`store` 阶段 3 渠失败置 `REFUND_FAILED`、释放额度、不缓存键；重试成功置 `REFUNDED`、仅一次。**偏差**：渠失败返回 HTTP 502 而非 `<500` → Golden `test_third_party_failure_is_not_marked_success`/`test_failed_refund_does_not_consume_quota`/`test_failed_refund_can_be_retried` 因状态码断言失败（本地状态语义正确） |
| FD-08 | 用户不能操作他人资源，也不能绕过审核执行退款 | **FAIL** | Golden `test_security.py::test_unauthorized_after_sale_access` **失败**：bob（普通用户，无角色头）可 `approve` alice 的售后使其变 `APPROVED`。根因：`app.review_after_sale`（169–195 行）**只校验 `X-User-Role`，完全不校验 `X-User-Id` 归属** → 任意用户可自评自批他人售后 |

### D3 Task Efficiency（3/3）

| ID | 命题 | 判定 | 依据 |
| --- | --- | --- | --- |
| TE-01 | 修复问题无无关大规模重构 | **PASS** | R4–R9 diff 聚焦本轮问题；R9 整数分改造属金额精度正确性范畴 |
| TE-02 | 可单独执行的定向回归 + 全量回归闭环 | **PASS** | `test_review_comment_r4.py` / `test_refund_gateway.py` / `test_round8.py`（六类 14 子项）；全量 90 通过 |
| TE-03 | 未引入不必要基础设施 | **PASS** | 仅 SQLite；无 Redis/Kafka/Celery/分布式锁 |

### D4 Architecture Quality（5/5）

| ID | 命题 | 判定 | 依据 |
| --- | --- | --- | --- |
| AQ-01 | 核心并发约束由跨进程持久化机制保护（非单进程锁） | **PASS** | Golden `test_cluster_really_is_multi_process` 通过（真实两进程）；`BEGIN IMMEDIATE` + 条件 UPDATE |
| AQ-02 | 金额/幂等约束在并发与数据增长下有可靠持久化保护 | **PASS** | 条件 UPDATE + `idempotency` 唯一约束 + 三索引 + `limit/offset` 分页 |
| AQ-03 | 状态转换边界清晰，普通路径不能绕过状态机 | **PASS** | 状态写入集中于 `store.refund_transaction`；外部渠道调用在事务外 |
| AQ-04 | 外部副作用语义正确，渠道可确定性测试 | **PASS** ⚠️ | `RefundGateway` 可注入；失败分支不写 `REFUNDED`；偏差同 FD-07（502 状态码） |
| AQ-05 | 说明方案/替代/原因/边界 | **PASS** | README「替代方案与限制」列 A/B/C 并明确边界（SQLite 写串行、`busy_timeout`、pay/review 未额外加锁） |

### D5 Context Understanding（3/3）

| ID | 命题 | 判定 | 依据 |
| --- | --- | --- | --- |
| CU-01 | 后续修改保持此前核心 invariant | **PASS** | R3/R6 不变量在 R9 全绿；功能类 Golden 不变量仍成立 |
| CU-02 | 能据事故定位真实原因并针对性修复 | **PASS** | R6 准确定位「本地未调渠道即标 REFUNDED」根因，补 `RefundGateway` + `REFUND_FAILED` + 释放额度 |
| CU-03 | 模型解释与实际代码一致 | **PASS** | `TRACE_R5` 逐条对应真实 SQLite 实现；主动指出 `float`/`REAL` 与 models.py 陈旧注释等不一致 |

## 5. key failures（2 条 FAIL）

| # | 失败点 | 落在哪条 | 证据 | 可复现 |
| --- | --- | --- | --- | --- |
| 1 | 创建端不消费幂等键：相同 `Idempotency-Key` 重复提交产生两条 AfterSale | FD-04 | Golden `test_duplicate_submit_creates_one_after_sale` FAIL；CODE `create_after_sale` 不读键 | 是 |
| 2 | 审核端点无归属校验：普通用户可自评自批他人售后 | FD-08 | Golden `test_unauthorized_after_sale_access` FAIL（双模式）；CODE `app.review_after_sale` 仅查 `X-User-Role` 不查 `X-User-Id` | 是 |

## 6. 诚实备注（不扣分但须知会）

1. **README 第 14 条保证虚标**：README 声称「/review 强制 reviewer 角色否则 403，普通用户无法自评自批」，但代码仅在「带了非 reviewer 角色头」时才 403；无角色头则放行 → 任何用户可 approve 他人售后。模型自评/文档**夸大了保证 14**，Golden T16 为硬证。
2. **FD-04 部分实现**：执行端幂等正确、金额不超发，但创建端缺去重。
3. **契约偏差**：超额 clamp 退剩余（非 4xx）、第三方失败返 502（非 4xx）——不变量均仍成立，仅 HTTP 状态码与 canonical 不同。
4. **金额类型**：R9 改整数分内部运算，DB 列仍 `REAL`、对外仍元（float）；浮点误差已被整数分消除。

## 7. 一句话结论

Hy3 在 R0–R9 交付了一个**架构正确、并发与第三方失败处理扎实**的退款服务，22 Rubric 判定 **20/22 PASS，Final = 0.91**。两处真实缺陷：**FD-04 创建端幂等缺失**、**FD-08 审核端点缺归属校验（且 README 虚标该保证）**；另有两处契约偏差（clamp / 502）不破坏不变量。
