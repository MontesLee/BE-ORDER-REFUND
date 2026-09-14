# trace — Hy3（BE-ORDER-REFUND 真实 Model Trial）

> 评测方独立留痕。模型亲笔逐轮 trace 见 `final-artifact/TRACE_R2.md … TRACE_R9.md`（R0/R1 留痕缺失，见 §2）。
> 逐轮原始留痕登记见 `raw-trace/R0.md … R9.md`（缺失轮显式标 `MISSING`）。
> 本文件以**实测**为准，不采信模型自报数字（协议 §6）。

## 1. 会话信息

| 字段 | 值 |
| --- | --- |
| 模型名 | `hy3`（账号权威清单确认有效） |
| 模型版本 | `POWERED-BY: Hy3`（与 `hy3` 一致，R9 子 Agent 末尾输出） |
| 被测日期 | 2026-09-14 |
| 工作区路径 | `D:\Workspace\trial-workspaces\hy3`（独立工作区，从 `init/` 复制） |
| 隔离铁律 | 子 Agent 仅可读 `trial-workspaces/hy3`；禁止读 `instruction.md/rubric.md/evidence-matrix.md/final-audit.md/evaluation-report.md/introduction.md`、`golden_answer/`、`round-evidence/`、`evaluation/`（除本任务显式输出目录）、`kimi-k3/glm-5.3/`、`_prompts/_traces/_evidence/` |
| 路由校验 | R9 子 Agent 末尾 `POWERED-BY: Hy3` → 路由生效 |
| 配额 | hy3 限频 18:00:01 UTC+8 重置；R9 于 18:01 后派发成功落地 |

## 2. 逐轮留痕

逐轮**原始留痕登记**（含每轮的 Prompt 来源 / 模型留痕 / 代码变化 / 独立核验）见
`raw-trace/R0.md … R9.md`；下表为汇总。

| 轮次 | Prompt 来源 | 模型亲笔留痕 | `model_trace_id`（真实 request id） | 模型报错 | 备注 |
| --- | --- | --- | --- | --- | --- |
| R0 | `round-evidence/R0/prompt.md` | `_trial-history/hy3/trace/R0.md` | `MISSING` | 否 | 前序真实运行（11 passed） |
| R1 | `round-evidence/R1/prompt.md` | `MISSING` | `MISSING` | 否 | 前序真实运行（19 passed，快照在 `_trial-history/hy3/final-artifact-so-far/`） |
| R2 | `round-evidence/R2/prompt.md` | `final-artifact/TRACE_R2.md` | `MISSING` | 否 | 前序完成，独立复跑 24 passed |
| R3 | `round-evidence/R3/prompt.md` | `final-artifact/TRACE_R3.md` | `MISSING` | 否 | 前序完成，独立复跑 30 passed |
| R4 | `round-evidence/R4/prompt.md` | `final-artifact/TRACE_R4.md` | `MISSING` | 否 | 前序完成，独立复跑 34 passed |
| R5 | `round-evidence/R5/prompt.md` | `final-artifact/TRACE_R5.md` | `MISSING` | 否 | 前序完成，独立复跑 34 passed |
| R6 | `round-evidence/R6/prompt.md` | `final-artifact/TRACE_R6.md` | `MISSING` | 否 | 前序完成，独立复跑 43 passed |
| R7 | `round-evidence/R7/prompt.md` | `final-artifact/TRACE_R7.md` | `MISSING` | 否 | 前序完成，独立复跑 55 passed |
| R8 | `round-evidence/R8/prompt.md` | `final-artifact/TRACE_R8.md`（评测方据产物重建） | `MISSING` | 是（429 截断回复，**但已落地**） | 独立复跑 76 passed |
| R9 | `round-evidence/R9/prompt.md` | `final-artifact/TRACE_R9.md`（模型亲笔） | **`agent-d00735d3`** | 否 | **本会话执行**，落地 90/90 |

> R0–R8 由前序会话在配额窗口内完成。本会话负责被 429 阻断的 **R9**（18:01 配额开窗后派发）。

### 2.1 `model_trace_id` 现状（**不伪造**）

| 项 | 值 |
| --- | --- |
| 唯一真实的派发 ID | `agent-d00735d3`（R9，本会话 Agent 派发标识） |
| R0–R8 的 request id | `MISSING` —— 执行时未采集平台 request id，事后无可核验来源可恢复 |
| 生成规则 | **不存在**。未根据文件名 / 模型名 / Git commit 生成过任何 ID |
| 补充方式 | 只能在**下一轮 Trial 开始时**开启 request id 采集；已发生的 R0–R8 无法回填 |

`MISSING` 表示「无真实来源」，**不表示「没跑过」**：每轮的执行真实性由工作区产物、
模型亲笔留痕与评测方独立复跑共同证明（见 §3 与 `raw-trace/`）。

> 另：平台在 R8 派发时返回的 **429 限频回执**中携带过 request id，
> 但那是限频事件的标识，**不是某轮执行的 trace id**，仅作过程佐证记录于 `raw-trace/README.md` §4。

## 3. R9 执行与独立核验（关键）

**派发**：`model="hy3"`，wrapper 含原文 14 项核心保证 + 7 条交付要求 + 隔离铁律 + 「末尾 `POWERED-BY`」。

**模型自报**：`TRACE_R9.md` 称「`90 passed, clean environment`」，并完成整数分精度改造 + 超额 clamp 语义 + 6 个旧测试对齐。

**评测方独立复跑（托管解释器，非模型自报）**：

| 套件 | 命令 | 实测结果 |
| --- | --- | --- |
| 模型自带 `tests/` | `pytest tests -v` | **90 passed**（与自报一致，非虚假） |
| Golden 统一（owner 模式） | `harness_test/` + 冻结产物 | **12 passed / 6 failed** |
| Golden 统一（caller 模式） | `HY3_EXECUTOR=caller` | **2 passed / 1 failed** |
| **Golden 合计** | — | **14 passed / 7 failed** |

**冻结**：`trial-workspaces/hy3` → `evaluation/HY3/final-artifact/`（排除 `.pytest_cache`/`_quarantine`），store.py 18:41:28。

**与 R0–R8 基线对照**：基线（冻结前 R0–R8 产物）Golden 亦为 14 passed / 7 failed（见 `GOLDEN_BASELINE_R0-R8.md`）。R9 把金额改为整数分（精度提升）、超额改为 clamp（语义变更），未改变 Golden 通过数，但改变了两条测试的行为（超额测试由 4xx→clamp 200、第三方失败 502 不变）。

## 4. 并行运行冲突说明（重要）

18:01 用户触发续跑时，**一处并行自动化（`a3e075e8`）也曾派发 R9**，于 18:37–39 对一份**带 `NameError` 的中间态 R9 产物**（store.py 未定义 `amount`）写出过期 `result.md`/`evidence.md`/`trace.md`（67F/23P、Golden 4–6 passed）。该中间态后被本会话的正确 R9（store.py 18:41:28，`orow["amount"]` 正确，90/90）覆盖；本目录三文件已按独立复跑结论覆盖。以本文件 + `result.md` + `evidence.md`（18:56 复跑确认 14/7）为权威。

## 5. 原始留痕位置

| 类型 | 路径 |
| --- | --- |
| 逐轮原始留痕登记（R0–R9，含 MISSING 标注） | `raw-trace/`（`README.md` + `R0.md … R9.md`） |
| 逐轮 diff / 快照 | `D:\Workspace\trial-workspaces\_eval_progress\baseline_hy3_before_R9.txt`、`r9_pytest.txt`、`rerun_func.txt`、`rerun_sec.txt` |
| 最终工作区（冻结） | `evaluation/HY3/final-artifact/` |
| 模型亲笔 trace | `final-artifact/TRACE_R9.md`（R2–R9 同目录） |
| Golden 适配层 | `evaluation/HY3/harness_test/`（`conftest.py` + `harness.py`，仅接口适配，未改断言） |
| 基线（R0–R8） | `evaluation/HY3/GOLDEN_BASELINE_R0-R8.md` |
| 冲突产物（过期） | `result.md`/`evidence.md`/`trace.md` @ 18:37–39（已被覆盖，不再引用） |
