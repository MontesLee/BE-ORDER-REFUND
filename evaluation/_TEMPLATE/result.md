# result — <model>

> **模板。** 复制 `_TEMPLATE/` 为 `<model>/` 后填写；**未发生真实 Trial 前不得填写本文件**。
> 缺项写「未采集」，不得留空、不得编造。

## 1. 模型与环境

| 字段 | 值 |
| --- | --- |
| model name | `<HY3 / model_c / model_d …>` |
| model version | `<未采集>` |
| environment | `<OS / Python 版本 / 依赖安装方式>` |
| 被测日期 | `<YYYY-MM-DD>` |
| 起始工作区 | `init/`（关闭记忆、最高思考等级） |
| rounds completed | `<R0…R9 中实际完成的轮次；未完成写清断在哪一轮>` |

## 2. final test result

```
命令：cd <model>/final-artifact && pytest tests -rA      （按 test/README.md §4 完成接口适配）
结果：<N passed / N failed / N error>
```

> 沿用 `golden_answer/tests/` 的断言，**只改 `harness.py` 适配接口**；不得为了让结果变绿而删改断言。
> 无法适配的测试点要写明「该点无法自动化，转人工」。

## 3. rubric result

| 维度（权重） | 适用条数 | PASS | FAIL | NA | 维度得分 |
| --- | --- | --- | --- | --- | --- |
| D1 Instruction Following (15%) | | | | | |
| D2 Feature Delivery (35%) | | | | | |
| D3 Task Efficiency (15%) | | | | | |
| D4 Architecture Quality (20%) | | | | | |
| D5 Context Understanding (15%) | | | | | |
| **Final** | | | | | |

> 计分公式见 `rubric.md` §3；`NOT_APPLICABLE` 不入分母。

## 4. key failures

| # | 失败点 | 落在哪条不变量 / 哪个决策 | 证据 | 是否可复现 |
| --- | --- | --- | --- | --- |
| 1 | | | | |

## 5. human review result

| 人工评审项 | 结论 | 锚定的证据（CODE / DOC / REVIEW） |
| --- | --- | --- |
| 技术取舍说明（方案 / 替代方案 / 原因 / 边界） | | |
| 解释与真实代码是否一致（CU-03） | | |
| 是否过度设计（TE-03） | | |
| 是否为最小修改（TE-01） | | |
| 是否增量演进、无大规模重写（IF-02） | | |

## 6. 一句话结论

`<该模型在本题的强项与短板，以及它在哪一条不变量上与其它模型分层>`
