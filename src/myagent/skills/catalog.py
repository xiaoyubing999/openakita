"""
技能目录 (Skill Catalog)

遵循 Agent Skills 规范的渐进式披露:
- Level 1: 技能清单 (name + description) - 在系统提示中提供
- Level 2: 完整指令 (SKILL.md body) - 激活时加载
- Level 3: 资源文件 - 按需加载

技能清单在 Agent 启动时生成，并注入到系统提示中，
让大模型在首次对话时就知道有哪些技能可用。
"""

import logging
from pathlib import Path
from typing import Optional

from .registry import SkillRegistry

logger = logging.getLogger(__name__)


class SkillCatalog:
    """
    技能目录
    
    管理技能清单的生成和格式化，用于系统提示注入。
    """
    
    # 技能清单模板
    CATALOG_TEMPLATE = """
## Available Skills

The following skills are available. Each skill has specialized capabilities.
When a user's request matches a skill's description, use `get_skill_info` to load full instructions.

{skill_list}

### How to Use Skills

1. **Identify relevant skill** from the list above based on user's request
2. **Load skill instructions**: Use `get_skill_info(skill_name)` to get detailed instructions
3. **Run skill scripts**: Use `run_skill_script(skill_name, script_name, args)` if needed
4. **Generate new skills**: If no existing skill matches, use `generate_skill(description)` to create one
"""

    SKILL_ENTRY_TEMPLATE = "- **{name}**: {description}"
    
    def __init__(self, registry: SkillRegistry):
        self.registry = registry
        self._cached_catalog: Optional[str] = None
    
    def generate_catalog(self) -> str:
        """
        生成技能清单
        
        Returns:
            格式化的技能清单字符串
        """
        skills = self.registry.list_all()
        
        if not skills:
            return "\n## Available Skills\n\nNo skills installed. Use `generate_skill` to create new skills.\n"
        
        skill_entries = []
        for skill in skills:
            # 获取简短描述 (第一行或前100字符)
            desc = skill.description
            first_line = desc.split('\n')[0].strip()
            if len(first_line) > 120:
                first_line = first_line[:117] + "..."
            
            entry = self.SKILL_ENTRY_TEMPLATE.format(
                name=skill.name,
                description=first_line,
            )
            skill_entries.append(entry)
        
        skill_list = "\n".join(skill_entries)
        
        catalog = self.CATALOG_TEMPLATE.format(skill_list=skill_list)
        self._cached_catalog = catalog
        
        logger.info(f"Generated skill catalog with {len(skills)} skills")
        return catalog
    
    def get_catalog(self, refresh: bool = False) -> str:
        """
        获取技能清单
        
        Args:
            refresh: 是否强制刷新
        
        Returns:
            技能清单字符串
        """
        if refresh or self._cached_catalog is None:
            return self.generate_catalog()
        return self._cached_catalog
    
    def get_compact_catalog(self) -> str:
        """
        获取紧凑版技能清单 (仅名称列表)
        
        用于 token 受限的场景
        """
        skills = self.registry.list_all()
        if not skills:
            return "No skills installed."
        
        names = [s.name for s in skills]
        return f"Available skills: {', '.join(names)}"
    
    def get_skill_summary(self, skill_name: str) -> Optional[str]:
        """
        获取单个技能的摘要
        
        Args:
            skill_name: 技能名称
        
        Returns:
            技能摘要 (name + description)
        """
        skill = self.registry.get(skill_name)
        if not skill:
            return None
        
        return f"**{skill.name}**: {skill.description}"
    
    def invalidate_cache(self) -> None:
        """使缓存失效"""
        self._cached_catalog = None
    
    @property
    def skill_count(self) -> int:
        """技能数量"""
        return self.registry.count


def generate_skill_catalog(registry: SkillRegistry) -> str:
    """便捷函数：生成技能清单"""
    catalog = SkillCatalog(registry)
    return catalog.generate_catalog()
