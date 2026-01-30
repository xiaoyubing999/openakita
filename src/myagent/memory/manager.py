"""
记忆管理器 - 核心记忆系统

功能:
1. 协调实时提取和批量整理
2. 管理 MEMORY.md 文件
3. 提供记忆注入策略
4. 自动触发记忆更新

注入策略:
- 会话开始: 注入最近的记忆摘要
- 任务执行: 注入相关的记忆
- 会话结束: 保存新记忆
"""

import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import re

from .types import Memory, MemoryType, MemoryPriority, ConversationTurn, SessionSummary
from .extractor import MemoryExtractor
from .consolidator import MemoryConsolidator

logger = logging.getLogger(__name__)


class MemoryManager:
    """记忆管理器"""
    
    def __init__(
        self,
        data_dir: Path,
        memory_md_path: Path,
        brain=None,
    ):
        """
        Args:
            data_dir: 数据目录
            memory_md_path: MEMORY.md 文件路径
            brain: LLM 大脑实例
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.memory_md_path = Path(memory_md_path)
        self.brain = brain
        
        # 子组件
        self.extractor = MemoryExtractor(brain)
        self.consolidator = MemoryConsolidator(data_dir, brain, self.extractor)
        
        # 记忆存储
        self.memories_file = self.data_dir / "memories.json"
        self._memories: dict[str, Memory] = {}
        
        # 当前会话
        self._current_session_id: Optional[str] = None
        self._session_turns: list[ConversationTurn] = []
        
        # 加载记忆
        self._load_memories()
    
    def _load_memories(self) -> None:
        """加载所有记忆"""
        if self.memories_file.exists():
            try:
                with open(self.memories_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        memory = Memory.from_dict(item)
                        self._memories[memory.id] = memory
                logger.info(f"Loaded {len(self._memories)} memories")
            except Exception as e:
                logger.error(f"Failed to load memories: {e}")
    
    def _save_memories(self) -> None:
        """保存所有记忆"""
        try:
            data = [m.to_dict() for m in self._memories.values()]
            with open(self.memories_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save memories: {e}")
    
    # ==================== 会话管理 ====================
    
    def start_session(self, session_id: str) -> None:
        """开始新会话"""
        self._current_session_id = session_id
        self._session_turns = []
        logger.info(f"Started session: {session_id}")
    
    def record_turn(self, role: str, content: str, tool_calls: list = None, tool_results: list = None) -> None:
        """记录对话轮次"""
        turn = ConversationTurn(
            role=role,
            content=content,
            tool_calls=tool_calls or [],
            tool_results=tool_results or [],
        )
        self._session_turns.append(turn)
        
        # 保存到历史
        if self._current_session_id:
            self.consolidator.save_conversation_turn(self._current_session_id, turn)
        
        # 实时提取 (只从用户消息)
        if role == "user":
            memories = self.extractor.extract_from_turn(turn)
            for memory in memories:
                self.add_memory(memory)
    
    def end_session(self, task_description: str = "", success: bool = True, errors: list = None) -> None:
        """结束会话"""
        if not self._current_session_id:
            return
        
        # 从任务完成结果提取记忆
        tool_calls = []
        for turn in self._session_turns:
            tool_calls.extend(turn.tool_calls)
        
        memories = self.extractor.extract_from_task_completion(
            task_description=task_description,
            success=success,
            tool_calls=tool_calls,
            errors=errors or [],
        )
        
        for memory in memories:
            self.add_memory(memory)
        
        logger.info(f"Ended session {self._current_session_id}: {len(memories)} memories extracted")
        
        self._current_session_id = None
        self._session_turns = []
    
    # ==================== 记忆操作 ====================
    
    def add_memory(self, memory: Memory) -> str:
        """添加记忆"""
        # 去重检查
        existing = list(self._memories.values())
        unique = self.extractor.deduplicate([memory], existing)
        
        if unique:
            memory = unique[0]
            self._memories[memory.id] = memory
            self._save_memories()
            logger.debug(f"Added memory: {memory.id} - {memory.content[:50]}")
            return memory.id
        
        return ""
    
    def get_memory(self, memory_id: str) -> Optional[Memory]:
        """获取单条记忆"""
        memory = self._memories.get(memory_id)
        if memory:
            memory.access_count += 1
            memory.updated_at = datetime.now()
        return memory
    
    def search_memories(
        self,
        query: str = "",
        memory_type: Optional[MemoryType] = None,
        tags: list[str] = None,
        limit: int = 10,
    ) -> list[Memory]:
        """搜索记忆"""
        results = []
        
        for memory in self._memories.values():
            # 类型过滤
            if memory_type and memory.type != memory_type:
                continue
            
            # 标签过滤
            if tags:
                if not any(tag in memory.tags for tag in tags):
                    continue
            
            # 关键词过滤
            if query:
                if query.lower() not in memory.content.lower():
                    continue
            
            results.append(memory)
        
        # 按重要性和访问次数排序
        results.sort(key=lambda m: (m.importance_score, m.access_count), reverse=True)
        
        return results[:limit]
    
    def delete_memory(self, memory_id: str) -> bool:
        """删除记忆"""
        if memory_id in self._memories:
            del self._memories[memory_id]
            self._save_memories()
            return True
        return False
    
    # ==================== 记忆注入 ====================
    
    def get_injection_context(
        self,
        task_description: str = "",
        max_memories: int = 15,
    ) -> str:
        """
        获取要注入系统提示的记忆上下文
        
        策略:
        1. 永久记忆 (规则、重要事实)
        2. 与任务相关的记忆
        3. 最近的记忆
        """
        selected = []
        
        # 1. 永久记忆 (规则)
        permanent = [m for m in self._memories.values() 
                     if m.priority == MemoryPriority.PERMANENT]
        selected.extend(permanent[:5])
        
        # 2. 与任务相关 (基于关键词匹配)
        if task_description:
            keywords = task_description.lower().split()
            related = []
            for memory in self._memories.values():
                if memory in selected:
                    continue
                content_lower = memory.content.lower()
                if any(kw in content_lower for kw in keywords if len(kw) > 2):
                    related.append(memory)
            
            related.sort(key=lambda m: m.importance_score, reverse=True)
            selected.extend(related[:5])
        
        # 3. 最近的高重要性记忆
        recent = sorted(
            [m for m in self._memories.values() if m not in selected],
            key=lambda m: (m.importance_score, m.updated_at),
            reverse=True
        )
        selected.extend(recent[:max_memories - len(selected)])
        
        # 生成上下文文本
        if not selected:
            return ""
        
        lines = ["## 相关记忆"]
        
        # 按类型分组
        by_type = {}
        for memory in selected:
            by_type.setdefault(memory.type, []).append(memory)
        
        type_names = {
            MemoryType.RULE: "规则约束",
            MemoryType.SKILL: "成功模式",
            MemoryType.ERROR: "错误教训",
            MemoryType.PREFERENCE: "用户偏好",
            MemoryType.FACT: "事实信息",
            MemoryType.CONTEXT: "上下文",
        }
        
        for mem_type, memories in by_type.items():
            lines.append(f"\n### {type_names.get(mem_type, mem_type.value)}")
            for memory in memories[:5]:
                lines.append(memory.to_markdown())
        
        return "\n".join(lines)
    
    # ==================== MEMORY.md 同步 ====================
    
    def sync_to_memory_md(self) -> None:
        """
        同步记忆到 MEMORY.md
        
        只更新 "Learned Experiences" 部分
        """
        try:
            content = self.memory_md_path.read_text(encoding="utf-8") if self.memory_md_path.exists() else ""
            
            # 生成 Learned Experiences 部分
            experience_section = self._generate_experience_section()
            
            # 替换或追加
            pattern = r'(## Learned Experiences\s*)(.*?)(?=## |\Z)'
            
            if re.search(pattern, content, re.DOTALL):
                new_content = re.sub(
                    pattern,
                    f"## Learned Experiences\n\n{experience_section}\n\n",
                    content,
                    flags=re.DOTALL
                )
            else:
                new_content = content + f"\n## Learned Experiences\n\n{experience_section}\n"
            
            self.memory_md_path.write_text(new_content, encoding="utf-8")
            logger.info("Synced memories to MEMORY.md")
            
        except Exception as e:
            logger.error(f"Failed to sync to MEMORY.md: {e}")
    
    def _generate_experience_section(self) -> str:
        """生成 Learned Experiences 部分"""
        lines = []
        
        # 成功模式
        skills = self.search_memories(memory_type=MemoryType.SKILL, limit=10)
        if skills:
            lines.append("### Successful Patterns\n")
            for m in skills:
                lines.append(f"- {m.content}")
            lines.append("")
        
        # 错误教训
        errors = self.search_memories(memory_type=MemoryType.ERROR, limit=10)
        if errors:
            lines.append("### Failed Attempts & Solutions\n")
            for m in errors:
                lines.append(f"- {m.content}")
            lines.append("")
        
        # 用户偏好
        prefs = self.search_memories(memory_type=MemoryType.PREFERENCE, limit=5)
        if prefs:
            lines.append("### User Preferences\n")
            for m in prefs:
                lines.append(f"- {m.content}")
            lines.append("")
        
        return "\n".join(lines) if lines else "[暂无]"
    
    # ==================== 批量整理 ====================
    
    async def consolidate_daily(self) -> dict:
        """
        每日批量整理
        
        适合在空闲时段 (如凌晨) 执行
        """
        logger.info("Starting daily consolidation...")
        
        # 整理所有未处理的会话
        summaries, memories = await self.consolidator.consolidate_all_unprocessed()
        
        # 添加新记忆
        added = 0
        for memory in memories:
            if self.add_memory(memory):
                added += 1
        
        # 同步到 MEMORY.md
        self.sync_to_memory_md()
        
        # 清理过期记忆
        cleaned = self._cleanup_expired_memories()
        
        # 清理旧历史文件
        deleted_files = self.consolidator.cleanup_old_history(days=30)
        
        result = {
            "sessions_processed": len(summaries),
            "memories_added": added,
            "memories_cleaned": cleaned,
            "history_files_deleted": deleted_files,
        }
        
        logger.info(f"Daily consolidation complete: {result}")
        return result
    
    def _cleanup_expired_memories(self) -> int:
        """清理过期记忆"""
        now = datetime.now()
        expired = []
        
        for memory_id, memory in self._memories.items():
            # 短期记忆: 3天过期
            if memory.priority == MemoryPriority.SHORT_TERM:
                if (now - memory.updated_at) > timedelta(days=3):
                    expired.append(memory_id)
            
            # 临时记忆: 1天过期
            elif memory.priority == MemoryPriority.TRANSIENT:
                if (now - memory.updated_at) > timedelta(days=1):
                    expired.append(memory_id)
        
        for memory_id in expired:
            del self._memories[memory_id]
        
        if expired:
            self._save_memories()
            logger.info(f"Cleaned up {len(expired)} expired memories")
        
        return len(expired)
    
    # ==================== 统计 ====================
    
    def get_stats(self) -> dict:
        """获取记忆统计"""
        type_counts = {}
        priority_counts = {}
        
        for memory in self._memories.values():
            type_counts[memory.type.value] = type_counts.get(memory.type.value, 0) + 1
            priority_counts[memory.priority.value] = priority_counts.get(memory.priority.value, 0) + 1
        
        return {
            "total": len(self._memories),
            "by_type": type_counts,
            "by_priority": priority_counts,
            "sessions_today": len(self.consolidator.get_today_sessions()),
            "unprocessed_sessions": len(self.consolidator.get_unprocessed_sessions()),
        }
