# BE-ORDER-REFUND — 多轮式后端开发 Agent 评测题

> 一道面向 Backend Agent 的**多轮**工程评测题。领域为**电商订单售后退款**（状态机 + 资金一致性），
> 通过 R0–R9 共 10 轮连续对话考察模型在「需求演进 + 技术取舍 + 线上事故 + 安全/性能」下的工程能力。
>
> 版本：`BE-ORDER-REFUND_202609141100` ｜ 技术栈：**Python 3.11+ · FastAPI · SQLite · pytest**

---

## 0. 状态：已完成 / 未完成（先看这里）

| | 内容 |
| --- | --- |
| ✅ **已完成** | Benchmark 设计（R0–R9 连续 10 轮）· Golden Answer 参考实现 · 22 条自动化测试 · `verify.sh` 一键验证 · 6 条核心不变量自动化 · 22 条原子 Rubric · Rubric→Evidence→Test 双向追溯 · 变异测试区分度实证 |
| ✅ **已完成** | **真实模型评测（单模型）：Hy3** —— 已完成 R0–R9，冻结产物与 22 条 Rubric 判定已入库，**Final = 0.91**（20 PASS / 2 FAIL）。见 `evaluation/HY3/` 与 `evaluation/comparison.md` |
| 🚫 **不在本次交付范围** | 其它模型（试标占位名 `model_c` / `model_d`，即 Kimi-K3 / GLM-5.3）：**未评测、无判定**。其仅到 R0/R1 的历史留痕存于 `evaluation/_trial-history/` |

**当前验证状态**（只列实测数据；任何一处与实际结果不一致时，**以真实测试结果为准**）：

| 项 | 实测值 |
| --- | --- |
| Golden Answer | **PASS** —— `pytest tests -rA` → **22 passed / 0 failed / 0 error**（exit 0） |
| Golden 存储级守卫 | **6/6**（`verify_doc/check_db_guards.py`） |
| Golden 覆盖矩阵 | **18/18**，R8 六类分类 **6/6**（`verify_doc/check_coverage_matrix.py`） |
| Hy3 Trial | **COMPLETE**（R0–R9） |
| Hy3 Final Score | **0.91** |
| Hy3 Rubric | **20 PASS / 2 FAIL**（FAIL = FD-04, FD-08） |
| Rubrics | **22** |
| Rounds | **R0–R9**（10 轮） |
| 题目质量门 | **S1–S6 = 17/18 → PASS** |

> **本仓库包含一次完整的真实 Coding Agent 评测（Hy3，R0–R9 全程）。**
> 模型级结论与逐条证据在 `evaluation/HY3/`，冻结产物在 `evaluation/HY3/final-artifact/`。
> `evaluation/_trial-history/` 保存的是 2026-09-14 一次多模型 Trial 被配额（HTTP 429）中断时的历史留痕，
> 那里刻意**不使用** `final-artifact/` 等完成态命名。
>
> 请注意区分两类证据：本仓库其它位置出现的 `PASS` 多为 **Golden Answer、测试套、题目质量**
> 的判定结果，**不是模型评测结果**。三者关系：
>
> ```
> Rubric PASS  ≠  Golden Answer PASS  ≠  Model PASS
> ```
>
> 模型证据只存放在 `evaluation/<model>/`。

---

## 1. 这是什么

本仓库是一套**可直接入库的评测题交付包**，包含四件套（题目 / 测试 / 参考实现 / 评测反馈报告）
以及逐轮留痕与一套可运行的参考解（Golden Answer）。

| 项 | 内容 |
| --- | --- |
| 领域 | 电商订单售后退款（状态机 + 资金一致性） |
| 轮次 | R0–R9，共 10 轮，同一连续工作区 |
| 核心矛盾 | 状态机 + 事务一致性 + 幂等 + 并发 + 权限（五类交织） |
| 区分度来源 | check-then-write 竞态 · 进程内锁冒充分布式保护 · 第三方失败误记成功 · 只校验存在性不校验归属 |
| 评审成本 | 客观不变量全自动化；人工集中在取舍与解释一致性，2–4 小时可控 |

**六条核心不变量（I1–I6）**，全部落在**数据库层**而非进程内：

| 编号 | 语义 | 落地机制 |
| --- | --- | --- |
| I1 | 累计成功退款 ≤ 已支付金额 | `CHECK (refunded_amount <= paid_amount)` + 单条带条件 `UPDATE` 预占 |
| I2 | 同一售后至多一条成功退款 | 部分唯一索引 `ux_refunds_one_success ... WHERE status='REFUNDED'` + 认领 CAS |
| I3 | 只允许合法状态迁移，`REFUNDED` 为终态 | `app/state_machine.py` 单一转换表，所有写状态经它 |
| I4 | 第三方渠道失败时本地不得标记成功 | 渠道裁决在事务外取得，`_settle()` 二分；失败分支回退额度 |
| I5 | 多 worker 并发下 I1/I2 仍成立 | `BEGIN IMMEDIATE` + `busy_timeout=30s` + 上述数据库约束（**非** `threading.Lock`） |
| I6 | 不能访问他人订单/售后，不能绕过审核 | `assert_can_view` 归属校验（跨租户 **404**）+ `approve/execute` 仅 `AGENT` |

**不变量分层**（仅为便于评审快速抓重点，**不改变测试与业务逻辑**——六条全部照常自动化验证）：

| 层级 | 不变量 | 为什么在这一层 |
| --- | --- | --- |
| **Primary** | **I1** 金额上限（不可超额退款）· **I2** 一个 AfterSale 最多一条成功退款 · **I4** 第三方失败不得标记本地成功 | 直接决定「钱会不会算错 / 会不会重复出款」。这题的核心不是「功能多」，而是围绕这三条反复施压 |
| **Supporting** | **I3** 状态机合法性 · **I5** 多 worker 并发安全 · **I6** 用户权限隔离 | 保障与放大层：I3 约束「什么时候允许动钱」，I5 决定 Primary 在多进程下是否依然成立，I6 决定谁能触发 |

> 关键设计：并发保护必须**跨进程**有效，所以用 SQLite 写锁 + 约束兜底，而不是进程内锁——后者在单进程测试中会通过，却是本题要抓的高发失效模式。

---

## 2. 文件结构

```
BE-ORDER-REFUND/
├── README.md                   本文件
├── DELIVERY-MAP.md             一页导航：每个文件/目录的角色，以及「想看什么该走哪条路径」
├── instruction.md              题目全文：概览 / 核心矛盾 / 六条不变量 / 状态机 / 实体模型 /
│                               统一接口契约 / R0–R9 Prompt 原文 / 每轮评分边界 / 17 条失效模式
├── introduction.md             题目速览 + 包内容与交付格式映射 + Golden 基线 + 模型表现（Hy3 实测）
├── rubric.md                   22 条原子 Rubric（D1–D5 / IF·FD·TE·AQ·CU）+ 逐条 Verification + 计分
├── evidence-matrix.md          Rubric → Evidence → Test 双向追溯矩阵
├── evaluation-report.md        评测反馈报告：B1–B5 / S1–S6 / 变异测试 / 覆盖 / 风险 / 结论
│
├── init/                       被测模型的起始工作区（**故意为空**，仅说明文件，避免泄题）
│   └── README.md
│
├── golden_answer/              参考实现（Golden Answer）+ 测试套 + 一键验证
│   ├── app/                    FastAPI 应用，按职责分层
│   │   ├── main.py             路由入口、错误码映射
│   │   ├── service.py          业务规则与事务边界；三段式执行退款
│   │   ├── repository.py       SQLite 连接 / DDL / SQL；I1、I2 的数据库级保护
│   │   ├── state_machine.py    状态转换单一真相表
│   │   ├── auth.py             调用方身份与归属 / 角色校验
│   │   ├── refund_gateway.py   可替换第三方渠道（可编程成功/失败）
│   │   ├── models.py           领域枚举与值对象（无 I/O）
│   │   └── schemas.py          请求/响应模型（金额声明为 int）
│   ├── tests/                  22 个测试（T01–T18 + R0 基线 + 边界）
│   │   ├── conftest.py         fixture：TestClient + 双进程 uvicorn 集群
│   │   ├── harness.py          ★ 唯一接口适配层（Api 类）——接被测模型只改这里
│   │   └── test_*.py           按主题分文件（order / refund / amount / idempotency /
│   │                           state_machine / failure_retry / concurrency / security / performance）
│   ├── verify.sh               一键验证：建干净 venv → 装依赖 → 全量测试 → 两项探测
│   ├── verify_doc/             验证留痕与探针
│   │   ├── test-result.txt     真实运行输出（22 passed + 两项探测）
│   │   ├── check_db_guards.py          存储级不变量探针（确定性，不依赖时序）
│   │   ├── check_coverage_matrix.py    T01–T18 与 R8 六类分类覆盖探针
│   │   ├── inspect_for_explanation.py  R5 代码检视输出
│   │   └── README.md
│   ├── requirements.txt · pytest.ini · README.md · .gitignore
│
├── round-evidence/             逐轮留痕（Golden 侧）
│   └── R0…R9/                  每轮 prompt.md · test-result.txt · evidence.json · reviewer.md
│                               （R3 另含 mutation-test.py 与 mutation-report.json）
│
├── evaluation/                 真实模型 Trial 结果存放区
│   ├── README.md               口径：Golden Evidence vs Model Evidence · 目录结构 · 判定流程
│   ├── comparison.md           单模型（Hy3）结果汇总
│   ├── HY3/                    Hy3 评测结果（**已完成 R0–R9**）
│   │   ├── trace.md            评测方留痕：隔离 / 路由校验 / 逐轮 / 独立复跑
│   │   ├── result.md           模型级结论：环境 / 完成轮数 / 测试与 Rubric 结果 / 人工复核
│   │   ├── evidence.md         逐条 Rubric 判定表
│   │   ├── harness_test/       Golden 断言的适配层（只改 harness.py 做接口适配）
│   │   ├── GOLDEN_BASELINE_R0-R8.md   适配层在 R0–R8 产物上的基线结果
│   │   └── final-artifact/     Hy3 从 init/ 出发的最终工作区（冻结）
│   ├── _TEMPLATE/              空白模板（下划线前缀 = 非真实结果）
│   └── _trial-history/         2026-09-14 多模型 Trial 中断时的历史留痕（非完成态）
│
├── test/README.md              测试套说明 + 「如何适配被测模型产出」（6 步流程）
└── solve/README.md             参考实现交付说明与设计取舍一览
```

---

## 3. 快速开始

```bash
cd golden_answer

# 方式一：一键完整验证（新建 venv + 装依赖 + 全量测试 + 存储/覆盖探测，约 8 分钟）
./verify.sh

# 方式二：手动
python -m venv .venv
#   Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
pytest tests -v
uvicorn app.main:app --reload          # 交互式文档 http://127.0.0.1:8000/docs
```

金额单位统一为**分（integer cents）**，全程不使用 `float`；调用方身份通过 `X-User-Id` 请求头传递。

环境变量：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `REFUND_DB_PATH` | `<repo>/data/refund.db` | SQLite 文件路径（便于测试隔离） |
| `REFUND_GATEWAY_MODE` | `ok` | `ok` / `fail` / `fail_first`，注入第三方渠道故障 |
| `REFUND_GATEWAY_FAIL_N` | `1` | `fail_first` 模式下前 N 次调用失败 |

`verify.sh` 额外开关：`VERIFY_PYTHON=/path/to/python`（跳过建 venv）、`VERIFY_SKIP_VENV=1`（复用当前解释器）。

### 3.1 如何评测一个模型（最短流程）

```text
1. 从 init/ 起：把 init/ 复制到一个全新工作区（一个模型一个，关闭记忆，最高思考等级）
2. 按 R0–R9 顺序：逐轮原文发送 round-evidence/R#/prompt.md 的内容，不补解读、不预告后续轮次
3. 跑验证：把模型产出按 test/README.md §4 适配（只改 harness.py），用 golden_answer/tests/ 的断言验证
4. 按 rubric.md 评分：对照 round-evidence/R#/evidence.json 的同一套命题逐条判 PASS / FAIL / NOT_APPLICABLE
5. 看真实样例：evaluation/HY3/ 是本次交付的真实模型实测（trace / result / evidence / raw-trace / final-artifact）
```

> 评分边界见 `instruction.md` §8（**不得提前扣分**）；证据优先级 `TEST > CODE > TRACE > DOC > REVIEW`。

---

## 4. 实测结果（Golden Answer 基线）

| 项目 | 命令 | 结果 |
| --- | --- | --- |
| 全量测试套 | `pytest tests -rA` | **22 passed / 0 failed / 0 error** |
| 一键验证 | `./verify.sh` | **exit code 0** |
| 存储级不变量保护 | `verify_doc/check_db_guards.py` | **6/6 通过**（第二条成功退款被唯一索引拒；超额被 CHECK 拒；跨连接写锁互斥） |
| Golden test 覆盖 | `verify_doc/check_coverage_matrix.py` | **18/18**（T01–T18），R8 六类分类 **6/6** |
| 质量门 | `evaluation-report.md` §3 | **S1–S6 = 17/18 → PASS** |
| 区分度实证 | `evaluation-report.md` §4 | 6 个弱实现变异体 **6/6 被测试套杀死**，对照组全绿 |

---

## 5. 多轮脚本概览

| 轮次 | 主题 |
| --- | --- |
| R0 | 项目启动 —— 从空工作区搭出可运行的主流程 |
| R1 | 细节补充：部分退款（累计金额上限 I1） |
| R2 | 需求改变：幂等（同一售后至多一条成功退款 I2） |
| R3 | 技术取舍：Multi-worker（并发保护必须跨进程有效 I5） |
| R4 | Code Review —— 定位竞态并给出最小修复 |
| R5 | 代码解释 —— 解释须与实现一致 |
| R6 | 线上事故：第三方退款失败（失败一致性 I4） |
| R7 | 安全 / 性能加压（授权隔离 I6 + 索引与分页） |
| R8 | 测试要求 —— 覆盖六类场景并保证稳定 |
| R9 | 最终收敛 —— 完善测试并跑通全量回归 |

> 每轮的 Prompt **原文**见 `round-evidence/R#/prompt.md`；评分边界见 `instruction.md` §8（**不得提前扣分**）。

---

## 6. 接入被测模型

测试套只有**一个**适配点：`golden_answer/tests/harness.py` 的 `Api` 类。
把它翻译成对被测服务的实际调用（路径、字段名、身份方式、分页参数）后即可复用全部断言，
测试本体不动。完整 6 步流程见 `test/README.md` §4；逐轮判定见 `round-evidence/R#/evidence.json`。

---

## 7. 说明与已知限制

- **模型评测范围**：本次交付只评测 **Hy3**（已完成 R0–R9，见 `evaluation/HY3/`）。
  试标占位名 `model_c` / `model_d`（Kimi-K3 / GLM-5.3）**不在交付范围**：未评测、无判定；
  其仅到 R0/R1 的历史留痕见 `evaluation/_trial-history/`（`Historical / exploratory only.
  Not part of the formal model trial.`）。`introduction.md` §4 只填 Hy3 的实际值，其余不虚构。
  > **本次正式模型实测仅使用 Hy3。未进行其他模型实测，因此不做跨模型能力排序或模型区分度结论。**
- **参考解只是 baseline**：模型用别的机制（如换 Postgres 行锁、乐观锁版本号）达成同样不变量，同样可拿满分。
- **崩溃窗口**：认领成功但第三方未回写时进程挂掉会留下 `REFUNDING` 与预留额度，由
  `POST /maintenance/reconcile` 显式释放——这是 SQLite 单机方案的真实边界，不是缺陷。
- **SQLite 写入串行**：写事务经 `BEGIN IMMEDIATE` 排队，适用中小规模；迁到 PostgreSQL 时同一套约束可平移。
- **环境代理会破坏 HTTP 测试**：测试客户端全部使用 `trust_env=False`（回环地址不应走环境代理），
  适配脚本须沿用。
- 并发用例会临时占用本机回环端口并启动两个子进程；严格禁端口的 CI 上可只跑非并发子集，但不可直接跳过并发用例。
