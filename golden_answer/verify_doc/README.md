# verify_doc — 参考解的验证留痕

本目录存放 **golden answer 的可执行验证材料**，而不是设计说明。
所有 `*-check.txt` 都是真实运行输出，可用对应命令复现。

| 文件 | 内容 | 复现命令 |
| --- | --- | --- |
| `README.md` | 本文件：验证口径与已知限制 | — |
| `test-result.txt` | 干净 venv 中 `verify.sh` 的完整原始输出（含 22 个测试 + 存储级保护探测 + 覆盖率探测） | `./verify.sh` |
| `db-guard-check.txt` | 数据库级不变量保护探测输出（6 项） | `python verify_doc/check_db_guards.py` |
| `coverage-matrix-check.txt` | golden test T01–T18 与 R8 分类覆盖探测输出 | `python verify_doc/check_coverage_matrix.py` |

## 1. 三层证据

单靠"测试全绿"不足以说明参考解真的守住了不变量，因此验证分三层：

1. **业务层（`tests/`）** — 从 HTTP 接口观察业务结果：成功退款笔数、累计金额、售后终态。
   断言可观测结果，不绑定具体实现机制。
2. **跨进程层（`tests/test_concurrency.py`）** — 2 个真实 uvicorn 进程共享同一 SQLite 文件，
   网关延迟 0.15s 刻意拉宽"认领 → 结算"窗口，让竞态被复现而不是靠运气。
3. **存储层（`check_db_guards.py`）** — 直接对数据库发非法的写请求，确认
   **数据库自己**会拒绝：第二条 `REFUNDED` 撞部分唯一索引；超额写入撞 `CHECK`；
   第二个 `BEGIN IMMEDIATE` 写者被写锁挡住。

第 3 层存在的理由：竞态本质是时序事件，某台机器上坏实现可能侥幸通过。
存储层探测把"侥幸"去掉——只要约束还在，非法写入必然失败。

## 2. `test-result.txt` 是怎么产生的

```bash
cd golden_answer
./verify.sh
```

脚本会新建 `.venv`、安装 `requirements.txt`、指向一次性数据库、跑完整套件，
最后把 pytest 的退出码透传出来。`test-result.txt` 中的路径带着 `.venv/`，
说明它确实来自干净环境而不是复用已有解释器。（仓库交付时不保留 `.venv`，
重跑 `verify.sh` 会重建。）

## 3. 与题目 Rubric 的对应

| 证据 | 支撑的 Rubric |
| --- | --- |
| `tests/` 全部通过 | IF-01 / IF-03 / FD-01…FD-08 / CU-01 / TE-02 |
| `test_concurrency.py` 通过 | AQ-01 / AQ-02 / FD-05 |
| `db-guard-check.txt` | AQ-01 / AQ-02 |
| `coverage-matrix-check.txt` | IF-03 / TE-02 |
| `README.md` §4 §7 | AQ-05（方案、替代方案、限制） |
| `README.md` §5 与 `app/` 实际实现一致 | CU-03 |

完整的 Rubric → Evidence 追溯见 `../evidence-matrix.md`。

## 4. 已知限制（不隐瞒）

1. **没有真实模型 Trace。** 本包只提供 Golden Answer 证据。`IF-02`（增量演进）
   与 `TE-01`（是否做最小修改）依赖模型多轮过程，因此在基线里是
   `NOT_APPLICABLE`，必须由实测 Trace 填写。按试标规则要求，**不伪造 Trace**。
2. **跨进程竞态存在理论不确定性。** T13/T14 用栅栏同步 + 多轮 + 网关延迟把窗口拉宽，
   但它终究是时序测试；`check_db_guards.py` 提供的确定性证据才是"保护机制真的存在"
   的硬证据。两者互补，不可互相替代。
3. **T13 在部分坏实现上可能侥幸通过。** 已实测：移除写锁与全部数据库约束的变异体
   被 T14 稳定杀死，T13 在同机环境下未复现。因此 AQ-01/AQ-02 的判定不单独依赖 T13。
4. **代理环境注意。** 测试套所有 HTTP 客户端都设 `trust_env=False`：回环流量不应走
   环境里的 `HTTP_PROXY`，否则复用连接会以绝对形式请求行发出并被判为未知路径
   （本机验证时确实踩到，已修）。
