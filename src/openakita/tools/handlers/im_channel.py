"""
IM 通道处理器

处理 IM 通道相关的系统技能：
- send_to_chat: 发送消息
- get_voice_file: 获取语音文件
- get_image_file: 获取图片文件
- get_chat_history: 获取聊天历史
"""

import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.agent import Agent

logger = logging.getLogger(__name__)


class IMChannelHandler:
    """IM 通道处理器"""
    
    TOOLS = [
        "send_to_chat",
        "get_voice_file",
        "get_image_file",
        "get_chat_history",
    ]
    
    def __init__(self, agent: "Agent"):
        self.agent = agent
    
    async def handle(self, tool_name: str, params: dict[str, Any]) -> str:
        """处理工具调用"""
        from ...core.agent import Agent
        
        if not Agent._current_im_session:
            return "❌ 当前不在 IM 会话中，无法使用此工具"
        
        if tool_name == "send_to_chat":
            return await self._send_to_chat(params)
        elif tool_name == "get_voice_file":
            return self._get_voice_file(params)
        elif tool_name == "get_image_file":
            return self._get_image_file(params)
        elif tool_name == "get_chat_history":
            return await self._get_chat_history(params)
        else:
            return f"❌ Unknown IM channel tool: {tool_name}"
    
    async def _send_to_chat(self, params: dict) -> str:
        """发送消息到聊天"""
        from ...core.agent import Agent
        
        session = Agent._current_im_session
        text = params.get("text")
        file_path = params.get("file_path")
        voice_path = params.get("voice_path")
        caption = params.get("caption")
        
        try:
            if file_path:
                await session.send_file(file_path, caption=caption)
                return f"✅ 已发送文件: {file_path}"
            elif voice_path:
                await session.send_voice(voice_path)
                return f"✅ 已发送语音: {voice_path}"
            elif text:
                await session.send_text(text)
                return f"✅ 已发送消息"
            else:
                return "❌ 请指定 text、file_path 或 voice_path"
        except Exception as e:
            return f"❌ 发送失败: {e}"
    
    def _get_voice_file(self, params: dict) -> str:
        """获取语音文件路径"""
        from ...core.agent import Agent
        
        session = Agent._current_im_session
        if hasattr(session, 'voice_file_path') and session.voice_file_path:
            return f"语音文件路径: {session.voice_file_path}"
        else:
            return "❌ 当前消息没有语音文件"
    
    def _get_image_file(self, params: dict) -> str:
        """获取图片文件路径"""
        from ...core.agent import Agent
        
        session = Agent._current_im_session
        if hasattr(session, 'image_file_path') and session.image_file_path:
            return f"图片文件路径: {session.image_file_path}"
        else:
            return "❌ 当前消息没有图片文件"
    
    async def _get_chat_history(self, params: dict) -> str:
        """获取聊天历史"""
        from ...core.agent import Agent
        
        session = Agent._current_im_session
        limit = params.get("limit", 20)
        include_system = params.get("include_system", True)
        
        if hasattr(session, 'get_history'):
            history = await session.get_history(limit=limit, include_system=include_system)
            
            if not history:
                return "没有聊天历史"
            
            output = f"最近 {len(history)} 条消息:\n\n"
            for msg in history:
                sender = msg.get('sender', 'unknown')
                text = msg.get('text', '')
                output += f"[{sender}] {text}\n"
            
            return output
        else:
            return "❌ 当前通道不支持获取聊天历史"


def create_handler(agent: "Agent"):
    """创建 IM 通道处理器"""
    handler = IMChannelHandler(agent)
    return handler.handle
