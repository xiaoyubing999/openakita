"""
MyAgent 技能系统
"""

from .base import BaseSkill, SkillResult
from .registry import SkillRegistry
from .loader import SkillLoader

__all__ = ["BaseSkill", "SkillResult", "SkillRegistry", "SkillLoader"]
