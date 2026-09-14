## 本轮考点

Review Comment 是否成立、根因定位是否准确、修复是否最小、有没有补 regression。
Review 描述的是**读状态与写状态之间的窗口**，所以"加个重试"或"加个 try/except"都不算解决。

## 人工评审要点

| 看什么 | 判定依据 |
| --- | --- |
| 是否承认 Comment 成立 | 若模型否认，要看它的论证是否真的站得住（本题参考解认定成立） |
| 根因表述 | 应指向 check-then-write / 缺失互斥 / 非原子条件更新 |
| 修复是否最小 | diff 应集中在认领与额度预留，而不是重写 service 层 |
| 是否补 regression | 必须有一个可单独执行、能复现该竞态的用例 |
| 是否跑测试 | 应给出运行结果，而不是"理论上已经修复" |

## Golden Answer 观察

- 根因：R3 之前的"读状态 → 判断 → 写状态"三步之间没有互斥，两个 worker 都能读到 `APPROVED`。
- 修复：把三步收进一个 `BEGIN IMMEDIATE` 事务，并把额度判断写成单条条件 `UPDATE`；
  状态写入用 `expect_status` 做 CAS，不再"读后盲写"。
- regression：`test_concurrency.py::test_concurrent_same_after_sale`
  用栅栏同步 + 跨进程 + 多轮重复，稳定复现该竞态。
- 修复未触碰 HTTP 层与数据模型——这就是"最小修复"的样子。

## 自动化证据

`test-result.txt` 中 R4-T01..T03。

## Rubric 判定提示

- `TE-01`（是否做了无关大规模重构）依赖模型的 diff 与 Trace，基线无法判定，
  故标记 `NOT_APPLICABLE`，须在实测中依据 diff 大小与改动范围填写。
- 如果模型只改测试不改实现、或把整个服务重写一遍，`TE-01` 判 FAIL。

## 模型 Trace 留痕（待实测填写）

| 模型 | 承认 Comment | 根因准确 | 修复最小 | 补 regression | 备注 |
| --- | --- | --- | --- | --- | --- |
| HY3 | 待填 | 待填 | 待填 | 待填 | 待填 |
| model_c | 待填 | 待填 | 待填 | 待填 | 待填 |
| model_d | 待填 | 待填 | 待填 | 待填 | 待填 |
