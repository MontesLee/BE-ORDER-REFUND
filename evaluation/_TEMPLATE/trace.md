# trace — <model>

> **模板。** 复制 `_TEMPLATE/` 为 `<model>/` 后填写；**未发生真实 Trial 前不得填写本文件**。
> 填不出的字段写「未采集」，不得编造。

## 1. 会话信息

| 字段 | 值 |
| --- | --- |
| 模型名 | `<HY3 / model_c / model_d …>` |
| 模型版本 | `<未采集>` |
| 被测日期 | `<YYYY-MM-DD>` |
| 工作区路径 | `<该模型独立 workspace 路径>` |
| 起始工作区 | `init/` |
| 记忆状态 | 关闭 |
| 思考等级 | 最高 |
| 一轮一 workspace | 是 |

## 2. 逐轮留痕

| 轮次 | 发出的 Prompt | request id / trace id | 用时 | 模型是否报错 | 备注 |
| --- | --- | --- | --- | --- | --- |
| R0 | `round-evidence/R0/prompt.md` | | | | |
| R1 | `round-evidence/R1/prompt.md` | | | | |
| R2 | `round-evidence/R2/prompt.md` | | | | |
| R3 | `round-evidence/R3/prompt.md` | | | | |
| R4 | `round-evidence/R4/prompt.md` | | | | |
| R5 | `round-evidence/R5/prompt.md` | | | | |
| R6 | `round-evidence/R6/prompt.md` | | | | |
| R7 | `round-evidence/R7/prompt.md` | | | | |
| R8 | `round-evidence/R8/prompt.md` | | | | |
| R9 | `round-evidence/R9/prompt.md` | | | | |

## 3. 插入轮（非评分轮）

模型报错需要 debug 而插入的轮次。**这些轮次不计入评分**，但必须留痕，
以便人工判断"是环境问题还是模型问题"。

| 插入位置 | 插入原因 | request id / trace id | 备注 |
| --- | --- | --- | --- |
| | | | |

## 4. 原始留痕位置

| 类型 | 路径 / 标识 |
| --- | --- |
| 会话导出 | `<路径或链接>` |
| 逐轮 diff / 快照 | `<路径>` |
| 最终工作区 | `<model>/final-artifact/` |
