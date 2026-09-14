# BE-ORDER-REFUND — 题目与模型表现简述

> 版本：`BE-ORDER-REFUND_202609141100`
> 四件套：`instruction.md`（题目）· `test/`（测试）· `solve/`（参考实现）·
> `evaluation-report.md`（评测反馈报告）

---

## 1. 题目速览

| 项 | 内容 |
| --- | --- |
| 领域 | 电商订单售后退款（状态机 + 资金一致性） |
| 技术栈 | Python 3.11+ · FastAPI · SQLite · pytest |
| 轮次 | R0–R9，共 10 轮，同一连续工作区 |
| 核心矛盾 | 状态机 + 事务一致性 + 幂等 + 并发 + 权限（五类交织） |
| 六条不变量 | I1 金额上限 · I2 一售后一成功退款 · I3 状态机 · I4 第三方失败一致性 · I5 多 worker · I6 权限隔离 |
| 区分度来源 | check-then-write 竞态、进程内锁冒充分布式保护、第三方失败误记成功、只校验存在性不校验归属 |
| 评审成本 | 自动化覆盖全部客观不变量；人工评审集中在取舍说明与解释一致性，2–4 小时可控 |

---

## 2. 包内容与 Tlabel 交付格式的映射

```
BE-ORDER-REFUND/
├── instruction.md          题目说明（含 R0–R9 Prompt 原文与评分边界）
├── introduction.md         本文件：题目与模型表现简述
├── rubric.md               22 条原子 Rubric
├── evidence-matrix.md      Rubric → Evidence 追溯矩阵
├── evaluation-report.md    评测反馈报告（含质量校验结论）
├── init/                   被测模型的起始工作区（本题初始无自带文件 → 空目录）
├── golden_answer/          参考实现 + 22 个测试 + verify.sh + verify_doc
├── round-evidence/R0…R9/   每轮 prompt.md / test-result.txt / evidence.json / reviewer.md
├── test/README.md          测试套说明与"如何适配被测模型产出"
└── solve/README.md         参考实现交付说明
```

对应标注平台要求（`version` 命名的压缩包内容）：

| 平台要求 | 本包对应 |
| --- | --- |
| `init/` 项目初始态 | `init/`（空） |
| `golden_answer/` | `golden_answer/`（含 `verify_doc/`，即 README、可执行测试套、运行日志） |
| `model_A_name/` 等模型产物 | 待实测后按模型名创建（**当前为空，不伪造**） |
| `introduction.md` | 本文件（§4 模型表现表） |
| 其他留痕 | `round-evidence/`、`evidence-matrix.md`、`evaluation-report.md` |

---

## 3. Golden Answer 基线（已完成实测）

| 指标 | 结果 | 证据 |
| --- | --- | --- |
| 测试套 | **22 passed / 0 failed**（干净 venv，9.23s） | `golden_answer/verify_doc/test-result.txt` |
| 存储级不变量保护 | **6/6 通过**（第二条成功退款被唯一索引拒绝；超额写入被 CHECK 拒绝；跨连接写锁互斥） | 同上 / `verify_doc/db-guard-check.txt` |
| Golden test 覆盖 | **18/18**（T01–T18），R8 六类分类 **6/6** | `verify_doc/coverage-matrix-check.txt` |
| `verify.sh` | **exit code 0** | 同上 |
| 质量校验 | **S1–S6 = 17/18 → PASS** | `evaluation-report.md` §3 |
| 区分度实证 | 6 个真实弱实现变异体 **6/6 被测试套杀死**；对照组全绿 | `evaluation-report.md` §4 |

---

## 4. 各模型表现简述

> **状态：待实测填写。** 按试标规则 §3.2，题目锁定后须用给定模型实测确认区分度。
> 本次试标模型：**HY3、model_c、model_d**（正式评测可用 Hy 3、Kimi 3、
> deepseek v4 flash、Claude Opus 5）。
> **没有真实模型 Trace 之前，本表不填任何结论**（不允许伪造）。

### 4.1 逐轮关键判定

| 轮次 / 关键点 | Golden Answer | HY3 | model_c | model_d |
| --- | --- | --- | --- | --- |
| R0 可运行 + 主流程 | PASS | 待填 | 待填 | 待填 |
| R1 累计金额上限（I1） | PASS | 待填 | 待填 | 待填 |
| R2 幂等（I2） | PASS | 待填 | 待填 | 待填 |
| R3 多 worker 保护（I5） | PASS | 待填 | 待填 | 待填 |
| R3 并发测试是否校验业务结果 | PASS | 待填 | 待填 | 待填 |
| R4 竞态定位 + 最小修复 | PASS | 待填 | 待填 | 待填 |
| R5 解释与代码一致 | PASS | 待填 | 待填 | 待填 |
| R6 第三方失败语义（I4） | PASS | 待填 | 待填 | 待填 |
| R7 授权隔离与性能（I6） | PASS | 待填 | 待填 | 待填 |
| R8 测试覆盖与稳定性 | PASS | 待填 | 待填 | 待填 |
| R9 最终收敛与全量回归 | PASS | 待填 | 待填 | 待填 |

### 4.2 Rubric 得分

| 维度（权重） | Golden Answer | HY3 | model_c | model_d |
| --- | --- | --- | --- | --- |
| D1 Instruction Following (15%) | 1.00 | 待填 | 待填 | 待填 |
| D2 Feature Delivery (35%) | 1.00 | 待填 | 待填 | 待填 |
| D3 Task Efficiency (15%) | 1.00 | 待填 | 待填 | 待填 |
| D4 Architecture Quality (20%) | 1.00 | 待填 | 待填 | 待填 |
| D5 Context Understanding (15%) | 1.00 | 待填 | 待填 | 待填 |
| **Final** | **1.00** | 待填 | 待填 | 待填 |

### 4.3 待填的观察点

- 各自的分层点落在哪一条不变量上（决定本题的实际区分度）。
- 是否出现"进程内锁冒充分布式保护"（失效模式 #7）。
- R6 是否真的做出可替换的网关抽象，还是只加 `try/except`。
- R7 的性能修复是否克制（有没有为了"优化"引入缓存却没有证据）。
- 是否有模型在 R9 收敛时弱化历史不变量（删掉并发断言等）。
- 每个模型的 `trace_id` 按试标规则 §6.2 获取后填入 `round-evidence/*/reviewer.md`。

---

## 5. 评测操作提示

1. 每个模型一个**全新工作区**，从 `init/` 起，关闭记忆，最高思考等级。
2. 逐轮发送 `round-evidence/R#/prompt.md` 的**原文**，不补充解读、不透露后续轮次。
3. 模型报错需要 debug 时，插入轮保持与主轮次一致的风格。
4. 保存每个模型的最终交付物，按 `test/README.md` §4 适配测试套后运行。
5. 按 `round-evidence/R#/evidence.json` 逐轮判定 Rubric，`PASS/FAIL/NOT_APPLICABLE` 三选一。
6. 按 `rubric.md` §3 汇总五维得分；`NOT_APPLICABLE` 不入分母。
