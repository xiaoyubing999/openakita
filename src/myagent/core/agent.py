"""
Agent 主类 - 协调所有模块

这是 MyAgent 的核心，负责:
- 接收用户输入
- 协调各个模块
- 执行工具调用
- 执行 Ralph 循环
- 管理对话和记忆
"""

import logging
import uuid
import json
from datetime import datetime
from typing import Any, Optional

from .brain import Brain, Context, Response
from .identity import Identity
from .ralph import RalphLoop, Task, TaskResult, TaskStatus

from ..config import settings
from ..tools.shell import ShellTool
from ..tools.file import FileTool
from ..tools.web import WebTool

logger = logging.getLogger(__name__)


class Agent:
    """
    MyAgent 主类
    
    一个全能自进化AI助手，基于 Ralph Wiggum 模式永不放弃。
    """
    
    # 工具定义 (Claude API tool use format)
    TOOLS = [
        {
            "name": "run_shell",
            "description": "执行Shell命令，用于运行系统命令、创建目录、执行脚本等",
            "input_schema": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的Shell命令"},
                    "cwd": {"type": "string", "description": "工作目录(可选)"}
                },
                "required": ["command"]
            }
        },
        {
            "name": "write_file",
            "description": "写入文件内容，可以创建新文件或覆盖已有文件",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "content": {"type": "string", "description": "文件内容"}
                },
                "required": ["path", "content"]
            }
        },
        {
            "name": "read_file",
            "description": "读取文件内容",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"}
                },
                "required": ["path"]
            }
        },
        {
            "name": "list_directory",
            "description": "列出目录内容",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "目录路径"}
                },
                "required": ["path"]
            }
        }
    ]
    
    def __init__(
        self,
        name: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.name = name or settings.agent_name
        
        # 初始化核心组件
        self.identity = Identity()
        self.brain = Brain(api_key=api_key)
        self.ralph = RalphLoop(
            max_iterations=settings.max_iterations,
            on_iteration=self._on_iteration,
            on_error=self._on_error,
        )
        
        # 初始化工具
        self.shell_tool = ShellTool()
        self.file_tool = FileTool()
        self.web_tool = WebTool()
        
        # 对话上下文
        self._context = Context()
        self._conversation_history: list[dict] = []
        
        # 状态
        self._initialized = False
        self._running = False
        
        logger.info(f"Agent '{self.name}' created")
    
    async def initialize(self) -> None:
        """初始化 Agent"""
        if self._initialized:
            return
        
        # 加载身份文档
        self.identity.load()
        
        # 设置系统提示词
        self._context.system = self.identity.get_system_prompt()
        
        # TODO: 加载记忆
        # TODO: 加载技能
        # TODO: 初始化工具
        
        self._initialized = True
        logger.info(f"Agent '{self.name}' initialized")
    
    async def chat(self, message: str) -> str:
        """
        对话接口
        
        Args:
            message: 用户消息
        
        Returns:
            Agent 响应
        """
        if not self._initialized:
            await self.initialize()
        
        logger.info(f"User: {message[:100]}...")
        
        # 添加到对话历史
        self._conversation_history.append({
            "role": "user",
            "content": message,
            "timestamp": datetime.now().isoformat(),
        })
        
        # 更新上下文
        self._context.messages.append({
            "role": "user",
            "content": message,
        })
        
        # 判断是否是简单对话还是需要执行任务
        if self._is_task_request(message):
            # 作为任务执行（Ralph 模式）
            result = await self.execute_task_from_message(message)
            response_text = self._format_task_result(result)
        else:
            # 简单对话
            response = await self.brain.think(
                message,
                context=self._context,
            )
            response_text = response.content
        
        # 添加响应到历史
        self._conversation_history.append({
            "role": "assistant",
            "content": response_text,
            "timestamp": datetime.now().isoformat(),
        })
        
        # 更新上下文
        self._context.messages.append({
            "role": "assistant",
            "content": response_text,
        })
        
        logger.info(f"Agent: {response_text[:100]}...")
        
        return response_text
    
    def _is_task_request(self, message: str) -> bool:
        """
        判断是否是需要执行工具的任务请求
        
        简单问答、代码解释、知识问题等不需要执行工具
        需要创建文件、运行命令等操作的才是任务
        """
        # 排除简单问答（问号结尾通常是问答）
        if message.strip().endswith("？") or message.strip().endswith("?"):
            return False
        
        # 排除短消息
        if len(message) < 15:
            return False
        
        # 任务关键词（需要执行文件/命令操作的）
        task_keywords = [
            "创建", "生成文件", "写入", "保存到",
            "在目录", "在文件夹", "mkdir", "touch",
            "运行", "执行", "启动", "部署",
            "下载", "安装", "pip install", "npm install",
            "删除", "移动", "复制", "重命名",
        ]
        
        # 检查是否匹配任务模式
        message_lower = message.lower()
        for kw in task_keywords:
            if kw in message or kw.lower() in message_lower:
                return True
        
        # 默认不是任务（简单对话）
        return False
    
    async def execute_task_from_message(self, message: str) -> TaskResult:
        """从消息创建并执行任务"""
        task = Task(
            id=str(uuid.uuid4())[:8],
            description=message,
            priority=1,
        )
        return await self.execute_task(task)
    
    async def _execute_tool(self, tool_name: str, tool_input: dict) -> str:
        """
        执行工具调用
        
        Args:
            tool_name: 工具名称
            tool_input: 工具输入参数
        
        Returns:
            工具执行结果
        """
        logger.info(f"Executing tool: {tool_name} with {tool_input}")
        
        try:
            if tool_name == "run_shell":
                result = await self.shell_tool.run(
                    tool_input["command"],
                    cwd=tool_input.get("cwd")
                )
                if result.success:
                    return f"命令执行成功:\n{result.stdout}"
                else:
                    return f"命令执行失败:\n{result.stderr}"
            
            elif tool_name == "write_file":
                await self.file_tool.write(
                    tool_input["path"],
                    tool_input["content"]
                )
                return f"文件已写入: {tool_input['path']}"
            
            elif tool_name == "read_file":
                content = await self.file_tool.read(tool_input["path"])
                return f"文件内容:\n{content}"
            
            elif tool_name == "list_directory":
                files = await self.file_tool.list_dir(tool_input["path"])
                return f"目录内容:\n" + "\n".join(files)
            
            else:
                return f"未知工具: {tool_name}"
                
        except Exception as e:
            return f"工具执行错误: {str(e)}"
    
    async def execute_task(self, task: Task) -> TaskResult:
        """
        执行任务（带工具调用）
        
        Args:
            task: 任务对象
        
        Returns:
            TaskResult
        """
        if not self._initialized:
            await self.initialize()
        
        logger.info(f"Executing task: {task.description[:100]}...")
        
        # 构建系统提示词
        system_prompt = self.identity.get_system_prompt() + """

你有以下工具可以使用来完成任务：
- run_shell: 执行Shell命令
- write_file: 写入文件
- read_file: 读取文件
- list_directory: 列出目录

请使用工具来实际执行任务，而不是只给出计划。每次只调用必要的工具，等待结果后再继续。"""

        messages = [{"role": "user", "content": task.description}]
        max_tool_iterations = 20
        iteration = 0
        final_response = ""
        
        while iteration < max_tool_iterations:
            iteration += 1
            logger.info(f"Task iteration {iteration}")
            
            # 调用 Brain
            response = self.brain.client.messages.create(
                model=self.brain.model,
                max_tokens=self.brain.max_tokens,
                system=system_prompt,
                tools=self.TOOLS,
                messages=messages,
            )
            
            # 处理响应
            tool_calls = []
            text_content = ""
            
            for block in response.content:
                if block.type == "text":
                    text_content += block.text
                elif block.type == "tool_use":
                    tool_calls.append({
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })
            
            # 如果有文本响应，保存
            if text_content:
                final_response = text_content
            
            # 如果没有工具调用，任务完成
            if not tool_calls:
                break
            
            # 执行工具调用
            assistant_content = []
            for block in response.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })
            
            messages.append({"role": "assistant", "content": assistant_content})
            
            # 执行每个工具并收集结果
            tool_results = []
            for tool_call in tool_calls:
                result = await self._execute_tool(tool_call["name"], tool_call["input"])
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_call["id"],
                    "content": result,
                })
                logger.info(f"Tool {tool_call['name']} result: {result[:100]}...")
            
            messages.append({"role": "user", "content": tool_results})
            
            # 检查是否应该停止
            if response.stop_reason == "end_turn":
                break
        
        task.mark_completed(final_response)
        
        return TaskResult(
            success=True,
            data=final_response,
            iterations=iteration,
        )
    
    def _format_task_result(self, result: TaskResult) -> str:
        """格式化任务结果"""
        if result.success:
            return f"""✅ 任务完成

{result.data}

---
迭代次数: {result.iterations}
耗时: {result.duration_seconds:.2f}秒"""
        else:
            return f"""❌ 任务未能完成

错误: {result.error}

---
尝试次数: {result.iterations}
耗时: {result.duration_seconds:.2f}秒

我会继续尝试其他方法..."""
    
    async def self_check(self) -> dict[str, Any]:
        """
        自检
        
        Returns:
            自检结果
        """
        logger.info("Running self-check...")
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "status": "healthy",
            "checks": {},
        }
        
        # 检查 Brain
        try:
            response = await self.brain.think("你好，这是一个测试。请回复'OK'。")
            results["checks"]["brain"] = {
                "status": "ok" if "OK" in response.content or "ok" in response.content.lower() else "warning",
                "message": "Brain is responsive",
            }
        except Exception as e:
            results["checks"]["brain"] = {
                "status": "error",
                "message": str(e),
            }
            results["status"] = "unhealthy"
        
        # 检查 Identity
        try:
            soul = self.identity.soul
            agent = self.identity.agent
            results["checks"]["identity"] = {
                "status": "ok" if soul and agent else "warning",
                "message": f"SOUL.md: {len(soul)} chars, AGENT.md: {len(agent)} chars",
            }
        except Exception as e:
            results["checks"]["identity"] = {
                "status": "error",
                "message": str(e),
            }
        
        # 检查配置
        results["checks"]["config"] = {
            "status": "ok" if settings.anthropic_api_key else "error",
            "message": "API key configured" if settings.anthropic_api_key else "API key missing",
        }
        
        # TODO: 添加更多检查
        # - 技能系统
        # - 工具系统
        # - 存储系统
        # - MCP 连接
        
        logger.info(f"Self-check complete: {results['status']}")
        
        return results
    
    def _on_iteration(self, iteration: int, task: Task) -> None:
        """Ralph 循环迭代回调"""
        logger.debug(f"Ralph iteration {iteration} for task {task.id}")
    
    def _on_error(self, error: str, task: Task) -> None:
        """Ralph 循环错误回调"""
        logger.warning(f"Ralph error for task {task.id}: {error[:100]}")
    
    @property
    def is_initialized(self) -> bool:
        """是否已初始化"""
        return self._initialized
    
    @property
    def conversation_history(self) -> list[dict]:
        """对话历史"""
        return self._conversation_history.copy()
