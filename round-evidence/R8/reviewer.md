## 本轮考点

不按测试文件数量评分，只看三件事：**覆盖、稳定、能验证不变量**。

## 人工评审要点

| 看什么 | 判定依据 |
| --- | --- |
| 覆盖 R8 列出的类别 | Business / State / Idempotency / Concurrency / Third-party / Security 六类是否都有 |
| 并发测试的断言对象 | 是否校验业务结果（成功笔数、累计金额），而不是"请求已并发发出" |
| 稳定性 | 是否依赖随机 sleep；重复运行是否稳定通过 |
| 断言强度 | 是否只断言 200 / 只测 happy path（失效模式 #11） |
| 是否有回归能力 | 把某个不变量改坏，测试是否真的会红 |

## Golden Answer 观察

- 22 个测试节点，`verify_doc/check_coverage_matrix.py` 逐个核对 T01–T18 与六类覆盖。
- 并发用例跨进程且断言数据；失败注入由可编程网关完成，不使用随机 sleep。
- 金额、幂等、状态、第三方、并发、安全六条不变量全部有自动化断言。

## 自动化证据

`test-result.txt` 中 R8-T01（全量套件）与 R8-T02（覆盖率探测）。

## 模型 Trace 留痕

> 本次交付仅评测一个模型：**Hy3（已完成 R0–R9）**。逐轮判定与证据见 `evaluation/HY3/evidence.md`，
> 汇总见 `evaluation/HY3/result.md`。占位名 `model_c` / `model_d` **不在本次交付范围**（未评测），故不列。
