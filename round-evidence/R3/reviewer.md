## 本轮考点

这是全题最锋利的一轮：**并发保护必须跨进程有效**。
R3 已经把话说到位——"当前数据库使用 SQLite"，并要求说明方案、替代方案和限制。

判定基线：`threading.Lock`（或任何进程内对象）**不足以**满足 I5，
即使单进程测试全绿也不行。参考解为此把保护下沉到数据库。

## 人工评审要点

| 看什么 | 判定依据 |
| --- | --- |
| 并发保护的位置 | 是否依赖数据库写锁 / 唯一约束 / 原子条件更新，而不是进程内锁 |
| 是否回答"替代方案" | 例如"换 PostgreSQL 用行锁/SERIALIZABLE"、"乐观锁 + 版本号"、"把扣减做成单语句" |
| 是否说明限制 | SQLite 单文件写锁、吞吐上限、崩溃窗口是否有交代 |
| 并发测试的质量 | **必须校验业务结果**（成功笔数、累计金额），只 `asyncio.gather` 或只断言"请求都发出了"不算 |
| 是否引入不必要基础设施 | Redis/Kafka/Celery 之类对单机 SQLite 服务属于过度设计 |

## Golden Answer 观察

- `BEGIN IMMEDIATE` + `busy_timeout=30000`：在第一次读之前就拿到写锁，杜绝 check-then-write 交错。
- 额度预留是**单条带条件 UPDATE**：`WHERE refunded_amount + ? <= paid_amount`，检查与写入原子完成。
- 两层数据库兜底：`CHECK (refunded_amount <= paid_amount)` 与
  `ux_refunds_one_success ON refunds(after_sale_id) WHERE status='REFUNDED'`。
- 第三方调用放在两个短事务**之间**，慢渠道不持有写锁。
- 并发测试用 2 个真实 uvicorn 进程 + 0.15s 网关延迟拉宽窗口 + 栅栏同步 + 多轮重复。
- 存储层探测（`check_db_guards.py`）提供与时序无关的确定性证据。

## 自动化证据

`test-result.txt` 中 R3-T01..T04（含 `check_db_guards.py` 的 6 项输出）。

## Rubric 判定提示

- `AQ-01` 若要判 PASS，必须看到**跨进程**证据（T13/T14 或存储层探测），不能只凭代码里有一个 Lock。
- 如果模型声称用进程内锁解决了多 worker，`AQ-01` 直接判 FAIL——这正是失效模式 #7。

## 模型 Trace 留痕（待实测填写）

| 模型 | 并发方案 | 是否跨进程有效 | T13 | T14 | 是否说明替代方案/限制 |
| --- | --- | --- | --- | --- | --- |
| HY3 | 待填 | 待填 | 待填 | 待填 | 待填 |
| model_c | 待填 | 待填 | 待填 | 待填 | 待填 |
| model_d | 待填 | 待填 | 待填 | 待填 | 待填 |
