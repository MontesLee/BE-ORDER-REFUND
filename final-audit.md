# Final Benchmark Audit — BE-ORDER-REFUND

审计时间：2026-09-14 · 对象：`BE-ORDER-REFUND`（多轮式后端开发 Agent 评测题）
方式：Audit（只读） → Minimal Fix → Validation → Final Audit
口径：**对齐 Tlabel 后端 Benchmark 规范；不重新设计题目，不为"看起来完整"增加功能。**

---

## 1. Overall Status

**PASS WITH FOLLOW-UP**

题目、参考解、测试体系、Rubric、证据链已达交付标准，可**直接进入真实 Tlabel Model Trial 阶段**。
唯一未完成的环节是**真实模型 Trial 本身**——这是流程性的"尚未执行"，不是设计缺陷。

---

## 2. Benchmark Structure

R0–R9（10 轮，同一连续工作区）：

```
R0 项目启动 → R1 细节补充(部分退款) → R2 需求改变(幂等) → R3 技术取舍(multi-worker)
→ R4 Code Review(竞态) → R5 代码解释 → R6 线上事故(第三方失败) → R7 安全/性能
→ R8 测试要求 → R9 最终收敛
```

| 检查项 | 结论 | 说明 |
| --- | --- | --- |
| 主题连贯（B1） | PASS | 10 轮全部在"订单 → 售后 → 审核 → 退款 → 渠道失败 → 权限"同一条主线上，无发散轮 |
| 非机械 CRUD（B5） | PASS | 轮次类型为 启动/补规则/改需求/取舍/Review/解释/事故/安全性能/测试/收敛，不是"加字段→加接口"循环 |
| 中间轮不可删 | PASS | R3 定义并发保护 → R4 必须依赖 R3 暴露的问题（Review Comment 问的正是 check-then-write）；R6 → R8 → R9 形成连续演进 |
| 末轮可验收（B3） | PASS | R9 的 14 条要求全部落到自动化断言 |
| R0–R9 设计 | **未改动** | 未删除、未重排、未合并、未新增轮次 |

---

## 3. Golden Answer

| 项目 | 结果 |
| --- | --- |
| Tests | **PASS** — `22 passed / 0 failed / 0 error`，7.29s（干净 venv） |
| Verification | **PASS** — `./verify.sh` **exit code 0** |

**业务逻辑未改动。** 本轮未修改 `golden_answer/app/**` 与 `golden_answer/tests/**` 的任一行；
唯一被写入的是 `verify_doc/test-result.txt`（重跑验证时脚本自动覆盖的运行日志）。

---

## 4. Rubric Compliance

| 项目 | 结果 |
| --- | --- |
| 22 rubrics | **PASS**（22 条均为原子命题 · PASS/FAIL/NA 三选一 · 单一维度 · 有 Evidence） |
| Round field | **PASS**（22/22 为**单一最后相关轮次**，无区间、无斜杠） |
| 维度合法性 | PASS（只用 D1 Instruction Following / D2 Feature Delivery / D3 Task Efficiency / D4 Architecture Quality / D5 Context Understanding，未新增维度） |
| 可判定性 | PASS（命题形如 "Does the implementation prevent cumulative successful refunds from exceeding paid_amount?"，不存在"设计合理/架构优雅"类表述） |
| Subjective 项 | PASS（TE-01 / TE-03 / AQ-05 / CU-03 均给出 Reviewer 该看什么证据、什么算 PASS） |

### Round 字段逐条判定（多轮 → 最后一个相关轮次）

| Rubric | 原值 | 现值 | 依据 |
| --- | --- | --- | --- |
| IF-02 | `R1–R9` | **R9** | 增量演进只能在末轮判定 |
| FD-03 | `R1/R3` | **R3** | 累计上限 R1 引入，R3 要求并发下仍成立 |
| FD-05 | `R2/R3` | **R3** | R3 要求跨进程并发下仍至多一条成功退款 |
| FD-06 | `R2/R6` | **R6** | R6 扩展状态机（新增 `REFUND_FAILED` 与重试语义） |
| TE-01 | `R4–R9` | **R9** | 是否做过无关重构要看全程 diff |
| TE-02 | `R4/R6/R8` | **R8** | 定向回归 → 确定性复现 → 全量套件，闭环在 R8 收口 |
| TE-03 | `R3/R6/R7` | **R7** | R6 可能引入 MQ/Outbox、R7 可能引入缓存，最后一次要求是 R7 |
| AQ-02 | `R3` | **R7** | 命题含"数据增长下不退化"，该要求由 R7 提出（证据 `R7-E04`） |
| AQ-03 | `R5/R6` | **R6** | R6 的失败路径同样必须走状态机，属要求加强 |
| AQ-05 | `R3/R5` | **R5** | R5 才要求解释"当前方案的限制" |
| CU-01 | `R3–R9` | **R9** | 历史不变量只能看全程 |

**刻意未改的两条**（说明规则是按语义判定、不是取最大值）：

- `AQ-01` 保持 **R3**：R4 是对同一并发要求的 Review 复核、R5 是解释，**都没有新增或加强**该命题；
  `R5-E03` 仅为佐证型 CODE 证据。
- `FD-01` 保持 **R0**、`FD-04` 保持 **R2**、`FD-07`/`AQ-04`/`CU-02` 保持 **R6**：命题在引入后未被后续轮次加强。
- 规则明确写成"要求最后一次成为最终形态的轮次"，**不是**"最后一次重复测它的轮次"——
  否则几乎所有 Rubric 都会退化成 R9（这是须避免的机械做法）。

---

## 5. Evidence

| 项目 | 结果 |
| --- | --- |
| Golden evidence | **PASS** — `golden_answer/` + `round-evidence/` + `test/` 三段齐全；Rubric→Evidence→Test 双向可追溯；6 条不变量（I1–I6）均具备 Prompt 要求 → 参考实现 → 自动化验证 → Rubric 四段完整链路 |
| Model evidence | **READY FOR TRIAL** — `evaluation/README.md` 已定义口径、目录结构、四类文件字段规范与 10 步判定流程；`evaluation/_TEMPLATE/` 提供空白模板；**无任何模型结果** |
| 证据语义 | **PASS** — `Rubric PASS ≠ Golden Answer PASS ≠ Model PASS` 已在 5 处显式声明（`rubric.md` §4、`evidence-matrix.md` 开头、`evaluation-report.md` 开头、`README.md` §0、`evaluation/README.md` §1） |
| Evidence 优先级 | PASS（统一 `TEST > CODE > TRACE > DOC > REVIEW`；客观项全部由 TEST 支撑） |

---

## 6. Tlabel Compliance

| 件 | 结论 | 说明 |
| --- | --- | --- |
| instruction.md | **PASS** | 评测方文档，已标注阅读边界；第 7 节的 R0–R9 Prompt 原文**逐轮下发给模型**，不含 Rubric / Golden / 不变量编号 / 失效模式表 / 评分规则 |
| test | **PASS** | 断言业务结果不绑定机制；并发用例跨真实进程；失败可确定性注入 |
| solve | **PASS** | 参考解交付说明 + 设计取舍；只作 baseline，不声称唯一解 |
| golden_answer | **PASS** | clean environment 可运行，`verify.sh` 退出码 0 |
| rubric | **PASS** | 22 条原子细则，字段符合 Tlabel（含 `round` 单一轮次） |
| evidence | **PASS** | 双向追溯 + 不变量链路 + 覆盖自检 |
| model evaluation | **PENDING REAL TRIAL** | 尚未执行，未伪造 |

---

## 7. Known Limitations

1. **Real model traces not yet collected** — `IF-02`（增量演进）与 `TE-01`（是否最小修改）在 Golden 基线中
   只能记 `NOT_APPLICABLE`，必须由实测 Trace 填写。
2. **Model stratification not yet measured** — 分层点尚未实测；目前只有**变异测试**证明"测试套能判好坏实现"
   （6/6 变异体被杀死，对照组全绿），这不等于"模型之间一定分层"。
3. **10-round evaluation has relatively high execution cost** — 比规则推荐的 4–8 轮偏多（S6 = 2/3）。
   候选优化：合并 R4/R5，或合并 R7/R8；**本次不合并**，仅记录。
4. **Concurrency timing has known nondeterministic characteristics** — T13 在个别弱实现上可能侥幸通过
   （本机实测 M1 未被 T13 复现、被 T14 稳定杀死）。因此 `AQ-01`/`AQ-02` 另有与时序无关的存储层硬证据
   `verify_doc/check_db_guards.py`（6/6）。
5. **金额类型若用 `float` 在小额整数场景未必被自动抓出** — 已限定为人工代码审查项（`rubric.md` 中标注）。
6. **并发用例依赖本机回环端口** — 严格禁端口 CI 上可只跑非并发子集并单独记录，不可直接跳过。
7. **`AGENTS.md` 不存在** — 本仓库不使用该约定文件，无需创建。

---

## 8. Next Required Step

**最大的剩余问题不是 Benchmark 设计，而是真实 Coding Agent Trial 尚未执行。**

```
1.  CodeBuddy 创建独立 workspace
2.  从 init/ 开始
3.  使用 evaluator 指定模型（HY3 / model_c / model_d）
4.  严格按 R0 → R9 发送 Prompt 原文
5.  保存最终 artifact → evaluation/<model>/final-artifact/
6.  保存 request ID / trace ID → evaluation/<model>/trace.md
7.  执行 Golden tests（只改 harness.py 适配）
8.  根据实际模型行为填写 Rubric → evaluation/<model>/evidence.md
9.  找出模型之间真正产生差异的 invariant / decision
10. 更新 evaluation report 与 introduction.md §4
```

模板与字段规范见 `evaluation/README.md`；判定标准见 `rubric.md`；接口适配见 `test/README.md` §4。

---

## 9. 本次修改清单

| 文件 | 变更 | 原因 |
| --- | --- | --- |
| `rubric.md` | Round 字段 11 条收敛为单一轮次；新增 Round 字段口径与判定示例；§4 增加"这不是模型评测结果"的证据边界 | Tlabel 规范：多轮 Rubric 取最后一个相关轮次；杜绝 `Rubric PASS = Model PASS` 歧义 |
| `evidence-matrix.md` | 表头 `Trigger` → `Round` 并对齐新值；开头增加 Golden vs Model 两类证据对照；§4 增加两项自检；**新增 §5 六条不变量 → Rubric → Evidence 链路** | 字段一致性 + 证据语义澄清 + 不变量链路可查 |
| `evaluation/`（新增） | `README.md`（口径 / 结构 / 四类文件字段规范 / 10 步流程 / 禁止事项）+ `_TEMPLATE/`（`trace.md`、`result.md`、`evidence.md`、`final-artifact/README.md`） | 为真实 Trial 建立标准目录与记录结构；**不含任何伪造模型结果** |
| `README.md` | 新增 §0「已完成 / 未完成」状态表与证据边界；文件结构补 `evaluation/`；§7 补"模型 Trial 未执行" | README 必须准确表达当前状态 |
| `evaluation-report.md` | 开头新增证据边界表；§1 交付物补 `README.md` / `evaluation/`；§5 时间改为实测值并注明环境；§10 结论增加"模型评测 = 未执行"与交付就绪度 | 区分 Golden 基线与模型评测；不填写推测值 |
| `introduction.md` | §2 目录补 `README.md` / `evaluation/`；平台映射行指向 `evaluation/<model>/`；§3 标题与时间更新 | 状态一致 |
| `instruction.md` | §10 交付物补 `README.md` / `evaluation/` 并注明评测方文档边界；§11 评测流程补第 7 步与"已就绪、待实测"说明 | 交付结构与流程完整 |
| `test/README.md` | 开头新增"这套测试产生哪一类证据"对照表 | 明确 Golden / Model 证据来源 |
| `solve/README.md` | §5 改为指向 `evaluation/<model>/`；新增 §6「这份参考解算哪一类证据」 | 证据语义澄清 |
| `golden_answer/verify_doc/test-result.txt` | 由重跑 `./verify.sh` 自动覆盖（真实运行日志） | 验证留痕须为最近一次真实执行 |

**未修改**：`golden_answer/app/**`、`golden_answer/tests/**`、`golden_answer/verify.sh`、
`golden_answer/verify_doc/*.py`、`round-evidence/R*/prompt.md`、`round-evidence/R*/evidence.json`、
`init/`、`evaluation/` 之外无新增业务文件。

---

## 10. 未做（按约束明确不做）

未伪造 HY3 / model_c / model_d 结果与 `trace_id`；未削弱 Golden Answer 以制造差异；
未增加 Redis / Kafka / K8s / 微服务 / ORM；未大规模重构；未改动客户端业务语义；
未把模型评价写入 Golden baseline；未删除失效模式；未删除或合并 R0–R9。
