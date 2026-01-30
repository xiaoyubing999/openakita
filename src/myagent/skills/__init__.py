"""
技能系统

遵循 Agent Skills 规范 (agentskills.io/specification)
"""

from .parser import (
    SkillParser,
    SkillMetadata,
    ParsedSkill,
    parse_skill,
    parse_skill_directory,
)

from .registry import (
    SkillRegistry,
    SkillEntry,
    default_registry,
    register_skill,
    get_skill,
)

from .loader import (
    SkillLoader,
    SKILL_DIRECTORIES,
)

__all__ = [
    # Parser
    "SkillParser",
    "SkillMetadata",
    "ParsedSkill",
    "parse_skill",
    "parse_skill_directory",
    # Registry
    "SkillRegistry",
    "SkillEntry",
    "default_registry",
    "register_skill",
    "get_skill",
    # Loader
    "SkillLoader",
    "SKILL_DIRECTORIES",
]
