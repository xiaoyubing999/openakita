"""
技能注册中心
"""

import logging
from typing import Optional

from .base import BaseSkill, SkillInfo

logger = logging.getLogger(__name__)


class SkillRegistry:
    """
    技能注册中心
    
    管理所有已注册的技能，提供注册、查找、搜索功能。
    """
    
    def __init__(self):
        self._skills: dict[str, BaseSkill] = {}
        self._aliases: dict[str, str] = {}  # alias -> skill name
    
    def register(
        self,
        skill: BaseSkill,
        aliases: Optional[list[str]] = None,
    ) -> None:
        """
        注册技能
        
        Args:
            skill: 技能实例
            aliases: 别名列表
        """
        if skill.name in self._skills:
            logger.warning(f"Skill '{skill.name}' already registered, overwriting")
        
        self._skills[skill.name] = skill
        logger.info(f"Registered skill: {skill.name} v{skill.version}")
        
        # 注册别名
        if aliases:
            for alias in aliases:
                self._aliases[alias] = skill.name
                logger.debug(f"Registered alias '{alias}' -> '{skill.name}'")
    
    def unregister(self, name: str) -> bool:
        """
        取消注册技能
        
        Args:
            name: 技能名称
        
        Returns:
            是否成功
        """
        if name in self._skills:
            del self._skills[name]
            # 清理别名
            self._aliases = {
                alias: skill_name
                for alias, skill_name in self._aliases.items()
                if skill_name != name
            }
            logger.info(f"Unregistered skill: {name}")
            return True
        return False
    
    def get(self, name: str) -> Optional[BaseSkill]:
        """
        获取技能
        
        Args:
            name: 技能名称或别名
        
        Returns:
            技能实例或 None
        """
        # 先检查别名
        if name in self._aliases:
            name = self._aliases[name]
        
        return self._skills.get(name)
    
    def has(self, name: str) -> bool:
        """检查技能是否存在"""
        if name in self._aliases:
            name = self._aliases[name]
        return name in self._skills
    
    def list_all(self) -> list[SkillInfo]:
        """列出所有技能"""
        return [skill.get_info() for skill in self._skills.values()]
    
    def search(
        self,
        query: str,
        tags: Optional[list[str]] = None,
    ) -> list[SkillInfo]:
        """
        搜索技能
        
        Args:
            query: 搜索词（匹配名称或描述）
            tags: 标签过滤
        
        Returns:
            匹配的技能列表
        """
        results = []
        query_lower = query.lower()
        
        for skill in self._skills.values():
            # 匹配名称或描述
            if (
                query_lower in skill.name.lower() or
                query_lower in skill.description.lower()
            ):
                # 检查标签
                if tags:
                    if not any(tag in skill.tags for tag in tags):
                        continue
                
                results.append(skill.get_info())
        
        return results
    
    def get_by_tag(self, tag: str) -> list[SkillInfo]:
        """按标签获取技能"""
        return [
            skill.get_info()
            for skill in self._skills.values()
            if tag in skill.tags
        ]
    
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


# 全局技能注册中心
default_registry = SkillRegistry()


def register_skill(skill: BaseSkill, aliases: Optional[list[str]] = None) -> None:
    """注册技能到默认注册中心"""
    default_registry.register(skill, aliases)


def get_skill(name: str) -> Optional[BaseSkill]:
    """从默认注册中心获取技能"""
    return default_registry.get(name)
