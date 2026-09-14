"""项目根 conftest：确保项目根目录（hy3）始终在 sys.path 中。

这样无论 pytest 从哪个工作目录启动（例如 `python -m pytest tests` 或
`python -m pytest /abs/path/tests`），`from app import app` / `from store import store`
都能正确解析，保证「clean environment 直接可运行」。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
