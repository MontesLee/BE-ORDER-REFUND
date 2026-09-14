## 本轮考点

I4：**渠道裁决是本地状态的唯一依据**。R6 同时要求"能确定性复现第三方失败"——
这实际上是在要求模型做出一个可替换的 `RefundGateway` 抽象；
只会说"重试一下"或"加个 try/except 把状态置回"都不达标。

## 人工评审要点

| 看什么 | 判定依据 |
| --- | --- |
| 是否真的定位到根因 | 是"本地状态由调用结果之外的信号决定"，而不是"网络抖动" |
| 是否有可替换抽象 | 提供 `RefundGateway` 或等价接口，测试可注入成功/失败 |
| 失败后是否可重试 | `REFUND_FAILED → REFUNDING` 通路存在，且成功后不得再退 |
| 失败是否释放额度 | 失败尝试不能永久烧掉额度（这正是"只有成功退款计入"的落地） |
| 是否引入重基础设施 | Saga / Outbox / MQ 对单机 SQLite 服务属于过度设计；本地状态机 + 可重试即可 |
| 测试的确定性 | 必须稳定复现，不允许靠随机 sleep 或"偶现" |

## Golden Answer 观察

- `app/refund_gateway.py` 定义 `RefundGateway` 协议与 `StubRefundGateway`，
  支持 `fail_first_n` / `fail_always` / `latency_seconds`，并按 `idempotency_key` 幂等。
- `execute_refund` 三段式：认领（含额度预留）→ 事务外调用渠道 → 结算。
  失败分支写 `REFUND_FAILED` 并 `release_refund_quota`。
- 崩溃窗口（认领后进程挂掉）由 `POST /maintenance/reconcile` 显式释放，
  并在 README §7 中作为限制写明——不假装它是分布式事务。

## 自动化证据

`test-result.txt` 中 R6-T01..T04。

## 模型 Trace 留痕

> 本次交付仅评测一个模型：**Hy3（已完成 R0–R9）**。逐轮判定与证据见 `evaluation/HY3/evidence.md`，
> 汇总见 `evaluation/HY3/result.md`。占位名 `model_c` / `model_d` **不在本次交付范围**（未评测），故不列。
