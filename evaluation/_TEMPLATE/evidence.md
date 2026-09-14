# evidence — <model>

> **模板。** 复制 `_TEMPLATE/` 为 `<model>/` 后填写；**未发生真实 Trial 前不得填写本文件**。
> 逐条对照 `rubric.md` §1 的 22 条命题判定，三选一：`PASS` / `FAIL` / `N/A`（NOT_APPLICABLE）。

## 0. 判定口径

- `Evidence type` 取 `TEST > CODE > TRACE > DOC > REVIEW`。能用 TEST 就不用 REVIEW；
  只有必须判断模型过程时才用 TRACE。
- `Evidence path` 必须是**可打开的实际文件或可复跑的命令**，不接受"看起来合理"。
- `N/A` 只用于该模型事实上不适用/不可判定的条目（例如未跑到该轮）；
  **不得**用它规避失败。

## 1. 判定表

| Rubric | Round | Result | Evidence type | Evidence path | Reason |
| --- | --- | --- | --- | --- | --- |
| IF-01 | R0 | | | | |
| IF-02 | R9 | | | | |
| IF-03 | R9 | | | | |
| FD-01 | R0 | | | | |
| FD-02 | R1 | | | | |
| FD-03 | R3 | | | | |
| FD-04 | R2 | | | | |
| FD-05 | R3 | | | | |
| FD-06 | R6 | | | | |
| FD-07 | R6 | | | | |
| FD-08 | R7 | | | | |
| TE-01 | R9 | | | | |
| TE-02 | R8 | | | | |
| TE-03 | R7 | | | | |
| AQ-01 | R3 | | | | |
| AQ-02 | R7 | | | | |
| AQ-03 | R6 | | | | |
| AQ-04 | R6 | | | | |
| AQ-05 | R5 | | | | |
| CU-01 | R9 | | | | |
| CU-02 | R6 | | | | |
| CU-03 | R5 | | | | |

> `Round` 列与 `rubric.md` §1 保持一致（Tlabel：多轮 Rubric 取**最后一个相关轮次**）。

## 2. 汇总

```
Total: 22
PASS:
FAIL:
N/A:
Issues:
```

## 3. 与其它模型的差异点

| 分层点（不变量 / 决策） | 本模型 | 其它模型 | 证据 |
| --- | --- | --- | --- |
| | | | |
