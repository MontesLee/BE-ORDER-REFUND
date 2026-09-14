# raw-trace — Hy3 逐轮原始留痕登记

> 本目录是 Hy3（`hy3`）真实 Model Trial 的**逐轮原始留痕登记**：R0–R9 每轮一行登记，
> 记录「该轮的 Prompt 来源 / 模型留痕 / 派发标识 / 独立核验结果」。
>
> **本目录只做登记与指向，不复制、不改写任何原始产物。**
> 模型亲笔留痕的权威原件在 `../final-artifact/TRACE_R2.md … TRACE_R9.md`（冻结快照内）。
>
> 登记原则：**没有可核验来源的字段一律写 `MISSING`，不补写、不推测、不生成。**

---

## 1. 逐轮登记

| 轮次 | Prompt 来源 | 模型留痕 | 派发 / trace ID | 独立核验（评测方复跑） | 状态 |
| --- | --- | --- | --- | --- | --- |
| R0 | `round-evidence/R0/prompt.md` | `../_trial-history/hy3/trace/R0.md` | `MISSING` | 11 passed（模型 R0 留痕自述） | 已登记（留痕在历史目录） |
| R1 | `round-evidence/R1/prompt.md` | `MISSING` | `MISSING` | 19 passed（`../_trial-history/hy3/self-test-verified.txt`，对 R1 快照的评测方复跑） | **MISSING**（模型留痕） |
| R2 | `round-evidence/R2/prompt.md` | `../final-artifact/TRACE_R2.md` | `MISSING` | 24 passed | 已登记 |
| R3 | `round-evidence/R3/prompt.md` | `../final-artifact/TRACE_R3.md` | `MISSING` | 30 passed | 已登记 |
| R4 | `round-evidence/R4/prompt.md` | `../final-artifact/TRACE_R4.md` | `MISSING` | 34 passed | 已登记 |
| R5 | `round-evidence/R5/prompt.md` | `../final-artifact/TRACE_R5.md` | `MISSING` | 34 passed | 已登记 |
| R6 | `round-evidence/R6/prompt.md` | `../final-artifact/TRACE_R6.md` | `MISSING` | 43 passed | 已登记 |
| R7 | `round-evidence/R7/prompt.md` | `../final-artifact/TRACE_R7.md` | `MISSING` | 55 passed | 已登记 |
| R8 | `round-evidence/R8/prompt.md` | `../final-artifact/TRACE_R8.md`（评测方据产物重建，见该文件首注） | `MISSING` | 76 passed | 已登记 |
| R9 | `round-evidence/R9/prompt.md` | `../final-artifact/TRACE_R9.md`（模型亲笔） | `agent-d00735d3`（本会话 Agent 派发标识） | 90 passed | 已登记 |

> 每轮的独立核验数字均为评测方用托管解释器 `pytest tests -v` 复跑所得，**不采信模型自报**。
> 复跑原始输出在 trial 运行目录（过程证据，不入仓库）：`trial-workspaces/_eval_progress/`。

---

## 2. trace ID / request ID 现状（P0 说明）

Tlabel 要求记录真实的 **CodeBuddy / WorkBuddy request ID（`model_trace_id`）**。本次实况：

| 轮次 | 真实 request id | 说明 |
| --- | --- | --- |
| R9 | `agent-d00735d3` | 本会话通过 Agent 派发 R9 时平台返回的派发标识，**是唯一被保留的派发 ID** |
| R0–R8 | `MISSING` | 该批轮次执行时未采集平台 request id，事后已无法从任何可核验来源恢复 |

- **未编造任何 ID**：没有根据文件名、模型名、Git commit 生成过任何 ID。
- `MISSING` 的含义是「无真实来源」，不是「没跑过」。各轮的**执行真实性**由工作区产物、
  模型亲笔留痕与评测方独立复跑共同证明（见 §1 与 `../trace.md` §3）。
- 若要补齐 `model_trace_id`，须在**下一轮 Trial 开始时**开启 request id 采集；
  已发生的 R0–R8 无法回填。

---

## 3. 已知留痕缺口

| 缺口 | 影响 | 处置 |
| --- | --- | --- |
| R1 无模型亲笔留痕 | 无法逐字复核 R1 的模型自述 | 如实标 `MISSING`；R1 的**行为结果**仍可由 `../_trial-history/hy3/final-artifact-so-far/`（R1 结束时的工作区快照，19 passed）与 R2 起的增量 diff 证明 |
| R0–R8 无平台 request id | 无法提供 `model_trace_id` | 如实标 `MISSING`，不补写 |
| R8 模型最终回复被 HTTP 429 截断 | 缺 `POWERED-BY` 与模型自述 | 工作区核验确认 R8 真实执行（`tests/test_round8.py` + 独立复跑 76 passed），`TRACE_R8.md` 由评测方据产物重建并**在文件首注明确标注** |

---

## 4. 附录：平台限频（HTTP 429）回执中出现过的 request id

以下是 Trial 过程中平台返回 429 限频错误时，回执文本里携带的请求 id：

| 出现时机 | 回执中的 request id |
| --- | --- |
| R8 派发时（限频拦截，但 R8 实际已落地） | `1f4e22956daf4aebbac48b5202903751/f5925c18-4dee-450e-848b-8cbe74634017` |

> **这不是某轮执行的 trace id**，而是限频事件的请求标识，仅作为过程真实性佐证记录在此。
> 不得被引用为任何轮次的 `model_trace_id`。

---

## 5. 相关文件

| 内容 | 路径 |
| --- | --- |
| 评测方留痕（含 R9 执行与独立核验） | `../trace.md` |
| 模型亲笔逐轮留痕（R2–R9） | `../final-artifact/TRACE_R2.md … TRACE_R9.md` |
| R0 亲笔留痕（历史目录） | `../_trial-history/hy3/trace/R0.md` |
| 逐轮 Prompt 原文 | `../../round-evidence/R0…R9/prompt.md` |
| R0–R8 基线 Golden 结果 | `../GOLDEN_BASELINE_R0-R8.md` |
