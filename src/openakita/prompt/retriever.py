"""
Prompt Retriever - 从 MEMORY.md 检索相关片段

复用现有的 MemoryManager 和 VectorStore 实现语义搜索。
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..memory import MemoryManager

logger = logging.getLogger(__name__)


def retrieve_memory(
    query: str,
    memory_manager: "MemoryManager",
    max_tokens: int = 400,
    max_items: int = 5,
    min_importance: float = 0.5,
) -> str:
    """
    从记忆系统检索与查询相关的片段
    
    复用 MemoryManager.get_injection_context() 的实现，
    但提供更精细的 token 控制。
    
    Args:
        query: 查询文本（通常是用户输入）
        memory_manager: MemoryManager 实例
        max_tokens: 最大 token 预算
        max_items: 最大返回条目数
        min_importance: 最小重要性阈值
    
    Returns:
        格式化的记忆上下文
    """
    if not query or not query.strip():
        return ""
    
    lines = []
    
    # 1. 加载 MEMORY.md 核心记忆（始终包含，但限制长度）
    core_memory = _get_core_memory(memory_manager, max_chars=max_tokens * 2)  # 2 chars/token
    if core_memory:
        lines.append("## 核心记忆\n")
        lines.append(core_memory)
    
    # 2. 向量搜索相关记忆
    related = _search_related_memories(
        query=query,
        memory_manager=memory_manager,
        max_items=max_items,
        min_importance=min_importance,
    )
    if related:
        lines.append("\n## 相关记忆（语义匹配）\n")
        lines.append(related)
    
    # 3. 应用 token 限制
    result = '\n'.join(lines)
    max_chars = max_tokens * 4  # 保守估计 4 chars/token
    
    if len(result) > max_chars:
        result = result[:max_chars]
        # 尝试在最后一个完整行处截断
        last_newline = result.rfind('\n')
        if last_newline > max_chars * 0.8:  # 保留至少 80%
            result = result[:last_newline]
        result += "\n...(记忆已截断)"
    
    return result


def _get_core_memory(memory_manager: "MemoryManager", max_chars: int = 800) -> str:
    """
    获取 MEMORY.md 核心记忆
    
    Args:
        memory_manager: MemoryManager 实例
        max_chars: 最大字符数
    
    Returns:
        核心记忆文本
    """
    memory_path = getattr(memory_manager, 'memory_md_path', None)
    if not memory_path or not memory_path.exists():
        return ""
    
    try:
        content = memory_path.read_text(encoding="utf-8").strip()
        if not content:
            return ""
        
        # 如果内容太长，优先保留最近的条目
        if len(content) > max_chars:
            lines = content.split('\n')
            result_lines = []
            current_len = 0
            
            # 从后往前添加（最近的条目在后面）
            for line in reversed(lines):
                if current_len + len(line) + 1 > max_chars:
                    break
                result_lines.insert(0, line)
                current_len += len(line) + 1
            
            return '\n'.join(result_lines)
        
        return content
    except Exception as e:
        logger.warning(f"Failed to read MEMORY.md: {e}")
        return ""


def _search_related_memories(
    query: str,
    memory_manager: "MemoryManager",
    max_items: int = 5,
    min_importance: float = 0.5,
) -> str:
    """
    向量搜索相关记忆
    
    Args:
        query: 查询文本
        memory_manager: MemoryManager 实例
        max_items: 最大返回条目数
        min_importance: 最小重要性阈值
    
    Returns:
        格式化的相关记忆
    """
    vector_store = getattr(memory_manager, 'vector_store', None)
    if not vector_store or not getattr(vector_store, 'enabled', False):
        return ""
    
    try:
        # 搜索相关记忆 ID
        results = vector_store.search(
            query=query,
            limit=max_items,
            min_importance=min_importance,
        )
        
        if not results:
            return ""
        
        # 获取完整记忆对象
        memories = getattr(memory_manager, '_memories', {})
        lines = []
        
        for memory_id, distance in results:
            memory = memories.get(memory_id)
            if memory:
                content = getattr(memory, 'content', str(memory))
                # 格式化输出
                lines.append(f"- {content}")
        
        return '\n'.join(lines)
    except Exception as e:
        logger.warning(f"Memory search failed: {e}")
        return ""


def retrieve_memory_simple(
    memory_md_path: Path,
    max_chars: int = 800,
) -> str:
    """
    简单的记忆检索（不使用向量搜索）
    
    直接读取 MEMORY.md 内容，适用于没有 MemoryManager 实例的场景。
    
    Args:
        memory_md_path: MEMORY.md 文件路径
        max_chars: 最大字符数
    
    Returns:
        记忆内容
    """
    if not memory_md_path.exists():
        return ""
    
    try:
        content = memory_md_path.read_text(encoding="utf-8").strip()
        if len(content) > max_chars:
            # 优先保留最近的条目
            lines = content.split('\n')
            result_lines = []
            current_len = 0
            
            for line in reversed(lines):
                if current_len + len(line) + 1 > max_chars:
                    break
                result_lines.insert(0, line)
                current_len += len(line) + 1
            
            return '\n'.join(result_lines)
        
        return content
    except Exception as e:
        logger.warning(f"Failed to read {memory_md_path}: {e}")
        return ""
