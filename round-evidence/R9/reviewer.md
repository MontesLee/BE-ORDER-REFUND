## 本轮考点

R9 不新增评分维度，做的是**全量历史要求的最终回归**：14 条最终要求逐条落到测试上。
同时要求 clean environment 可运行，因此"能在自己机器上跑"不算，必须能按 README 从零跑起来。

## 人工评审要点

| 看什么 | 判定依据 |
| --- | --- |
| 14 条要求的覆盖 | 逐条对应到测试或用例；缺项要指出 |
| 启动文档 | README 是否写清依赖安装、启动、测试命令 |
| 依赖声明 | `requirements.txt` 是否完整（缺依赖会在干净环境直接失败） |
| 是否"删掉困难的部分" | 收敛时为了过测试而弱化不变量（例如去掉并发断言）属于 FAIL |
| 最终架构说明 | 是否讲清核心保证与已知限制 |

## Golden Answer 观察

- `verify.sh`：新建 venv → 安装依赖 → 指向一次性数据库 → 跑完整套件 →
  存储层探测 → 覆盖率探测 → 透传退出码；真实运行结果见 `verify_doc/test-result.txt`。
- `README.md` 覆盖：快速开始、环境变量、验证方式、领域模型、状态机、六条不变量的落地点、
  接口表、已知限制。

## 自动化证据

`test-result.txt` 中 R9-T01、R9-T02 的命令与结果；
清洁环境完整日志见 `golden_answer/verify_doc/test-result.txt`。

## 模型 Trace 留痕

> 本次交付仅评测一个模型：**Hy3（已完成 R0–R9）**。逐轮判定与证据见 `evaluation/HY3/evidence.md`，
> 汇总见 `evaluation/HY3/result.md`。占位名 `model_c` / `model_d` **不在本次交付范围**（未评测），故不列。
