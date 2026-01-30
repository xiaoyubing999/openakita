"""
MCP (Model Context Protocol) 客户端

遵循 MCP 规范 (modelcontextprotocol.io/specification/2025-11-25)
支持连接 MCP 服务器，调用工具、获取资源和提示词
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 尝试导入官方 MCP SDK
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    MCP_SDK_AVAILABLE = True
except ImportError:
    MCP_SDK_AVAILABLE = False
    logger.warning("MCP SDK not installed. Run: pip install mcp")


@dataclass
class MCPTool:
    """MCP 工具"""
    name: str
    description: str
    input_schema: dict = field(default_factory=dict)


@dataclass
class MCPResource:
    """MCP 资源"""
    uri: str
    name: str
    description: str = ""
    mime_type: str = ""


@dataclass
class MCPPrompt:
    """MCP 提示词"""
    name: str
    description: str
    arguments: list[dict] = field(default_factory=list)


@dataclass
class MCPServerConfig:
    """MCP 服务器配置"""
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    description: str = ""


@dataclass
class MCPCallResult:
    """MCP 调用结果"""
    success: bool
    data: Any = None
    error: Optional[str] = None


class MCPClient:
    """
    MCP 客户端
    
    连接 MCP 服务器并调用其功能
    """
    
    def __init__(self):
        self._servers: dict[str, MCPServerConfig] = {}
        self._connections: dict[str, Any] = {}  # 活跃连接
        self._tools: dict[str, MCPTool] = {}
        self._resources: dict[str, MCPResource] = {}
        self._prompts: dict[str, MCPPrompt] = {}
    
    def add_server(self, config: MCPServerConfig) -> None:
        """添加服务器配置"""
        self._servers[config.name] = config
        logger.info(f"Added MCP server config: {config.name}")
    
    def load_servers_from_config(self, config_path: Path) -> int:
        """
        从配置文件加载服务器
        
        配置文件格式 (JSON):
        {
            "mcpServers": {
                "server-name": {
                    "command": "python",
                    "args": ["-m", "my_server"],
                    "env": {}
                }
            }
        }
        """
        if not config_path.exists():
            logger.warning(f"MCP config not found: {config_path}")
            return 0
        
        try:
            data = json.loads(config_path.read_text(encoding='utf-8'))
            servers = data.get('mcpServers', {})
            
            for name, server_data in servers.items():
                config = MCPServerConfig(
                    name=name,
                    command=server_data.get('command', ''),
                    args=server_data.get('args', []),
                    env=server_data.get('env', {}),
                    description=server_data.get('description', ''),
                )
                self.add_server(config)
            
            logger.info(f"Loaded {len(servers)} MCP servers from {config_path}")
            return len(servers)
            
        except Exception as e:
            logger.error(f"Failed to load MCP config: {e}")
            return 0
    
    async def connect(self, server_name: str) -> bool:
        """
        连接到 MCP 服务器
        
        Args:
            server_name: 服务器名称
        
        Returns:
            是否成功
        """
        if not MCP_SDK_AVAILABLE:
            logger.error("MCP SDK not available")
            return False
        
        if server_name not in self._servers:
            logger.error(f"Server not found: {server_name}")
            return False
        
        if server_name in self._connections:
            logger.debug(f"Already connected to {server_name}")
            return True
        
        config = self._servers[server_name]
        
        try:
            # 创建 stdio 连接
            server_params = StdioServerParameters(
                command=config.command,
                args=config.args,
                env=config.env or None,
            )
            
            # 启动客户端
            async with stdio_client(server_params) as (read, write):
                client = Client(read, write)
                await client.initialize()
                
                # 获取可用功能
                tools_result = await client.list_tools()
                for tool in tools_result.tools:
                    self._tools[f"{server_name}:{tool.name}"] = MCPTool(
                        name=tool.name,
                        description=tool.description or "",
                        input_schema=tool.inputSchema or {},
                    )
                
                # 获取资源
                try:
                    resources_result = await client.list_resources()
                    for resource in resources_result.resources:
                        self._resources[f"{server_name}:{resource.uri}"] = MCPResource(
                            uri=resource.uri,
                            name=resource.name,
                            description=resource.description or "",
                            mime_type=resource.mimeType or "",
                        )
                except:
                    pass  # 资源是可选的
                
                # 获取提示词
                try:
                    prompts_result = await client.list_prompts()
                    for prompt in prompts_result.prompts:
                        self._prompts[f"{server_name}:{prompt.name}"] = MCPPrompt(
                            name=prompt.name,
                            description=prompt.description or "",
                            arguments=prompt.arguments or [],
                        )
                except:
                    pass  # 提示词是可选的
                
                self._connections[server_name] = client
                logger.info(f"Connected to MCP server: {server_name}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to connect to {server_name}: {e}")
            return False
    
    async def disconnect(self, server_name: str) -> None:
        """断开服务器连接"""
        if server_name in self._connections:
            del self._connections[server_name]
            # 清理该服务器的工具/资源/提示词
            self._tools = {k: v for k, v in self._tools.items() if not k.startswith(f"{server_name}:")}
            self._resources = {k: v for k, v in self._resources.items() if not k.startswith(f"{server_name}:")}
            self._prompts = {k: v for k, v in self._prompts.items() if not k.startswith(f"{server_name}:")}
            logger.info(f"Disconnected from MCP server: {server_name}")
    
    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict,
    ) -> MCPCallResult:
        """
        调用 MCP 工具
        
        Args:
            server_name: 服务器名称
            tool_name: 工具名称
            arguments: 参数
        
        Returns:
            MCPCallResult
        """
        if not MCP_SDK_AVAILABLE:
            return MCPCallResult(
                success=False,
                error="MCP SDK not available. Install with: pip install mcp",
            )
        
        if server_name not in self._connections:
            return MCPCallResult(
                success=False,
                error=f"Not connected to server: {server_name}",
            )
        
        tool_key = f"{server_name}:{tool_name}"
        if tool_key not in self._tools:
            return MCPCallResult(
                success=False,
                error=f"Tool not found: {tool_name}",
            )
        
        try:
            client = self._connections[server_name]
            result = await client.call_tool(tool_name, arguments)
            
            # 解析结果
            content = []
            for item in result.content:
                if hasattr(item, 'text'):
                    content.append(item.text)
                elif hasattr(item, 'data'):
                    content.append(item.data)
            
            return MCPCallResult(
                success=True,
                data=content[0] if len(content) == 1 else content,
            )
            
        except Exception as e:
            return MCPCallResult(
                success=False,
                error=str(e),
            )
    
    async def read_resource(
        self,
        server_name: str,
        uri: str,
    ) -> MCPCallResult:
        """
        读取 MCP 资源
        
        Args:
            server_name: 服务器名称
            uri: 资源 URI
        
        Returns:
            MCPCallResult
        """
        if not MCP_SDK_AVAILABLE:
            return MCPCallResult(success=False, error="MCP SDK not available")
        
        if server_name not in self._connections:
            return MCPCallResult(success=False, error=f"Not connected: {server_name}")
        
        try:
            client = self._connections[server_name]
            result = await client.read_resource(uri)
            
            content = []
            for item in result.contents:
                if hasattr(item, 'text'):
                    content.append(item.text)
                elif hasattr(item, 'blob'):
                    content.append(item.blob)
            
            return MCPCallResult(
                success=True,
                data=content[0] if len(content) == 1 else content,
            )
            
        except Exception as e:
            return MCPCallResult(success=False, error=str(e))
    
    async def get_prompt(
        self,
        server_name: str,
        prompt_name: str,
        arguments: dict = None,
    ) -> MCPCallResult:
        """
        获取 MCP 提示词
        
        Args:
            server_name: 服务器名称
            prompt_name: 提示词名称
            arguments: 参数
        
        Returns:
            MCPCallResult
        """
        if not MCP_SDK_AVAILABLE:
            return MCPCallResult(success=False, error="MCP SDK not available")
        
        if server_name not in self._connections:
            return MCPCallResult(success=False, error=f"Not connected: {server_name}")
        
        try:
            client = self._connections[server_name]
            result = await client.get_prompt(prompt_name, arguments or {})
            
            messages = []
            for msg in result.messages:
                messages.append({
                    "role": msg.role,
                    "content": msg.content.text if hasattr(msg.content, 'text') else str(msg.content),
                })
            
            return MCPCallResult(success=True, data=messages)
            
        except Exception as e:
            return MCPCallResult(success=False, error=str(e))
    
    def list_servers(self) -> list[str]:
        """列出所有配置的服务器"""
        return list(self._servers.keys())
    
    def list_connected(self) -> list[str]:
        """列出已连接的服务器"""
        return list(self._connections.keys())
    
    def list_tools(self, server_name: str = None) -> list[MCPTool]:
        """列出工具"""
        if server_name:
            prefix = f"{server_name}:"
            return [t for k, t in self._tools.items() if k.startswith(prefix)]
        return list(self._tools.values())
    
    def list_resources(self, server_name: str = None) -> list[MCPResource]:
        """列出资源"""
        if server_name:
            prefix = f"{server_name}:"
            return [r for k, r in self._resources.items() if k.startswith(prefix)]
        return list(self._resources.values())
    
    def list_prompts(self, server_name: str = None) -> list[MCPPrompt]:
        """列出提示词"""
        if server_name:
            prefix = f"{server_name}:"
            return [p for k, p in self._prompts.items() if k.startswith(prefix)]
        return list(self._prompts.values())
    
    def get_tool_schemas(self) -> list[dict]:
        """获取所有工具的 LLM 调用 schema"""
        schemas = []
        for key, tool in self._tools.items():
            server_name = key.split(":")[0]
            schemas.append({
                "name": f"mcp_{server_name}_{tool.name}".replace("-", "_"),
                "description": f"[MCP:{server_name}] {tool.description}",
                "input_schema": tool.input_schema,
            })
        return schemas


# 全局客户端
mcp_client = MCPClient()


# 便捷函数
async def connect_mcp_server(name: str) -> bool:
    """连接 MCP 服务器"""
    return await mcp_client.connect(name)


async def call_mcp_tool(server: str, tool: str, args: dict) -> MCPCallResult:
    """调用 MCP 工具"""
    return await mcp_client.call_tool(server, tool, args)


def get_mcp_tool_schemas() -> list[dict]:
    """获取 MCP 工具 schema"""
    return mcp_client.get_tool_schemas()
