"""
MyAgent 自我进化模块
"""

from .analyzer import NeedAnalyzer
from .installer import AutoInstaller
from .generator import SkillGenerator
from .self_check import SelfChecker

__all__ = ["NeedAnalyzer", "AutoInstaller", "SkillGenerator", "SelfChecker"]
