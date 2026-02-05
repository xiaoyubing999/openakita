"""
OpenAkita - 全能自进化AI Agent

基于 Ralph Wiggum 模式，永不放弃。
"""

from importlib.metadata import version, PackageNotFoundError

try:
    # 从已安装的包获取版本（pip install 后可用）
    __version__ = version("openakita")
except PackageNotFoundError:
    # 开发模式：从 pyproject.toml 读取
    try:
        from pathlib import Path
        import tomllib
        
        pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
        if pyproject_path.exists():
            with open(pyproject_path, "rb") as f:
                pyproject = tomllib.load(f)
                __version__ = pyproject["project"]["version"]
        else:
            __version__ = "0.0.0-dev"
    except Exception:
        __version__ = "0.0.0-dev"

__author__ = "OpenAkita"
