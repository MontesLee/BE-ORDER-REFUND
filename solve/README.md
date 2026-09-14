# solve — 参考实现（Golden Answer）交付说明

本目录是四件套中的 **参考实现 / solve** 件。实现在
`../golden_answer/`，本文件说明它是什么、怎么用、按什么口径被引用。

---

## 1. 内容清单

```
golden_answer/
├── app/
│   ├── main.py             FastAPI 应用、路由、错误码映射
│   ├── models.py           领域枚举与值对象（无 I/O）
│   ├── schemas.py          请求/响应模型（金额声明为 int）
│   ├── repository.py       SQLite 连接、DDL、SQL；I1/I2 的数据库级保护在这里
│   ├── service.py          业务规则与事务边界；三段式执行退款在这里
│   ├── state_machine.py    状态转换单一真相表
│   ├── refund_gateway.py   可替换第三方渠道（可编程成功/失败）
│   └── auth.py             调用方身份与归属/角色校验
├── tests/                  22 个测试（T01–T18 + R0 基线 + 额外边界）
├── requirements.txt        fastapi / uvicorn / pytest / httpx
├── pytest.ini
├── README.md               设计说明：不变量落地点、接口表、已知限制
├── verify.sh               干净环境一键验证
└── verify_doc/
    ├── README.md           验证口径
    ├── test-result.txt     真实运行输出（含 22 passed + 两项探测）
    ├── check_db_guards.py        存储级不变量探测
    ├── check_coverage_matrix.py  T01–T18 覆盖探测
    └── inspect_for_explanation.py R5 代码检视输出
```

## 2. 怎么用

```bash
cd golden_answer

# 一键验证（新建 venv + 装依赖 + 全量测试 + 两项探测）
./verify.sh

# 手动运行
pip install -r requirements.txt
uvicorn app.main:app --reload        # http://127.0.0.1:8000/docs
pytest tests -v
```

金额单位为**分（integer cents）**；身份通过 `X-User-Id` 请求头传递。

## 3. 设计取舍一览（也是评分时的人工参照）

| 决策 | 选择 | 理由 |
| --- | --- | --- |
| 金额表示 | `int` 分 | `float` 无法精确表示 0.01，会静默破坏 I1 |
| 并发保护 | `BEGIN IMMEDIATE` + 数据库约束 | 必须跨进程有效；`threading.Lock` 在多 worker 下无效 |
| 额度扣减 | 认领时用单条带条件 `UPDATE` 预留，失败回退 | 检查与写入原子完成；失败不烧额度 |
| 一售后一成功 | 部分唯一索引 `WHERE status='REFUNDED'` | 数据库兜底，应用逻辑写错也拦得住 |
| 幂等键载体 | `after_sales.idempotency_key` + 部分唯一索引 | 持久、可跨进程、可审计 |
| 第三方调用位置 | 两个短事务之间 | 慢渠道不持有数据库写锁 |
| 渠道抽象 | `RefundGateway` 协议 + 可编程实现 | 让 I4 可确定性测试，而不是"偶现" |
| 崩溃恢复 | 显式 `POST /maintenance/reconcile` | 不假装有分布式事务；边界写进 README |
| 跨租户响应码 | `404` 而非 `403` | 不泄露资源是否存在 |
| 状态写入 | 全部经过 `state_machine` + `expect_status` CAS | 单一转换表，无旁路 |

## 4. 它被引用在哪里

| 用途 | 引用点 |
| --- | --- |
| baseline 对照 | `introduction.md`（模型表现对比表） |
| 测试套来源 | `test/README.md`、`golden_answer/tests/` |
| Rubric 依据 | `rubric.md` §2 的 Verification 列 |
| Evidence 来源 | `round-evidence/R0..R9/evidence.json`、`evidence-matrix.md` |
| 质量校验 | `evaluation-report.md` §3 §4 |

## 5. 明确不包含的内容

- **不包含任何模型的产出**：没有真实模型 Trace 时不得伪造。模型产物存放在
  仓库根的 `evaluation/<model>/`（`trace.md` / `result.md` / `final-artifact/` / `evidence.md`），
  **该目录当前只有 `README.md` 与 `_TEMPLATE/`，没有任何模型结果**。
- **不包含"标准答案式"的唯一解**：参考解只是 baseline。模型用别的机制达成同样的
  不变量（例如换 Postgres 行锁、用乐观锁版本号）同样可以拿满分。
- **不包含隐藏的评测逻辑**：所有断言都在 `tests/` 里明文可见，没有暗桩。

## 6. 这份参考解算哪一类证据

**Golden Evidence**——回答"参考答案本身是否满足 Benchmark 要求"，**不回答**
"某个模型是否通过"。两者的边界见 `../evaluation/README.md` §1 与
`../rubric.md` §4。
