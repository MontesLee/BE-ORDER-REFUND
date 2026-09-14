# BE-ORDER-REFUND — 多轮式后端开发 Agent 评测题

> **阅读边界（重要）**
> 本文件是**出题/评测方文档**：包含评分边界、接口契约基线、失效模式清单，**不下发给被测模型**。
> 被测模型在每一轮只会看到：初始工作区 + 当前代码 + **该轮 Prompt 原文**（第 7 节）。
> 第 6 节的接口契约仅供评测人做**测试套适配**与人工评审参照（R0 的"模糊启动"是刻意保留的）。

---

## 1. 题目概览

| 项 | 内容 |
| --- | --- |
| ID | `BE-ORDER-REFUND` |
| 领域 | 电商 / 订单售后与资金退回 |
| 技术栈 | Python 3.11+ · FastAPI · SQLite · pytest（不得引入 Redis / MQ / K8s / 微服务 / 分布式事务 / 复杂 ORM） |
| 规模 | 单服务、本地可运行；4 张表；约 15 个 HTTP 接口 |
| 轮次 | R0–R9，共 10 轮，同一连续工作区、同一系统工程 |
| 一句话考点 | **在"钱不能算错"的约束下，看 Agent 能否把状态机、幂等、额度上限、第三方失败语义、多 worker 并发和权限隔离依次做对，并且不在需求变化中把前面已建立的不变量搞坏。** |
| 评审成本 | 自动化覆盖主要不变量；人工评审集中在架构取舍与代码解释一致性，2–4 小时可控 |

题目的难点来自 **业务一致性 + 并发 + 幂等 + 状态机 + 外部副作用 + 安全 + 多轮上下文**，不来自业务规模。

---

## 2. 核心矛盾

| 矛盾类型 | 本题体现 |
| --- | --- |
| 状态机 | `PENDING → APPROVED → REFUNDING → REFUNDED / REFUND_FAILED →(retry) REFUNDING`；`REFUNDED` 终态 |
| 事务一致性 | 额度预留与流水写入必须原子；第三方失败必须回退预留 |
| 幂等副作用 | 重复提交售后申请、重复执行退款；第三方渠道同样被重复调用 |
| 并发冲突 | 多 worker 同时执行同一售后 / 同一订单的多个售后 |
| 排障诊断 | R6 的"渠道失败但本地成功"事故 |
| 权限边界 | 用户只能看自己的订单/售后；普通用户不能跳过审核执行退款 |

> 本题**刻意叠加**状态机 + 事务一致性 + 幂等 + 并发 + 权限，而不是单点考一个矛盾：
> 只做状态机的题目工程价值不足，也无法把强弱模型拉开差距。

---

## 3. 六条核心不变量

| ID | 不变量 | 说明 |
| --- | --- | --- |
| **I1** | `sum(成功退款金额) <= order.paid_amount` | 任意时刻成立，且 `orders.refunded_amount` 与成功流水之和一致 |
| **I2** | 同一个 AfterSale 最多一条成功 Refund | 重复提交/重复执行/并发执行都不得产生第二条 |
| **I3** | 只有合法状态迁移会发生 | `REFUNDED` 为终态；`PENDING → REFUNDED` 非法 |
| **I4** | 第三方失败时 `local_status != REFUNDED` | 渠道裁决是本地状态的唯一依据；失败必须可重试 |
| **I5** | 多 worker 并发下 I1 / I2 仍成立 | 保护机制必须跨进程有效，不能是进程内锁 |
| **I6** | 用户不能访问他人订单/售后，不能绕过审核执行退款 | 跨租户读取不得泄露资源存在性 |

---

## 4. 状态机

```
PENDING
  │ approve（AGENT）
  ▼
APPROVED
  │ execute（AGENT）
  ▼
REFUNDING ──渠道成功──▶ REFUNDED（终态）
  │
  └──渠道失败──▶ REFUND_FAILED ──重试（execute）──▶ REFUNDING
```

禁止：`REFUNDED → REFUNDING`、`REFUNDED → REFUND_FAILED`、`PENDING → REFUNDED`、`REFUNDING → APPROVED`。
只在 `APPROVED` 与 `REFUND_FAILED` 两个状态允许发起退款尝试——这条约束同时让"重试"合法、"重复执行"无害。

---

## 5. 实体模型（参考，可增加必要字段）

```
User(id, name, role)                                  role ∈ {USER, AGENT}
Order(id, user_id, total_amount, paid_amount, refunded_amount, payment_status)
AfterSale(id, order_id, user_id, refund_amount, status, idempotency_key)
Refund(id, after_sale_id, order_id, amount, status, attempt, third_party_ref)
```

金额一律为**整数分（cents）**。使用 `float` 处理金额视为严重缺陷（二进制浮点无法精确表示 0.01，会静默破坏 I1）。

---

## 6. 统一接口契约（评测方基线，不下发给被测模型）

评测人用它把被测模型的实现映射到统一测试套；Golden Answer 按此实现。
**R0 不给出这些细节是刻意的**（考察默认取舍），因此接口命名允许差异，映射工作由评测人完成。
换行处标注的 `(R#)` 表示该能力最早在哪一轮被要求。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 存活探针 |
| POST | `/users` | 创建调用方（评测基础设施，题目未要求；模型未实现时由评测人注入） |
| POST | `/orders` | `{amount}` 创建订单，`UNPAID` (R0) |
| POST | `/orders/{id}/pay` | 支付，幂等 (R0) |
| GET | `/orders/{id}` | 订单详情，含 `paid_amount` / `refunded_amount` / `payment_status` (R0) |
| GET | `/orders` | 当前用户订单，分页 (R7) |
| POST | `/orders/{id}/after-sales` | `{refund_amount, idempotency_key?}` 创建售后 (R0) |
| GET | `/orders/{id}/after-sales` | 分页列表 (R1) |
| GET | `/after-sales/{id}` | 售后详情 (R0) |
| POST | `/after-sales/{id}/approve` | 仅 `AGENT` (R0) |
| POST | `/after-sales/{id}/execute` | 仅 `AGENT`；已成功→重放，进行中→409 (R0) |
| GET | `/after-sales/{id}/refunds` | 退款尝试流水，分页 (R7) |

身份：`X-User-Id: <int>` 请求头（模型可自选等价机制，需在测试适配层对应）。
幂等键：body 字段 `idempotency_key` 或头部 `Idempotency-Key`（任一即可，测试套两者都发）。
错误语义：`400` 参数 / `401` 身份 / `403` 角色 / `404` 不存在**或不可见**（跨租户不泄露存在性）/ `409` 状态与额度冲突。

---

## 7. 多轮脚本（下发给被测模型的 Prompt 原文）

> 每一轮都是可独立发送的自然语言消息。评测时**逐轮原文发送**，不补充解读、不预告后续轮次。

### R0 项目启动

```
请实现一个最小可运行的"订单售后退款服务"。用户购买商品并完成支付后，可以针对订单发起售后退款申请。客服审核通过后，系统执行退款。

基础版本：

* 创建订单
* 支付订单
* 创建售后申请
* 审核售后申请
* 执行退款
* 查询订单和售后状态

只考虑全额退款，不考虑优惠券、积分等复杂业务。

项目需要本地可运行，提供基本 API、合理数据模型、基础测试和 README。

直接实现，不需要过度设计。
```

### R1 细节补充：部分退款

```
现在补充业务规则：

1. 一个订单可以存在多个售后申请；
2. 支持部分退款；
3. refund_amount 必须大于 0；
4. 所有成功退款金额累计不能超过订单实际支付金额；
5. 只有成功退款才计入累计退款金额。

请在现有实现上增量修改，并补充必要测试。不要重写无关代码。
```

### R2 需求改变：幂等

```
现在考虑客户端重复提交和网络超时。

同一个业务请求可能被重复发送。

请保证：

1. 重复提交不会产生多个有效退款；
2. 同一个 AfterSale 最多只能有一个成功退款；
3. 幂等机制不能破坏累计退款金额限制。

请修改现有实现并增加测试。

不要求使用某一种具体技术方案，请自行选择合理实现。
```

### R3 技术取舍：Multi-worker

```
现在服务可能运行多个 Worker。

两个 Worker 可能同时处理：

1. 同一个 AfterSale；
2. 同一个 Order 下的多个 AfterSale。

请检查当前实现是否仍然满足：

* 同一个 AfterSale 最多一个成功退款；
* 成功退款累计金额不超过订单实际支付金额。

当前数据库使用 SQLite。

请：

1. 分析当前实现；
2. 选择合适的并发控制方案；
3. 修改代码；
4. 增加并发测试；
5. 说明方案、替代方案和限制。

并发测试必须验证实际业务结果，而不是只验证请求被同时发出。
```

### R4 Code Review

```
退款执行前会先读取售后状态，再决定是否退款。如果两个 Worker 同时读取到相同状态，是否可能重复退款？累计退款金额的检查是否也存在类似问题？

请判断这个 Review Comment 是否成立。

如果成立：

1. 定位根因；
2. 最小化修复；
3. 增加 regression test；
4. 运行相关测试。

不要进行无关重构。
```

### R5 代码解释

```
请基于当前真实代码解释：

1. 请求处理流程；
2. 状态机；
3. 什么条件下允许退款；
4. 幂等如何保证；
5. 累计退款金额如何保证；
6. 多 Worker 如何保证；
7. 当前方案有什么限制。

必须以当前实际代码为准。如果代码实现与预期不一致，请明确指出。
```

### R6 线上事故：第三方退款失败

```
线上出现以下问题：

部分退款请求在第三方支付渠道已经失败的情况下，本地订单却显示退款成功。

已知：

* 第三方渠道可能因为网络或服务问题失败；
* 问题间歇性发生；
* 当前日志有限。

请判断当前代码是否可能出现这个问题，定位原因并修复。

要求：

1. 第三方成功时，本地最终可以进入 REFUNDED；
2. 第三方失败时，本地不能进入 REFUNDED；
3. REFUND_FAILED 可以 retry；
4. 成功后不能重复退款；
5. 增加可以稳定复现第三方失败的测试；
6. 不破坏已有金额、幂等、状态和并发约束。

请提供可替换的 RefundGateway 或等价抽象，使测试可以确定性模拟第三方成功/失败。
```

### R7 安全 / 性能加压

```
请对当前退款服务做一次安全和基础性能检查，并修复实际存在的问题。

安全重点：

1. 用户不能访问其他用户订单；
2. 用户不能访问其他用户 AfterSale；
3. 普通用户不能绕过审核直接执行退款；
4. 异常请求不能绕过金额限制；
5. 重复请求不能造成重复退款。

性能重点：

* 明显 N+1；
* 不必要的重复查询；
* Refund 数量增长后的明显查询退化；
* 不必要的长事务/长时间锁；
* 无界加载大量数据。

不要求进行大规模 QPS 压测。

请只修复真实问题，避免无意义优化，并增加安全 regression tests。
```

### R8 测试要求

```
请为当前系统补齐完整自动化测试，并确保测试可以稳定、重复运行。

至少覆盖：

Business：

* normal refund；
* unpaid refund；
* invalid amount；
* multiple partial refunds；
* over-refund。

State：

* not approved cannot refund；
* REFUND_FAILED can retry；
* REFUNDED cannot retry；
* illegal transition。

Idempotency：

* duplicate submit；
* duplicate execute。

Concurrency：

* same AfterSale concurrent；
* multiple AfterSale concurrent over-refund。

Third-party：

* failure；
* retry；
* execute after success。

Security：

* unauthorized order；
* unauthorized AfterSale；
* normal user protected execution。

不要使用随机 sleep 作为核心正确性证明。

最后运行完整测试集并修复失败。
```

### R9 最终收敛

```
请完成最终交付。

最终系统必须满足：

1. paid order 可以退款；
2. unpaid order 不能退款；
3. 一个订单支持多个 AfterSale；
4. 累计成功退款不超过 paid_amount；
5. 一个 AfterSale 最多一个成功退款；
6. duplicate request 不产生重复有效退款；
7. 非法状态转换被拒绝；
8. REFUND_FAILED 可以 retry；
9. REFUNDED 不能 retry；
10. 第三方失败不能导致本地退款成功；
11. multi-worker 场景保持核心 invariant；
12. 用户不能访问其他用户订单；
13. 用户不能访问其他用户 AfterSale；
14. 普通用户不能绕过审核执行退款。

请：

* 完成代码；
* 完善测试；
* 完善 README；
* 运行完整测试；
* 修复所有失败；
* 确保 clean environment 可以运行；
* 简要说明最终架构和核心保证。
```

---

## 8. 每轮评分边界（**不得提前扣分**）

| 轮次 | 本轮开始正式评分的点 | 不得因"未来需求未实现"扣分 |
| --- | --- | --- |
| R0 | 项目可运行、基础流程、基础 API、基础测试 | partial refund / 累计上限 / 幂等 / 并发 / 第三方失败 / 安全 / 性能 |
| R1 | 多 AfterSale、部分退款、金额校验、**I1 累计上限** | 多 worker / 安全 / 第三方失败 |
| R2 | **I2 幂等**、重复提交、重复执行、历史不变量保持 | 多 worker |
| R3 | **I5 多 worker**、跨进程保护、并发测试质量 | 第三方失败 / 安全 |
| R4 | Review 理解 → 定位 → 最小修复 → regression 闭环 | 后续轮次新需求 |
| R5 | 代码解释与**真实代码**一致 | 后续轮次新需求 |
| R6 | **I4 第三方失败语义**、可重试、确定性复现测试 | 安全 / 性能 |
| R7 | **I6 授权隔离**、明显性能问题 | 后续轮次新需求 |
| R8 | 测试覆盖度、稳定性、不变量断言、回归能力 | 后续轮次新需求 |
| R9 | **全量历史要求最终回归**（不新增评分维度） | — |

后续轮次可以检查历史要求；但**前一轮不得因为没有实现未来需求而扣分**。

---

## 9. 模型高发失效模式（题目区分度的来源）

| # | 失效模式 | 对应轮次 | 杀死它的测试 |
| --- | --- | --- | --- |
| 1 | check-then-write race：先读状态再写，读与写之间没有互斥 | R3 / R4 | T13 / T14 |
| 2 | 重复退款：重复请求产生第二条有效退款 | R2 | T06 / T07 |
| 3 | 累计退款超额 | R1 / R3 | T03 / T04 |
| 4 | 第三方失败却把本地标记成功 | R6 | T11 / T12 |
| 5 | 非法状态转换（未审核直接退款） | R0 / R2 | T08 |
| 6 | retry 破坏状态机（成功后再次退款） | R6 | T09 / T10 |
| 7 | **只用进程内 Lock，却声称解决了分布式并发** | R3 | T13 / T14（跨进程集群） |
| 8 | 幂等只存在于内存（进程重启即失效） | R2 | T06 |
| 9 | 只校验资源存在，不校验归属 | R7 | T15 / T16 / T17 |
| 10 | 普通用户绕过审核直接执行退款 | R7 | T17 |
| 11 | 只测 happy path | R8 | T02 / T04 / T08 / T15–T17 |
| 12 | 需求变化后破坏历史不变量 | R1–R9 | 每轮的历史用例 |
| 13 | Review 能指出问题但不会修 | R4 | T13 / T14 修复后通过 |
| 14 | 代码解释与真实代码不一致 | R5 | 人工评审（CU-03） |
| 15 | 为小问题过度引入基础设施（MQ / Saga / Outbox / Redis） | R3 / R6 / R7 | 人工评审（TE-03） |
| 16 | 大规模重写已有项目 | R4–R9 | 人工评审 + Trace（IF-02 / TE-01） |
| 17 | 用 float 处理金额 | All | T01 / T03 / T04 金额断言 |

---

## 10. 交付物

```
BE-ORDER-REFUND/
├── README.md                   仓库说明（状态 / 不变量 / 文件结构 / 快速开始）
├── instruction.md              本文件
├── introduction.md             题目与各模型表现简述
├── rubric.md                   22 条原子 Rubric
├── evidence-matrix.md          Rubric → Evidence 追溯矩阵
├── evaluation-report.md        评测反馈报告（含质量校验结论）
├── init/                       被测模型的起始工作区（本题目初始无自带文件）
├── golden_answer/              参考实现 + 测试套 + verify.sh
├── round-evidence/R0..R9/      每轮 prompt / test-result / evidence.json / reviewer.md
├── evaluation/                 真实模型 Trial 结果区
│   ├── HY3/                    Hy3 完成态结果（trace.md / result.md / evidence.md / final-artifact/）
│   ├── comparison.md           单模型（Hy3）汇总；_TEMPLATE/ 空白模板；_trial-history/ 历史留痕
├── test/README.md              测试套说明与"如何适配到被测模型产出"
└── solve/README.md             golden answer 交付说明
```

> `instruction.md` 是**评测方文档**，不下发给被测模型：模型在每轮只会收到
> `round-evidence/R#/prompt.md` 的原文（见第 7 节），其中不含 Rubric、Golden Answer、
> 不变量编号（I1–I6）、失效模式表与评分规则。

四件套对应关系（Tlabel 口径）：`instruction.md` → 题目说明；`test/` → 测试用例说明；`solve/` → 参考实现；`evaluation-report.md` → 评测反馈报告。

---

## 11. 评测流程

```
1. 用 init/ 建立被测工作区（每个模型一个独立新工作区，关闭记忆，最高思考等级）
2. 逐轮原文发送 R0…R9；模型报错需 debug 时插入轮保持同风格
3. 保留每个模型从 init 出发的最终产物 → 存到 evaluation/<model>/final-artifact/
4. 用 golden_answer 的测试套对每个产物执行（按 test/README.md 做接口适配）
5. 按 round-evidence/R#/evidence.json 逐轮判定 Rubric（PASS / FAIL / NOT_APPLICABLE）
6. 按 §12 的权重汇总得分
7. 回写 evaluation/<model>/ 的 trace.md / result.md / evidence.md（字段规范见 evaluation/README.md）
```

**区分度实测口径**：题目锁定后必须用给定模型实测，确认至少在一个核心不变量或关键设计决策上出现分层。**未完成实测不得入库。**

> 本包当前状态：**已完成一次真实 Model Trial（单模型：Hy3，R0–R9）**。上述第 1–7 步已全部执行：
> Hy3 已完成 R0–R9，冻结产物与 22 条 Rubric 判定入库（Final = 0.91），见 `evaluation/HY3/`
> 与 `evaluation/comparison.md`。试标占位名 `model_c` / `model_d`（Kimi-K3 / GLM-5.3）
> **不在本次交付范围**：未评测、无判定；其仅到 R0/R1 的历史留痕见 `evaluation/_trial-history/`。
> **不伪造任何模型结果**。Golden Answer 验证（题目与参考答案可执行、可判定）见
> `evaluation-report.md` §5。

---

## 12. 评分体系

五个维度，权重固定，不得新增维度：

| 维度 | 权重 | 评什么 |
| --- | --- | --- |
| D1 Instruction Following | 15% | 是否准确执行当前轮要求与约束 |
| D2 Feature Delivery | 35% | 系统实际行为是否满足业务需求与核心不变量 |
| D3 Task Efficiency | 15% | 是否用合理、最小、有效的修改解决问题 |
| D4 Architecture Quality | 20% | 在当前约束下后端架构是否正确、清晰、可维护 |
| D5 Context Understanding | 15% | 是否理解并维护跨轮次的历史约束、代码状态、Review 与事故 |

（Testing / Security / Performance / Communication / Problem Solving 等能力必须映射到上述五维之一，不单独设维度。）

计算：

```
dimension_score = 通过且适用的 rubric 数 / 适用 rubric 数
Final = D1×0.15 + D2×0.35 + D3×0.15 + D4×0.20 + D5×0.15
```

`NOT_APPLICABLE` 不进入分母；单项结果只允许 `PASS` / `FAIL` / `NOT_APPLICABLE`。

---

## 13. 自动化与人工的边界

**必须自动化**（可稳定测试者不允许只靠人工）：退款、未支付、部分退款、超额、幂等、状态机、重试、第三方失败、并发、授权、最终回归。

**主要人工**：技术取舍说明、是否过度设计、是否最小修改、代码解释一致性、架构边界、跨轮上下文理解。

人工评价也必须锚定到可观察证据（CODE / DOC / REVIEW），不得只写"合理、优雅、稳定"。
