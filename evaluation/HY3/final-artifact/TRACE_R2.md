# TRACE_R2 — 退款幂等性（重复提交 / 网络超时）

## 本轮目标（ROUND PROMPT）

针对客户端重复提交与网络超时，保证：
1. 重复提交不会产生多个有效退款；
2. 同一个 AfterSale 最多只能有一个成功退款；
3. 幂等机制不能破坏累计退款金额限制。

实现方式由我自行选择，不限定具体技术方案。

## 文件改动清单

### `store.py`（修改）
- 新增 `IdempotencyRecord` 数据类（持有 `status_code` 与 `body`）。
- `Store` 新增 `idempotency: Dict[str, IdempotencyRecord]` 字段；`reset()` 一并清空该缓存，保证测试隔离。
- 去重读取/写入均在已有的 `store.lock` 内进行（见 app.py）。

### `app.py`（修改）
- 导入 `Header` 与 `IdempotencyRecord`。
- 原 `refund_after_sale` 拆分为：
  - 路由函数 `refund_after_sale(after_sale_id, req, idempotency_key: Header(None, alias="Idempotency-Key"))`：调用核心逻辑，按状态码抛 `HTTPException` 或返回 `AfterSale`。
  - 核心函数 `_refund_core(...)`：在 `with store.lock:` 内**原子**完成「幂等键去重 → 资源校验 → 计算金额 → 累计限额校验 → 落地」，返回 `(status_code, body_dict)`。
- 幂等逻辑三处：
  1. **幂等键去重**：若 `idempotency_key` 已缓存且为成功结果，直接返回缓存（200 + body），不重做。
  2. **资源级幂等**：`after_sale.status == REFUNDED` 时，直接返回既有 `model_dump(mode="json")` 结果（200），**不再累加** `order.refunded_amount`。
  3. 仅在成功（200）时把结果写入 `store.idempotency[idempotency_key]`；失败（404/409/400）不缓存，允许用同一键重试。

### `tests/test_api.py`（修改 / 新增）
新增 5 个用例（共 24 个，全部通过）：
- `test_refund_same_after_sale_only_one_successful_refund`：同一 AfterSale 退款两次，仅一次有效（累计=100）。
- `test_idempotency_key_dedupes_duplicate_request`：同一 `Idempotency-Key` 重放，响应体完全一致，只退一次。
- `test_idempotency_key_does_not_double_when_key_reused_after_success`：换不同幂等键针对同一 AfterSale，资源守卫仍保证只退一次。
- `test_idempotency_key_not_cached_on_failure`：未审核导致 409 不缓存幂等键，审核后用同一键重试可成功。
- `test_idempotent_refund_keeps_cumulative_limit`：对已退款售后反复重放超大金额，累计不被污染（仍为 80），且后续超额请求仍被 409 拦截。

### `README.md`（修改）
新增「幂等性（应对重复提交 / 网络超时）」小节，并在 API 表中标注 `Idempotency-Key` 头支持。

## 关键设计决策
- **双重幂等**：既提供标准 `Idempotency-Key` 头（应对网络超时重放），又提供资源级守卫（同一 AfterSale 仅退一次），两层互相兜底，满足要求 1 与 2。
- **仅缓存成功结果**：失败不缓存，避免把客户端「卡死」在一次永久性错误里，符合常见幂等实践，也由 `test_idempotency_key_not_cached_on_failure` 覆盖。
- **原子性**：幂等键检查与退款落地都在 `store.lock` 内完成，避免并发下「两个请求同时通过键检查」导致的双退；单线程 TestClient 下也保证行为正确。
- **不破坏累计限额**：任何去重分支都直接返回既有结果、不触碰 `order.refunded_amount`，从机制上保证要求 3。

## 问题与修复
- 初次担心 pydantic 版本：`model_dump(mode="json")` 与 `AfterSale(**body)` 往返。确认环境为 pydantic 2.13.5 / FastAPI 0.141.1，上述用法成立；19 个旧用例 + 5 个新用例全部通过。
- PowerShell 在本环境无法直接回显 stdout，改用「命令结果写入文件 → Read 读取」的方式核对输出；未影响实现。

## 已知限制 / 不确定点
- 幂等缓存为**进程内存**，重启即清空（与既有内存存储一致，README 已注明生产应换 Redis 等带 TTL 的持久化存储）。
- 幂等键**不做请求体一致性校验**：相同键 + 不同 body 不会返回 409，而是直接返回首次成功结果。本需求聚焦「不重复退款」，此简化可接受；若需更严格的键-body 绑定可后续补充。
- 仅在 refund 接口实现幂等；其余接口（支付等）沿用既有状态机约束（如支付幂等已通过 `status != CREATED` 拦截）。
