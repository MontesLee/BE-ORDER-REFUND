# test — 测试用例说明与"如何适配被测模型产出"

本目录是四件套中的 **测试用例** 件。可执行测试套本体位于
`golden_answer/tests/`，本文件说明它测什么、怎么跑、以及**怎么把它接到被测模型
的产出上**。

> **这套测试产生的是哪一类证据？**
>
> | 被执行对象 | 产生的证据 | 存放位置 | 当前状态 |
> | --- | --- | --- | --- |
> | `golden_answer/`（参考实现） | **Golden Evidence**：参考答案满足要求 | `golden_answer/verify_doc/` · `round-evidence/` | **已完成**（22 passed） |
> | 某模型的最终产出 | **Model Evidence**：该模型满足 Rubric | `evaluation/<model>/`（`result.md` / `evidence.md`） | **尚未执行**（无任何模型结果） |
>
> 两者共用同一套断言，但结论**不可互相推导**：Golden 全绿 ≠ 任何模型通过。
> §4 的适配流程就是"把同一套断言接到模型产出上"的那一步。

---

## 1. 目录

```
golden_answer/
├── tests/
│   ├── conftest.py           fixture：内存内 TestClient + 双进程 uvicorn 集群
│   ├── harness.py            ★ 唯一的接口适配层（Api 类）
│   ├── test_order.py         R0 基线：可运行 + 主流程
│   ├── test_refund.py        T01 正常退款 · T02 未支付不可退
│   ├── test_amount.py        T03 部分退款 · T04 超额被拒（+ 单笔超额）
│   ├── test_idempotency.py   T06 重复提交 · T07 重复执行
│   ├── test_state_machine.py T08 非法流转 · T10 REFUNDED 终态
│   ├── test_failure_retry.py T05 失败不占额度 · T09 失败重试 · T11 第三方失败 · T12 事故回归
│   ├── test_concurrency.py   T13 同售后并发 · T14 多售后并发超额（2 个真实进程）
│   ├── test_security.py      T15 越权订单 · T16 越权售后 · T17 执行保护
│   └── test_performance.py   T18 索引命中 + 分页有界 + 延迟预算
└── verify_doc/
    ├── check_db_guards.py          存储级不变量探测（确定性）
    └── check_coverage_matrix.py    T01–T18 与 R8 分类覆盖探测
```

## 2. 运行

```bash
cd golden_answer
pip install -r requirements.txt
pytest tests -v
```

或走完整验证（含存储层与覆盖率探测）：`./verify.sh`。

---

## 3. 断言设计原则（决定了它为什么能区分强弱模型）

| 原则 | 说明 |
| --- | --- |
| **断言业务结果，不绑定机制** | 只校验"成功退款笔数 / 累计金额 / 售后终态"。重复执行返回 `200`（重放）或 `409`（拒绝）都接受，产生第二次退款才 FAIL。 |
| **并发必须跨进程** | `test_concurrency.py` 启动 **2 个真实 uvicorn 进程**共享同一 SQLite 文件。单进程测试会让 `threading.Lock` 通过，那是失效模式 #7。 |
| **竞态要主动复现，不能靠运气** | 网关延迟 0.15s 拉宽"认领 → 结算"窗口；攻击线程用 `threading.Barrier` 同步释放；同一场景重复 3 轮。 |
| **失败必须确定性** | 通过可替换网关注入成功/失败，不用随机 `sleep`、不依赖"偶现"。 |
| **拒绝宽松断言** | 不允许"只要不是 5xx 就算过"这类写法；每条断言都对应一条不变量。 |
| **不断言未要求的东西** | R0 不检查部分退款，R2 不检查多 worker——提前扣分是评分污染。 |

---

## 4. ★ 如何适配被测模型的产出

测试套只有**一个**适配点：`tests/harness.py` 里的 `Api` 类。
它把"统一契约"翻译成对被测服务的实际调用。

### 步骤

1. **启动被测服务**
   ```bash
   cd <模型产出目录>
   # 按它自己的 README 启动（依赖名、启动命令可能与本参考解不同）
   uvicorn <它的入口>:app --port 8000
   ```
2. **替换 `Api.client`**（二选一）
   - 起真实服务后：
     ```python
     import httpx
     from harness import Api
     api = Api(httpx.Client(trust_env=False, timeout=60), base_url="http://127.0.0.1:8000")
     ```
   - 或直接把它导出 的 ASGI app 交给 `TestClient`（与 `conftest.py` 的 `client` fixture 相同做法）。
3. **按它的接口改写 `Api` 的 11 个方法**：路径、请求体字段名、身份传递方式、分页参数名。
   例如模型用 `POST /api/v1/orders/{id}/refund-requests` 而不是
   `POST /orders/{id}/after-sales`，只需改 `create_after_sale` 里的 URL。
4. **按它的身份机制改写 `headers()`**。本参考解用 `X-User-Id`；模型可能用
   `?user_id=`、`Authorization: Bearer <id>` 或会话 cookie。若模型**完全没有身份概念**，
   `headers()` 返回空字典即可——那么 T15/T16/T17 会直接 FAIL，这正是应有的判定结果。
5. **重跑**：先跑 `test_order.py` 打通，再逐步放开。
6. **对无法适配的部分**在报告里写清"该点无法自动化，转人工"，不要改断言去迁就实现。

### 已经做过的适配独立性设计

- `Api` 同时兼容 `fastapi.testclient.TestClient`（相对路径）与 `httpx.Client`（绝对 URL）。
- 幂等键**同时**以 body 字段 `idempotency_key` 和请求头 `Idempotency-Key` 发送，
  两种设计任一都能命中。
- 越权响应码接受 `401/403/404`，不强制某一种（`404` 在人工评审中加分）。
- 未支付订单：`create_after_sale` 阶段拒绝或 `execute` 阶段拒绝都算通过，
  只要最终 `refunded_amount == 0`。
- 列表响应字段名固定为 `items` / `total`（见 `Api.list_*`）。若模型用别的字段名，
  在 `Api` 里转换即可，测试本体不动。

---

## 5. 环境注意事项（实测踩到的坑）

**必须让测试用的 HTTP 客户端绕过环境代理。** 若 shell 里存在
`HTTP_PROXY`（例如指向本机服务网关），客户端在**复用连接**时会把请求行写成
绝对形式（日志里会看到 `POST http%3A//127.0.0.1%3A8000/users HTTP/1.1`），
服务端会正确地判为未知路径并返回 404，看起来像"接口不存在"。
`conftest.py` 里所有客户端都设了 `trust_env=False`：

```python
def http_client(**kwargs):
    kwargs.setdefault("timeout", 60.0)
    return httpx.Client(trust_env=False, **kwargs)
```

给被测模型跑适配脚本时，请沿用这一设置。

其它要求：

- Windows 下 `pytest` 需要能找到 `harness`：`conftest.py` 已把 `tests/` 目录加入 `sys.path`。
- 并发用例会临时占用两个随机端口并启动两个子进程，需要允许本机回环监听。
- 存储层探测 `check_db_guards.py` 会新建临时数据库，不触碰项目数据。

---

## 6. Golden test 与 Rubric 的对应

| golden test | Rubric |
| --- | --- |
| T01 / T02 | FD-01 |
| T03 / T04 | FD-02 / FD-03 |
| T06 / T07 | FD-04 / FD-05 |
| T08 / T10 | FD-06 |
| T05 / T09 / T11 / T12 | FD-07 / AQ-04 / CU-02 / TE-02 |
| T13 / T14 | FD-05 / FD-03 / AQ-01 / AQ-02 / CU-01 |
| T15 / T16 / T17 | FD-08 |
| T18 | AQ-02（性能信号归入 D4，见 `rubric.md` §2） |

完整追溯见 `../evidence-matrix.md`。
