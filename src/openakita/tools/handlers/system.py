"""
系统功能处理器

处理系统功能相关的系统技能：
- enable_thinking: 控制深度思考
- get_session_logs: 获取会话日志
- get_tool_info: 获取工具信息
"""

import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.agent import Agent

logger = logging.getLogger(__name__)


class SystemHandler:
    """系统功能处理器"""
    
    TOOLS = [
        "enable_thinking",
        "get_session_logs",
        "get_tool_info",
    ]
    
    def __init__(self, agent: "Agent"):
        self.agent = agent
    
    async def handle(self, tool_name: str, params: dict[str, Any]) -> str:
        """处理工具调用"""
        if tool_name == "enable_thinking":
            return self._enable_thinking(params)
        elif tool_name == "get_session_logs":
            return self._get_session_logs(params)
        elif tool_name == "get_tool_info":
            return self._get_tool_info(params)
        else:
            return f"❌ Unknown system tool: {tool_name}"
    
    def _enable_thinking(self, params: dict) -> str:
        """控制深度思考模式"""
        enabled = params["enabled"]
        reason = params.get("reason", "")
        
        self.agent.brain.set_thinking_mode(enabled)
        
        if enabled:
            logger.info(f"Thinking mode enabled by LLM: {reason}")
            return f"✅ 已启用深度思考模式。原因: {reason}\n后续回复将使用更强的推理能力。"
        else:
            logger.info(f"Thinking mode disabled by LLM: {reason}")
            return f"✅ 已关闭深度思考模式。原因: {reason}\n将使用快速响应模式。"
    
    def _get_session_logs(self, params: dict) -> str:
        """获取会话日志"""
        from ...logging import get_session_log_buffer
        
        count = params.get("count", 20)
        # level 参数改为 level_filter（修复参数名不匹配问题）
        level_filter = params.get("level_filter") or params.get("level")
        
        log_buffer = get_session_log_buffer()
        logs = log_buffer.get_logs(count=count, level_filter=level_filter)
        
        if not logs:
            return "没有会话日志"
        
        output = f"最近 {len(logs)} 条日志:\n\n"
        for log in logs:
            output += f"[{log['level']}] {log['module']}: {log['message']}\n"
        
        return output
    
    def _get_tool_info(self, params: dict) -> str:
        """获取工具信息"""
        tool_name_to_query = params["tool_name"]
        return self.agent.tool_catalog.get_tool_info_formatted(tool_name_to_query)


def create_handler(agent: "Agent"):
    """创建系统功能处理器"""
    handler = SystemHandler(agent)
    return handler.handle
