# Hy3 Golden 测试基线（R0–R8 产物，R9 执行前）

> 状态：R9 被平台配额窗口阻断（hy3 重置时间 2026-09-14 18:00:01 UTC+8），尚未执行。
> 本文件是 **R0–R8 已落地产物** 的统一 Golden 测试真实结果，作为 R9 执行前的对照基线。
> R9 执行后，将重新冻结产物并复跑本套件，结论以最终 `evaluation/HY3/` 下文件为准。

## 运行方式

- 测试断言：逐字复制自 `golden_answer/tests/test_*.py`（未改断言），排除 `test_performance.py`（hy3 无 `refunds` 表 / repository 模块）。
- 适配层：`evaluation/HY3/harness_test/harness.py` + `conftest.py`，仅桥接 hy3 契约差异：
  1. hy3 无 `/users` 注册，身份走 `X-User-Id` 头；
  2. 退款金额在**执行端**指定（canonical 在创建端），adapter 记忆后重放到 execute；
  3. 幂等键 `Idempotency-Key` 在执行端消费；
  4. 响应扁平、`status`→`payment_status`、裸列表→`{items,total}` 包装；
  5. 列表端点用 `GET /after-sales`（无 `/orders/{id}/after-sales`）。
- 双模式：功能不变量用 `HY3_EXECUTOR=owner`（canonical 的 agent 执行者 = hy3 的 owner）；安全/角色测试用 `HY3_EXECUTOR=caller`（透传 caller 验真实鉴权）。

## 结果（R0–R8 产物）

| 测试 | 业务含义 | 模式 | 结果 | 归因 |
|---|---|---|---|---|
| T01 normal full refund | 已支付可全额退 | owner | ✅ PASS | — |
| T02 unpaid cannot refund | 未支付不可退 | owner | ✅ PASS | — |
| T03/04 amount (partial/over/single) | 金额规则 | owner | ✅ PASS (3) | — |
| T05 failed refund no quota | 失败不退额度(I4) | owner | ⚠️ 测试失败，\*\*业务通过\*\* | hy3 返 502，断言要 `<500`；本地确为 REFUND_FAILED、额度未消耗 |
| T06 duplicate submit one after-sale | 创建端幂等(I2) | owner | ❌ FAIL | hy3 幂等在建执行端，创建端不消费 key → 重复 create 产生两个售后（退款不超发，但无 keyed 去重） |
| T07 duplicate execute one refund | 执行端幂等(I2) | owner | ✅ PASS | — |
| T08 state machine illegal / terminal | 状态机(I5) | owner | ✅ PASS (2) | — |
| T09 retry after failure | 失败可重试(I4) | owner | ⚠️ 测试失败，\*\*业务通过\*\* | 同 T05：502 vs `<500` 守卫 |
| T11 third-party failure not REFUNDED | 第三方失败不成功(I4) | owner | ⚠️ 测试失败，\*\*业务通过\*\* | 同 T05：502 vs `<500` 守卫 |
| T12 incident regression | R6 事故复现 | owner | ✅ PASS | — |
| T13/14 concurrency (same / multi) | 并发不变量(I3) | cluster | ✅ PASS (3) | 多进程 SQLite `BEGIN IMMEDIATE` + 条件 UPDATE 生效 |
| T15 order isolation | 订单隔离(I6) | caller | ✅ PASS | owner 隔离 |
| T16 after-sale approve isolation | 售后审核隔离(I6) | caller | ❌ FAIL | \*\*FD-08\*\*：review 端点仅查 `X-User-Role`，无角色头时放行；普通用户可 approve 他人售后 |
| T17 protected execution | 受保护执行(I6) | caller | ✅ PASS | 非 owner 执行被 403 拒绝 |

汇总：套件 verbatim 运行 **15 passed / 6 failed**。其中：
- **3 个失败（T05/T09/T11）是 502-vs-`<500` 守卫**，业务不变量 I4 完全满足 → 评估中计为 **I4 通过（HTTP 状态码偏差备注）**。
- **1 个失败（T06）是创建端幂等缺失** → 真实**部分实现**（R2 将幂等置于执行端）。
- **1 个失败（T16）是 FD-08 真实安全缺口**：review 端点无 owner 校验。
- **1 个失败（T17(b) 在 owner 模式）是 adapter 误报**，caller 模式已确认 hy3 正确拒绝 foreign 执行 → 计为 **通过**。

## 不变量结论（R0–R8 产物，预 R9）

| 不变量 | 判定 | 备注 |
|---|---|---|
| I1 已支付才可退 | ✅ 满足 | T02 |
| I2 单售后最多一成功退款 / 重复不重复退 | ✅ 满足（执行端）；⚠️ 创建端部分 | T07 通过；T06 创建端 keyed 去重缺失 |
| I3 累计退款 ≤ paid_amount | ✅ 满足 | 并发测试通过 |
| I4 第三方失败不标记本地成功 | ✅ 满足 | FD-08 无关；502 状态码偏差备注 |
| I5 状态机（非法转换拒绝 / REFUNDED 终态） | ✅ 满足 | T08 |
| I6 鉴权隔离 / 受保护执行 | ⚠️ 部分 | T15/T17 通过；**T16 FD-08 review 无 owner 校验** |

## 关键发现

1. **FD-08（安全）**：`POST /after-sales/{id}/review` 仅当携带 `X-User-Role` 且非 reviewer/admin 时拒绝；**无角色头时直接放行**（可信内网语义残留）。导致普通用户可"自评自批"他人售后。R7 加了 `X-User-Role` 网关但漏了 owner 校验。R9 若能补上 owner 校验，此缺可闭环。
2. **创建端幂等缺失**：R2 将幂等实现在执行/退款端，未覆盖 canonical 的创建端 keyed 去重（T06）。功能上不导致超退，但偏离 benchmark 预期。
3. **第三方失败返回 502**：语义正确（Bad Gateway），但与 canonical `<500` 守卫不符——属 HTTP 契约偏差，非功能失败。
4. **金额用 `float`/`REAL` 存储**：已知限制（R5 已自报），小额场景可接受，未做整数分存储。

> 以上为 R0–R8 基线。R9 执行并 freeze 后将用同一套件复跑，更新最终判定。
