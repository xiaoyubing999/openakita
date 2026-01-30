"""
Brain 模块 - 与 Claude API 交互

负责:
- 发送请求到 Claude API
- 管理对话历史
- 工具调用
"""

import logging
from typing import Any, Optional
from dataclasses import dataclass, field

from anthropic import Anthropic
from anthropic.types import Message, MessageParam, ToolParam

from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class Response:
    """LLM 响应"""
    content: str
    tool_calls: list[dict] = field(default_factory=list)
    stop_reason: str = ""
    usage: dict = field(default_factory=dict)


@dataclass
class Context:
    """对话上下文"""
    messages: list[MessageParam] = field(default_factory=list)
    system: str = ""
    tools: list[ToolParam] = field(default_factory=list)


class Brain:
    """Agent 大脑 - LLM 交互层"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ):
        self.api_key = api_key or settings.anthropic_api_key
        self.base_url = base_url or settings.anthropic_base_url
        self.model = model or settings.default_model
        self.max_tokens = max_tokens or settings.max_tokens
        
        if not self.api_key:
            raise ValueError(
                "Anthropic API key is required. "
                "Set ANTHROPIC_API_KEY environment variable or pass api_key parameter."
            )
        
        # 支持自定义 base_url（云雾AI等转发服务）
        self.client = Anthropic(
            api_key=self.api_key,
            base_url=self.base_url,
        )
        logger.info(f"Brain initialized with model: {self.model}, base_url: {self.base_url}")
    
    async def think(
        self,
        prompt: str,
        context: Optional[Context] = None,
        system: Optional[str] = None,
        tools: Optional[list[ToolParam]] = None,
    ) -> Response:
        """
        发送思考请求到 LLM
        
        Args:
            prompt: 用户输入
            context: 对话上下文
            system: 系统提示词
            tools: 可用工具列表
        
        Returns:
            LLM 响应
        """
        messages: list[MessageParam] = []
        
        # 添加上下文中的历史消息
        if context and context.messages:
            messages.extend(context.messages)
        
        # 添加当前用户消息
        messages.append({"role": "user", "content": prompt})
        
        # 确定系统提示词
        sys_prompt = system or (context.system if context else "")
        
        # 确定工具列表
        tool_list = tools or (context.tools if context else [])
        
        try:
            # 构建请求参数
            request_params: dict[str, Any] = {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "messages": messages,
            }
            
            if sys_prompt:
                request_params["system"] = sys_prompt
            
            if tool_list:
                request_params["tools"] = tool_list
            
            # 发送请求
            response: Message = self.client.messages.create(**request_params)
            
            # 解析响应
            content = ""
            tool_calls = []
            
            for block in response.content:
                if block.type == "text":
                    content += block.text
                elif block.type == "tool_use":
                    tool_calls.append({
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })
            
            return Response(
                content=content,
                tool_calls=tool_calls,
                stop_reason=response.stop_reason or "",
                usage={
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            )
            
        except Exception as e:
            logger.error(f"Brain think error: {e}")
            raise
    
    async def plan(self, task: str, context: Optional[Context] = None) -> str:
        """
        为任务生成执行计划
        
        Args:
            task: 任务描述
            context: 上下文
        
        Returns:
            执行计划文本
        """
        prompt = f"""请为以下任务制定详细的执行计划:

任务: {task}

要求:
1. 分解为具体的步骤
2. 识别需要的工具和技能
3. 考虑可能的失败情况和备选方案
4. 估计每个步骤的复杂度

请以 Markdown 格式输出计划。"""

        response = await self.think(prompt, context)
        return response.content
    
    async def generate_code(
        self,
        description: str,
        language: str = "python",
        context: Optional[Context] = None,
    ) -> str:
        """
        生成代码
        
        Args:
            description: 代码功能描述
            language: 编程语言
            context: 上下文
        
        Returns:
            生成的代码
        """
        prompt = f"""请生成以下功能的 {language} 代码:

{description}

要求:
1. 代码应该完整、可运行
2. 包含必要的导入语句
3. 添加适当的注释和 docstring
4. 遵循 {language} 的最佳实践
5. 如果是类，包含类型提示

只输出代码，不要解释。"""

        response = await self.think(prompt, context)
        
        # 提取代码块
        code = response.content
        if f"```{language}" in code:
            start = code.find(f"```{language}") + len(f"```{language}")
            end = code.find("```", start)
            if end > start:
                code = code[start:end].strip()
        elif "```" in code:
            start = code.find("```") + 3
            end = code.find("```", start)
            if end > start:
                code = code[start:end].strip()
        
        return code
    
    async def analyze_error(
        self,
        error: str,
        context: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        分析错误并提供解决方案
        
        Args:
            error: 错误信息
            context: 错误上下文
        
        Returns:
            分析结果和建议
        """
        prompt = f"""请分析以下错误并提供解决方案:

错误信息:
{error}

{"上下文:" + context if context else ""}

请提供:
1. 错误原因分析
2. 可能的解决方案（按优先级排序）
3. 如何避免类似错误

以 JSON 格式输出:
{{
    "cause": "错误原因",
    "solutions": ["解决方案1", "解决方案2"],
    "prevention": "预防措施"
}}"""

        response = await self.think(prompt)
        
        # 尝试解析 JSON
        import json
        try:
            content = response.content
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                content = content[start:end].strip()
            elif "```" in content:
                start = content.find("```") + 3
                end = content.find("```", start)
                content = content[start:end].strip()
            
            return json.loads(content)
        except json.JSONDecodeError:
            return {
                "cause": "Unable to parse error analysis",
                "solutions": [response.content],
                "prevention": "",
            }
