# TRACE_R8 — 补齐完整自动化测试（hy3）

> **注（评测方重建）**：本文件由评测方根据工作区真实产物重建。R8 的子 Agent 实际已执行完毕（工作区已落地 `tests/test_round8.py`，独立复跑 76 passed），但其最终回复因 HTTP 429（账户级配额，重置时间 2026-09-14 18:00:01 UTC+8）被工具截断，未回传 `POWERED-BY` 与自我总结。工作区核验确认执行真实发生，故据证据重建此 trace，不臆造模型原话。

## 轮次目标（instruction.md §7 原文）
为系统补齐完整自动化测试，确保稳定、重复运行；至少覆盖 Business / State / Idempotency / Concurrency / Third-party / Security 六大类共 14 个子项；不允许以随机 sleep 作为核心正确性证明；最后运行完整测试集并修复失败。

## 实际落地内容
- **新增** `tests/test_round8.py`（22 个测试函数），按六大类逐类确定性覆盖：
  - Business：`normal_refund` / `unpaid_refund_rejected`（CREATED 即拦截 409）/ `invalid_amount_zero_and_negative`（422）/ `invalid_amount_over_remaining`（409 不污染累计）/ `multiple_partial_refunds`（累计闭单）/ `over_refund_blocked`
  - State：`not_approved_cannot_refund`（PENDING 409）/ `refund_failed_can_retry`（502→REFUND_FAILED→换成功渠道重试 200）/ `refunded_cannot_retry`（重放不二次扣减）/ `illegal_transition`（REJECTED 409）
  - Idempotency：`duplicate_submit`（同 Idempotency-Key 结果完全一致、仅退一次）/ `duplicate_execute`（无键重复执行、渠道仅调用一次）
  - Concurrency：`same_after_sale_http`（12 线程并发同一售后，至多一次成功）/ `multiple_after_sales_over_refund_http`（5 售后并发抢退，恰好 1 成功 4 因超额 409，累计不超额）
  - Third-party：`failure`（502、本地绝不 REFUNDED、累计不变）/ `retry`（失败→成功渠道重试）/ `execute_after_success`（成功后重放不再调渠道）
  - Security：`unauthorized_order`（IDOR 403）/ `unauthorized_after_sale`（IDOR 403）/ `normal_user_protected_execution`（普通角色审核被拒 403、无法绕过审核）/ `normal_user_cannot_refund_others_after_sale`（跨归属 403）
- 并发用例均断言**最终落库业务状态**（累计退款金额 / 状态 / 渠道调用次数），而非仅断言“请求被同时发出”。
- 使用 `autouse` fixture 在每个用例前后 `store.reset()` + 恢复成功网关，保证隔离、可重复。

## 核心代码改动
- **无**：`app.py` / `store.py` / `models.py` / `schemas.py` / `gateway.py` 在 R8 期间 mtime 未变化（仍为 R7 产物）。R2–R7 已实现全部被要求的行为，R8 仅做测试补全与集中化，符合“补齐测试、不重写项目”的约束。

## 独立复跑结果（评测方，托管解释器）
```
C:\Users\aubor\.workbuddy\binaries\python\envs\default\Scripts\python.exe -m pytest tests -q
76 passed, 2 warnings in 13.96s
```
（R8 前为 55 passed；新增 `test_round8.py` 贡献 21 个测试，另有 1 个已含——实际 +21 → 76。）

## 已知限制 / 未决
- 金额仍以 `float`（`REAL`）存储，未切换为整数分；R5 已记录此限制，Golden 评测将据此判定 CU 相关 Rubric。
- 幂等与并发控制依赖共享 SQLite（`BEGIN IMMEDIATE`）；进程内与跨进程场景均已覆盖，但非分布式部署保证。
- 本 trace 为评测方重建，原始模型自述缺失。
