"""
MyAgent CLI 入口

使用 Typer 和 Rich 提供交互式命令行界面
"""

import asyncio
import logging
import sys
from typing import Optional

import typer
from typer import Context
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text

from .core.agent import Agent
from .config import settings

# 配置日志
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Typer 应用
app = typer.Typer(
    name="myagent",
    help="MyAgent - 全能自进化AI助手",
    add_completion=False,
)

# Rich 控制台
console = Console()

# 全局 Agent 实例
_agent: Optional[Agent] = None


def get_agent() -> Agent:
    """获取或创建 Agent 实例"""
    global _agent
    if _agent is None:
        _agent = Agent()
    return _agent


def print_welcome():
    """打印欢迎信息"""
    welcome_text = """
# MyAgent - 全能自进化AI助手

基于 **Ralph Wiggum 模式**，永不放弃。

## 核心特性
- 🔄 任务未完成绝不终止
- 🧠 自动学习和进化
- 🔧 动态安装新技能
- 📝 持续记录经验

## 命令
- 直接输入消息与 Agent 对话
- `/help` - 显示帮助
- `/status` - 显示状态
- `/selfcheck` - 运行自检
- `/clear` - 清空对话
- `/exit` 或 `/quit` - 退出
"""
    console.print(Panel(Markdown(welcome_text), title="Welcome", border_style="blue"))


def print_help():
    """打印帮助信息"""
    table = Table(title="可用命令")
    table.add_column("命令", style="cyan")
    table.add_column("描述", style="green")
    
    commands = [
        ("/help", "显示此帮助信息"),
        ("/status", "显示 Agent 状态"),
        ("/selfcheck", "运行自检"),
        ("/memory", "显示记忆状态"),
        ("/skills", "列出已安装技能"),
        ("/clear", "清空对话历史"),
        ("/exit, /quit", "退出程序"),
    ]
    
    for cmd, desc in commands:
        table.add_row(cmd, desc)
    
    console.print(table)


async def run_interactive():
    """运行交互式 CLI"""
    print_welcome()
    
    agent = get_agent()
    
    # 初始化 Agent
    with console.status("[bold green]正在初始化 Agent...", spinner="dots"):
        await agent.initialize()
    
    console.print("[green]✓[/green] Agent 已准备就绪\n")
    
    while True:
        try:
            # 获取用户输入
            user_input = Prompt.ask("[bold blue]You[/bold blue]")
            
            if not user_input.strip():
                continue
            
            # 处理命令
            if user_input.startswith("/"):
                cmd = user_input.lower().strip()
                
                if cmd in ("/exit", "/quit"):
                    console.print("[yellow]再见！[/yellow]")
                    break
                
                elif cmd == "/help":
                    print_help()
                    continue
                
                elif cmd == "/status":
                    await show_status(agent)
                    continue
                
                elif cmd == "/selfcheck":
                    await run_selfcheck(agent)
                    continue
                
                elif cmd == "/memory":
                    show_memory()
                    continue
                
                elif cmd == "/skills":
                    show_skills()
                    continue
                
                elif cmd == "/clear":
                    agent._conversation_history.clear()
                    agent._context.messages.clear()
                    console.print("[green]对话历史已清空[/green]")
                    continue
                
                else:
                    console.print(f"[red]未知命令: {cmd}[/red]")
                    print_help()
                    continue
            
            # 正常对话
            with console.status("[bold green]思考中...", spinner="dots"):
                response = await agent.chat(user_input)
            
            # 显示响应
            console.print()
            console.print(Panel(
                Markdown(response),
                title=f"[bold green]{agent.name}[/bold green]",
                border_style="green",
            ))
            console.print()
            
        except KeyboardInterrupt:
            console.print("\n[yellow]使用 /exit 退出[/yellow]")
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            console.print(f"[red]错误: {e}[/red]")


async def show_status(agent: Agent):
    """显示 Agent 状态"""
    table = Table(title="Agent 状态")
    table.add_column("属性", style="cyan")
    table.add_column("值", style="green")
    
    table.add_row("名称", agent.name)
    table.add_row("已初始化", "✓" if agent.is_initialized else "✗")
    table.add_row("对话轮数", str(len(agent.conversation_history) // 2))
    table.add_row("模型", settings.default_model)
    table.add_row("最大迭代", str(settings.max_iterations))
    
    console.print(table)


async def run_selfcheck(agent: Agent):
    """运行自检"""
    console.print("[bold]运行自检...[/bold]\n")
    
    with console.status("[bold green]检查中...", spinner="dots"):
        results = await agent.self_check()
    
    # 显示结果
    status_color = "green" if results["status"] == "healthy" else "red"
    console.print(f"状态: [{status_color}]{results['status']}[/{status_color}]")
    console.print()
    
    table = Table(title="检查项目")
    table.add_column("检查项", style="cyan")
    table.add_column("状态", style="green")
    table.add_column("消息", style="white")
    
    for name, check in results["checks"].items():
        status_icon = "✓" if check["status"] == "ok" else "⚠" if check["status"] == "warning" else "✗"
        status_style = "green" if check["status"] == "ok" else "yellow" if check["status"] == "warning" else "red"
        table.add_row(
            name,
            f"[{status_style}]{status_icon}[/{status_style}]",
            check.get("message", ""),
        )
    
    console.print(table)


def show_memory():
    """显示记忆状态"""
    try:
        content = settings.memory_path.read_text(encoding="utf-8")
        console.print(Panel(
            Markdown(content[:2000] + ("..." if len(content) > 2000 else "")),
            title="MEMORY.md",
            border_style="blue",
        ))
    except Exception as e:
        console.print(f"[red]无法读取 MEMORY.md: {e}[/red]")


def show_skills():
    """显示已安装技能"""
    console.print("[yellow]技能系统尚未实现[/yellow]")
    # TODO: 实现技能列表


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", help="显示版本信息"),
):
    """
    MyAgent - 全能自进化AI助手
    
    直接运行进入交互模式
    """
    if version:
        from . import __version__
        console.print(f"MyAgent v{__version__}")
        raise typer.Exit(0)
    
    # 如果没有子命令，进入交互模式
    if ctx.invoked_subcommand is None:
        # 检查 API Key
        if not settings.anthropic_api_key:
            console.print("[red]错误: 未设置 ANTHROPIC_API_KEY[/red]")
            console.print("请设置环境变量或在 .env 文件中配置")
            raise typer.Exit(1)
        
        # 运行交互式 CLI
        asyncio.run(run_interactive())


@app.command()
def run(
    task: str = typer.Argument(..., help="要执行的任务"),
):
    """执行单个任务"""
    async def _run():
        agent = get_agent()
        await agent.initialize()
        
        with console.status("[bold green]执行任务中...", spinner="dots"):
            result = await agent.execute_task_from_message(task)
        
        if result.success:
            console.print(Panel(
                Markdown(str(result.data)),
                title="[green]任务完成[/green]",
                border_style="green",
            ))
        else:
            console.print(Panel(
                f"错误: {result.error}",
                title="[red]任务失败[/red]",
                border_style="red",
            ))
    
    asyncio.run(_run())


@app.command()
def selfcheck(
    full: bool = typer.Option(False, "--full", "-f", help="运行完整自检"),
    fix: bool = typer.Option(False, "--fix", help="自动修复发现的问题"),
):
    """运行自检"""
    async def _selfcheck():
        agent = get_agent()
        await agent.initialize()
        await run_selfcheck(agent)
    
    asyncio.run(_selfcheck())


@app.command()
def status():
    """显示 Agent 状态"""
    async def _status():
        agent = get_agent()
        await agent.initialize()
        await show_status(agent)
    
    asyncio.run(_status())


if __name__ == "__main__":
    app()
