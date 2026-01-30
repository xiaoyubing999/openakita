"""
技能注册中心

遵循 Agent Skills 规范 (agentskills.io/specification)
存储和管理技能元数据，支持渐进式披露
"""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .parser import ParsedSkill, SkillMetadata

logger = logging.getLogger(__name__)


@dataclass
class SkillEntry:
    """
    技能注册条目
    
    存储技能的元数据和引用
    支持渐进式披露:
    - Level 1: 元数据 (name, description) - 总是可用
    - Level 2: body (完整指令) - 激活时加载
    - Level 3: scripts/references/assets - 按需加载
    """
    name: str
    description: str
    license: Optional[str] = None
    compatibility: Optional[str] = None
    metadata: dict[str, str] = field(default_factory=dict)
    allowed_tools: list[str] = field(default_factory=list)
    disable_model_invocation: bool = False
    
    # 技能路径 (用于延迟加载)
    skill_path: Optional[str] = None
    
    # 完整技能对象引用 (延迟加载)
    _parsed_skill: Optional["ParsedSkill"] = field(default=None, repr=False)
    
    @classmethod
    def from_parsed_skill(cls, skill: "ParsedSkill") -> "SkillEntry":
        """从 ParsedSkill 创建条目"""
        meta = skill.metadata
        return cls(
            name=meta.name,
            description=meta.description,
            license=meta.license,
            compatibility=meta.compatibility,
            metadata=meta.metadata,
            allowed_tools=meta.allowed_tools,
            disable_model_invocation=meta.disable_model_invocation,
            skill_path=str(skill.path),
            _parsed_skill=skill,
        )
    
    def get_body(self) -> Optional[str]:
        """获取技能 body (Level 2)"""
        if self._parsed_skill:
            return self._parsed_skill.body
        return None
    
    def to_tool_schema(self) -> dict:
        """
        转换为 LLM 工具调用 schema
        
        用于将技能作为工具提供给 LLM
        """
        return {
            "name": f"skill_{self.name.replace('-', '_')}",
            "description": f"[Skill] {self.description}",
            "input_schema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "要执行的操作",
                    },
                    "params": {
                        "type": "object",
                        "description": "操作参数",
                    },
                },
                "required": ["action"],
            },
        }


class SkillRegistry:
    """
    技能注册中心
    
    管理所有已注册的技能，提供:
    - 注册/注销
    - 搜索/查找
    - 渐进式加载
    """
    
    def __init__(self):
        self._skills: dict[str, SkillEntry] = {}
    
    def register(self, skill: "ParsedSkill") -> None:
        """
        注册技能
        
        Args:
            skill: 解析后的技能对象
        """
        entry = SkillEntry.from_parsed_skill(skill)
        
        if entry.name in self._skills:
            logger.warning(f"Skill '{entry.name}' already registered, overwriting")
        
        self._skills[entry.name] = entry
        logger.info(f"Registered skill: {entry.name}")
    
    def unregister(self, name: str) -> bool:
        """
        注销技能
        
        Args:
            name: 技能名称
        
        Returns:
            是否成功
        """
        if name in self._skills:
            del self._skills[name]
            logger.info(f"Unregistered skill: {name}")
            return True
        return False
    
    def get(self, name: str) -> Optional[SkillEntry]:
        """
        获取技能
        
        Args:
            name: 技能名称
        
        Returns:
            SkillEntry 或 None
        """
        return self._skills.get(name)
    
    def has(self, name: str) -> bool:
        """检查技能是否存在"""
        return name in self._skills
    
    def list_all(self) -> list[SkillEntry]:
        """列出所有技能"""
        return list(self._skills.values())
    
    def list_metadata(self) -> list[dict]:
        """
        列出所有技能元数据 (Level 1)
        
        用于启动时向 LLM 展示可用技能
        """
        return [
            {
                "name": skill.name,
                "description": skill.description,
                "auto_invoke": not skill.disable_model_invocation,
            }
            for skill in self._skills.values()
        ]
    
    def search(
        self,
        query: str,
        include_disabled: bool = False,
    ) -> list[SkillEntry]:
        """
        搜索技能
        
        Args:
            query: 搜索词 (匹配名称或描述)
            include_disabled: 是否包含禁用自动调用的技能
        
        Returns:
            匹配的技能列表
        """
        results = []
        query_lower = query.lower()
        
        for skill in self._skills.values():
            if not include_disabled and skill.disable_model_invocation:
                continue
            
            if (
                query_lower in skill.name.lower() or
                query_lower in skill.description.lower()
            ):
                results.append(skill)
        
        return results
    
    def find_relevant(self, context: str) -> list[SkillEntry]:
        """
        根据上下文查找相关技能
        
        用于 Agent 决定是否激活某个技能
        
        Args:
            context: 上下文文本 (如用户输入)
        
        Returns:
            可能相关的技能列表
        """
        relevant = []
        context_lower = context.lower()
        
        for skill in self._skills.values():
            # 跳过禁用自动调用的技能
            if skill.disable_model_invocation:
                continue
            
            # 检查描述中的关键词
            desc_words = skill.description.lower().split()
            for word in desc_words:
                if len(word) > 3 and word in context_lower:
                    relevant.append(skill)
                    break
        
        return relevant
    
    def get_tool_schemas(self) -> list[dict]:
        """
        获取所有技能的工具 schema
        
        用于将技能作为工具提供给 LLM
        """
        return [skill.to_tool_schema() for skill in self._skills.values()]
    
    @property
    def count(self) -> int:
        """技能数量"""
        return len(self._skills)
    
    def __contains__(self, name: str) -> bool:
        return self.has(name)
    
    def __len__(self) -> int:
        return self.count
    
    def __iter__(self):
        return iter(self._skills.values())
    
    def __bool__(self) -> bool:
        """确保空 registry 不被误判为 falsy"""
        return True


# 全局注册中心
default_registry = SkillRegistry()


def register_skill(skill: "ParsedSkill") -> None:
    """注册技能到默认注册中心"""
    default_registry.register(skill)


def get_skill(name: str) -> Optional[SkillEntry]:
    """从默认注册中心获取技能"""
    return default_registry.get(name)
