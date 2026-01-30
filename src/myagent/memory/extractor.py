"""
记忆提取器 - 从对话中自动提取记忆

功能:
1. 实时提取: 任务完成时提取关键信息
2. 分类评分: 自动判断类型和重要性
3. 去重合并: 避免重复记忆
"""

import re
import logging
from typing import Optional
from datetime import datetime

from .types import Memory, MemoryType, MemoryPriority, ConversationTurn

logger = logging.getLogger(__name__)


class MemoryExtractor:
    """记忆提取器"""
    
    # 提取规则: 关键词 -> (类型, 优先级, 重要性基础分)
    EXTRACTION_RULES = {
        # 用户偏好
        "喜欢": (MemoryType.PREFERENCE, MemoryPriority.LONG_TERM, 0.7),
        "偏好": (MemoryType.PREFERENCE, MemoryPriority.LONG_TERM, 0.7),
        "习惯": (MemoryType.PREFERENCE, MemoryPriority.LONG_TERM, 0.6),
        "prefer": (MemoryType.PREFERENCE, MemoryPriority.LONG_TERM, 0.7),
        
        # 事实信息
        "我是": (MemoryType.FACT, MemoryPriority.PERMANENT, 0.8),
        "我的": (MemoryType.FACT, MemoryPriority.LONG_TERM, 0.6),
        "使用": (MemoryType.FACT, MemoryPriority.SHORT_TERM, 0.5),
        "工作": (MemoryType.FACT, MemoryPriority.LONG_TERM, 0.6),
        
        # 成功模式
        "成功": (MemoryType.SKILL, MemoryPriority.LONG_TERM, 0.8),
        "解决": (MemoryType.SKILL, MemoryPriority.LONG_TERM, 0.7),
        "有效": (MemoryType.SKILL, MemoryPriority.LONG_TERM, 0.7),
        "works": (MemoryType.SKILL, MemoryPriority.LONG_TERM, 0.7),
        
        # 错误教训
        "失败": (MemoryType.ERROR, MemoryPriority.LONG_TERM, 0.8),
        "错误": (MemoryType.ERROR, MemoryPriority.LONG_TERM, 0.7),
        "问题": (MemoryType.ERROR, MemoryPriority.SHORT_TERM, 0.5),
        "bug": (MemoryType.ERROR, MemoryPriority.LONG_TERM, 0.7),
        
        # 规则约束
        "不要": (MemoryType.RULE, MemoryPriority.PERMANENT, 0.9),
        "禁止": (MemoryType.RULE, MemoryPriority.PERMANENT, 0.9),
        "必须": (MemoryType.RULE, MemoryPriority.LONG_TERM, 0.8),
        "always": (MemoryType.RULE, MemoryPriority.LONG_TERM, 0.8),
        "never": (MemoryType.RULE, MemoryPriority.PERMANENT, 0.9),
    }
    
    def __init__(self, brain=None):
        """
        Args:
            brain: LLM 大脑实例 (可选，用于高级提取)
        """
        self.brain = brain
    
    def extract_from_turn(self, turn: ConversationTurn) -> list[Memory]:
        """
        从单个对话轮次提取记忆
        
        主要提取用户的输入中的重要信息
        """
        memories = []
        
        if turn.role != "user":
            return memories
        
        content = turn.content.lower()
        
        # 基于规则提取
        for keyword, (mem_type, priority, base_score) in self.EXTRACTION_RULES.items():
            if keyword.lower() in content:
                # 提取包含关键词的句子
                sentences = self._extract_relevant_sentences(turn.content, keyword)
                for sentence in sentences:
                    if len(sentence) > 10:  # 过滤太短的句子
                        memory = Memory(
                            type=mem_type,
                            priority=priority,
                            content=sentence.strip(),
                            source="conversation",
                            importance_score=base_score,
                            tags=[keyword],
                        )
                        memories.append(memory)
        
        return memories
    
    def extract_from_task_completion(
        self,
        task_description: str,
        success: bool,
        tool_calls: list[dict],
        errors: list[str],
    ) -> list[Memory]:
        """
        从任务完成结果中提取记忆
        
        这是最重要的记忆来源
        """
        memories = []
        
        if success:
            # 记录成功模式
            memory = Memory(
                type=MemoryType.SKILL,
                priority=MemoryPriority.LONG_TERM,
                content=f"成功完成任务: {task_description}",
                source="task_completion",
                importance_score=0.8,
                tags=["success", "pattern"],
            )
            memories.append(memory)
            
            # 提取使用的工具组合
            if tool_calls:
                tools_used = list(set(tc.get("name", "") for tc in tool_calls if tc.get("name")))
                if tools_used:
                    memory = Memory(
                        type=MemoryType.SKILL,
                        priority=MemoryPriority.LONG_TERM,
                        content=f"任务 '{task_description[:50]}...' 使用工具: {', '.join(tools_used)}",
                        source="task_completion",
                        importance_score=0.6,
                        tags=["tools", "pattern"] + tools_used[:3],
                    )
                    memories.append(memory)
        else:
            # 记录失败教训
            memory = Memory(
                type=MemoryType.ERROR,
                priority=MemoryPriority.LONG_TERM,
                content=f"任务失败: {task_description}",
                source="task_completion",
                importance_score=0.7,
                tags=["failure"],
            )
            memories.append(memory)
            
            # 记录具体错误
            for error in errors[:3]:  # 最多记录3个错误
                memory = Memory(
                    type=MemoryType.ERROR,
                    priority=MemoryPriority.LONG_TERM,
                    content=f"错误: {error[:200]}",
                    source="task_completion",
                    importance_score=0.8,
                    tags=["error", "lesson"],
                )
                memories.append(memory)
        
        return memories
    
    async def extract_with_llm(
        self,
        conversation: list[ConversationTurn],
        context: str = "",
    ) -> list[Memory]:
        """
        使用 LLM 进行高级记忆提取
        
        适用于:
        - 批量整理对话历史
        - 提取复杂的隐含信息
        """
        if not self.brain:
            logger.warning("LLM brain not available for advanced extraction")
            return []
        
        # 构建对话文本
        conv_text = "\n".join([
            f"[{turn.role}]: {turn.content[:500]}"
            for turn in conversation[-20:]  # 最近20轮
        ])
        
        prompt = f"""分析以下对话，提取值得记住的信息。

对话内容:
{conv_text}

{f"上下文: {context}" if context else ""}

请提取以下类型的信息:
1. **用户偏好** (PREFERENCE): 用户喜欢或不喜欢什么
2. **事实信息** (FACT): 关于用户或项目的事实
3. **成功模式** (SKILL): 有效的解决方案或方法
4. **错误教训** (ERROR): 需要避免的错误
5. **规则约束** (RULE): 必须遵守的规则

每条记忆用以下格式输出:
- [类型] 内容 | 重要性(0.1-1.0) | 标签(逗号分隔)

只输出真正有价值的信息，不要输出显而易见的内容。
最多输出10条记忆。
"""
        
        try:
            response = await self.brain.think(
                prompt,
                system="你是一个记忆提取专家，擅长从对话中识别关键信息。"
            )
            
            return self._parse_llm_response(response)
            
        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            return []
    
    def _extract_relevant_sentences(self, text: str, keyword: str) -> list[str]:
        """提取包含关键词的句子"""
        # 按句子分割
        sentences = re.split(r'[。！？\n]', text)
        relevant = []
        
        for sentence in sentences:
            if keyword.lower() in sentence.lower():
                relevant.append(sentence.strip())
        
        return relevant[:3]  # 最多返回3句
    
    def _parse_llm_response(self, response: str) -> list[Memory]:
        """解析 LLM 响应"""
        memories = []
        
        # 匹配格式: - [类型] 内容 | 重要性 | 标签
        pattern = r'-\s*\[(\w+)\]\s*(.+?)\s*\|\s*([\d.]+)\s*\|\s*(.+)'
        
        for match in re.finditer(pattern, response):
            type_str, content, importance, tags_str = match.groups()
            
            # 映射类型
            type_map = {
                "PREFERENCE": MemoryType.PREFERENCE,
                "FACT": MemoryType.FACT,
                "SKILL": MemoryType.SKILL,
                "ERROR": MemoryType.ERROR,
                "RULE": MemoryType.RULE,
            }
            
            mem_type = type_map.get(type_str.upper(), MemoryType.FACT)
            
            # 解析标签
            tags = [t.strip() for t in tags_str.split(",") if t.strip()]
            
            # 根据重要性确定优先级
            importance_score = float(importance)
            if importance_score >= 0.8:
                priority = MemoryPriority.PERMANENT
            elif importance_score >= 0.6:
                priority = MemoryPriority.LONG_TERM
            else:
                priority = MemoryPriority.SHORT_TERM
            
            memory = Memory(
                type=mem_type,
                priority=priority,
                content=content.strip(),
                source="llm_extraction",
                importance_score=importance_score,
                tags=tags,
            )
            memories.append(memory)
        
        return memories
    
    def deduplicate(self, memories: list[Memory], existing: list[Memory]) -> list[Memory]:
        """
        去重合并记忆
        
        避免存储重复或相似的记忆
        """
        unique = []
        existing_contents = set(m.content.lower()[:50] for m in existing)
        
        for memory in memories:
            content_key = memory.content.lower()[:50]
            if content_key not in existing_contents:
                unique.append(memory)
                existing_contents.add(content_key)
        
        return unique
