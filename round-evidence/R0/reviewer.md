## 本轮考点

R0 只问一件事：**能不能把一个最小后端服务真的搭起来并跑通主流程**。
当轮评分只看可运行性、基础流程、基础 API、基础测试——
partial refund / 累计上限 / 幂等 / 并发 / 第三方失败 / 安全 / 性能**一律不得在此扣分**。

## 人工评审要点

| 看什么 | 判定依据 |
| --- | --- |
| 项目能否按 README 启动 | README 里的启动命令是否真的可用；是否有 requirements 声明 |
| 数据模型是否合理 | 是否把订单/售后/退款分开；金额是不是整数分而不是 float |
| 状态是否显式建模 | 是否出现 `status` 字段与审核步骤，而不是"创建即退款" |
| 是否有基础测试 | 至少覆盖主流程；不要求覆盖未来需求 |
| 是否过度设计 | R0 明确说"不需要过度设计"；引入 MQ/微服务是负分 |

## Golden Answer 观察

- 目录：`app/{main,models,schemas,repository,service,state_machine,refund_gateway,auth}.py`，职责按层切开。
- 金额全部为整数分；`orders`/`after_sales` 上带 `CHECK` 约束。
- 状态机在 R0 就被抽成 `state_machine.py` 单一转换表——这是后续 R3/R4/R6 能"最小修复"的前提。
- R0 阶段的 `execute` 已经要求 `AGENT` 角色、已经要求 `APPROVED` 前置状态（为 R7 留出可收敛的接口）。

## 自动化证据

`test-result.txt` 中 R0-T01..T03 的命令与输出。

## 模型 Trace 留痕

> 本次交付仅评测一个模型：**Hy3（已完成 R0–R9）**。逐轮判定与证据见 `evaluation/HY3/evidence.md`，
> 汇总见 `evaluation/HY3/result.md`。占位名 `model_c` / `model_d` **不在本次交付范围**（未评测），故不列。
