# BE-ORDER-REFUND — Model Trial 对比（comparison）

> 横向对比各模型在 R0–R9 后的 Rubric 结果。详细判定见各模型目录 `evaluation/<model>/{trace,result,evidence}.md`。
> 本文件为**真实 Trial 结果**，不与 Golden Answer Validation 混淆。判定以评测方对冻结产物的独立复跑为准。

## Hy3（已完赛 R0–R9）

| 维度（权重） | 得分 | 关键结论 |
| --- | --- | --- |
| D1 Instruction Following (15%) | 1.00 | 项目可运行、增量演进、最终交付完整 |
| D2 Feature Delivery (35%) | 0.75 | 6/8：FD-04 创建端幂等缺失、FD-08 审核缺归属校验 |
| D3 Task Efficiency (15%) | 1.00 | 无无关重构、无多余基础设施、定向+全量回归闭环 |
| D4 Architecture Quality (20%) | 1.00 | 跨进程并发/金额/状态机架构完好；网关可注入 |
| D5 Context Understanding (15%) | 1.00 | 历史不变量保持、事故定位正确、解释与代码一致 |
| **Final** | **0.91** | 20 PASS / 2 FAIL / 0 NA |

- 冻结产物：`evaluation/HY3/final-artifact/`（store.py @ 18:41:28）
- Golden 统一套件（对冻结产物）：**14 passed / 7 failed**（功能 12/6 + 安全 2/1；排除 `test_performance.py`）
- 模型自带套件：实测 **90 passed**（独立复跑确认，非虚假）
- 真实缺陷：FD-04（创建端幂等缺失）、FD-08（审核端点无归属校验，且 README 虚标该保证）
- 契约偏差（不变量成立）：FD-03 超额 clamp 非 4xx；FD-07/AQ-04 第三方失败返 502 非 4xx

## 其它模型

| 模型 | 进度 | 状态 |
| --- | --- | --- |
| Hy3 (`hy3`) | R0–R9 全完成 | ✅ 已完赛（本文件上表） |
| model_c (Kimi-K3, `kimi-k3-1`) | R0–R1 | ⛔ 配额阻断，未完成（见 `_trial-incomplete/`） |
| model_d (GLM-5.3, `glm-5.3`) | R0 | ⛔ 配额阻断，未完成（见 `_trial-incomplete/`） |

> 注：18:01 一处并行自动化曾对带 `NameError` 的中间态 R9 写出过期对比（Final 0.41），已被正确 R9（90/90）覆盖；以上为独立复跑结论。

> kimi-k3 / glm-5.3 的完整 R0–R9 Trial 与对比待续跑后补充。
