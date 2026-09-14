# trace — Hy3（BE-ORDER-REFUND 真实 Model Trial）

> 评测方独立留痕。模型亲笔逐轮 trace 见 `final-artifact/TRACE_R2.md … TRACE_R9.md`（R0/R1 留痕缺失，见 §2）。
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

| 轮次 | Prompt 来源 | trace id | 模型报错 | 备注 |
| --- | --- | --- | --- | --- |
| R0 | `round-evidence/R0/prompt.md` | `TRIAL-RUN-LOG`（前序） | 否 | 前序真实运行 |
| R1 | `round-evidence/R1/prompt.md` | 留痕缺失（已知缺陷 D-1） | 否 | 前序真实运行 |
| R2…R8 | `round-evidence/R2…R8/prompt.md` | `TRACE_R2…R8`（模型亲笔） | 否 | 前序完成，独立复跑确认 |
| R9 | `round-evidence/R9/prompt.md` | `agent-d00735d3`（本会话派发） | 否 | **本会话执行**，落地 90/90 |

> R0–R8 由前序会话在配额窗口内完成。本会话负责被 429 阻断的 **R9**（18:01 配额开窗后派发）。

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
| 逐轮 diff / 快照 | `D:\Workspace\trial-workspaces\_eval_progress\baseline_hy3_before_R9.txt`、`r9_pytest.txt`、`rerun_func.txt`、`rerun_sec.txt` |
| 最终工作区（冻结） | `evaluation/HY3/final-artifact/` |
| 模型亲笔 trace | `final-artifact/TRACE_R9.md` |
| Golden 适配层 | `evaluation/HY3/harness_test/`（`conftest.py` + `harness.py`，仅接口适配，未改断言） |
| 基线（R0–R8） | `evaluation/HY3/GOLDEN_BASELINE_R0-R8.md` |
| 冲突产物（过期） | `result.md`/`evidence.md`/`trace.md` @ 18:37–39（已被覆盖，不再引用） |
