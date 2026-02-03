"""
Plan 模式处理器

处理任务计划相关的工具：
- create_plan: 创建任务执行计划
- update_plan_step: 更新步骤状态
- get_plan_status: 获取计划执行状态
- complete_plan: 完成计划
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.agent import Agent

logger = logging.getLogger(__name__)


class PlanHandler:
    """Plan 模式处理器"""
    
    TOOLS = [
        "create_plan",
        "update_plan_step",
        "get_plan_status",
        "complete_plan",
    ]
    
    def __init__(self, agent: "Agent"):
        self.agent = agent
        self.current_plan: Optional[dict] = None
        self.plan_dir = Path("data/plans")
        self.plan_dir.mkdir(parents=True, exist_ok=True)
    
    async def handle(self, tool_name: str, params: dict[str, Any]) -> str:
        """处理工具调用"""
        if tool_name == "create_plan":
            return await self._create_plan(params)
        elif tool_name == "update_plan_step":
            return await self._update_step(params)
        elif tool_name == "get_plan_status":
            return self._get_status()
        elif tool_name == "complete_plan":
            return await self._complete_plan(params)
        else:
            return f"❌ Unknown plan tool: {tool_name}"
    
    async def _create_plan(self, params: dict) -> str:
        """创建任务计划"""
        plan_id = f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        steps = params.get("steps", [])
        for step in steps:
            step["status"] = "pending"
            step["result"] = ""
            step["started_at"] = None
            step["completed_at"] = None
        
        self.current_plan = {
            "id": plan_id,
            "task_summary": params.get("task_summary", ""),
            "steps": steps,
            "status": "in_progress",
            "created_at": datetime.now().isoformat(),
            "completed_at": None,
            "logs": []
        }
        
        # 保存到文件
        self._save_plan_markdown()
        
        # 记录日志
        self._add_log(f"计划创建：{params.get('task_summary', '')}")
        
        # 生成计划展示消息
        plan_message = self._format_plan_message()
        
        # 通知用户（如果有 IM 会话）
        try:
            from ...core.agent import Agent
            if Agent._current_im_session:
                await self.agent.send_to_chat(plan_message)
        except Exception as e:
            logger.warning(f"Failed to send plan message: {e}")
        
        return f"✅ 计划已创建：{plan_id}\n\n{plan_message}"
    
    async def _update_step(self, params: dict) -> str:
        """更新步骤状态"""
        if not self.current_plan:
            return "❌ 当前没有活动的计划，请先调用 create_plan"
        
        step_id = params.get("step_id", "")
        status = params.get("status", "")
        result = params.get("result", "")
        
        # 查找并更新步骤
        step_found = False
        for step in self.current_plan["steps"]:
            if step["id"] == step_id:
                step["status"] = status
                step["result"] = result
                
                if status == "in_progress" and not step.get("started_at"):
                    step["started_at"] = datetime.now().isoformat()
                elif status in ["completed", "failed", "skipped"]:
                    step["completed_at"] = datetime.now().isoformat()
                
                step_found = True
                break
        
        if not step_found:
            return f"❌ 未找到步骤：{step_id}"
        
        # 保存更新
        self._save_plan_markdown()
        
        # 记录日志
        status_emoji = {
            "in_progress": "🔄",
            "completed": "✅",
            "failed": "❌",
            "skipped": "⏭️"
        }.get(status, "📌")
        
        self._add_log(f"{status_emoji} {step_id}: {result or status}")
        
        # 通知用户
        if status in ["completed", "failed"]:
            message = f"{status_emoji} {step_id} {'完成' if status == 'completed' else '失败'}"
            if result:
                message += f"：{result}"
            
            try:
                from ...core.agent import Agent
                if Agent._current_im_session:
                    await self.agent.send_to_chat(message)
            except Exception as e:
                logger.warning(f"Failed to send step update: {e}")
        
        return f"步骤 {step_id} 状态已更新为 {status}"
    
    def _get_status(self) -> str:
        """获取计划状态"""
        if not self.current_plan:
            return "当前没有活动的计划"
        
        plan = self.current_plan
        steps = plan["steps"]
        
        completed = sum(1 for s in steps if s["status"] == "completed")
        failed = sum(1 for s in steps if s["status"] == "failed")
        pending = sum(1 for s in steps if s["status"] == "pending")
        in_progress = sum(1 for s in steps if s["status"] == "in_progress")
        
        status_text = f"""## 计划状态：{plan['task_summary']}

**计划ID**: {plan['id']}
**状态**: {plan['status']}
**进度**: {completed}/{len(steps)} 完成

### 步骤列表

| 步骤 | 描述 | 状态 | 结果 |
|------|------|------|------|
"""
        
        for step in steps:
            status_emoji = {
                "pending": "⬜",
                "in_progress": "🔄",
                "completed": "✅",
                "failed": "❌",
                "skipped": "⏭️"
            }.get(step["status"], "❓")
            
            status_text += f"| {step['id']} | {step['description']} | {status_emoji} | {step.get('result', '-')} |\n"
        
        status_text += f"\n**统计**: ✅ {completed} 完成, ❌ {failed} 失败, ⬜ {pending} 待执行, 🔄 {in_progress} 执行中"
        
        return status_text
    
    async def _complete_plan(self, params: dict) -> str:
        """完成计划"""
        if not self.current_plan:
            return "❌ 当前没有活动的计划"
        
        summary = params.get("summary", "")
        
        self.current_plan["status"] = "completed"
        self.current_plan["completed_at"] = datetime.now().isoformat()
        self.current_plan["summary"] = summary
        
        # 统计
        steps = self.current_plan["steps"]
        completed = sum(1 for s in steps if s["status"] == "completed")
        failed = sum(1 for s in steps if s["status"] == "failed")
        
        # 保存最终状态
        self._save_plan_markdown()
        self._add_log(f"计划完成：{summary}")
        
        # 生成完成消息
        complete_message = f"""🎉 **任务完成！**

{summary}

**执行统计**：
- 总步骤：{len(steps)}
- 成功：{completed}
- 失败：{failed}
"""
        
        # 通知用户
        try:
            from ...core.agent import Agent
            if Agent._current_im_session:
                await self.agent.send_to_chat(complete_message)
        except Exception as e:
            logger.warning(f"Failed to send complete message: {e}")
        
        # 清理当前计划
        plan_id = self.current_plan["id"]
        self.current_plan = None
        
        return f"✅ 计划 {plan_id} 已完成\n\n{complete_message}"
    
    def _format_plan_message(self) -> str:
        """格式化计划展示消息"""
        if not self.current_plan:
            return ""
        
        plan = self.current_plan
        steps = plan["steps"]
        
        message = f"""📋 **任务计划**：{plan['task_summary']}

"""
        for i, step in enumerate(steps):
            prefix = "├─" if i < len(steps) - 1 else "└─"
            message += f"{prefix} {i+1}. {step['description']}\n"
        
        message += "\n开始执行..."
        
        return message
    
    def _save_plan_markdown(self) -> None:
        """保存计划到 Markdown 文件"""
        if not self.current_plan:
            return
        
        plan = self.current_plan
        plan_file = self.plan_dir / f"{plan['id']}.md"
        
        content = f"""# 任务计划：{plan['task_summary']}

**计划ID**: {plan['id']}
**创建时间**: {plan['created_at']}
**状态**: {plan['status']}
**完成时间**: {plan.get('completed_at', '-')}

## 步骤列表

| ID | 描述 | 工具 | 状态 | 结果 |
|----|------|------|------|------|
"""
        
        for step in plan["steps"]:
            status_emoji = {
                "pending": "⬜",
                "in_progress": "🔄",
                "completed": "✅",
                "failed": "❌",
                "skipped": "⏭️"
            }.get(step["status"], "❓")
            
            tool = step.get("tool", "-")
            result = step.get("result", "-")
            
            content += f"| {step['id']} | {step['description']} | {tool} | {status_emoji} | {result} |\n"
        
        content += "\n## 执行日志\n\n"
        for log in plan.get("logs", []):
            content += f"- {log}\n"
        
        if plan.get("summary"):
            content += f"\n## 完成总结\n\n{plan['summary']}\n"
        
        plan_file.write_text(content, encoding="utf-8")
        logger.info(f"[Plan] Saved to: {plan_file}")
    
    def _add_log(self, message: str) -> None:
        """添加日志"""
        if self.current_plan:
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.current_plan.setdefault("logs", []).append(f"[{timestamp}] {message}")


def create_plan_handler(agent: "Agent") -> PlanHandler:
    """创建 Plan Handler 实例"""
    return PlanHandler(agent)
