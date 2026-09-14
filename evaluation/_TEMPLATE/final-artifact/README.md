# final-artifact — <model>

> **模板。** 复制 `_TEMPLATE/` 为 `<model>/` 后使用。

本目录存放该模型**从 `init/` 出发、按 R0 → R9 逐轮演进后的最终工作区原件**。

规则：

- **原样保存**：源码、测试、README、依赖声明，不裁剪、不美化、不补写。
- 模型没写 README，就保留"没有 README"这个事实——它是评分依据，不是缺陷工单。
- 不要在这里替换成 Golden Answer 的文件，也不要把 Golden 的文件补进来。
- 测试执行请在**本目录内按它自己的 README 启动服务**，用
  `../../golden_answer/tests/` 的断言（只改 `harness.py` 适配，见 `../../../test/README.md` §4）。

```
<model>/final-artifact/
├── <模型自己的源码 / 测试 / README / requirements>
└── （无 .venv、无 __pycache__、无本地数据库残留）
```
