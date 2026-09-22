# Tlabel 提交内容 — BE-ORDER-REFUND

> 面向 https://tlabel.tencent.com/ 的题目提交表单，按 9 个字段组织，可直接复制填写。

---

## 题目名称

**推荐填写（主推）：**

```
订单售后退款服务多轮开发：状态机 × 幂等 × 跨进程并发 × 第三方失败语义 × 权限隔离
```

> 构成：场景（订单售后退款服务）+ 形态（多轮开发）+ 五大核心考点，与 22 条 Rubric / 六条不变量一一对应，检索友好。

**备选（按偏好选用）：**

| # | 题目名称 | 适用 |
| --- | --- | --- |
| 1 | 订单售后退款服务多轮开发：状态机 × 幂等 × 跨进程并发 × 第三方失败语义 × 权限隔离 | **主推**：考点最完整 |
| 2 | 订单售后退款服务十轮演进：钱不能算错、不能重复退、不能越权 | 想要记忆点、口语化 |
| 3 | 多轮需求变更下的订单退款服务：持续守住六条资金与状态不变量 | 想突出「不破坏历史不变量」这一最独特考点 |
| 4 | 订单售后退款服务（10 轮）：金额上限 · 幂等 · 并发 · 第三方失败 · 权限隔离 | 平台对名称长度有限制时 |
| 5 | BE-ORDER-REFUND — 从零构建资金安全的订单售后退款服务（多轮 R0–R9） | 想带题目 ID 便于检索 |
> 内容来源：`instruction.md` §1–§7、`rubric.md` §1、`evaluation-report.md`、`evaluation/HY3/result.md`。
> 题目 ID：`BE-ORDER-REFUND` · 一句话考点：在"钱不能算错"的约束下，看 Agent 能否把状态机、幂等、额度上限、第三方失败语义、多 worker 并发与权限隔离依次做对，并且不在需求变化中把前面已建立的不变量搞坏。

---

## 填写速查（§6–§9 单选字段）

| 字段 | 建议填写 |
| --- | --- |
| 二级任务分类 | **技术平台** |
| 题目类型 | **模糊需求型** |
| 题目难度 | **困难** |
| 编程语言 | **Python** |

---

## 1. 多条对话数据

> 共 12 条：1 条 `system prompt` + 10 条 `user`（R0–R9，逐字原文）+ 1 条说明。
> **`assistant` / `tool` 轮次由被测模型在评测时产生，题目侧不预填**；若平台强制要求 user/assistant 交替，
> 可在每条 user 后插入一条占位 assistant（如"（模型本轮实现与说明）"），`tool` 轮次留空即可。

### [1/12] role = system prompt

```
你是一名资深后端开发 Agent，将在一个空的工作区中从零构建一个服务。

工作环境：
- 起始工作区为空（仅有一个占位 README）。请在其中从零创建实现、测试与说明文档。
- 技术栈：Python 3.11+ / FastAPI / SQLite / pytest。
- 约束：项目必须本地可运行；禁止引入 Redis、消息队列、Kubernetes、微服务拆分、分布式事务框架或复杂 ORM。

工作方式：
- 直接实现，不要过度设计。
- 后续会有一系列需求补充、需求变更、Code Review、线上事故与安全性能要求；请在现有实现上增量演进，不要进行无必要的大规模重写。
- 每次修改后补充必要测试并运行完整测试，确保此前已建立的功能与约束不被破坏。
```

### [2/12] role = user（R0 项目启动）

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

### [3/12] role = user（R1 细节补充：部分退款）

```
现在补充业务规则：

1. 一个订单可以存在多个售后申请；
2. 支持部分退款；
3. refund_amount 必须大于 0；
4. 所有成功退款金额累计不能超过订单实际支付金额；
5. 只有成功退款才计入累计退款金额。

请在现有实现上增量修改，并补充必要测试。不要重写无关代码。
```

### [4/12] role = user（R2 需求改变：幂等）

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

### [5/12] role = user（R3 技术取舍：Multi-worker）

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

### [6/12] role = user（R4 Code Review）

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

### [7/12] role = user（R5 代码解释）

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

### [8/12] role = user（R6 线上事故：第三方退款失败）

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

### [9/12] role = user（R7 安全 / 性能加压）

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

### [10/12] role = user（R8 测试要求）

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

### [11/12] role = user（R9 最终收敛）

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

### [12/12] role = assistant（说明，非对话内容）

```
（本轮次由被测模型在评测时产生，题目侧不预置 assistant / tool 内容。
评测时逐轮原文发送 R0–R9 的 user 消息，不补充解读、不预告后续轮次。）
```

---

## 2. 附件

### 2.0 打包上传（推荐）

整个项目仅 **0.79 MB / 180 文件**，可直接打包上传。已生成两个包，**按平台是否把附件下发给做题方来选**：

| 包 | 体积 | 内容 | 什么时候用 |
| --- | --- | --- | --- |
| `BE-ORDER-REFUND-full.zip` | **335 KB / 178 文件** | 完整交付物：题目 + 参考实现 + 22 条 Rubric + 逐轮证据 + Hy3 实测结果 | **默认选这个**（附件仅平台/评审归档，不下发给做题方） |
| `BE-ORDER-REFUND-nogolden.zip` | 35 KB / 8 文件 | 仅题面：README / instruction / introduction / DELIVERY-MAP / evaluation-report / init / test/README | 平台会把附件一并发给做题方或标注者时 |

> ⚠️ **为什么分两个包**：全量包 178 个文件里有 **168 个带答案**——
> `golden_answer/`（完整参考实现）、`rubric.md`（22 条评分标准）、`evidence-matrix.md`、
> `round-evidence/`（逐轮证据）、`evaluation/`（Hy3 等模型的完整产物与判定）。
> 若这些被下发给被测模型，等于把答案和评分细则一起交出去，题目直接失效。
> 上传全量包时请在平台标注：**「含参考实现与评分标准，仅供评审归档，不下发被测方」**。
>
> 两个包均已排除 `.git` / `__pycache__` / `.pytest_cache` / `.workbuddy`。

### 2.1 附件文本写什么：先划定红线

附件文本的价值是"补充题面没说完的**约束与环境**"，而不是"补充答案"。按能否下发分三类：

| 类别 | 内容 | 能否写进下发附件 |
| --- | --- | --- |
| ✅ 该写 | 起始工作区状态、运行环境与技术栈约束（含禁止项）、交付物要求、评测方式、通用工程要求 | 可以 |
| ⚠️ 慎写 | 六条不变量的**自然语言业务规则**（R9 prompt 已全部公开，写无妨）；但 **I1–I6 编号化表述、状态机图、实体模型字段**属评测方抽象 | 只写自然语言规则 |
| ❌ 绝不能写 | **统一接口契约**（端点路径 / `X-User-Id` / 状态码语义）、失效模式清单、22 条 Rubric 与权重、参考实现、模型实测结论 | 绝对不行 |

> **最需要守住的一条**：统一接口契约写进下发附件 = 把"模糊需求型"变成"照着契约填空"。
> R0 刻意不给契约，就是要看模型自己怎么设计端点、数据模型和金额边界；
> 契约一旦泄露，D1（Instruction Following）与 D4（Architecture Quality）的区分度会直接塌掉。
> 评测侧是靠 `harness.py` 适配层去对接任意接口的，**不需要模型迁就任何特定契约**。

---

### 附件文本 A（推荐，做题方视角，可安全下发）

```
# 题目补充说明：订单售后退款服务（多轮开发任务）

## 起始工作区
起始目录为空（仅含占位说明）。请从零创建实现、测试与说明文档。

## 运行环境与技术栈
- Python 3.11+ / FastAPI / SQLite / pytest
- 项目必须本地可运行，需提供安装与启动方式
- 禁止引入：Redis、消息队列、Kubernetes、微服务拆分、分布式事务框架、复杂 ORM
- 第三方支付渠道请抽象为可替换接口，使测试能够确定性模拟成功与失败

## 交付物要求
最终交付需包含：实现源码、自动化测试、README、依赖声明，以及可一键执行的验证方式。

## 评测方式
- 本题为多轮对话任务，共 10 轮。后续轮次会依次补充业务规则、变更需求、Code Review 意见、
  线上事故、安全与性能要求，最后收敛交付。
- 评测方会用统一的测试套对最终产物进行验证；**接口命名、数据模型与实现方案均由你自行决定**，
  评测侧通过适配层对接，不需要你迁就任何特定契约。
- 每轮都在上一轮的基础上继续，请在现有实现上增量演进，不要进行无必要的大规模重写。

## 通用工程要求
- 直接实现，不要过度设计。
- 每次修改后补充必要测试并运行，确保此前已建立的功能与约束不被破坏。
- 涉及金额计算时请注意精度问题。
```

> 这段文本的妙处在于"评测方式"一节：明确告诉模型「接口自由、适配层对接」，
> 既不泄露契约，又避免模型因为怕对不上契约而不敢自选设计。

### 附件文本 B（仅评审归档用，❌ 不下发）

> 以下 ② 两段属**评测方基线**：`I1–I6` 编号化不变量、状态机图、实体模型字段、统一接口契约。
> **只能出现在归档附件中**；写进下发附件会削弱「模糊需求型」的考察（模型会直接照抄设计）。
> 若确需让做题方知道业务规则，用 R9 prompt 里的自然语言 14 条即可，不要用这里的编号与图形。

#### ① 六条核心不变量与状态机

```
六条核心不变量：
I1  sum(成功退款金额) <= order.paid_amount（任意时刻成立，且与成功流水之和一致）
I2  同一个 AfterSale 最多一条成功 Refund（重复提交/重复执行/并发执行都不得产生第二条）
I3  只有合法状态迁移会发生（REFUNDED 为终态；PENDING → REFUNDED 非法）
I4  第三方失败时 local_status != REFUNDED（渠道裁决是本地状态的唯一依据；失败必须可重试）
I5  多 worker 并发下 I1 / I2 仍成立（保护机制必须跨进程有效，不能是进程内锁）
I6  用户不能访问他人订单/售后，不能绕过审核执行退款（跨租户读取不得泄露资源存在性）

状态机：
PENDING --approve(AGENT)--> APPROVED --execute(AGENT)--> REFUNDING
REFUNDING --渠道成功--> REFUNDED（终态）
REFUNDING --渠道失败--> REFUND_FAILED --重试(execute)--> REFUNDING
禁止：REFUNDED→REFUNDING、REFUNDED→REFUND_FAILED、PENDING→REFUNDED、REFUNDING→APPROVED
只在 APPROVED 与 REFUND_FAILED 两个状态允许发起退款尝试。

实体模型：
User(id, name, role)                     role ∈ {USER, AGENT}
Order(id, user_id, total_amount, paid_amount, refunded_amount, payment_status)
AfterSale(id, order_id, user_id, refund_amount, status, idempotency_key)
Refund(id, after_sale_id, order_id, amount, status, attempt, third_party_ref)
金额一律为整数分（cents）；使用 float 处理金额视为严重缺陷。
```

#### ② 统一接口契约（评测基线）

> 🚫 **整份文档中最不能外泄的一段**。端点路径、`X-User-Id` 请求头、状态码语义一旦下发给做题方，
> 模型可直接照抄实现，「模糊需求型」考察当场失效。它只服务于评测侧的测试套适配。

```
GET    /health                            存活探针
POST   /users                             创建调用方（评测基础设施）
POST   /orders                            {amount} 创建订单，UNPAID (R0)
POST   /orders/{id}/pay                   支付，幂等 (R0)
GET    /orders/{id}                       订单详情 (R0)
GET    /orders                            当前用户订单，分页 (R7)
POST   /orders/{id}/after-sales           {refund_amount, idempotency_key?} (R0)
GET    /orders/{id}/after-sales           分页列表 (R1)
GET    /after-sales/{id}                  售后详情 (R0)
POST   /after-sales/{id}/approve          仅 AGENT (R0)
POST   /after-sales/{id}/execute          仅 AGENT；已成功→重放，进行中→409 (R0)
GET    /after-sales/{id}/refunds          退款尝试流水，分页 (R7)

身份：X-User-Id: <int> 请求头（模型可自选等价机制，需在测试适配层对应）
幂等键：body 字段 idempotency_key 或头部 Idempotency-Key（测试套两者都发）
错误语义：400 参数 / 401 身份 / 403 角色 / 404 不存在或不可见（跨租户不泄露存在性）/
          409 状态与额度冲突
```

#### ③ 参考实现与测试套清单（同属归档内容）

```
golden_answer/     参考实现（FastAPI + SQLite，8 模块）+ 22 个测试 + verify.sh（一键验证 exit 0）
test/README.md     测试套说明 +「如何适配被测模型产出」（唯一适配点 harness.py）
round-evidence/R0…R9/   每轮 prompt.md / test-result.txt / evidence.json / reviewer.md
```

---

## 3. 多条预设 Rubric（22 条）

> 字段对齐：`判定标准` = 判断命题（Yes/No）｜`优先级` = Must→must have / Nice→nice to have｜
> `所属维度` = D1–D5｜`是否隐式` = Explicit / Implicit｜`主观性/客观性` = objective / subjective｜`涉及对话轮次` = Round（单一轮次）。
>
> ⚠️ 源表中 AQ-01 / AQ-02 / AQ-04 / CU-02 标注为 `Objective+Subjective`，表单只能单选，
> 下表已给出**推荐取值**（按"是否具备确定性自动化证据"取舍），如需保留混合属性请在备注列说明。

| # | ID | 判定标准（Yes/No 命题） | 优先级 | 所属维度 | 是否隐式 | 主观/客观 | 涉及对话轮次 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | IF-01 | 项目能在 clean environment 按 README 启动并运行 | must have | Instruction Following | Explicit | objective | R0 |
| 2 | IF-02 | 后续轮次在已有项目上增量演进，没有无必要的大规模重写 | must have | Instruction Following | Implicit | subjective | R9 |
| 3 | IF-03 | 最终 source / tests / README / requirements / verification 完整且可运行 | must have | Instruction Following | Explicit | objective | R9 |
| 4 | FD-01 | 只有满足支付与审核条件的 AfterSale 才能退款 | must have | Feature Delivery | Explicit | objective | R0 |
| 5 | FD-02 | 一个订单支持多个 AfterSale 与部分退款 | must have | Feature Delivery | Explicit | objective | R1 |
| 6 | FD-03 | 成功退款金额累计不超过 `paid_amount` | must have | Feature Delivery | Explicit | objective | R3 |
| 7 | FD-04 | 重复业务请求不产生多个有效退款结果 | must have | Feature Delivery | Explicit | objective | R2 |
| 8 | FD-05 | 一个 AfterSale 最多一条成功 Refund | must have | Feature Delivery | Explicit | objective | R3 |
| 9 | FD-06 | 非法状态转换被拒绝，`REFUNDED` 为终态 | must have | Feature Delivery | Explicit | objective | R6 |
| 10 | FD-07 | 第三方失败后进入可重试状态，重试成功后进入 `REFUNDED` | must have | Feature Delivery | Explicit | objective | R6 |
| 11 | FD-08 | 用户不能操作他人资源，也不能绕过审核执行退款 | must have | Feature Delivery | Explicit | objective | R7 |
| 12 | TE-01 | 修复问题时没有进行无关的大规模重构 | nice to have | Task Efficiency | Implicit | subjective | R9 |
| 13 | TE-02 | 存在可单独执行的定向回归用例，且全量套件可运行（diagnose→fix→targeted regression→full regression 闭环） | must have | Task Efficiency | Explicit | objective | R8 |
| 14 | TE-03 | 没有为小型 SQLite 服务引入明显不必要的基础设施 | nice to have | Task Efficiency | Implicit | subjective | R7 |
| 15 | AQ-01 | 核心并发约束不依赖单进程内存锁，而由对 multi-worker 有效的持久化/数据库机制保护 | must have | Architecture Quality | Implicit | objective ⚠️ | R3 |
| 16 | AQ-02 | 金额上限与 AfterSale 幂等约束在并发与数据增长下有可靠的持久化保护 | must have | Architecture Quality | Implicit | objective ⚠️ | R7 |
| 17 | AQ-03 | 状态转换边界清晰，普通业务路径不能绕过状态机 | must have | Architecture Quality | Implicit | subjective | R6 |
| 18 | AQ-04 | 第三方失败不会错误记录为本地成功，且第三方调用可确定性测试 | must have | Architecture Quality | Explicit | objective ⚠️ | R6 |
| 19 | AQ-05 | 能说明当前方案、合理替代方案、选择原因及 SQLite / multi-worker 限制 | nice to have | Architecture Quality | Explicit | subjective | R5 |
| 20 | CU-01 | 后续修改始终保持此前建立的核心 invariant | must have | Context Understanding | Implicit | objective | R9 |
| 21 | CU-02 | 能根据事故定位真实原因并针对性修复 | must have | Context Understanding | Implicit | subjective ⚠️ | R6 |
| 22 | CU-03 | 模型解释与实际代码一致 | must have | Context Understanding | Implicit | subjective | R5 |

统计（已核对源表）：**Must 20 条 · Nice 2 条**（Nice 仅 TE-01、TE-03）｜**Explicit 13 · Implicit 9**｜**objective 15 · subjective 7**（含 4 条 ⚠️ 混合属性的推荐取值）
维度分布：Instruction Following 3 · Feature Delivery 8 · Task Efficiency 3 · Architecture Quality 5 · Context Understanding 3 = **22**

> ⚠️ 说明：AQ-01 有跨进程集群与存储层排他探测硬证据；AQ-02 有 `check_db_guards.py` 存储层探测；
> AQ-04 有确定性渠道失败注入测试——三者均有客观证据，故推荐 `objective`。
> CU-02「能否定位真实根因」本质依赖评审判断，推荐 `subjective`。

---

## 4. 难点和思路

### 难点

1. **多矛盾叠加，而非单点考察。** 状态机 × 事务一致性 × 幂等 × 跨进程并发 × 第三方失败语义 × 权限隔离六类矛盾交织在同一条退款链路上，任一环缺失都会破坏"钱不能算错"这一总约束。只考单点（如仅状态机）工程价值不足，也无法拉开强弱模型差距。

2. **跨进程并发不能靠进程内锁。** 多 worker 下必须由持久化机制保护（`BEGIN IMMEDIATE` + 带条件 `UPDATE` + 部分唯一索引 + `CHECK` 约束 + WAL/`busy_timeout`）。"只用 `threading.Lock` 却声称解决了分布式并发"是最强的伪装型失效模式（#7）——代码看起来有锁，实际跨进程完全失效。

3. **第三方失败的语义边界。** 渠道裁决必须是本地状态的唯一依据；渠道调用须在事务外取得裁决，失败要回退预留额度、置 `REFUND_FAILED` 且可重试。"渠道失败但本地标记成功"（#4）是典型隐蔽缺陷，间歇发生、日志有限，极难自测发现。

4. **幂等要同时覆盖"创建"与"执行"两端。** 只做执行端幂等、创建端不消费幂等键，仍会重复建单——这是实测中出现的真实缺陷（Hy3 FD-04 FAIL，Golden `test_duplicate_submit_creates_one_after_sale` 杀死）。

5. **权限要做"归属"校验而非"存在性/角色头"校验。** 只校验资源是否存在、或只校验 `X-User-Role` 而不校验 `X-User-Id` 归属，会导致任意用户审批他人售后（Hy3 FD-08 FAIL），且模型 README 还**虚标**了该保证——文档自述与代码不符本身就是考点（CU-03）。

6. **多轮上下文保持与"不过度设计"的平衡。** 后续轮次不得破坏前面已建立的不变量（CU-01），也不能被新需求诱导大规模重写（IF-02 / TE-01）；同时又不能为小问题引入 MQ / Saga / Outbox / Redis 等重基础设施（TE-03）。

7. **金额精度。** 必须用整数分；用 `float` 处理金额会静默破坏 I1（#17），且在小额整数场景下自动化测试未必能直接抓出，需结合代码审查。

### 思路

**出题设计**

- **10 轮覆盖 10 种真实用户行为**：项目启动 / 细节补充 / 需求改变 / 技术取舍 / Code Review / 代码解释 / 线上事故 / 安全性能 / 测试要求 / 最终收敛。轮次间存在真实依赖，非显性约束累加。
- **R0 刻意模糊**：不下发接口契约，考察模型的默认取舍；契约差异由评测方用适配层（`harness.py`）映射，不让模型迁就评测。
- **每轮独立评分边界**：前一轮不得因"未实现未来需求"而扣分（如 R0 不因没做幂等扣分），避免题目要求被提前泄露式的误判。
- **隔离下发**：模型每轮只看到"当前工作区 + 当前代码 + 本轮 Prompt 原文"，不含 Rubric、不变量编号、参考答案与失效模式清单。
- **区分度靠实证而非感觉**：明确 17 条模型高发失效模式，并用变异测试验证——对参考实现注入 6 个真实弱实现变异体（竞态、失败误记成功、忽略幂等键、只校验存在性、非法状态放行、失败不释放额度），**6/6 被杀死，对照组全绿**。
- **自动化 / 人工边界清晰**：退款、未支付、部分退款、超额、幂等、状态机、重试、第三方失败、并发、授权、最终回归必须自动化；仅技术取舍说明、是否过度设计、是否最小修改、解释一致性、架构边界走人工，且人工结论必须锚定 CODE / DOC / REVIEW 证据。

**参考解思路（Golden Answer）**

- **状态机集中**：`state_machine.py` 单一转换表，所有写状态必须经它，杜绝散落字面量旁路；外部渠道调用置于事务外。
- **第三方语义**：渠道裁决在事务外取得，`_settle` 二分成功 / 失败；失败分支回退预留额度并置 `REFUND_FAILED`，绝不写成功。提供可注入的 `RefundGateway`，测试可确定性模拟成功 / 失败（不依赖随机 sleep）。
- **并发与不变量**：`BEGIN IMMEDIATE` + 带条件 `UPDATE` 守卫额度 + 部分唯一索引 `ux_refunds_one_success` 保证"一售后一成功" + `CHECK (refunded_amount <= paid_amount)` + WAL/`busy_timeout`；全部为持久化机制，跨进程有效。
- **幂等**：创建端唯一键去重 + 执行端认领阶段 CAS。
- **权限**：`assert_can_view`（跨租户返回 404，不泄露存在性）+ `require_agent`。
- **金额**：全程整数分。

**区分度实证（真实模型实测）**

- Hy3 跑完 R0–R9：模型自带测试 90 passed，Golden 统一套件 14 passed / 7 failed，22 条 Rubric **20 PASS / 2 FAIL，Final = 0.91**。
- 两条真实 FAIL 正是设计意图：FD-04（创建端幂等缺失）、FD-08（审核端点缺归属校验，且 README 虚标该保证）。
- 结论：题目不是"满分题"也不是"送分题"，能在强模型上稳定抓出真实缺陷，具备分层能力。

---

## 5. 题目来源

**原创自研（人工构造）**，非公开数据集采集、非线上问题直接搬运。

- **业务原型**：真实电商「订单售后与资金退回」场景抽象而来。业务规则（金额上限、状态流转、审核角色、失败重试、权限边界）在题面内给足，不依赖外部领域知识。
- **参考实现与测试套**：由出题方自建——`golden_answer/`（FastAPI + SQLite，8 模块）+ 22 个测试 + `verify.sh` 一键验证（新建 venv → 装依赖 → 跑测试，exit 0）；存储级不变量探测 6/6 通过；覆盖率探测 18/18 golden tests、6/6 分类。
- **质量校验**：`evaluation-report.md` 已给出 B1–B5 底线检查（全通过）、S1–S6 出题评分（17/18 PASS）、变异测试（6/6 杀死）。
- **实测留痕**：已用真实模型 Hy3 完成 R0–R9 全流程实测（工作区隔离、关闭记忆、最高思考等级），冻结产物与逐条证据见 `evaluation/HY3/`。
- **可复现**：`round-evidence/R0…R9/` 保存每轮 prompt 原文、真实测试输出、evidence.json 与 reviewer.md。

---

## 6. 二级任务分类

**技术平台**

理由：任务本体是「从零构建一个可运行的后端服务」，考察的是技术平台侧的工程能力——Web 框架（FastAPI）、关系型存储（SQLite）、事务与并发控制、状态机设计、接口契约、鉴权与测试工程；产出物是代码仓库而非行业业务方案。虽以电商售后为外衣，但业务规则已在题面内给足，不构成行业垂类知识门槛，不应归入「行业垂类」。

---

## 7. 题目类型

**模糊需求型**

理由：R0 只给出一句业务目标和"直接实现，不需要过度设计"，**刻意不下发接口契约、数据模型与不变量编号**；后续 9 轮以真实用户行为的方式逐步注入/变更需求（部分退款 → 幂等 → 多 worker → Review → 事故 → 安全性能 → 测试 → 收敛），模型必须自行补全大量未言明的工程决策（并发方案、幂等机制、第三方抽象、鉴权方式）。

排除理由：非 PRD 类型（无一次性给全的详细规格）；非 SWE-bench style（无既有仓库的 issue/缺陷要修）；非 RepoBench style（非跨文件代码补全）；非 Whole-repo Refactoring（起点为空仓库，且明确要求增量演进、禁止大规模重写）。

---

## 8. 题目难度

**困难**

依据：

- **轮次多、跨度大**：10 轮连续对话，同一工作区、同一工程，跨轮上下文保持本身就是难度来源。
- **不变量硬**：6 条核心不变量（I1 金额上限 / I2 一售后一成功 / I3 状态机 / I4 第三方失败语义 / I5 跨进程并发 / I6 权限隔离）必须同时成立，且任意时刻成立。
- **并发要求跨进程**：进程内锁直接判负，必须给出对 multi-worker 有效的持久化保护，并用真实多进程测试证明。
- **副作用语义隐蔽**：第三方失败不得记为本地成功，需可注入网关 + 确定性复现测试。
- **需求会变、会追责**：R4 要求判断 Review 是否成立并最小修复；R6 要求从"日志有限的间歇性事故"定位根因；R9 要求全量历史回归。
- **实测印证**：强模型 Hy3 跑完全程得 Final = 0.91（20/22），仍在「创建端幂等」与「审核归属校验」两处留下真实缺陷；中等模型预期会在并发保护、第三方失败语义、权限归属上明显失守。

---

## 9. 编程语言

**Python**

- 版本：Python 3.11+
- 主要依赖：FastAPI、SQLite（标准库 `sqlite3`）、pytest、uvicorn、httpx、pydantic
- 明确禁止引入：Redis、消息队列（Kafka/RabbitMQ 等）、Kubernetes、微服务拆分、分布式事务框架、复杂 ORM

---

## 10. 选填：Repo 链接 / Commit Hash / PR 链接

是的，这三个都是 **GitHub** 的。实测值（取自本机 `git remote -v` / `git rev-parse HEAD`）：

| 字段 | 填写值 |
| --- | --- |
| **Repo 链接** | `https://github.com/MontesLee/BE-ORDER-REFUND` |
| **Commit Hash** | `e1f58fa0013496727f2c30cace996a7717a6245d`（短：`e1f58fa`） |
| **PR 链接** | 留空（本仓库无 PR） |

当前 HEAD 信息：

```
commit e1f58fa0013496727f2c30cace996a7717a6245d
Author: MontesLee <graduateleaf2009@gmail.com>
Date:   Mon Sep 14 20:58:23 2026 +0800

    Finalize BE-ORDER-REFUND benchmark delivery and Hy3 evaluation evidence

branch: main        共 9 个 commit
remote: git@github.com:MontesLee/BE-ORDER-REFUND.git
```

### 三个注意点

1. **Commit Hash 建议先 commit 再填。** 上面这个 hash 指向的状态**不包含**本次新建的
   `tlabel-submission.md`（目前是未跟踪文件，`git status` 显示 `?? tlabel-submission.md`）。
   若希望链接指向的状态包含完整提交材料，先提交它再取新 hash：

   ```bash
   git add tlabel-submission.md
   git commit -m "Add Tlabel submission content"
   git rev-parse HEAD    # ← 用这个新 hash
   ```

   不 commit 也能填 `e1f58fa`——题目正文与 Rubric 都已在其中，只是没有这份填写草稿。

2. **确认仓库是公开的。** 这三个字段的意义是让平台/评审能追溯题目材料。
   若仓库为私有，平台侧访问不到，填了等于无效——此时应转为依赖附件 zip，
   或把仓库改为 public。（本机 `gh` 未认证，无法自动确认可见性，需你在 GitHub 页面确认。）

3. **PR 链接留空即可。** 这是个人 benchmark 仓库，9 个 commit 均直接提交到 `main`，
   无 PR 流程。只有当题目源自"给某仓库提的一个 PR"（例如 SWE-bench style 题目）时才需要填。
