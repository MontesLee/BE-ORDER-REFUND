# BE-ORDER-REFUND — 评测反馈报告

版本：`BE-ORDER-REFUND_202609141100` · 题目：多轮式后端开发 Agent Benchmark（订单售后退款服务）

> **证据边界（先读）**
>
> 本报告包含的结论分两类，**不可互相推导**：
>
> | 类别 | 本报告中的位置 | 状态 |
> | --- | --- | --- |
> | **Golden Answer Validation**（题目与参考答案是否可执行、可判定） | §2 底线检查 · §3 出题评分 · §4 变异测试 · §5 验证结果 · §6 覆盖 | **已完成** |
> | **Real Model Trial**（某模型跑完 R0–R9 后是否满足 Rubric） | —— | **已启动，未完成（INCOMPLETE）** |
>
> 关于该行：真实 Trial 已于 2026-09-14 启动——3 个模型真实跑通 R0/R1 后被账号级模型配额
> （HTTP 429）阻断，未到达 R9。全部真实进展、配额事件与已发现缺陷见
> `evaluation/_trial-incomplete/TRIAL-RUN-LOG.md`。
> **因未到达 R9，本报告不给出任何模型判定、维度得分或分层结论。**
>
> 因此：**`Rubric PASS` ≠ `Golden Answer PASS` ≠ `Model PASS`**。
> 本报告不包含任何模型名、模型版本、`trace_id`、模型产出或模型的 PASS / FAIL，
> 也不得被解读为"模型已通过/失败"。模型证据只存放于 `evaluation/<model>/`，
> 目录与字段规范见 `evaluation/README.md`。

---

## 1. 交付物

| 文件 | 说明 |
| --- | --- |
| `README.md` | 仓库说明：状态、六条不变量、文件结构、快速开始、实测结果、已知限制 |
| `instruction.md` | 题目说明：核心矛盾、六条不变量、状态机、统一接口契约、R0–R9 Prompt 原文、每轮评分边界、失效模式清单、交付物与评测流程 |
| `introduction.md` | 题目与模型表现简述（模型列待续跑完成后填写） |
| `rubric.md` | 22 条原子 Rubric + 逐条 Verification + 基线判定 + 计分公式 |
| `evidence-matrix.md` | Rubric → Evidence → Test 双向追溯矩阵 + 六条不变量链路 |
| `golden_answer/` | 完整可运行参考实现（8 个模块）+ 22 个测试 + `verify.sh` + `verify_doc/` |
| `round-evidence/R0…R9/` | 每轮 `prompt.md` / `test-result.txt`（真实执行）/ `evidence.json` / `reviewer.md` |
| `evaluation/` | 真实模型 Trial 结果区（**当前仅 `README.md` + `_TEMPLATE/`，无任何模型结果**） |
| `init/` | 被测模型起始工作区（空） |
| `test/README.md` | 测试套说明 + "如何适配被测模型产出" |
| `solve/README.md` | 参考实现交付说明与设计取舍 |

---

## 2. 底线剔除检查（B1–B5）

| 编号 | 检查项 | 结论 | 说明 |
| --- | --- | --- | --- |
| B1 | 主题不连贯 | ✅ 通过 | 10 轮全部围绕同一售后系统：订单 → 售后申请 → 审核 → 退款 → 渠道失败 → 权限。无发散轮次 |
| B2 | 题目无区分度 | ✅ 通过 | 含状态机 / 事务一致性 / 幂等 / 并发 / 权限五类矛盾；变异测试实测 6/6 弱实现被杀死 |
| B3 | 最后一轮不可验收 | ✅ 通过 | R9 给出 14 条客观要求，全部落到自动化断言；`test/README.md` 给出单测/人评边界 |
| B4 | 领域知识过度依赖 | ✅ 通过 | 需求自身给足规则（金额上限、状态流转、失败语义、权限边界）；第三方渠道被抽象为可替换接口而非外部真实系统 |
| B5 | 多轮为机械拆分 | ✅ 通过 | 轮次类型为：项目启动 / 细节补充 / 需求改变 / 技术取舍 / Review / 代码解释 / 事故 / 安全性能 / 测试 / 收敛。删除任一关键中间轮都会造成后续歧义（见 §5 一致性检查） |

补充说明（试标规则 §4.1 的注意项）：

- "事故反馈"轮（R6）已按规则建议**改写成假设情境**——原文是"请**判断当前代码是否可能**出现这个问题"，
  而不是断言模型已经犯错。因此即便某个模型没有该缺陷，本轮仍然可判。
- R4 的 Review Comment 刻意点出了"读状态 → 判断 → 写状态"的窗口。这是设计意图：
  考察的是**能否定位根因并最小修复**，而不是能否猜出问题（该能力由 R3 的开放提问考察）。

---

## 3. 出题评分（S1–S6）

| 维度 | 评分问题 | 得分 | 理由 |
| --- | --- | --- | --- |
| **S1 场景与约束** | 是否真实专业、约束清楚、输出域收窄 | **3 / 3** | 电商售后退款是真实业务；角色（用户/客服 `AGENT`）、目标、约束明确；可验证强约束 ≥ 3：金额上限、状态机、幂等、并发、权限边界 |
| **S2 后端核心矛盾** | 是否覆盖状态/事务/权限/幂等/并发/排障 | **3 / 3** | 五类矛盾交织：状态机 × 事务一致性（额度预留与回退）× 幂等 × 并发 × 权限，且全部锚定到明确业务不变量 |
| **S3 多轮真实性** | 轮次是否像真实用户响应 | **3 / 3** | 覆盖 10 种真实用户行为（启动/补规则/改需求/取舍/Review/解释/事故/安全性能/测试/收敛）；轮次间存在真实依赖，非显性约束累加 |
| **S4 可评估性** | 终态是否可测、单测与人评边界是否明确 | **3 / 3** | 最终验收 14 条全部自动化可测；`rubric.md` §2 逐条给出 Verification；人评项限于取舍说明、解释一致性、是否过度设计/最小修改 |
| **S5 区分度** | 是否有明确失效模式 | **3 / 3** | 明确 17 条失效模式；其中 #1/#3/#4/#7/#9 已被变异测试证实可被本测试套捕获（6/6 杀死）。中等模型易踩"进程内锁""失败误记成功""只校验存在性"；强模型有升华空间（替代方案与边界说明） |
| **S6 多样性与成本** | 是否补充题库分布、成本是否可控 | **2 / 3** | 领域为电商售后账务，与现有题库中偏多的并发/幂等题在**核心矛盾上存在重叠**（本题的亮点在"状态机 × 事务一致性 × 第三方失败语义"的组合，但仍是并发+幂等题材）；10 轮比规则推荐的 4–8 轮偏多，评审成本高于典型题（自动化部分约 9s，人工约 2–4h） |
| **合计** | | **17 / 18** | **PASS（≥15）** |

---

## 4. 区分度实证：变异测试（真实执行）

方法：把参考实现复制成 6 个"弱实现变异体"（每个注入一类模型常见缺陷），跑测试套，
验证"坏实现必然变红"。结果（原始数据：`round-evidence/R3/mutation-report.json`，
可复跑脚本：`round-evidence/R3/mutation-test.py`；产物已并入本节）：

| 变异体 | 注入缺陷 | 期望 | 实际 | 杀死的用例 |
| --- | --- | --- | --- | --- |
| **M0** | 无（对照组） | 全绿 | ✅ 22 passed | — |
| **M1** | check-then-write 竞态：把 `BEGIN IMMEDIATE` 降级为 `BEGIN`，去掉部分唯一索引、`CHECK` 约束与额度守卫 | 至少 1 条 FAIL | ✅ 被杀 | `test_over_refund_is_rejected`、`test_single_refund_larger_than_paid_amount_is_rejected`、`test_concurrent_multiple_after_sales` |
| **M2** | 第三方失败仍把本地结算为成功 | 至少 1 条 FAIL | ✅ 被杀 | `test_third_party_failure_is_not_marked_success`、`test_failed_refund_can_be_retried`、`test_failed_refund_does_not_consume_quota`、`test_incident_regression_provider_failure` |
| **M3** | 忽略幂等键（重复提交产生新记录，且去掉唯一索引） | 至少 1 条 FAIL | ✅ 被杀 | `test_duplicate_submit_creates_one_after_sale` |
| **M4** | 只校验资源存在性，不校验归属 | 至少 1 条 FAIL | ✅ 被杀 | `test_unauthorized_order_access`、`test_unauthorized_after_sale_access` |
| **M5** | 允许 `PENDING` 直接发起退款尝试 | 至少 1 条 FAIL | ✅ 被杀 | `test_illegal_state_transitions_rejected` |
| **M6** | 失败尝试不释放预留额度 | 至少 1 条 FAIL | ✅ 被杀 | 同 M2 的 4 条 |

**结论：6/6 变异体被杀死，对照组全绿。** 测试套不是"写完就算"，它确实能把弱实现判红。

**诚实披露的不确定性**：M1 在同机环境下**未被 T13 复现**（时序竞态需要精确交错），
但被 T14 稳定杀死。因此 AQ-01/AQ-02 的判定不单独依赖 T13；另有确定性硬证据——
`verify_doc/check_db_guards.py` 直接证明数据库会拒绝非法写入（见 §5）。

---

## 5. Golden Answer 验证结果（真实执行）

| 项目 | 命令 | 结果 |
| --- | --- | --- |
| 全量测试套 | `pytest tests -rA` | **22 passed / 0 failed / 0 error**，7.29s |
| 干净环境一键验证 | `./verify.sh`（新建 venv + `pip install -r requirements.txt`） | **exit code 0** |
| 存储级不变量探测 | `python verify_doc/check_db_guards.py` | **6/6 通过** |
| Golden test 覆盖率 | `python verify_doc/check_coverage_matrix.py` | **18/18 golden tests，6/6 分类** |

> 以上为**最近一次真实执行**的结果（Python 3.13.14 / fastapi 0.141.1 / httpx 0.28.1 /
> pytest 9.1.1 / uvicorn 0.52.4，干净 venv）。原始输出见
> `golden_answer/verify_doc/test-result.txt`。重跑会覆盖该日志。

存储级探测的实际输出（决定性证据，不依赖时序）：

```
[PASS] I2  a second successful refund for one after-sale is rejected
         observed : IntegrityError: UNIQUE constraint failed: refunds.after_sale_id
[PASS] I1  orders.refunded_amount > paid_amount is rejected
         observed : IntegrityError: CHECK constraint failed: refunded_amount <= paid_amount
[PASS] I1  negative refunded_amount is rejected
         observed : IntegrityError: CHECK constraint failed: refunded_amount >= 0
[PASS] R1  after_sales.refund_amount > 0 is enforced by the schema
         observed : IntegrityError: CHECK constraint failed: refund_amount > 0
[PASS] I5  a second BEGIN IMMEDIATE writer is refused while one holds the lock
         observed : OperationalError: database is locked
[PASS] I5  the write lock is released after the holder commits
         observed : NO_ERROR_RAISED
```

六条不变量的落地方式：

| 不变量 | 落地机制 | 验证方式 |
| --- | --- | --- |
| I1 金额上限 | `CHECK (refunded_amount <= paid_amount)` + 单条带条件 `UPDATE` 守卫 | T03/T04 + 存储探测 |
| I2 一售后一成功 | 部分唯一索引 `ux_refunds_one_success` + 认领阶段 CAS | T06/T07/T13 + 存储探测 |
| I3 状态机 | `state_machine.py` 单一转换表，所有写状态经它 | T08/T10 + CODE |
| I4 第三方失败 | 渠道裁决在事务外取得，`_settle` 二分；失败回退额度 | T05/T09/T11/T12 |
| I5 多 worker | `BEGIN IMMEDIATE` + `busy_timeout` + 上述数据库约束 | T13/T14（2 个真实进程）+ 存储探测 |
| I6 权限隔离 | `assert_can_view`（跨租户 404）+ `require_agent` | T15/T16/T17 |

---

## 6. 覆盖情况

| 覆盖对象 | 覆盖情况 |
| --- | --- |
| 六条不变量 I1–I6 | 6/6 有自动化断言 |
| R8 列出的六类测试 | 6/6（business 4、state 2、idempotency 2、concurrency 2、third-party 4、security 3） |
| Golden test T01–T18 | 18/18 |
| 22 条 Rubric | 20 条 PASS（有 Evidence）、2 条 NOT_APPLICABLE（依赖模型 Trace） |
| `instruction.md` §9 的 17 条失效模式 | 15 条有自动化用例直接覆盖；#14（解释与代码不一致）与 #16（大规模重写）依赖人工/Trace，已在 `rubric.md` 中操作化 |
| 每轮 evidence.json | 10/10 轮齐备，Test → Evidence → Rubric 链路完整 |

---

## 7. 未完成事项与风险（不隐瞒）

| # | 事项 | 影响 | 处理 |
| --- | --- | --- | --- |
| 1 | **没有真实模型 Trace** | `IF-02`（增量演进）、`TE-01`（是否最小修改）在基线中不可判定 | 已标 `NOT_APPLICABLE` 并在 `round-evidence/*/reviewer.md` 留好占位表。按试标规则要求**不伪造 Trace**，须在实测环节填写 |
| 2 | **轮次 10 轮 > 规则推荐的 4–8 轮** | 评审成本偏高，体现在 S6=2 | 已在 §9 给出压缩方案；若排期紧张建议先按 8 轮版本试标 |
| 3 | **并发用例存在时序不确定性** | T13 在个别弱实现上可能侥幸通过 | 已用"栅栏同步 + 多轮重复 + 网关延迟 0.15s"降低不确定性；并补了与时序无关的存储层探测作为 AQ-01/AQ-02 的硬证据 |
| 4 | **金额若用 `float`，小额整数场景未必被自动抓出** | 失效模式 #17 可能漏判 | 自动化断言只覆盖整数分场景。**须在 D4 人工代码审查中检查金额类型**；`rubric.md` 中已在 AQ-02 的 CODE 证据里标注 |
| 5 | **R7 的性能要求刻意未给量化阈值** | 不同评审人可能判罚不一 | 已把可自动化的部分操作化（索引命中、`limit=5` 返回 5 行、分页延迟 < 500ms），其余限定为"只修真实问题"，并在 `round-evidence/R7/reviewer.md` 给出判据 |
| 6 | **多进程并发用例依赖本机回环端口** | 在严格禁网/禁端口的 CI 上可能失败 | `verify_doc/README.md` 已注明；若环境不允许，可只跑 `tests/` 的非并发子集并单独记录，不可直接跳过并发用例 |
| 7 | **环境代理会破坏 HTTP 测试** | 复用时请求行变绝对形式 → 假 404 | 所有测试客户端已设 `trust_env=False`；`test/README.md` §5 已写明，适配脚本须沿用 |

---

## 8. 优化建议

**短期（不影响入库）**

1. 试标时优先用"最高思考等级 + 关闭记忆 + 全新工作区"三件套，并把 `trace_id`
   按规则 §6.2 填入 `round-evidence/*/reviewer.md` 的占位表。
2. 先跑 `test_order.py` 打通接口适配，再逐文件放开；`test/README.md` §4 已给出 6 步流程。
3. 人工评审时把 D4 的判定与 `rubric.md` §2 的 Verification 逐条对齐，避免"印象分"。

**中期（提升区分度）**

4. 若试标结果显示多模型在同一点全对或全错，优先调整**该点的尖锐度**：
   - 并发点全对 → 把 T13 的攻击线程提到 16 并增加轮数（成本 +10s），
     或在 R3 追加"换 Postgres 时方案如何平移"的追问；
   - 金额点全对 → 在 R7 追加"异常请求不能绕过金额限制"的具体形态（如 `refund_amount` 传超大整数/负数/字符串）。
5. 若需要更强的"是否最小修改"信号，可在 R4 后追加一轮"请用 `git diff` 说明你改了哪些文件、
   为什么这是最小改动"——把主观项变成可留痕的自证。

**长期（题库分布）**

6. 本题与既有并发/幂等题材存在部分重叠（S6=2）。若要补分布短板，可基于同一骨架
   派生一道**数据库方向**的题（例如"退款流水的分表与在线归档"）或**简化版后端工具复刻**
   （例如"实现一个带幂等与限流的内部 RPC 网关"），复用本包的 Rubric 结构与验证方法。

---

## 9. 轮次压缩方案（可选）

若评审排期紧张，可把 10 轮压到 8 轮，且不损失任何不变量覆盖：

- 合并 **R4 与 R5**：一轮内先让模型判断 Review Comment 是否成立，再要求它解释当前实现。
  （代价：Review 与解释两个考察点会相互提示。）
- 合并 **R8 与 R9**：R9 本身已要求"完善测试并运行完整测试"，R8 的清单可作为 R9 的子项。

不推荐删除 R3（技术取舍）与 R6（事故）——并发保护与第三方失败语义是本题最主要的区分点。

---

## 10. 结论

| 项目 | 结论 |
| --- | --- |
| 底线剔除 B1–B5 | 全部通过 |
| 质量评分 S1–S6 | **17 / 18 → PASS**（S6=2，因核心矛盾与题库既有并发/幂等题材部分重叠且轮次偏多） |
| Golden Answer | 本机跑通，22 个测试全绿，存储级保护 6/6，`verify.sh` 退出码 0，日志留痕 |
| 测试套 | 22 个节点，T01–T18 全覆盖，6/6 分类覆盖，并发跨进程、失败确定性 |
| 区分度 | 变异测试 6/6 杀死；失效模式与用例一一对应 |
| Rubric | 22 条原子细则，20 条有证据 PASS，2 条待实测 Trace；`round` 字段 22/22 为单一最后相关轮次 |
| **模型评测** | **未完成（INCOMPLETE）**——3 个真实模型已跑通 R0/R1 后被账号级模型配额（HTTP 429）阻断，未到 R9；仍无任何模型的完整 PASS / FAIL。留痕见 `evaluation/_trial-incomplete/` |
| 交付就绪度 | **已进入真实 Model Trial 阶段（未完成）**；Trial 已真实启动并跑到 R0/R1，待补动作是在配额窗口内续跑 R2–R9，再填写 `evaluation/<MODEL>/` 与模型列 |

> 最后一行是本次交付的定位：**让 `BE-ORDER-REFUND` 达到"可直接进入真实 Model Trial"的状态，
> 而不是假装已经完成 Model Trial。**
