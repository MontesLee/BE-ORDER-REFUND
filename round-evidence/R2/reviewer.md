## 本轮考点

幂等从这一轮开始正式计分。注意 R2 **不指定技术方案**，因此评审只看结果：
重复请求不能产生第二个有效退款。

## 人工评审要点

| 看什么 | 判定依据 |
| --- | --- |
| 幂等载体 | 唯一约束 / upsert / 重放表都可以；"进程内 dict" 不可以（重启即失效） |
| 幂等粒度 | 客户端重复提交（申请）与重复触发（执行）是否都覆盖 |
| 是否破坏 I1 | 重复请求不得两次占用额度 |
| 状态机是否被绕开 | 重复执行不应把 `REFUNDED` 拉回 `REFUNDING` |
| 是否过度设计 | 为幂等引入 Redis/MQ 属于过度设计 |

## Golden Answer 观察

- 申请侧：`after_sales.idempotency_key` + 部分唯一索引 `ux_after_sales_idempotency`；
  同 key 重放返回原记录（HTTP 200，`replayed=true`）。
- 执行侧：认领阶段做 `expect_status` CAS；`REFUNDED` 状态下的再次执行走"重放"分支返回原退款。
- `ux_refunds_one_success`（`WHERE status='REFUNDED'`）是从数据库层面兜住"一个售后一条成功退款"。
  **注意这是深防，不是模型必须采用的方案**——模型用别的手段达成同样结果即可。

## 自动化证据

`test-result.txt` 中 R2-T01..T05。

## 模型 Trace 留痕

> 本次交付仅评测一个模型：**Hy3（已完成 R0–R9）**。逐轮判定与证据见 `evaluation/HY3/evidence.md`，
> 汇总见 `evaluation/HY3/result.md`。占位名 `model_c` / `model_d` **不在本次交付范围**（未评测），故不列。
