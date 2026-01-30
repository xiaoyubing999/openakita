"""
技能加载器

支持从文件、目录、包动态加载技能。
"""

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Optional, Type

from .base import BaseSkill
from .registry import SkillRegistry

logger = logging.getLogger(__name__)


class SkillLoader:
    """
    技能加载器
    
    支持:
    - 从 Python 文件加载
    - 从目录加载所有技能
    - 从包名加载
    """
    
    def __init__(self, registry: Optional[SkillRegistry] = None):
        self.registry = registry if registry is not None else SkillRegistry()
    
    def load_from_file(self, path: str) -> Optional[BaseSkill]:
        """
        从文件加载技能
        
        文件应该包含一个继承 BaseSkill 的类。
        
        Args:
            path: Python 文件路径
        
        Returns:
            技能实例或 None
        """
        file_path = Path(path)
        
        if not file_path.exists():
            logger.error(f"Skill file not found: {path}")
            return None
        
        if not file_path.suffix == ".py":
            logger.error(f"Not a Python file: {path}")
            return None
        
        try:
            # 动态加载模块
            module_name = f"skill_{file_path.stem}"
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            
            if spec is None or spec.loader is None:
                logger.error(f"Cannot load module spec from: {path}")
                return None
            
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            
            # 查找 BaseSkill 子类
            skill_class = self._find_skill_class(module)
            
            if skill_class is None:
                logger.error(f"No BaseSkill subclass found in: {path}")
                return None
            
            # 实例化并注册
            skill = skill_class()
            self.registry.register(skill)
            
            logger.info(f"Loaded skill from {path}: {skill.name}")
            return skill
            
        except Exception as e:
            logger.error(f"Failed to load skill from {path}: {e}")
            return None
    
    def load_from_directory(
        self,
        directory: str,
        recursive: bool = False,
    ) -> list[BaseSkill]:
        """
        从目录加载所有技能
        
        Args:
            directory: 目录路径
            recursive: 是否递归子目录
        
        Returns:
            加载的技能列表
        """
        dir_path = Path(directory)
        
        if not dir_path.is_dir():
            logger.error(f"Not a directory: {directory}")
            return []
        
        skills = []
        pattern = "**/*.py" if recursive else "*.py"
        
        for file_path in dir_path.glob(pattern):
            # 跳过 __init__.py 和以 _ 开头的文件
            if file_path.name.startswith("_"):
                continue
            
            skill = self.load_from_file(str(file_path))
            if skill:
                skills.append(skill)
        
        logger.info(f"Loaded {len(skills)} skills from {directory}")
        return skills
    
    def load_from_package(self, package_name: str) -> Optional[BaseSkill]:
        """
        从包名加载技能
        
        包应该有一个 skill 或 Skill 类继承自 BaseSkill。
        
        Args:
            package_name: 包名
        
        Returns:
            技能实例或 None
        """
        try:
            module = importlib.import_module(package_name)
            
            skill_class = self._find_skill_class(module)
            
            if skill_class is None:
                logger.error(f"No BaseSkill subclass found in package: {package_name}")
                return None
            
            skill = skill_class()
            self.registry.register(skill)
            
            logger.info(f"Loaded skill from package {package_name}: {skill.name}")
            return skill
            
        except ImportError as e:
            logger.error(f"Cannot import package {package_name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to load skill from package {package_name}: {e}")
            return None
    
    def _find_skill_class(self, module) -> Optional[Type[BaseSkill]]:
        """在模块中查找 BaseSkill 子类"""
        for name in dir(module):
            obj = getattr(module, name)
            
            # 检查是否是类
            if not isinstance(obj, type):
                continue
            
            # 检查是否是 BaseSkill 子类（排除 BaseSkill 本身）
            if issubclass(obj, BaseSkill) and obj is not BaseSkill:
                return obj
        
        return None
    
    def unload(self, name: str) -> bool:
        """
        卸载技能
        
        Args:
            name: 技能名称
        
        Returns:
            是否成功
        """
        return self.registry.unregister(name)
    
    def reload(self, name: str) -> Optional[BaseSkill]:
        """
        重新加载技能（TODO: 需要记录原始路径）
        """
        logger.warning("Reload not yet implemented")
        return None
