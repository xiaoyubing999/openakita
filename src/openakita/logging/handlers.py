"""
自定义日志处理器

功能:
- ErrorOnlyHandler: 只记录 ERROR/CRITICAL 级别日志
- ColoredConsoleHandler: 彩色控制台输出
- SessionLogHandler: 会话级日志缓存，供 AI 查询
"""

import logging
import sys
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from typing import TextIO, Optional

from .session_buffer import get_session_log_buffer


class ErrorOnlyHandler(TimedRotatingFileHandler):
    """
    只记录 ERROR 和 CRITICAL 级别日志的处理器
    
    继承 TimedRotatingFileHandler，按天轮转
    """
    
    def emit(self, record: logging.LogRecord) -> None:
        """只处理 ERROR 及以上级别"""
        if record.levelno >= logging.ERROR:
            super().emit(record)


class ColoredConsoleHandler(logging.StreamHandler):
    """
    彩色控制台日志处理器
    
    不同级别使用不同颜色:
    - DEBUG: 灰色
    - INFO: 默认
    - WARNING: 黄色
    - ERROR: 红色
    - CRITICAL: 红色加粗
    """
    
    # ANSI 颜色码
    COLORS = {
        logging.DEBUG: "\033[90m",      # 灰色
        logging.INFO: "\033[0m",        # 默认
        logging.WARNING: "\033[93m",    # 黄色
        logging.ERROR: "\033[91m",      # 红色
        logging.CRITICAL: "\033[91;1m", # 红色加粗
    }
    RESET = "\033[0m"
    
    def __init__(self, stream: TextIO = None):
        super().__init__(stream or sys.stdout)
        # 检测是否支持颜色（Windows 需要特殊处理）
        self._supports_color = self._check_color_support()
    
    def _check_color_support(self) -> bool:
        """检测终端是否支持颜色"""
        # 如果是 Windows，尝试启用 ANSI 支持
        if sys.platform == "win32":
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                # 启用虚拟终端处理
                kernel32.SetConsoleMode(
                    kernel32.GetStdHandle(-11),  # STD_OUTPUT_HANDLE
                    7  # ENABLE_PROCESSED_OUTPUT | ENABLE_WRAP_AT_EOL_OUTPUT | ENABLE_VIRTUAL_TERMINAL_PROCESSING
                )
                return True
            except Exception:
                return False
        
        # Unix/Linux/Mac 默认支持
        return hasattr(self.stream, "isatty") and self.stream.isatty()
    
    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录，添加颜色"""
        message = super().format(record)
        
        if self._supports_color:
            color = self.COLORS.get(record.levelno, self.RESET)
            return f"{color}{message}{self.RESET}"
        
        return message


class SessionLogHandler(logging.Handler):
    """
    会话日志处理器
    
    将日志记录到内存缓存中，按 session_id 分组，供 AI 查询当前会话的日志。
    
    使用方式:
    1. 在日志时通过 extra 传入 session_id:
       logger.info("message", extra={"session_id": "telegram_123_..."})
    
    2. 或者预先设置当前 session:
       get_session_log_buffer().set_current_session(session_id)
       logger.info("message")  # 自动关联到当前 session
    """
    
    def __init__(self, level: int = logging.DEBUG):
        """
        初始化会话日志处理器
        
        Args:
            level: 最低日志级别（默认 DEBUG，记录所有级别）
        """
        super().__init__(level)
        self._buffer = get_session_log_buffer()
    
    def emit(self, record: logging.LogRecord) -> None:
        """
        处理日志记录
        
        Args:
            record: 日志记录对象
        """
        try:
            # 尝试从 extra 获取 session_id
            session_id = getattr(record, "session_id", None)
            
            # 格式化消息
            message = self.format(record) if self.formatter else record.getMessage()
            
            # 添加到缓存
            self._buffer.add_log(
                level=record.levelname,
                module=record.name,
                message=message,
                session_id=session_id,
                timestamp=datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            )
        except Exception:
            # 日志处理器不应该抛出异常
            self.handleError(record)
