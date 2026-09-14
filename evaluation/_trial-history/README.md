# _trial-history —— 2026-09-14 真实 Model Trial 历史留痕

> **Historical / exploratory only. Not part of the formal model trial.**
> **本目录是历史存档，不是评测结论的权威位置。**
> 本次交付只评测一个模型：**Hy3（`hy3`）**，且已完成 R0–R9，结论在 `evaluation/HY3/`。
> 本目录保存那一次多模型 Trial 中断时点的真实过程留痕，供追溯与复核。

---

## 1. 交付范围（重要）

| 模型 | 状态 | 位置 |
| --- | --- | --- |
| **Hy3 (`hy3`)** | ✅ **已完成 R0–R9**（Final = 0.91） | `evaluation/HY3/` · `evaluation/comparison.md` |
| Kimi-K3 (`kimi-k3-1`)，占位名 `model_c` | ⛔ **不在本次交付范围**（未评测） | 本目录 `kimi-k3/`（仅 R0/R1 历史存档） |
| GLM-5.3 (`glm-5.3`)，占位名 `model_d` | ⛔ **不在本次交付范围**（未评测） | 本目录 `glm-5.3/`（仅 R0 历史存档） |

> Kimi-K3 / GLM-5.3 **未评测、无判定**。它们的部分留痕只作历史存档，
> 不构成任何评测结论，也不得被引用为模型表现。

---

## 2. 本目录包含什么

```
_trial-history/
├── README.md              本文件
├── TRIAL-RUN-LOG.md       完整时间线 / 配额事件 / 方法论发现（含「429 不代表未执行」）
├── state.json             机器可读历史状态（含各中间产物文件 sha256 前 16 位）
├── hy3/                   Hy3 的 R0/R1 早期留痕
│   ├── final-artifact-so-far/   R1 结束时的真实工作区快照
│   ├── trace/R0.md              模型亲笔留痕
│   └── self-test-verified.txt   评测方复跑该模型自带测试的真实输出
├── kimi-k3/               ⚠️ 不在交付范围：仅 R0/R1 留痕（历史存档）
└── glm-5.3/               ⚠️ 不在交付范围：仅 R0 留痕（历史存档）
```

---

## 3. 边界声明

**Historical / exploratory only. Not part of the formal model trial.**

- **不含**任何伪造的模型名称、trace ID、模型输出或 PASS/FAIL。
- 目录内使用 `final-artifact-so-far/` 命名，明确区别于完成态的 `final-artifact/`
  —— 这里保存的是 Trial 中断时的**中间快照**。
- **Hy3 的完成态产物不在本目录**，而在 `evaluation/HY3/final-artifact/`。
- **不含** Golden Answer 的任何内容，也未把 Golden 的结果写成模型结果。

---

## 4. 为什么保留（两条仍有价值的方法论）

该次运行发现并固化了两条对后续任何模型评测都适用的规则：

1. **`429` 不代表未执行** —— 平台返回配额错误时，调用可能已经在后台落地。
   重试前必须先用工作区文件特征核验该轮是否已执行，否则同一轮会被重复施加、污染 Trial。
   （详见 `TRIAL-RUN-LOG.md` §8「恢复协议」。）
2. **模型身份必须与账号级可用清单交叉验证** —— `model=` 参数不做校验，子 Agent
   自报的模型名可能并不在账号清单内（曾发现 `deepseek-v4-flash` 回显成立但账号无此模型）。
   仅凭自报身份使用，即为一次真实的伪造事故。

---

## 5. 完成态的权威位置

| 内容 | 路径 |
| --- | --- |
| 评测方逐轮留痕 | `evaluation/HY3/trace.md` |
| 模型级结论（22 Rubric 计分卡） | `evaluation/HY3/result.md` |
| 逐条证据映射 | `evaluation/HY3/evidence.md` |
| 冻结的最终产物 | `evaluation/HY3/final-artifact/` |
| Golden 适配测试层 | `evaluation/HY3/harness_test/` |
| 单模型汇总 | `evaluation/comparison.md` |
