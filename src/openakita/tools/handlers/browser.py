"""
浏览器处理器

处理浏览器相关的系统技能：
- browser_task: 【推荐优先使用】智能浏览器任务
- browser_open: 启动浏览器 + 状态查询
- browser_navigate: 导航到 URL
- browser_get_content: 获取页面内容（支持 max_length 截断）
- browser_screenshot: 截取页面截图
- browser_close: 关闭浏览器
"""

import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...core.agent import Agent

logger = logging.getLogger(__name__)


class BrowserHandler:
    """
    浏览器处理器

    通过 browser_mcp 处理所有浏览器相关的工具调用
    """

    TOOLS = [
        "browser_task",
        "browser_open",
        "browser_navigate",
        "browser_get_content",
        "browser_screenshot",
        "browser_close",
    ]

    # browser_get_content 默认最大字符数
    # 网页内容通常较大，12K 经常截断重要信息；提升到 32K 覆盖大多数页面。
    CONTENT_DEFAULT_MAX_LENGTH = 32000

    def __init__(self, agent: "Agent"):
        self.agent = agent

    async def handle(self, tool_name: str, params: dict[str, Any]) -> str:
        """处理工具调用"""
        if not hasattr(self.agent, "browser_mcp") or not self.agent.browser_mcp:
            return "❌ 浏览器 MCP 未启动。请确保已安装 playwright: pip install playwright && playwright install chromium"

        # 提取实际工具名（处理 mcp__browser-use__browser_navigate 格式）
        actual_tool_name = tool_name
        if "browser_" in tool_name and not tool_name.startswith("browser_"):
            match = re.search(r"(browser_\w+)", tool_name)
            if match:
                actual_tool_name = match.group(1)

        result = await self.agent.browser_mcp.call_tool(actual_tool_name, params)

        if result.get("success"):
            output = f"✅ {result.get('result', 'OK')}"
        else:
            output = f"❌ {result.get('error', '未知错误')}"

        # browser_get_content 的智能截断
        if actual_tool_name == "browser_get_content":
            max_length = params.get("max_length", self.CONTENT_DEFAULT_MAX_LENGTH)
            try:
                max_length = max(1000, int(max_length))
            except (TypeError, ValueError):
                max_length = self.CONTENT_DEFAULT_MAX_LENGTH

            if len(output) > max_length:
                total_chars = len(output)
                from ...core.tool_executor import save_overflow

                overflow_path = save_overflow("browser_get_content", output)
                output = output[:max_length]
                output += (
                    f"\n\n[OUTPUT_TRUNCATED] 页面内容共 {total_chars} 字符，"
                    f"已显示前 {max_length} 字符。\n"
                    f"完整内容已保存到: {overflow_path}\n"
                    f'使用 read_file(path="{overflow_path}", offset=1, limit=300) '
                    f"查看完整内容。\n"
                    f"也可以用 browser_get_content(selector=\"...\") 缩小查询范围。"
                )

        return output


def create_handler(agent: "Agent"):
    """创建浏览器处理器"""
    handler = BrowserHandler(agent)
    return handler.handle
