"""
MyAgent 记忆系统

实现三层记忆架构:
1. 短期记忆 (Short-term): 当前会话上下文
2. 工作记忆 (Working): MEMORY.md 中的任务进度
3. 长期记忆 (Long-term): 持久化的经验和模式

记忆策略:
- 实时提取: 任务完成时自动提取关键信息
- 批量整理: 空闲时段自动整理对话历史
- 按需注入: 根据任务相关性注入记忆
"""

from .manager import MemoryManager
from .extractor import MemoryExtractor
from .consolidator import MemoryConsolidator
from .types import (
    Memory,
    MemoryType,
    MemoryPriority,
    ConversationTurn,
    SessionSummary,
)

__all__ = [
    "MemoryManager",
    "MemoryExtractor", 
    "MemoryConsolidator",
    "Memory",
    "MemoryType",
    "MemoryPriority",
    "ConversationTurn",
    "SessionSummary",
]
