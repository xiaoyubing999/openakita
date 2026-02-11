"""
工具执行引擎

从 agent.py 提取的工具执行逻辑，负责:
- 单工具执行 (execute_tool)
- 批量工具执行 (execute_batch)
- 并行/串行策略
- Handler 互斥锁管理 (browser/desktop/mcp)
- 结构化错误处理 (ToolError)
- Plan 模式检查
"""

import asyncio
import logging
import time
from typing import Any

from ..config import settings
from ..tools.errors import ToolError, classify_error
from ..tools.handlers import SystemHandlerRegistry
from ..tracing.tracer import get_tracer
from .agent_state import TaskState

logger = logging.getLogger(__name__)


class ToolExecutor:
    """
    工具执行引擎。

    管理工具的串行/并行执行、Handler 互斥锁、
    结构化错误处理和 Plan 模式检查。
    """

    def __init__(
        self,
        handler_registry: SystemHandlerRegistry,
        max_parallel: int = 1,
    ) -> None:
        self._handler_registry = handler_registry

        # 并行控制
        self._semaphore = asyncio.Semaphore(max(1, max_parallel))
        self._max_parallel = max_parallel

        # 状态型工具互斥锁（browser/desktop/mcp 等不能并发执行）
        self._handler_locks: dict[str, asyncio.Lock] = {}
        for handler_name in ("browser", "desktop", "mcp"):
            self._handler_locks[handler_name] = asyncio.Lock()

    def get_handler_name(self, tool_name: str) -> str | None:
        """获取工具对应的 handler 名称"""
        try:
            return self._handler_registry.get_handler_name_for_tool(tool_name)
        except Exception:
            return None

    async def execute_tool(
        self,
        tool_name: str,
        tool_input: dict,
        *,
        session_id: str | None = None,
    ) -> str:
        """
        执行单个工具调用。

        优先使用 handler_registry 执行，
        捕获异常后返回结构化 ToolError。

        Args:
            tool_name: 工具名称
            tool_input: 工具输入参数
            session_id: 当前会话 ID（用于 Plan 检查）

        Returns:
            工具执行结果字符串
        """
        logger.info(f"Executing tool: {tool_name} with {tool_input}")

        # Plan 模式强制检查
        plan_block = self._check_plan_required(tool_name, session_id)
        if plan_block:
            return plan_block

        # 导入日志缓存
        from ..logging import get_session_log_buffer

        log_buffer = get_session_log_buffer()
        logs_before = log_buffer.get_logs(count=500)
        logs_before_count = len(logs_before)

        tracer = get_tracer()
        with tracer.tool_span(tool_name=tool_name, input_data=tool_input) as span:
            try:
                # 通过 handler_registry 执行
                if self._handler_registry.has_tool(tool_name):
                    result = await self._handler_registry.execute_by_tool(tool_name, tool_input)
                else:
                    span.set_attribute("error", f"unknown_tool: {tool_name}")
                    return f"❌ 未知工具: {tool_name}。请检查工具名称是否正确。"

                # 获取执行期间产生的新日志（WARNING/ERROR/CRITICAL）
                all_logs = log_buffer.get_logs(count=500)
                new_logs = [
                    log
                    for log in all_logs[logs_before_count:]
                    if log["level"] in ("WARNING", "ERROR", "CRITICAL")
                ]

                # 如果有警告/错误日志，附加到结果
                if new_logs:
                    result += "\n\n[执行日志]:\n"
                    for log in new_logs[-10:]:
                        result += f"[{log['level']}] {log['module']}: {log['message']}\n"

                span.set_attribute("result_length", len(result))
                return result

            except ToolError as e:
                # 结构化工具错误，直接序列化返回给 LLM
                logger.warning(f"Tool error ({e.error_type.value}): {tool_name} - {e.message}")
                span.set_attribute("error_type", e.error_type.value)
                span.set_attribute("error_message", e.message)
                return e.to_tool_result()

            except Exception as e:
                # 将通用异常分类为结构化 ToolError
                tool_error = classify_error(e, tool_name=tool_name)
                logger.error(f"Tool execution error: {e}", exc_info=True)
                span.set_attribute("error_type", tool_error.error_type.value)
                span.set_attribute("error_message", str(e))
                return tool_error.to_tool_result()

    async def execute_batch(
        self,
        tool_calls: list[dict],
        *,
        state: TaskState | None = None,
        task_monitor: Any = None,
        allow_interrupt_checks: bool = True,
        capture_delivery_receipts: bool = False,
    ) -> tuple[list[dict], list[str], list | None]:
        """
        执行一批工具调用，返回 tool_results。

        并行策略：
        - 默认串行（max_parallel=1 或启用中断检查时）
        - 当 max_parallel>1 时允许并行执行
        - browser/desktop/mcp handler 默认互斥锁

        Args:
            tool_calls: 工具调用列表 [{id, name, input}, ...]
            state: 任务状态（用于取消检查）
            task_monitor: 任务监控器
            allow_interrupt_checks: 是否允许中断检查
            capture_delivery_receipts: 是否捕获交付回执

        Returns:
            (tool_results, executed_tool_names, delivery_receipts)
        """
        executed_tool_names: list[str] = []
        delivery_receipts: list | None = None

        if not tool_calls:
            return [], executed_tool_names, delivery_receipts

        # 并行策略决策
        allow_parallel_with_interrupts = bool(
            getattr(settings, "allow_parallel_tools_with_interrupt_checks", False)
        )
        parallel_enabled = self._max_parallel > 1 and (
            (not allow_interrupt_checks) or allow_parallel_with_interrupts
        )

        session_id = state.session_id if state else None

        async def _run_one(tc: dict, idx: int) -> tuple[int, dict, str | None, list | None]:
            tool_name = tc.get("name", "")
            tool_input = tc.get("input") or {}
            tool_use_id = tc.get("id", "")

            # 检查取消
            if state and state.cancelled:
                return (
                    idx,
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": "[任务已被用户停止]",
                        "is_error": True,
                    },
                    None,
                    None,
                )

            handler_name = self.get_handler_name(tool_name)
            handler_lock = self._handler_locks.get(handler_name) if handler_name else None

            t0 = time.time()
            success = True
            result_str = ""
            receipts: list | None = None

            use_parallel_safe_monitor = (
                parallel_enabled
                and task_monitor is not None
                and hasattr(task_monitor, "record_tool_call")
            )
            if (not parallel_enabled) and task_monitor:
                task_monitor.begin_tool_call(tool_name, tool_input)

            try:
                async with self._semaphore:
                    if handler_lock:
                        async with handler_lock:
                            result = await self.execute_tool(
                                tool_name, tool_input, session_id=session_id
                            )
                    else:
                        result = await self.execute_tool(
                            tool_name, tool_input, session_id=session_id
                        )

                result_str = str(result) if result is not None else "操作已完成"

                # 终端输出工具返回结果（便于调试与观察）
                _preview = result_str if len(result_str) <= 800 else result_str[:800] + "\n... (已截断)"
                logger.info(f"[Tool] {tool_name} → {_preview}")

                # 捕获交付回执
                if capture_delivery_receipts and tool_name == "deliver_artifacts" and result_str:
                    try:
                        import json as _json

                        parsed = _json.loads(result_str)
                        rs = parsed.get("receipts") if isinstance(parsed, dict) else None
                        if isinstance(rs, list):
                            receipts = rs
                    except Exception:
                        pass

            except Exception as e:
                success = False
                tool_error = classify_error(e, tool_name=tool_name)
                result_str = tool_error.to_tool_result()
                logger.error(f"Tool batch execution error: {tool_name}: {e}")
                logger.info(f"[Tool] {tool_name} ❌ 错误: {result_str[:500]}{'...' if len(result_str) > 500 else ''}")

            elapsed = time.time() - t0

            # 记录到 task_monitor
            if use_parallel_safe_monitor and task_monitor:
                task_monitor.record_tool_call(tool_name, tool_input, elapsed, success)
            elif (not parallel_enabled) and task_monitor:
                task_monitor.end_tool_call(result_str, success)

            tool_result = {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": result_str,
            }
            if not success:
                tool_result["is_error"] = True

            return idx, tool_result, tool_name if success else None, receipts

        # 执行
        if parallel_enabled and len(tool_calls) > 1:
            # 并行执行
            tasks = [_run_one(tc, i) for i, tc in enumerate(tool_calls)]
            results = await asyncio.gather(*tasks)
            # 按原始顺序排序
            results = sorted(results, key=lambda x: x[0])
        else:
            # 串行执行
            results = []
            for i, tc in enumerate(tool_calls):
                result = await _run_one(tc, i)
                results.append(result)

                # 串行模式下检查中断和取消
                if state and state.cancelled:
                    # 为剩余工具生成取消结果
                    for j in range(i + 1, len(tool_calls)):
                        remaining_tc = tool_calls[j]
                        results.append((
                            j,
                            {
                                "type": "tool_result",
                                "tool_use_id": remaining_tc.get("id", ""),
                                "content": "[任务已被用户停止]",
                                "is_error": True,
                            },
                            None,
                            None,
                        ))
                    break

        # 整理结果
        tool_results = []
        for _, tool_result, name, receipts_item in results:
            tool_results.append(tool_result)
            if name:
                executed_tool_names.append(name)
            if receipts_item:
                delivery_receipts = receipts_item

        return tool_results, executed_tool_names, delivery_receipts

    def _check_plan_required(self, tool_name: str, session_id: str | None) -> str | None:
        """
        检查是否需要先创建 Plan。

        如果当前 session 被标记为需要 Plan（compound 任务），
        但还没有创建 Plan，则拒绝执行其他工具。

        Returns:
            阻止消息字符串，或 None（允许执行）
        """
        if tool_name == "create_plan":
            return None

        try:
            from ..tools.handlers.plan import has_active_plan, is_plan_required

            if session_id and is_plan_required(session_id) and not has_active_plan(session_id):
                return (
                    "⚠️ **这是一个多步骤任务，必须先创建计划！**\n\n"
                    "请先调用 `create_plan` 工具创建任务计划，然后再执行具体操作。\n\n"
                    "示例：\n"
                    "```\n"
                    "create_plan(\n"
                    "  task_summary='写脚本获取时间并显示',\n"
                    "  steps=[\n"
                    "    {id: 'step1', description: '创建Python脚本', tool: 'write_file'},\n"
                    "    {id: 'step2', description: '执行脚本', tool: 'run_shell'},\n"
                    "    {id: 'step3', description: '读取结果', tool: 'read_file'}\n"
                    "  ]\n"
                    ")\n"
                    "```"
                )
        except Exception:
            pass

        return None
