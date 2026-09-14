"""tests/conftest：把项目根目录（hy3）加入 sys.path。

无论 pytest 从哪个工作目录启动（例如 `python -m pytest tests` 从项目根，
或 `python -m pytest /abs/hy3/tests` 从任意目录），都能让 `from app import app`
正确解析，保证 clean environment 直接可运行。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
