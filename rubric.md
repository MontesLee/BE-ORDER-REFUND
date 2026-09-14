# BE-ORDER-REFUND — Rubric（22 条原子细则）

> 每条 Rubric 只判断一个命题，可用 Yes/No 回答。结果只允许
> `PASS`（1 分）/ `FAIL`（0 分）/ `NOT_APPLICABLE`（不入分母）。
> 禁止"部分通过""基本通过""看起来合理"。

**维度映射**（权重固定，不新增维度）：

```
D1 Instruction Following  15%   IF-01 … IF-03
D2 Feature Delivery       35%   FD-01 … FD-08
D3 Task Efficiency        15%   TE-01 … TE-03
D4 Architecture Quality   20%   AQ-01 … AQ-05
D5 Context Understanding  15%   CU-01 … CU-03
```

**Evidence 类型**只允许 `TEST > CODE > TRACE > DOC > REVIEW`。
每条 Must Rubric 至少有一条 Evidence；客观 Rubric 必须有自动化证据。

**Round 字段口径（Tlabel）**：`round` **只填一个轮次**。若一条 Rubric 涉及多个轮次，
填**最后一个相关轮次**——即该命题最后一次被「引入 / 加强 / 判定」的轮次，
而不是范围。轮次跨度与判定依据写在 §2 的 `Trigger` 里，`round` 字段不复述范围。

> 判定示例（说明"最后一个相关轮次"如何得出，不是机械取最大值）：
>
> | Rubric | 相关轮次 | round | 依据 |
> | --- | --- | --- | --- |
> | FD-03 | R1 引入累计上限 → R3 要求并发下仍成立 | **R3** | 要求被 R3 加强 |
> | FD-05 | R1 隐含 → R2 幂等 → R3 跨进程并发 | **R3** | 要求被 R3 加强 |
> | FD-06 | R2 状态机 → R6 新增 `REFUND_FAILED` / 重试且成功不得重复 | **R6** | R6 扩展了状态机要求 |
> | AQ-01 | R3 提出跨进程保护；R4 只是对同一要求的 Review 复核 | **R3** | R4/R5 未新增要求，仅复核与解释 |
> | AQ-02 | R3 持久化守卫 → R7 明确"Refund 数量增长后不退化 / 无界加载" | **R7** | 命题中的"数据增长"由 R7 提出 |
> | TE-02 | R4 定向回归 → R6 确定性复现 → R8 全量套件 | **R8** | 闭环在 R8 收口 |
> | IF-02 / CU-01 / TE-01 | 覆盖全流程（R1/R3–R9） | **R9** | 只能在末轮判定 |
>
> 规则是「要求最后一次成为最终形态的轮次」，**不是**「最后一次重复测它的轮次」，
> 否则几乎所有 Rubric 都会退化成 R9。

---

## 1. 细则总表

| ID | 判断命题（Yes/No） | 维度 | Round | 优先级 | 显/隐 | 客/主 | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| IF-01 | 项目能在 clean environment 按 README 启动并运行 | D1 | R0 | Must | Explicit | Objective | R0-E01, R0-E04 |
| IF-02 | 后续轮次在已有项目上增量演进，没有无必要的大规模重写 | D1 | R9 | Must | Implicit | Subjective | R1…R9 Trace/REVIEW |
| IF-03 | 最终 source / tests / README / requirements / verification 完整且可运行 | D1 | R9 | Must | Explicit | Objective | R9-E01, R9-E02, R9-E03, R8-E01 |
| FD-01 | 只有满足支付与审核条件的 AfterSale 才能退款 | D2 | R0 | Must | Explicit | Objective | R0-E02, R0-E03 |
| FD-02 | 一个订单支持多个 AfterSale 与部分退款 | D2 | R1 | Must | Explicit | Objective | R1-E01 |
| FD-03 | 成功退款金额累计不超过 `paid_amount` | D2 | R3 | Must | Explicit | Objective | R1-E01, R1-E02, R1-E03, R3-E02 |
| FD-04 | 重复业务请求不产生多个有效退款结果 | D2 | R2 | Must | Explicit | Objective | R2-E01, R2-E02 |
| FD-05 | 一个 AfterSale 最多一条成功 Refund | D2 | R3 | Must | Explicit | Objective | R2-E03, R3-E01 |
| FD-06 | 非法状态转换被拒绝，`REFUNDED` 为终态 | D2 | R6 | Must | Explicit | Objective | R2-E04, R2-E05, R2-E06, R6-E03 |
| FD-07 | 第三方失败后进入可重试状态，重试成功后进入 `REFUNDED` | D2 | R6 | Must | Explicit | Objective | R6-E01, R6-E02 |
| FD-08 | 用户不能操作他人资源，也不能绕过审核执行退款 | D2 | R7 | Must | Explicit | Objective | R7-E01, R7-E02, R7-E03, R7-E05 |
| TE-01 | 修复问题时没有进行无关的大规模重构 | D3 | R9 | Nice | Implicit | Subjective | R4…R9 Trace/REVIEW |
| TE-02 | 存在可单独执行的定向回归用例，且全量套件可运行（diagnose→fix→targeted regression→full regression 闭环） | D3 | R8 | Must | Explicit | Objective | R4-E02, R4-E03, R6-E04, R8-E01, R8-E02 |
| TE-03 | 没有为小型 SQLite 服务引入明显不必要的基础设施 | D3 | R7 | Nice | Implicit | Subjective | R3-E05 |
| AQ-01 | 核心并发约束不依赖单进程内存锁，而由对 multi-worker 有效的持久化/数据库机制保护 | D4 | R3 | Must | Implicit | Objective+Subjective | R3-E01, R3-E03, R3-E04, R5-E03 |
| AQ-02 | 金额上限与 AfterSale 幂等约束在并发与数据增长下有可靠的持久化保护 | D4 | R7 | Must | Implicit | Objective+Subjective | R3-E04, R3-E05, R7-E04 |
| AQ-03 | 状态转换边界清晰，普通业务路径不能绕过状态机 | D4 | R6 | Must | Implicit | Subjective | R5-E01, R5-E02, R6-E03 |
| AQ-04 | 第三方失败不会错误记录为本地成功，且第三方调用可确定性测试 | D4 | R6 | Must | Explicit | Objective+Subjective | R6-E01, R6-E05 |
| AQ-05 | 能说明当前方案、合理替代方案、选择原因及 SQLite/multi-worker 限制 | D4 | R5 | Nice | Explicit | Subjective | R3-E05, R5-E04 |
| CU-01 | 后续修改始终保持此前建立的核心 invariant | D5 | R9 | Must | Implicit | Objective | R3-E02, R6-E02, R9-E01 |
| CU-02 | 能根据事故定位真实原因并针对性修复 | D5 | R6 | Must | Implicit | Objective+Subjective | R6-E02, R6-E03 |
| CU-03 | 模型解释与实际代码一致 | D5 | R5 | Must | Implicit | Subjective | R5-E01, R5-E02, R5-E03, R5-E04 |

计数：Instruction Following 3 · Feature Delivery 8 · Task Efficiency 3 · Architecture Quality 5 · Context Understanding 3 = **22**。
Round 字段全部为**单一轮次**，无区间、无斜杠（见上方 Round 字段口径）。

---

## 2. 逐条验证方式（Verification）

### D1 Instruction Following

**IF-01 项目可运行**
- Trigger：R0 结束时。
- Verification：在 clean environment（新建 venv / 容器）按 README 执行安装与启动，服务 `/health` 可用；执行项目自带测试无 import/collect 错误。
- 反面证据：README 命令不存在、依赖未声明、启动报错。
- Evidence：`R0-E01`（TEST：`tests/test_order.py::test_project_runs_and_basic_flow`）、`R0-E04`（DOC）。

**IF-02 增量演进**
- Trigger：R1 起每一轮。
- Verification：逐轮对比工作区快照，统计被整体重写的文件比例；出现"删掉重来"或与当前轮无关的大范围改动即 FAIL。
- 注意：**依赖真实模型 Trace / diff**；Golden Answer 基线中为 `NOT_APPLICABLE`。
- Evidence：R1–R9 的 Trace 与 REVIEW（基线不填，禁止伪造）。

**IF-03 最终交付完整**
- Trigger：R9 结束时。
- Verification：R9 工作区含实现源码 + 测试 + README + 依赖声明 + 可执行的验证方式；`pytest` 全量运行无失败；按 README 在 clean environment 可复现。
- Evidence：`R9-E01`（全量套件）、`R9-E02`（`bash verify.sh` 退出码 0）、`R9-E03`（README）、`R8-E01`。

### D2 Feature Delivery

**FD-01 退款资格**
- Verification：未支付订单不得产生成功退款；未审核（`PENDING`）不得退款。
- 判据：`refunded_amount == 0` 且无 `REFUNDED` 流水。
- Evidence：`R0-E02`、`R0-E03`。

**FD-02 部分退款与多售后**
- Verification：同一订单可建 ≥2 条 AfterSale，各自金额独立；三笔 3000/3000/4000 累加等于 10000。
- Evidence：`R1-E01`。

**FD-03 累计金额不变量**
- Verification：任意时点 `Σ成功退款 ≤ paid_amount`，且订单计数器与成功流水之和一致；第 N+1 笔超额请求被拒（`4xx`）且计数器不变。
- Evidence：`R1-E01`、`R1-E02`、`R1-E03`、`R3-E02`。

**FD-04 幂等**
- Verification：同一幂等键重复提交 ⇒ 只有一条 AfterSale（同一 id）；同一 AfterSale 重复执行 ⇒ 只有一条成功退款。**只看结果，不指定实现机制。**
- Evidence：`R2-E01`、`R2-E02`。

**FD-05 一售后一成功退款**
- Verification：并发（跨进程）与串行两种情况下，单个 AfterSale 的 `REFUNDED` 流水数恒为 1。
- Evidence：`R2-E03`、`R3-E01`。

**FD-06 状态机**
- Verification：`PENDING → REFUNDED` 不可能；`REFUNDED` 之后 approve/execute 不能改变状态、不能再次退款；非法迁移返回 `4xx`。
- Evidence：`R2-E04`、`R2-E05`、`R2-E06`（CODE：单一转换表）、`R6-E03`。

**FD-07 失败重试**
- Verification：渠道失败后售后状态为 `REFUND_FAILED`（不得停在 `REFUNDING`，也不得为 `REFUNDED`）；再次执行可成功并进入 `REFUNDED`，且成功仅一次；失败不消耗额度。
- Evidence：`R6-E01`、`R6-E02`。

**FD-08 授权与执行保护**
- Verification：跨用户读取他人订单/售后被拒（`403`/`404` 均可，`404` 更优）且响应体不含对方数据；跨用户 approve/execute 不改变状态、不产生退款；普通用户对未审核申请执行退款不得成功。
- Evidence：`R7-E01`、`R7-E02`、`R7-E03`、`R7-E05`（CODE：归属校验与角色校验位置）。

### D3 Task Efficiency

**TE-01 不做无关重构**
- Verification：审查 R4–R9 的 diff，改动是否聚焦于本轮问题；引入与问题无关的目录重构、框架替换、批量改名即 FAIL。
- 注意：依赖 Trace / diff；基线为 `NOT_APPLICABLE`。

**TE-02 定向回归 + 全量回归闭环**
- Verification：交付物中存在**可单独执行**、且能复现对应缺陷的定向回归用例（并发、失败重试各至少一条），且全量套件可运行通过。
- Evidence：`R4-E02`、`R4-E03`、`R6-E04`、`R8-E01`、`R8-E02`（覆盖率探测）。

**TE-03 不引入不必要基础设施**
- Verification：检查依赖与 import——为单机 SQLite 服务引入 Redis / Kafka / Celery / K8s / 分布式锁服务即 FAIL；纯本地状态机 + 可重试方案为 PASS。
- Evidence：`R3-E05`（CODE：依赖与实现位置）。

### D4 Architecture Quality

**AQ-01 原子并发保护（跨进程）**
- Verification：必须看到**跨进程**证据——要么并发用例跑在两个真实 worker 进程上并校验业务结果（T13/T14），要么直接证明持久化机制排他（存储层探测：第二个 `BEGIN IMMEDIATE` 被拒）。
  仅凭代码里存在 `threading.Lock` / `asyncio.Lock` 判 FAIL（失效模式 #7）。
- Evidence：`R3-E01`、`R3-E03`、`R3-E04`、`R5-E03`。

**AQ-02 持久化不变量保护**
- Verification：金额上限与"一售后一成功"存在数据库级或等价的持久化约束；且这些约束所用查询走索引、列表接口被分页约束（数据增长后不退化、无无界加载）。
- 说明：评分体系不设 Performance 维度，因此 R7 的性能信号归入本条。
- Evidence：`R3-E04`（存储层探测：`CHECK` 拒绝超额、部分唯一索引拒绝第二条成功）、`R3-E05`、`R7-E04`。

**AQ-03 状态边界**
- Verification：状态写入集中、可枚举（单一转换表或等价结构），不存在从任意位置直接写状态字面量的旁路；外部调用不在事务内。
- Evidence：`R5-E01`、`R5-E02`、`R6-E03`。

**AQ-04 外部副作用语义**
- Verification：本地状态由渠道裁决决定，失败分支不得写入成功；渠道以可替换接口注入，测试可确定性模拟成功/失败（不依赖随机 sleep 或"偶现"）。
- Evidence：`R6-E01`、`R6-E05`（CODE：`RefundGateway` 协议与可编程实现）。

**AQ-05 技术取舍说明**
- Verification：文字/README 中是否同时给出 ① 当前方案 ② 至少一个合理替代方案 ③ 选择原因 ④ 当前方案的边界（如 SQLite 单写锁、崩溃窗口、无分布式事务）。缺 ④ 不得 PASS。
- Evidence：`R3-E05`、`R5-E04`。

### D5 Context Understanding

**CU-01 历史不变量保持**
- Verification：R3 之后的所有轮次（含最终 R9）重跑历史用例仍全绿；不存在为过新测试而放宽旧断言的痕迹。
- Evidence：`R3-E02`、`R6-E02`、`R9-E01`。

**CU-02 事故定位与修复**
- Verification：是否指出真实根因（本地状态与渠道裁决脱钩），而不是归因于"网络不稳定"；修复是否针对根因；是否补充能稳定复现的回归用例。
- Evidence：`R6-E02`、`R6-E03`。

**CU-03 解释与代码一致**
- Verification：把 R5 自述逐条对照真实代码。任一处机制描述与代码不符即 FAIL（例如声称用了分布式锁/outbox 而代码里没有）；代码与预期不符但**主动指出**不扣分。
- Evidence：`R5-E01`、`R5-E02`、`R5-E03`、`R5-E04`。

---

## 3. 计分

```
对每个维度：
    dimension_score = 该维度 PASS 的条数 / 该维度适用（不含 NOT_APPLICABLE）的条数

最终得分：
    Final = D1×0.15 + D2×0.35 + D3×0.15 + D4×0.20 + D5×0.15
```

R9 不新增维度，只做全量历史回归。后续轮次可以检查历史要求，
但**前一轮不得因为没有实现未来需求而扣分**。

---

## 4. Golden Answer 基线结果（**不是模型评测结果**）

> **这一节判定的是"参考答案本身是否满足 Benchmark 要求"（Golden Answer Validation），
> 不等于任何模型的评测结果。**
>
> ```
> Golden Answer Validation      ← 本节内容：证明题目与参考答案可执行、可判定
>         ↓（完成这一步 ≠ 完成模型评测）
> Real Model Trial              ← 已完成（单模型 Hy3 跑完 R0–R9；判定见 evaluation/HY3/）
>         ↓
> Model Trace + Final Artifact
>         ↓
> Rubric Evaluation             ← 用同一套 Rubric，对模型产物逐条判定
>         ↓
> Model Result
> ```
>
> 真实模型得分必须来自实测：`evaluation/<model>/` 下的 `trace.md` +
> `final-artifact/` + `evidence.md`（模板见 `evaluation/README.md`）。
> **在真实 Trial 完成前，不得声称任何模型 PASS / FAIL。**
> 下面表格中的 `Result` 全部只代表 Golden Answer 基线。

参考实现上逐条判定（依据 `round-evidence/*/evidence.json`）：

| 维度 | 适用条款 | PASS | FAIL | N/A | 维度得分 |
| --- | --- | --- | --- | --- | --- |
| D1 Instruction Following | IF-01, IF-03 | 2 | 0 | IF-02 | 1.00 |
| D2 Feature Delivery | FD-01…FD-08 | 8 | 0 | — | 1.00 |
| D3 Task Efficiency | TE-02, TE-03 | 2 | 0 | TE-01 | 1.00 |
| D4 Architecture Quality | AQ-01…AQ-05 | 5 | 0 | — | 1.00 |
| D5 Context Understanding | CU-01…CU-03 | 3 | 0 | — | 1.00 |
| **合计** | 22 条 | **20** | 0 | 2 | **Final = 1.00** |

`IF-02` 与 `TE-01` 依赖模型多轮 Trace（增量演进、是否做无关重构），
在仅有 Golden Answer 的基线中不可判定，故标 `NOT_APPLICABLE`——
按试标规则要求**不伪造 Trace**，实测时据 diff 与过程记录填写。

---

## 5. 区分度实测（变异测试，真实执行）

为验证 Rubric 真的能分辨好坏实现，对参考实现注入 6 个真实弱实现（变异体）并跑测试套：

| 变异体 | 注入的缺陷 | 期望 | 实际 | 被杀死的用例 |
| --- | --- | --- | --- | --- |
| M0 | 无（对照组） | 全部通过 | ✅ 全绿 | — |
| M1 | check-then-write 竞态：去掉写锁与全部数据库级约束 | 至少 1 条 FAIL | ✅ 被杀 | T04、T14、`test_single_refund_larger_than_paid_amount_is_rejected` |
| M2 | 渠道失败仍标记本地成功 | 至少 1 条 FAIL | ✅ 被杀 | T05、T09、T11、T12 |
| M3 | 忽略幂等键，重复提交产生新记录 | 至少 1 条 FAIL | ✅ 被杀 | T06 |
| M4 | 只校验存在性，不校验归属 | 至少 1 条 FAIL | ✅ 被杀 | T15、T16 |
| M5 | 允许 `PENDING` 直接发起退款尝试 | 至少 1 条 FAIL | ✅ 被杀 | T08 |
| M6 | 失败尝试不释放预留额度 | 至少 1 条 FAIL | ✅ 被杀 | T05、T09、T11、T12 |

**结论：6/6 变异体被杀死，对照组全绿。** 数据见 `evaluation-report.md` §4。

诚实说明：M1 在同机环境下未被 T13 复现（时序竞态的不确定性），但被 T14 稳定杀死；
因此 AQ-01/AQ-02 的判定不单独依赖 T13，另有存储层确定性探测（`check_db_guards.py`）作为硬证据。
