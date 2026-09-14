# evaluation — 真实模型 Trial 结果存放区

> **本目录当前包含一个完成态的模型评测：Hy3（`HY3/`）。**
> Hy3 已于 2026-09-14 完成 R0–R9，冻结产物与逐条判定见 `HY3/`，汇总见 `comparison.md`。
> 试标占位名 `model_c` / `model_d`（Kimi-K3 / GLM-5.3）**不在本次交付范围**：未评测、无判定；
> 其仅到 R0/R1 的历史留痕存于 `_trial-history/`（那里刻意**不使用** `final-artifact/` 等完成态命名）。
> **`<MODEL>/` 中的一切内容都必须由实测填写，不得伪造。**

---

## 1. 为什么单独开这个目录

本题的证据分两类，**不可混用**：

```
┌─────────────────────────────┐
│ Golden Evidence             │  回答：参考答案本身是否满足 Benchmark 要求？
│ golden_answer/              │
│ round-evidence/             │  → 只能证明「题目可执行、参考答案自洽」
│ test/                       │  → 已完成（见 evaluation-report.md §5）
└─────────────────────────────┘
              │
              │  这两者之间没有推导关系：
              │  Rubric PASS ≠ Golden Answer PASS ≠ Model PASS
              ▼
┌─────────────────────────────┐
│ Model Evidence              │  回答：某个 Coding Agent 跑完 R0–R9 后是否满足 Rubric？
│ evaluation/<model>/         │
│   trace.md                  │  → 只能由真实 Trial 产生
│   result.md                 │  → 当前：HY3 已完成（见 HY3/result.md）
│   final-artifact/           │
│   evidence.md               │
└─────────────────────────────┘
```

判定链条（每一段都必须有实物证据，不能跳段）：

```
Real Model Trial
        ↓   从 init/ 起，逐轮原文发送 R0…R9
Model Trace + Final Artifact
        ↓   保存 request id / trace id 与最终工作区
Rubric Evaluation
        ↓   用 round-evidence/R#/evidence.json 的同一套命题逐条判定
Model Result
```

---

## 2. 目录结构（每个模型一个独立目录）

```
evaluation/
├── README.md                  本文件：口径、结构、判定流程
├── _TEMPLATE/                 空白模板（下划线前缀 = 非真实结果）
│   ├── trace.md
│   ├── result.md
│   ├── evidence.md
│   └── final-artifact/
│       └── README.md
│
├── HY3/                       真实 Trial 结果（已完成 R0–R9）
│   ├── trace.md               调用留痕（隔离、路由校验、逐轮）
│   ├── result.md              模型级结论（环境、完成轮数、测试与 Rubric 结果、人工复核）
│   ├── evidence.md            逐条 Rubric 判定（ID / PASS-FAIL-NA / 证据类型 / 路径 / 理由）
│   ├── harness_test/          Golden 断言的适配层（只改 harness.py 做接口适配）
│   └── final-artifact/        模型从 init/ 出发的最终工作区（源码 + 测试 + README）
├── _trial-history/            2026-09-14 中断的多模型 Trial 历史留痕（非完成态）
├── comparison.md              横向对比（本交付仅一个模型：Hy3）
└── _TEMPLATE/                 空白模板（下划线前缀 = 非真实结果）
```

**命名**：目录名 = 评测报告里使用的模型名（如 `HY3`）。
不要建空目录占位——**没有真实 Trace 就不建目录**，避免被误读为"已评测但结果为空"。

**本次交付范围**：只评测 **Hy3**（已完成，见 `HY3/`）。试标占位名 `model_c` / `model_d`
（Kimi-K3 / GLM-5.3）**不在本次交付范围**：未评测、不建目录、无判定。

---

## 3. 四个文件的字段规范

### 3.1 `trace.md` — 调用留痕

记录 **CodeBuddy request ID / model trace ID**，以及每一轮的发送与回执。

必须字段：

| 字段 | 说明 |
| --- | --- |
| 模型名 / 模型版本 | 与 `result.md` 一致 |
| 被测日期 | |
| 工作区路径 | 该模型独立 workspace 的路径 |
| 记忆状态 | 应为 **关闭** |
| 思考等级 | 应为 **最高** |
| 起始工作区 | 应为 `init/` |
| 逐轮表 | 轮次 / 发出的 Prompt / request id 或 trace id / 用时 / 是否报错 |
| 插入轮 | 若模型报错需 debug 而插入轮次，单独列出并标注"非评分轮" |

### 3.2 `result.md` — 模型级结论

必须字段（缺项写"未采集"，不得留空误导）：

```
model name
model version
environment            （OS / Python 版本 / 依赖安装方式）
rounds completed       （R0…R9 中实际完成的轮次；未完成要写清断在哪一轮）
final test result      （pytest 结果：通过 / 失败 / 收集错误，附命令）
rubric result          （D1…D5 与 Final 得分）
key failures           （关键失败点：落在哪条不变量 / 哪个决策上）
human review result    （人工评审结论：取舍说明、解释一致性、是否过度设计）
```

### 3.3 `evidence.md` — 逐条 Rubric 判定

每条 Rubric 一行，字段固定：

```
Rubric ID | PASS/FAIL/NA | Evidence type | Evidence path | Reason
```

`Evidence type` 取 `TEST > CODE > TRACE > DOC > REVIEW`；
能用 TEST 就不用 REVIEW；必须判断过程时才用 TRACE。
`Evidence path` 必须是**可打开的实际文件/命令**（例如
`final-artifact/tests/test_concurrency.py::test_concurrent_same_after_sale`）。

### 3.4 `final-artifact/` — 模型产出

模型从 `init/` 出发的**最终工作区原件**（源码 + 测试 + README + 依赖声明）。
不裁剪、不美化、不补写；模型没产出 README 就原样保留"没有 README"这个事实。

---

## 4. 判定流程（每轮一次，逐轮留痕；顺序不可跳）

```
1.  CodeBuddy 创建独立 workspace            （一个模型一个，禁止复用）
2.  从 init/ 起                             （不要给任何示例代码）
3.  使用 evaluator 指定模型                  （关闭记忆、最高思考等级）
4.  严格按 R0 → R9 顺序发送 round-evidence/R#/prompt.md 的原文
5.  保存最终 artifact 到 <model>/final-artifact/
6.  保存 request ID / trace ID 到 <model>/trace.md
7.  对 final-artifact 执行 Golden tests      （按 test/README.md §4 只改 harness.py 适配）
8.  按 round-evidence/R#/evidence.json 的同一套命题逐条判定 Rubric
9.  找出模型之间真正产生差异的 invariant / decision
10. 回写 <model>/result.md 与 evidence.md，并更新 evaluation-report.md 的模型表现部分
```

**第 4 步是硬约束**：逐轮原文发送，不补充解读、不预告后续轮次、不提前施加未来轮次的要求
（评分边界见 `instruction.md` §8「不得提前扣分」）。

---

## 5. 禁止事项（P0）

- 不伪造模型名、模型版本、`trace_id`、模型输出。
- 不伪造模型 PASS / FAIL，不把 Golden Answer 的结果写成模型结果。
- 不为"制造区分度"而削弱 Golden Answer 或删改测试。
- 不把模型评价写入 Golden baseline（`rubric.md` §4、`evidence-matrix.md` §1 只记 Golden）。
- 不把未跑完的 Trial 写成"已完成"；未完成的轮次要显式写清断点。

---

## 6. 相关文件

| 文件 | 作用 |
| --- | --- |
| `_TEMPLATE/` | 空白模板，复制成 `<model>/` 后填写 |
| `../rubric.md` | 逐条判定标准（22 条）与 Golden 基线 |
| `../evidence-matrix.md` | Rubric → Evidence 追溯（Golden 侧） |
| `../round-evidence/R0…R9/` | 每轮 Prompt 原文、evidence.json、reviewer.md 占位表 |
| `../test/README.md` | 测试套 + 「如何适配被测模型产出」（唯一适配点 `harness.py`） |
| `../evaluation-report.md` | 评测反馈报告：质量门 / 变异测试 / 风险与结论 |
