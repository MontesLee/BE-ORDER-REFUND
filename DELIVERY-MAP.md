# Delivery Map — BE-ORDER-REFUND

> 一页看懂「每个文件/目录是什么角色、该看哪个」。详细说明见 `README.md`；
> 评测口径见 `evaluation/README.md`；证据追溯见 `evidence-matrix.md`。

---

## 1. 交付物一览

| 路径 | 角色 | 说明 |
| --- | --- | --- |
| `instruction.md` | **Benchmark Instruction** | 出题/评测方文档：题目、六条不变量、状态机、统一接口契约、**R0–R9 Prompt 原文**、每轮评分边界、17 条失效模式。**不下发给被测模型。** |
| `introduction.md` | **题目与模型表现简述** | 题目速览 + 包内容与 Tlabel 格式映射 + Golden 基线 + 本次 Hy3 实测表现 |
| `rubric.md` | **Rubric（评分标准）** | 22 条原子细则（D1–D5 / IF·FD·TE·AQ·CU），逐条 Verification 与计分 |
| `evidence-matrix.md` | **Evidence Mapping** | Rubric → Evidence → Test 双向追溯（Golden 侧）+ 六条不变量完整链路 |
| `evaluation-report.md` | **评测反馈报告** | B1–B5 / S1–S6 质量门、变异测试、覆盖率、风险与结论；含 §11 Hy3 模型判定 |
| `final-audit.md` | **提交前审计** | 对齐 Tlabel 规范的审计结论（PASS / 关注项 / 未做项） |
| `init/` | **起始工作区** | 被测模型的起点（本题初始为空，仅一个中性 README）。**不含任何评测信息。** |
| `golden_answer/` | **可执行参考实现** | FastAPI + SQLite 参考解 + 22 个测试 + `verify.sh` 一键验证 + `verify_doc/` 验证留痕 |
| `test/` | **测试用例说明** | 测试套说明 + 「如何适配被测模型产出」（唯一适配点 `harness.py`） |
| `solve/` | **参考解交付说明** | 参考实现的设计取舍一览与引用关系 |
| `round-evidence/` | **逐轮证据** | `R0…R9/`：每轮 `prompt.md`（Prompt 原文）· `test-result.txt` · `evidence.json` · `reviewer.md` |
| `evaluation/` | **模型实测结果区** | `README.md`（口径）+ `comparison.md`（汇总）+ `HY3/`（本次实测）+ `_TEMPLATE/` + `_trial-history/` |
| `evaluation/HY3/` | **正式 Hy3 Trial** | 冻结产物 · 逐轮原始留痕 · 逐条证据 · 模型级结论（见 §2） |

---

## 2. `evaluation/HY3/` 内部导航

| 路径 | 内容 |
| --- | --- |
| `final-artifact/` | **Hy3 的最终交付物原件**（24 文件：业务代码 6 · 工程配套 2 · 测试 9 · 逐轮 TRACE 8）。与 trial 工作区 SHA256 逐字节一致，**未做任何人工修复**。 |
| `raw-trace/` | 逐轮原始留痕登记 `R0.md … R9.md`：每轮的 Prompt 来源 / 模型留痕 / 代码变化 / 独立核验 / `model_trace_id`（缺失标 `MISSING`） |
| `trace.md` | 评测方留痕：会话信息、逐轮汇总、R9 执行与独立核验、并行冲突说明、`model_trace_id` 现状 |
| `result.md` | **模型级结论**：22 条 Rubric 计分卡、逐条判定、2 条 key failure、诚实备注 |
| `evidence.md` | **逐条证据映射**：`Rubric | Round | Result | Evidence type | Path | Reason` |
| `harness_test/` | Golden 断言的**适配层**（断言字不变，仅 `harness.py` 适配 Hy3 契约）+ 8 个逐字复制的 `test_*.py` |
| `GOLDEN_BASELINE_R0-R8.md` | 适配层在 R0–R8 产物上的基线结果 |

---

## 3. 从零理解这个交付包的三条路径

| 你想看什么 | 建议顺序 |
| --- | --- |
| **题目本身** | `README.md` §1 → `instruction.md` §1–§7 → `test/README.md` |
| **参考解是否可跑** | `golden_answer/README.md` → `cd golden_answer && ./verify.sh` → `verify_doc/test-result.txt` |
| **Hy3 实测结果** | `evaluation/comparison.md` → `evaluation/HY3/result.md` → `evaluation/HY3/evidence.md` → `evaluation/HY3/raw-trace/` |

---

## 4. 本次交付的模型范围

> **正式模型实测仅使用 Hy3。** 未进行其他模型实测，因此**不做跨模型能力排序或模型区分度结论**。

- `evaluation/HY3/` 是唯一的正式模型结果。
- `evaluation/_trial-history/` 是一次多模型 Trial 被配额（HTTP 429）中断时的历史留痕，
  属 **Historical / exploratory only. Not part of the formal model trial.**，不得被引用为模型表现。
