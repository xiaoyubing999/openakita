"""
MCP 处理器

处理 MCP 相关的系统技能：
- call_mcp_tool: 调用 MCP 工具
- list_mcp_servers: 列出服务器
- get_mcp_instructions: 获取使用说明
"""

import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.agent import Agent

logger = logging.getLogger(__name__)


class MCPHandler:
    """MCP 处理器"""
    
    TOOLS = [
        "call_mcp_tool",
        "list_mcp_servers",
        "get_mcp_instructions",
    ]
    
    def __init__(self, agent: "Agent"):
        self.agent = agent
    
    async def handle(self, tool_name: str, params: dict[str, Any]) -> str:
        """处理工具调用"""
        if tool_name == "call_mcp_tool":
            return await self._call_tool(params)
        elif tool_name == "list_mcp_servers":
            return self._list_servers(params)
        elif tool_name == "get_mcp_instructions":
            return self._get_instructions(params)
        else:
            return f"❌ Unknown MCP tool: {tool_name}"
    
    async def _call_tool(self, params: dict) -> str:
        """调用 MCP 工具"""
        server = params["server"]
        mcp_tool_name = params["tool_name"]
        arguments = params.get("arguments", {})
        
        # 检查服务器是否已连接
        if server not in self.agent.mcp_client.list_connected():
            connected = await self.agent.mcp_client.connect(server)
            if not connected:
                return f"❌ 无法连接到 MCP 服务器: {server}"
        
        result = await self.agent.mcp_client.call_tool(server, mcp_tool_name, arguments)
        
        if result.success:
            return f"✅ MCP 工具调用成功:\n{result.data}"
        else:
            return f"❌ MCP 工具调用失败: {result.error}"
    
    def _list_servers(self, params: dict) -> str:
        """列出 MCP 服务器"""
        servers = self.agent.mcp_catalog.list_servers()
        connected = self.agent.mcp_client.list_connected()
        
        if not servers:
            return "当前没有配置 MCP 服务器\n\n提示: MCP 服务器配置放在 mcps/ 目录下"
        
        output = f"已配置 {len(servers)} 个 MCP 服务器:\n\n"
        for server_id in servers:
            status = "🟢 已连接" if server_id in connected else "⚪ 未连接"
            output += f"- **{server_id}** {status}\n"
        
        output += "\n使用 `call_mcp_tool(server, tool_name, arguments)` 调用工具"
        return output
    
    def _get_instructions(self, params: dict) -> str:
        """获取 MCP 使用说明"""
        server = params["server"]
        instructions = self.agent.mcp_catalog.get_server_instructions(server)
        
        if instructions:
            return f"# MCP 服务器 {server} 使用说明\n\n{instructions}"
        else:
            return f"❌ 未找到服务器 {server} 的使用说明，或服务器不存在"


def create_handler(agent: "Agent"):
    """创建 MCP 处理器"""
    handler = MCPHandler(agent)
    return handler.handle
