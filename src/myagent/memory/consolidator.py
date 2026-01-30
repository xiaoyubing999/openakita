"""
记忆整合器 - 批量整理对话历史

实现用户的想法:
1. 保存一整天的对话上下文
2. 空闲时段 (如凌晨) 自动整理
3. 归纳精华存入 MEMORY.md

参考:
- Claude-Mem Worker Service
- LangMem Background Manager
"""

import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

from .types import Memory, MemoryType, MemoryPriority, ConversationTurn, SessionSummary
from .extractor import MemoryExtractor

logger = logging.getLogger(__name__)


class MemoryConsolidator:
    """记忆整合器 - 批量处理对话历史"""
    
    def __init__(
        self,
        data_dir: Path,
        brain=None,
        extractor: Optional[MemoryExtractor] = None,
    ):
        """
        Args:
            data_dir: 数据目录 (存放对话历史)
            brain: LLM 大脑实例
            extractor: 记忆提取器
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.brain = brain
        self.extractor = extractor or MemoryExtractor(brain)
        
        # 对话历史存储目录
        self.history_dir = self.data_dir / "conversation_history"
        self.history_dir.mkdir(exist_ok=True)
        
        # 已整理的会话
        self.summaries_file = self.data_dir / "session_summaries.json"
        
    def save_conversation_turn(
        self,
        session_id: str,
        turn: ConversationTurn,
    ) -> None:
        """
        保存对话轮次 (实时保存)
        
        每个会话一个文件，追加写入
        """
        session_file = self.history_dir / f"{session_id}.jsonl"
        
        with open(session_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(turn.to_dict(), ensure_ascii=False) + "\n")
    
    def load_session_history(self, session_id: str) -> list[ConversationTurn]:
        """加载会话历史"""
        session_file = self.history_dir / f"{session_id}.jsonl"
        
        if not session_file.exists():
            return []
        
        turns = []
        with open(session_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    turn = ConversationTurn(
                        role=data["role"],
                        content=data["content"],
                        timestamp=datetime.fromisoformat(data["timestamp"]),
                        tool_calls=data.get("tool_calls", []),
                        tool_results=data.get("tool_results", []),
                    )
                    turns.append(turn)
        
        return turns
    
    def get_today_sessions(self) -> list[str]:
        """获取今天的所有会话 ID"""
        today = datetime.now().date()
        sessions = []
        
        for file in self.history_dir.glob("*.jsonl"):
            # 检查文件修改时间
            mtime = datetime.fromtimestamp(file.stat().st_mtime)
            if mtime.date() == today:
                sessions.append(file.stem)
        
        return sessions
    
    def get_unprocessed_sessions(self) -> list[str]:
        """获取未处理的会话"""
        # 加载已处理的会话
        processed = set()
        if self.summaries_file.exists():
            with open(self.summaries_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        summary = json.loads(line)
                        processed.add(summary["session_id"])
        
        # 找出未处理的
        unprocessed = []
        for file in self.history_dir.glob("*.jsonl"):
            if file.stem not in processed:
                unprocessed.append(file.stem)
        
        return unprocessed
    
    async def consolidate_session(
        self,
        session_id: str,
    ) -> tuple[SessionSummary, list[Memory]]:
        """
        整理单个会话
        
        1. 加载对话历史
        2. 生成会话摘要
        3. 提取记忆
        """
        turns = self.load_session_history(session_id)
        
        if not turns:
            return None, []
        
        # 生成会话摘要
        summary = await self._generate_summary(session_id, turns)
        
        # 提取记忆
        memories = []
        
        # 基于规则提取
        for turn in turns:
            extracted = self.extractor.extract_from_turn(turn)
            memories.extend(extracted)
        
        # 使用 LLM 高级提取
        if self.brain:
            llm_memories = await self.extractor.extract_with_llm(
                turns,
                context=f"会话摘要: {summary.task_description}"
            )
            memories.extend(llm_memories)
        
        # 去重
        memories = self.extractor.deduplicate(memories, [])
        
        # 更新摘要中的记忆 ID
        summary.memories_created = [m.id for m in memories]
        
        # 保存摘要
        self._save_summary(summary)
        
        return summary, memories
    
    async def consolidate_all_unprocessed(self) -> tuple[list[SessionSummary], list[Memory]]:
        """
        整理所有未处理的会话
        
        适合在空闲时段 (如凌晨) 批量执行
        """
        unprocessed = self.get_unprocessed_sessions()
        
        all_summaries = []
        all_memories = []
        
        for session_id in unprocessed:
            try:
                summary, memories = await self.consolidate_session(session_id)
                if summary:
                    all_summaries.append(summary)
                    all_memories.extend(memories)
                    logger.info(f"Consolidated session {session_id}: {len(memories)} memories")
            except Exception as e:
                logger.error(f"Failed to consolidate session {session_id}: {e}")
        
        return all_summaries, all_memories
    
    async def _generate_summary(
        self,
        session_id: str,
        turns: list[ConversationTurn],
    ) -> SessionSummary:
        """使用 LLM 生成会话摘要"""
        
        start_time = turns[0].timestamp if turns else datetime.now()
        end_time = turns[-1].timestamp if turns else datetime.now()
        
        # 简单摘要 (不用 LLM)
        if not self.brain or len(turns) < 3:
            # 从用户消息提取任务描述
            user_messages = [t.content for t in turns if t.role == "user"]
            task_desc = user_messages[0][:200] if user_messages else "Unknown task"
            
            return SessionSummary(
                session_id=session_id,
                start_time=start_time,
                end_time=end_time,
                task_description=task_desc,
                outcome="completed",
            )
        
        # 使用 LLM 生成详细摘要
        conv_text = "\n".join([
            f"[{turn.role}]: {turn.content[:300]}"
            for turn in turns[-30:]  # 最近30轮
        ])
        
        prompt = f"""总结以下对话会话:

{conv_text}

请提供:
1. task_description: 用户的主要任务是什么 (一句话)
2. outcome: 任务结果 (success/partial/failed)
3. key_actions: 关键操作 (最多5个)
4. learnings: 值得记住的经验 (最多3个)
5. errors: 遇到的错误 (如果有)

用 JSON 格式输出。
"""
        
        try:
            response = await self.brain.think(
                prompt,
                system="你是一个会话分析专家，擅长提取关键信息。只输出 JSON，不要其他内容。"
            )
            
            # 解析 JSON
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return SessionSummary(
                    session_id=session_id,
                    start_time=start_time,
                    end_time=end_time,
                    task_description=data.get("task_description", ""),
                    outcome=data.get("outcome", "completed"),
                    key_actions=data.get("key_actions", []),
                    learnings=data.get("learnings", []),
                    errors_encountered=data.get("errors", []),
                )
        except Exception as e:
            logger.error(f"LLM summary generation failed: {e}")
        
        # 回退到简单摘要
        user_messages = [t.content for t in turns if t.role == "user"]
        return SessionSummary(
            session_id=session_id,
            start_time=start_time,
            end_time=end_time,
            task_description=user_messages[0][:200] if user_messages else "Unknown",
            outcome="completed",
        )
    
    def _save_summary(self, summary: SessionSummary) -> None:
        """保存会话摘要"""
        with open(self.summaries_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(summary.to_dict(), ensure_ascii=False) + "\n")
    
    def get_recent_summaries(self, days: int = 7) -> list[SessionSummary]:
        """获取最近N天的会话摘要"""
        if not self.summaries_file.exists():
            return []
        
        cutoff = datetime.now() - timedelta(days=days)
        summaries = []
        
        with open(self.summaries_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    end_time = datetime.fromisoformat(data["end_time"])
                    if end_time > cutoff:
                        summaries.append(SessionSummary(
                            session_id=data["session_id"],
                            start_time=datetime.fromisoformat(data["start_time"]),
                            end_time=end_time,
                            task_description=data.get("task_description", ""),
                            outcome=data.get("outcome", ""),
                            key_actions=data.get("key_actions", []),
                            learnings=data.get("learnings", []),
                            errors_encountered=data.get("errors_encountered", []),
                            memories_created=data.get("memories_created", []),
                        ))
        
        return summaries
    
    def cleanup_old_history(self, days: int = 30) -> int:
        """
        清理旧的对话历史文件
        
        保留摘要和记忆，删除原始对话
        """
        cutoff = datetime.now() - timedelta(days=days)
        deleted = 0
        
        for file in self.history_dir.glob("*.jsonl"):
            mtime = datetime.fromtimestamp(file.stat().st_mtime)
            if mtime < cutoff:
                file.unlink()
                deleted += 1
                logger.info(f"Deleted old history file: {file.name}")
        
        return deleted
