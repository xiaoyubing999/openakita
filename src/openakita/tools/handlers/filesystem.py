"""
文件系统处理器

处理文件系统相关的系统技能：
- run_shell: 执行 Shell 命令
- write_file: 写入文件
- read_file: 读取文件
- list_directory: 列出目录
"""

import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.agent import Agent

logger = logging.getLogger(__name__)


class FilesystemHandler:
    """
    文件系统处理器
    
    处理所有文件系统相关的工具调用
    """
    
    # 该处理器处理的工具
    TOOLS = [
        "run_shell",
        "write_file", 
        "read_file",
        "list_directory",
    ]
    
    def __init__(self, agent: "Agent"):
        """
        初始化处理器
        
        Args:
            agent: Agent 实例，用于访问 shell_tool 和 file_tool
        """
        self.agent = agent
    
    async def handle(self, tool_name: str, params: dict[str, Any]) -> str:
        """
        处理工具调用
        
        Args:
            tool_name: 工具名称
            params: 参数字典
        
        Returns:
            执行结果字符串
        """
        if tool_name == "run_shell":
            return await self._run_shell(params)
        elif tool_name == "write_file":
            return await self._write_file(params)
        elif tool_name == "read_file":
            return await self._read_file(params)
        elif tool_name == "list_directory":
            return await self._list_directory(params)
        else:
            return f"❌ Unknown filesystem tool: {tool_name}"
    
    async def _run_shell(self, params: dict) -> str:
        """执行 Shell 命令"""
        command = params["command"]
        timeout = params.get("timeout", 60)
        timeout = max(10, min(timeout, 600))
        
        result = await self.agent.shell_tool.run(
            command,
            cwd=params.get("cwd"),
            timeout=timeout,
        )
        
        # 记录到日志
        from ...logging import get_session_log_buffer
        log_buffer = get_session_log_buffer()
        
        if result.success:
            log_buffer.add_log(
                level="INFO",
                module="shell",
                message=f"$ {command}\n[exit: 0]\n{result.stdout}",
            )
            return f"命令执行成功 (exit code: 0):\n{result.stdout}"
        else:
            log_buffer.add_log(
                level="ERROR",
                module="shell",
                message=f"$ {command}\n[exit: {result.returncode}]\nstdout: {result.stdout}\nstderr: {result.stderr}",
            )
            
            output_parts = [f"命令执行失败 (exit code: {result.returncode})"]
            if result.stdout:
                output_parts.append(f"[stdout]:\n{result.stdout}")
            if result.stderr:
                output_parts.append(f"[stderr]:\n{result.stderr}")
            if not result.stdout and not result.stderr:
                output_parts.append("(无输出，可能命令不存在或语法错误)")
            output_parts.append("\n提示: 如果不确定原因，可以调用 get_session_logs 查看详细日志，或尝试其他命令。")
            return "\n".join(output_parts)
    
    async def _write_file(self, params: dict) -> str:
        """写入文件"""
        await self.agent.file_tool.write(
            params["path"],
            params["content"]
        )
        return f"文件已写入: {params['path']}"
    
    async def _read_file(self, params: dict) -> str:
        """读取文件"""
        content = await self.agent.file_tool.read(params["path"])
        return f"文件内容:\n{content}"
    
    async def _list_directory(self, params: dict) -> str:
        """列出目录"""
        files = await self.agent.file_tool.list_dir(params["path"])
        return f"目录内容:\n" + "\n".join(files)


def create_handler(agent: "Agent"):
    """
    创建文件系统处理器
    
    Args:
        agent: Agent 实例
    
    Returns:
        处理器的 handle 方法
    """
    handler = FilesystemHandler(agent)
    return handler.handle
