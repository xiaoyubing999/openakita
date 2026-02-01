"""
工具调用格式转换器

负责在内部格式（Anthropic-like）和 OpenAI 格式之间转换工具定义和调用。
支持文本格式工具调用解析（降级方案）。
"""

import json
import re
import uuid
import logging
from typing import Optional

from ..types import Tool, ToolUseBlock

logger = logging.getLogger(__name__)


def convert_tools_to_openai(tools: list[Tool]) -> list[dict]:
    """
    将内部工具定义转换为 OpenAI 格式
    
    内部格式:
    {
        "name": "get_weather",
        "description": "获取天气",
        "input_schema": {"type": "object", "properties": {...}}
    }
    
    OpenAI 格式:
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取天气",
            "parameters": {"type": "object", "properties": {...}}
        }
    }
    """
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            }
        }
        for tool in tools
    ]


def convert_tools_from_openai(tools: list[dict]) -> list[Tool]:
    """
    将 OpenAI 工具定义转换为内部格式
    """
    result = []
    for tool in tools:
        if tool.get("type") == "function":
            func = tool.get("function", {})
            result.append(Tool(
                name=func.get("name", ""),
                description=func.get("description", ""),
                input_schema=func.get("parameters", {}),
            ))
    return result


def convert_tool_calls_from_openai(tool_calls: list[dict]) -> list[ToolUseBlock]:
    """
    将 OpenAI 工具调用转换为内部格式
    
    OpenAI 格式:
    {
        "id": "call_xxx",
        "type": "function",
        "function": {
            "name": "get_weather",
            "arguments": "{\"location\": \"Beijing\"}"  # JSON 字符串
        }
    }
    
    内部格式:
    {
        "type": "tool_use",
        "id": "call_xxx",
        "name": "get_weather",
        "input": {"location": "Beijing"}  # JSON 对象
    }
    """
    result = []
    for tc in tool_calls:
        if tc.get("type") == "function":
            func = tc.get("function", {})
            
            # 解析 arguments（JSON 字符串 -> dict）
            arguments = func.get("arguments", "{}")
            if isinstance(arguments, str):
                try:
                    input_dict = json.loads(arguments)
                except json.JSONDecodeError:
                    input_dict = {}
            else:
                input_dict = arguments
            
            result.append(ToolUseBlock(
                id=tc.get("id", ""),
                name=func.get("name", ""),
                input=input_dict,
            ))
    
    return result


def convert_tool_calls_to_openai(tool_uses: list[ToolUseBlock]) -> list[dict]:
    """
    将内部工具调用转换为 OpenAI 格式
    """
    return [
        {
            "id": tu.id,
            "type": "function",
            "function": {
                "name": tu.name,
                "arguments": json.dumps(tu.input, ensure_ascii=False),
            }
        }
        for tu in tool_uses
    ]


def convert_tool_result_to_openai(tool_use_id: str, content: str, is_error: bool = False) -> dict:
    """
    将工具结果转换为 OpenAI 格式消息
    
    OpenAI 使用独立的 "tool" 角色消息来传递工具结果
    """
    return {
        "role": "tool",
        "tool_call_id": tool_use_id,
        "content": content,
    }


def convert_tool_result_from_openai(msg: dict) -> Optional[dict]:
    """
    将 OpenAI 工具结果消息转换为内部格式
    """
    if msg.get("role") != "tool":
        return None
    
    return {
        "type": "tool_result",
        "tool_use_id": msg.get("tool_call_id", ""),
        "content": msg.get("content", ""),
    }


def parse_text_tool_calls(text: str) -> tuple[str, list[ToolUseBlock]]:
    """
    从文本中解析工具调用（降级方案）
    
    当 LLM 不支持原生工具调用时，会以文本格式返回工具调用。
    此函数解析这些文本格式的工具调用。
    
    支持格式：
    1. <function_calls>...</function_calls> 块
    2. <minimax:tool_call>...</minimax:tool_call> 块（MiniMax 格式）
    
    Args:
        text: LLM 返回的文本内容
        
    Returns:
        (clean_text, tool_calls): 清理后的文本和解析出的工具调用列表
    """
    tool_calls = []
    clean_text = text
    
    # === 格式 1: <function_calls>...</function_calls> ===
    function_calls_pattern = r'<function_calls>\s*(.*?)\s*</function_calls>'
    matches = re.findall(function_calls_pattern, text, re.DOTALL | re.IGNORECASE)
    
    if not matches:
        # 尝试匹配不完整的格式（没有结束标签）
        function_calls_pattern_incomplete = r'<function_calls>\s*(.*?)$'
        matches = re.findall(function_calls_pattern_incomplete, text, re.DOTALL | re.IGNORECASE)
    
    for match in matches:
        tool_calls.extend(_parse_invoke_blocks(match))
    
    # === 格式 2: <minimax:tool_call>...</minimax:tool_call> (MiniMax 格式) ===
    minimax_pattern = r'<minimax:tool_call>\s*(.*?)\s*</minimax:tool_call>'
    minimax_matches = re.findall(minimax_pattern, text, re.DOTALL | re.IGNORECASE)
    
    if not minimax_matches:
        # 尝试匹配不完整的格式
        minimax_pattern_incomplete = r'<minimax:tool_call>\s*(.*?)$'
        minimax_matches = re.findall(minimax_pattern_incomplete, text, re.DOTALL | re.IGNORECASE)
    
    for match in minimax_matches:
        tool_calls.extend(_parse_invoke_blocks(match))
    
    # === 格式 3: <<|tool_calls_section_begin|>>...<<|tool_calls_section_end|>> (Kimi K2 格式) ===
    kimi_tool_calls = _parse_kimi_tool_calls(text)
    tool_calls.extend(kimi_tool_calls)
    
    # 清理文本，移除已解析的工具调用
    if tool_calls:
        # 移除 function_calls 块
        clean_text = re.sub(
            r'<function_calls>.*?</function_calls>',
            '',
            text,
            flags=re.DOTALL | re.IGNORECASE
        ).strip()
        
        # 移除不完整的 function_calls 块
        clean_text = re.sub(
            r'<function_calls>.*$',
            '',
            clean_text,
            flags=re.DOTALL | re.IGNORECASE
        ).strip()
        
        # 移除 minimax:tool_call 块
        clean_text = re.sub(
            r'<minimax:tool_call>.*?</minimax:tool_call>',
            '',
            clean_text,
            flags=re.DOTALL | re.IGNORECASE
        ).strip()
        
        # 移除不完整的 minimax:tool_call 块
        clean_text = re.sub(
            r'<minimax:tool_call>.*$',
            '',
            clean_text,
            flags=re.DOTALL | re.IGNORECASE
        ).strip()
        
        # 移除 Kimi K2 格式的工具调用
        clean_text = re.sub(
            r'<<\|tool_calls_section_begin\|>>.*?<<\|tool_calls_section_end\|>>',
            '',
            clean_text,
            flags=re.DOTALL
        ).strip()
        
        # 移除不完整的 Kimi 格式
        clean_text = re.sub(
            r'<<\|tool_calls_section_begin\|>>.*$',
            '',
            clean_text,
            flags=re.DOTALL
        ).strip()
    
    return clean_text, tool_calls


def _parse_kimi_tool_calls(text: str) -> list[ToolUseBlock]:
    """
    解析 Kimi K2 格式的工具调用
    
    格式：
    <<|tool_calls_section_begin|>>
    <<|tool_call_begin|>>functions.get_weather:0<<|tool_call_argument_begin|>>{"city": "Beijing"}<<|tool_call_end|>>
    <<|tool_calls_section_end|>>
    
    Args:
        text: 包含工具调用的文本
        
    Returns:
        工具调用列表
    """
    tool_calls = []
    
    # 检查是否包含 Kimi 格式
    if '<<|tool_calls_section_begin|>>' not in text:
        return []
    
    # 提取工具调用区块
    section_pattern = r'<<\|tool_calls_section_begin\|>>(.*?)<<\|tool_calls_section_end\|>>'
    section_matches = re.findall(section_pattern, text, re.DOTALL)
    
    if not section_matches:
        # 尝试不完整格式
        section_pattern_incomplete = r'<<\|tool_calls_section_begin\|>>(.*?)$'
        section_matches = re.findall(section_pattern_incomplete, text, re.DOTALL)
    
    for section in section_matches:
        # 提取每个工具调用
        # 格式: <<|tool_call_begin|>>functions.func_name:idx<<|tool_call_argument_begin|>>{json}<<|tool_call_end|>>
        call_pattern = r'<<\|tool_call_begin\|>>\s*(?P<tool_id>[\w\.]+:\d+)\s*<<\|tool_call_argument_begin\|>>\s*(?P<arguments>.*?)\s*<<\|tool_call_end\|>>'
        
        for match in re.finditer(call_pattern, section, re.DOTALL):
            tool_id = match.group('tool_id')
            arguments_str = match.group('arguments').strip()
            
            # 解析函数名: functions.get_weather:0 -> get_weather
            try:
                func_name = tool_id.split('.')[1].split(':')[0]
            except IndexError:
                func_name = tool_id
            
            # 解析参数
            try:
                arguments = json.loads(arguments_str)
            except json.JSONDecodeError:
                arguments = {"raw": arguments_str}
            
            tool_call = ToolUseBlock(
                id=f"kimi_call_{tool_id.replace('.', '_').replace(':', '_')}",
                name=func_name,
                input=arguments,
            )
            tool_calls.append(tool_call)
            logger.info(f"[KIMI_TOOL_PARSE] Extracted tool call: {func_name} with args: {list(arguments.keys())}")
    
    return tool_calls


def _parse_invoke_blocks(content: str) -> list[ToolUseBlock]:
    """
    解析 <invoke> 块中的工具调用
    
    Args:
        content: 包含 <invoke> 块的内容
        
    Returns:
        工具调用列表
    """
    tool_calls = []
    
    # 查找 invoke 块
    invoke_pattern = r'<invoke\s+name=["\']?([^"\'>\s]+)["\']?\s*>(.*?)</invoke>'
    invokes = re.findall(invoke_pattern, content, re.DOTALL | re.IGNORECASE)
    
    if not invokes:
        # 尝试不完整格式
        invoke_pattern_incomplete = r'<invoke\s+name=["\']?([^"\'>\s]+)["\']?\s*>(.*?)(?:</invoke>|$)'
        invokes = re.findall(invoke_pattern_incomplete, content, re.DOTALL | re.IGNORECASE)
    
    for tool_name, invoke_content in invokes:
        # 解析参数
        params = {}
        param_pattern = r'<parameter\s+name=["\']?([^"\'>\s]+)["\']?\s*>(.*?)</parameter>'
        param_matches = re.findall(param_pattern, invoke_content, re.DOTALL | re.IGNORECASE)
        
        for param_name, param_value in param_matches:
            # 清理参数值
            param_value = param_value.strip()
            
            # 尝试解析为 JSON
            try:
                params[param_name] = json.loads(param_value)
            except json.JSONDecodeError:
                params[param_name] = param_value
        
        # 创建工具调用
        tool_call = ToolUseBlock(
            id=f"text_call_{uuid.uuid4().hex[:8]}",
            name=tool_name.strip(),
            input=params,
        )
        tool_calls.append(tool_call)
        logger.info(f"[TEXT_TOOL_PARSE] Extracted tool call: {tool_name} with params: {list(params.keys())}")
    
    return tool_calls


def has_text_tool_calls(text: str) -> bool:
    """
    检查文本中是否包含工具调用格式
    
    支持检测：
    - <function_calls> 格式（通用）
    - <minimax:tool_call> 格式（MiniMax）
    - <<|tool_calls_section_begin|>> 格式（Kimi K2）
    """
    return bool(
        re.search(r'<function_calls>', text, re.IGNORECASE) or
        re.search(r'<minimax:tool_call>', text, re.IGNORECASE) or
        re.search(r'<<\|tool_calls_section_begin\|>>', text)
    )
