"""
Ralph Wiggum 循环引擎

参考来源:
- https://github.com/anthropics/claude-code/tree/main/plugins/ralph-wiggum
- https://claytonfarr.github.io/ralph-playbook/

核心理念:
- 任务未完成，绝不终止
- 通过文件持久化状态
- 每次迭代 fresh context
- 通过 backpressure（测试验证）强制自我修正
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from ..config import settings

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class Task:
    """任务定义"""
    id: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 0
    attempts: int = 0
    max_attempts: int = 10
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    result: Any = None
    subtasks: list["Task"] = field(default_factory=list)
    
    def mark_in_progress(self) -> None:
        """标记为进行中"""
        self.status = TaskStatus.IN_PROGRESS
        self.attempts += 1
    
    def mark_completed(self, result: Any = None) -> None:
        """标记为完成"""
        self.status = TaskStatus.COMPLETED
        self.completed_at = datetime.now()
        self.result = result
    
    def mark_failed(self, error: str) -> None:
        """标记为失败"""
        self.error = error
        if self.attempts >= self.max_attempts:
            self.status = TaskStatus.FAILED
        else:
            self.status = TaskStatus.PENDING  # 可重试
    
    @property
    def is_complete(self) -> bool:
        """是否已完成"""
        return self.status == TaskStatus.COMPLETED
    
    @property
    def can_retry(self) -> bool:
        """是否可以重试"""
        return (
            self.status in (TaskStatus.PENDING, TaskStatus.FAILED) 
            and self.attempts < self.max_attempts
        )


@dataclass
class TaskResult:
    """任务执行结果"""
    success: bool
    data: Any = None
    error: Optional[str] = None
    iterations: int = 0
    duration_seconds: float = 0


class StopHook:
    """
    Stop Hook - 拦截退出尝试
    
    当 Agent 试图退出但任务未完成时，拦截并继续
    """
    
    def __init__(self, task: Task):
        self.task = task
        self.intercepted_count = 0
    
    def should_stop(self) -> bool:
        """检查是否应该停止"""
        if self.task.is_complete:
            return True
        
        if not self.task.can_retry:
            logger.warning(f"Task {self.task.id} cannot retry anymore")
            return True
        
        return False
    
    def intercept(self) -> bool:
        """
        拦截退出尝试
        
        Returns:
            True 如果拦截成功（应继续执行），False 如果应该停止
        """
        if self.should_stop():
            return False
        
        self.intercepted_count += 1
        logger.info(
            f"Stop hook intercepted exit attempt #{self.intercepted_count} "
            f"for task {self.task.id}"
        )
        return True


class RalphLoop:
    """
    Ralph Wiggum 循环引擎
    
    核心循环逻辑:
    while not task.is_complete and iteration < max_iterations:
        1. 从 MEMORY.md 加载状态
        2. 执行一次迭代
        3. 检查结果
        4. 如果失败，分析原因并调整策略
        5. 保存进度到 MEMORY.md
        6. 继续下一次迭代
    """
    
    def __init__(
        self,
        max_iterations: int = 100,
        memory_path: Optional[Path] = None,
        on_iteration: Optional[Callable[[int, Task], None]] = None,
        on_error: Optional[Callable[[str, Task], None]] = None,
    ):
        self.max_iterations = max_iterations
        self.memory_path = memory_path or settings.memory_path
        self.on_iteration = on_iteration
        self.on_error = on_error
        
        self._current_task: Optional[Task] = None
        self._iteration = 0
        self._stop_hook: Optional[StopHook] = None
    
    async def run(
        self,
        task: Task,
        execute_fn: Callable[[Task], Any],
    ) -> TaskResult:
        """
        运行 Ralph 循环
        
        Args:
            task: 要执行的任务
            execute_fn: 执行函数，接收 Task 返回结果或抛出异常
        
        Returns:
            TaskResult
        """
        self._current_task = task
        self._iteration = 0
        self._stop_hook = StopHook(task)
        
        start_time = datetime.now()
        
        logger.info(f"Ralph loop starting for task: {task.id}")
        logger.info(f"Max iterations: {self.max_iterations}")
        
        while self._iteration < self.max_iterations:
            self._iteration += 1
            
            # 检查是否应该停止
            if self._stop_hook.should_stop():
                break
            
            # 加载进度
            await self._load_progress()
            
            # 通知迭代开始
            if self.on_iteration:
                self.on_iteration(self._iteration, task)
            
            logger.info(f"Iteration {self._iteration}/{self.max_iterations}")
            
            # 标记任务进行中
            task.mark_in_progress()
            
            try:
                # 执行任务
                result = await execute_fn(task)
                
                # 执行成功
                task.mark_completed(result)
                logger.info(f"Task {task.id} completed successfully")
                
                # 保存进度
                await self._save_progress()
                
                duration = (datetime.now() - start_time).total_seconds()
                return TaskResult(
                    success=True,
                    data=result,
                    iterations=self._iteration,
                    duration_seconds=duration,
                )
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Iteration {self._iteration} failed: {error_msg}")
                
                # 标记失败
                task.mark_failed(error_msg)
                
                # 通知错误
                if self.on_error:
                    self.on_error(error_msg, task)
                
                # 保存进度
                await self._save_progress()
                
                # 尝试拦截退出
                if not self._stop_hook.intercept():
                    break
                
                # 分析错误并调整策略
                await self._analyze_and_adapt(error_msg)
        
        # 循环结束但任务未完成
        duration = (datetime.now() - start_time).total_seconds()
        
        if task.is_complete:
            return TaskResult(
                success=True,
                data=task.result,
                iterations=self._iteration,
                duration_seconds=duration,
            )
        else:
            return TaskResult(
                success=False,
                error=task.error or "Max iterations reached",
                iterations=self._iteration,
                duration_seconds=duration,
            )
    
    async def _load_progress(self) -> None:
        """从 MEMORY.md 加载进度"""
        try:
            if self.memory_path.exists():
                content = self.memory_path.read_text(encoding="utf-8")
                # 解析 MEMORY.md 提取任务状态
                # 这里简化处理，实际应该解析 Markdown
                logger.debug("Progress loaded from MEMORY.md")
        except Exception as e:
            logger.warning(f"Failed to load progress: {e}")
    
    async def _save_progress(self) -> None:
        """保存进度到 MEMORY.md"""
        if not self._current_task:
            return
        
        try:
            # 读取现有内容
            content = ""
            if self.memory_path.exists():
                content = self.memory_path.read_text(encoding="utf-8")
            
            # 更新 Active Task 部分
            task = self._current_task
            task_info = f"""### Active Task

- **ID**: {task.id}
- **描述**: {task.description}
- **状态**: {task.status.value}
- **尝试次数**: {task.attempts}
- **最后更新**: {datetime.now().isoformat()}
"""
            
            # 简单替换 Active Task 部分
            if "### Active Task" in content:
                start = content.find("### Active Task")
                end = content.find("###", start + 1)
                if end == -1:
                    end = content.find("\n## ", start + 1)
                if end == -1:
                    end = len(content)
                content = content[:start] + task_info + content[end:]
            else:
                # 在 Current Task Progress 后插入
                insert_pos = content.find("## Current Task Progress")
                if insert_pos != -1:
                    insert_pos = content.find("\n", insert_pos) + 1
                    content = content[:insert_pos] + "\n" + task_info + content[insert_pos:]
            
            self.memory_path.write_text(content, encoding="utf-8")
            logger.debug("Progress saved to MEMORY.md")
            
        except Exception as e:
            logger.warning(f"Failed to save progress: {e}")
    
    async def _analyze_and_adapt(self, error: str) -> None:
        """
        分析错误并调整策略
        
        这是 Ralph 模式的核心:
        - 分析失败原因
        - 搜索解决方案
        - 调整策略
        """
        logger.info(f"Analyzing error and adapting strategy...")
        
        # TODO: 实现更智能的错误分析
        # 1. 使用 Brain 分析错误
        # 2. 搜索 GitHub 找解决方案
        # 3. 如果需要新能力，安装它
        # 4. 更新执行策略
        
        # 暂时简单等待后重试
        import asyncio
        await asyncio.sleep(1)
    
    @property
    def iteration(self) -> int:
        """当前迭代次数"""
        return self._iteration
    
    @property
    def current_task(self) -> Optional[Task]:
        """当前任务"""
        return self._current_task
