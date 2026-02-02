"""
记忆系统处理器

处理记忆相关的系统技能：
- add_memory: 添加记忆
- search_memory: 搜索记忆
- get_memory_stats: 获取记忆统计
"""

import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.agent import Agent

logger = logging.getLogger(__name__)


class MemoryHandler:
    """
    记忆系统处理器
    
    处理所有记忆相关的工具调用
    """
    
    TOOLS = [
        "add_memory",
        "search_memory",
        "get_memory_stats",
    ]
    
    def __init__(self, agent: "Agent"):
        self.agent = agent
    
    async def handle(self, tool_name: str, params: dict[str, Any]) -> str:
        """处理工具调用"""
        if tool_name == "add_memory":
            return self._add_memory(params)
        elif tool_name == "search_memory":
            return self._search_memory(params)
        elif tool_name == "get_memory_stats":
            return self._get_memory_stats(params)
        else:
            return f"❌ Unknown memory tool: {tool_name}"
    
    def _add_memory(self, params: dict) -> str:
        """添加记忆"""
        from ...memory.types import Memory, MemoryType, MemoryPriority
        
        content = params["content"]
        mem_type_str = params["type"]
        importance = params.get("importance", 0.5)
        
        type_map = {
            "fact": MemoryType.FACT,
            "preference": MemoryType.PREFERENCE,
            "skill": MemoryType.SKILL,
            "error": MemoryType.ERROR,
            "rule": MemoryType.RULE,
        }
        mem_type = type_map.get(mem_type_str, MemoryType.FACT)
        
        if importance >= 0.8:
            priority = MemoryPriority.PERMANENT
        elif importance >= 0.6:
            priority = MemoryPriority.LONG_TERM
        else:
            priority = MemoryPriority.SHORT_TERM
        
        memory = Memory(
            type=mem_type,
            priority=priority,
            content=content,
            source="manual",
            importance_score=importance,
        )
        
        memory_id = self.agent.memory_manager.add_memory(memory)
        if memory_id:
            return f"✅ 已记住: [{mem_type_str}] {content}\nID: {memory_id}"
        else:
            return "✅ 记忆已存在（语义相似），无需重复记录。请继续执行其他任务或结束。"
    
    def _search_memory(self, params: dict) -> str:
        """搜索记忆"""
        from ...memory.types import MemoryType
        
        query = params["query"]
        type_filter = params.get("type")
        
        mem_type = None
        if type_filter:
            type_map = {
                "fact": MemoryType.FACT,
                "preference": MemoryType.PREFERENCE,
                "skill": MemoryType.SKILL,
                "error": MemoryType.ERROR,
                "rule": MemoryType.RULE,
            }
            mem_type = type_map.get(type_filter)
        
        memories = self.agent.memory_manager.search_memories(
            query=query,
            memory_type=mem_type,
            limit=10
        )
        
        if not memories:
            return f"未找到与 '{query}' 相关的记忆"
        
        output = f"找到 {len(memories)} 条相关记忆:\n\n"
        for m in memories:
            output += f"- [{m.type.value}] {m.content}\n"
            output += f"  (重要性: {m.importance_score:.1f}, 访问次数: {m.access_count})\n\n"
        
        return output
    
    def _get_memory_stats(self, params: dict) -> str:
        """获取记忆统计"""
        stats = self.agent.memory_manager.get_stats()
        
        output = f"""记忆系统统计:

- 总记忆数: {stats['total']}
- 今日会话: {stats['sessions_today']}
- 待处理会话: {stats['unprocessed_sessions']}

按类型:
"""
        for type_name, count in stats.get('by_type', {}).items():
            output += f"  - {type_name}: {count}\n"
        
        output += "\n按优先级:\n"
        for priority, count in stats.get('by_priority', {}).items():
            output += f"  - {priority}: {count}\n"
        
        return output


def create_handler(agent: "Agent"):
    """创建记忆处理器"""
    handler = MemoryHandler(agent)
    return handler.handle
