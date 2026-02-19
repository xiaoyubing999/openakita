"""
UTF-8 编码强制模块 — 在所有入口点最早期导入

解决 Windows 上 sys.stdout/stderr 默认使用 GBK 编码，
导致中文、emoji 等 Unicode 字符输出乱码或崩溃的问题。

用法: 在每个入口模块的最顶部添加:
    import openakita._ensure_utf8  # noqa: F401
"""

import os
import sys


def ensure_utf8_stdio() -> None:
    """将 stdout/stderr 重新配置为 UTF-8 编码。

    仅在流对象支持 reconfigure 时生效（CPython 3.7+）。
    errors="replace" 确保遇到无法编码的字符时用替代符号而非崩溃。
    """
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


if sys.platform == "win32":
    ensure_utf8_stdio()

# 确保子进程也继承 UTF-8 编码设置
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
