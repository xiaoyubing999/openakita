"""
MCP 桥接层

连接和调用已配置的 MCP 服务器。
支持读取 mcps/ 目录下的工具描述文件。
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class MCPToolInfo:
    """MCP 工具信息"""
    name: str
    description: str
    server: str
    parameters: dict = field(default_factory=dict)


@dataclass
class MCPServerInfo:
    """MCP 服务器信息"""
    name: str
    folder_path: str
    tools: list[MCPToolInfo] = field(default_factory=list)
    use_instructions: str = ""


@dataclass
class MCPCallResult:
    """MCP 调用结果"""
    success: bool
    data: Any = None
    error: Optional[str] = None


class MCPBridge:
    """
    MCP 桥接层
    
    用于发现和调用已配置的 MCP 服务器工具。
    MCP 服务器配置在 mcps/ 目录下。
    """
    
    def __init__(self, mcps_dir: Optional[Path] = None):
        self.mcps_dir = mcps_dir or Path.home() / ".cursor" / "projects" / "d-coder-myagent" / "mcps"
        self._servers: dict[str, MCPServerInfo] = {}
        self._tools: dict[str, MCPToolInfo] = {}
    
    def discover_servers(self) -> list[MCPServerInfo]:
        """
        发现所有 MCP 服务器
        
        Returns:
            服务器信息列表
        """
        servers = []
        
        if not self.mcps_dir.exists():
            logger.warning(f"MCP directory not found: {self.mcps_dir}")
            return servers
        
        for server_dir in self.mcps_dir.iterdir():
            if not server_dir.is_dir():
                continue
            
            server_name = server_dir.name
            
            # 读取服务器说明
            instructions = ""
            instruction_file = server_dir / "instructions.md"
            if instruction_file.exists():
                instructions = instruction_file.read_text(encoding="utf-8")
            
            # 读取工具列表
            tools = []
            tools_dir = server_dir / "tools"
            if tools_dir.exists():
                for tool_file in tools_dir.glob("*.json"):
                    try:
                        tool_data = json.loads(tool_file.read_text(encoding="utf-8"))
                        tools.append(MCPToolInfo(
                            name=tool_data.get("name", tool_file.stem),
                            description=tool_data.get("description", ""),
                            server=server_name,
                            parameters=tool_data.get("parameters", {}),
                        ))
                    except Exception as e:
                        logger.warning(f"Failed to load tool {tool_file}: {e}")
            
            server_info = MCPServerInfo(
                name=server_name,
                folder_path=str(server_dir),
                tools=tools,
                use_instructions=instructions,
            )
            
            servers.append(server_info)
            self._servers[server_name] = server_info
            
            # 索引工具
            for tool in tools:
                tool_key = f"{server_name}:{tool.name}"
                self._tools[tool_key] = tool
        
        logger.info(f"Discovered {len(servers)} MCP servers with {len(self._tools)} tools")
        return servers
    
    def list_servers(self) -> list[str]:
        """列出所有服务器"""
        if not self._servers:
            self.discover_servers()
        return list(self._servers.keys())
    
    def list_tools(self, server: Optional[str] = None) -> list[MCPToolInfo]:
        """
        列出工具
        
        Args:
            server: 服务器名称，为空则列出所有
        
        Returns:
            工具列表
        """
        if not self._servers:
            self.discover_servers()
        
        if server:
            if server in self._servers:
                return self._servers[server].tools
            return []
        
        return list(self._tools.values())
    
    def get_tool_schema(self, server: str, tool_name: str) -> Optional[dict]:
        """
        获取工具的参数 schema
        
        Args:
            server: 服务器名称
            tool_name: 工具名称
        
        Returns:
            参数 schema 或 None
        """
        tool_key = f"{server}:{tool_name}"
        tool = self._tools.get(tool_key)
        
        if tool:
            return tool.parameters
        
        # 尝试直接读取文件
        tool_file = self.mcps_dir / server / "tools" / f"{tool_name}.json"
        if tool_file.exists():
            try:
                data = json.loads(tool_file.read_text(encoding="utf-8"))
                return data.get("parameters", {})
            except Exception:
                pass
        
        return None
    
    async def call_tool(
        self,
        server: str,
        tool_name: str,
        arguments: dict,
    ) -> MCPCallResult:
        """
        调用 MCP 工具
        
        注意：这是一个模拟实现。实际的 MCP 调用需要通过 Cursor IDE 的
        CallMcpTool 功能来完成，因为 MCP 服务器运行在 IDE 环境中。
        
        Args:
            server: 服务器名称
            tool_name: 工具名称
            arguments: 参数
        
        Returns:
            MCPCallResult
        """
        logger.info(f"MCP call: {server}:{tool_name} with {arguments}")
        
        # 验证服务器和工具存在
        if server not in self._servers:
            return MCPCallResult(
                success=False,
                error=f"Server not found: {server}",
            )
        
        tool_key = f"{server}:{tool_name}"
        if tool_key not in self._tools:
            return MCPCallResult(
                success=False,
                error=f"Tool not found: {tool_name} in {server}",
            )
        
        # 实际调用需要通过 IDE 的 MCP 功能
        # 这里返回一个占位响应
        return MCPCallResult(
            success=True,
            data={
                "message": f"MCP tool {server}:{tool_name} called",
                "note": "实际调用需要通过 Cursor IDE 的 CallMcpTool 功能",
                "arguments": arguments,
            },
        )
    
    def get_server_info(self, server: str) -> Optional[MCPServerInfo]:
        """获取服务器信息"""
        if not self._servers:
            self.discover_servers()
        return self._servers.get(server)
    
    def search_tools(self, query: str) -> list[MCPToolInfo]:
        """
        搜索工具
        
        Args:
            query: 搜索词
        
        Returns:
            匹配的工具列表
        """
        if not self._tools:
            self.discover_servers()
        
        query_lower = query.lower()
        matches = []
        
        for tool in self._tools.values():
            if (
                query_lower in tool.name.lower() or
                query_lower in tool.description.lower()
            ):
                matches.append(tool)
        
        return matches


# 全局实例
mcp_bridge = MCPBridge()


def get_available_mcp_tools() -> list[dict]:
    """获取所有可用的 MCP 工具（用于 LLM 工具调用）"""
    tools = mcp_bridge.list_tools()
    
    return [
        {
            "name": f"mcp_{tool.server}_{tool.name}",
            "description": f"[MCP:{tool.server}] {tool.description}",
            "parameters": tool.parameters,
        }
        for tool in tools
    ]
