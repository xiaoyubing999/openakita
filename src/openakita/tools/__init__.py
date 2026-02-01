"""
OpenAkita 工具模块
"""

import sys

from .shell import ShellTool
from .file import FileTool
from .web import WebTool
from .mcp import MCPClient, mcp_client
from .mcp_catalog import MCPCatalog, scan_mcp_servers

__all__ = [
    "ShellTool",
    "FileTool",
    "WebTool",
    "MCPClient",
    "mcp_client",
    "MCPCatalog",
    "scan_mcp_servers",
]

# Windows 桌面自动化模块（仅 Windows 平台可用）
if sys.platform == "win32":
    try:
        from .desktop import (
            DesktopController,
            get_controller,
            ScreenCapture,
            MouseController,
            KeyboardController,
            UIAClient,
            VisionAnalyzer,
            DESKTOP_TOOLS,
            DesktopToolHandler,
            register_desktop_tools,
        )
        
        __all__.extend([
            "DesktopController",
            "get_controller",
            "ScreenCapture",
            "MouseController",
            "KeyboardController",
            "UIAClient",
            "VisionAnalyzer",
            "DESKTOP_TOOLS",
            "DesktopToolHandler",
            "register_desktop_tools",
        ])
    except ImportError as e:
        # 依赖未安装时的警告
        import logging
        logging.getLogger(__name__).debug(
            f"Desktop automation module not available: {e}. "
            "Install with: pip install mss pyautogui pywinauto"
        )
