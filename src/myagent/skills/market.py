"""
技能市场

从 GitHub 搜索和安装技能。
"""

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..tools.web import WebTool
from ..tools.shell import ShellTool
from ..config import settings
from .base import BaseSkill, SkillInfo
from .loader import SkillLoader
from .registry import SkillRegistry

logger = logging.getLogger(__name__)


@dataclass
class RemoteSkillInfo:
    """远程技能信息"""
    name: str
    description: str
    url: str
    stars: int = 0
    language: str = ""
    topics: list[str] = None
    
    def __post_init__(self):
        if self.topics is None:
            self.topics = []


class SkillMarket:
    """
    技能市场
    
    从 GitHub 搜索、下载、安装技能。
    """
    
    def __init__(
        self,
        registry: Optional[SkillRegistry] = None,
        skills_dir: Optional[Path] = None,
    ):
        self.registry = registry or SkillRegistry()
        self.skills_dir = skills_dir or settings.skills_path
        self.web = WebTool()
        self.shell = ShellTool()
        self.loader = SkillLoader(self.registry)
    
    async def search(
        self,
        query: str,
        language: str = "python",
        limit: int = 10,
    ) -> list[RemoteSkillInfo]:
        """
        搜索 GitHub 上的技能
        
        Args:
            query: 搜索词
            language: 编程语言
            limit: 结果数量
        
        Returns:
            远程技能信息列表
        """
        # 构建搜索词
        search_query = f"{query} skill OR plugin OR tool"
        
        results = await self.web.search_github(
            search_query,
            language=language,
            limit=limit,
        )
        
        skills = []
        for result in results:
            # 解析仓库信息
            parts = result.title.split("/")
            if len(parts) != 2:
                continue
            
            skills.append(RemoteSkillInfo(
                name=parts[1],
                description=result.snippet or "",
                url=result.url,
            ))
        
        return skills
    
    async def install(
        self,
        url: str,
        name: Optional[str] = None,
    ) -> Optional[BaseSkill]:
        """
        从 GitHub URL 安装技能
        
        Args:
            url: GitHub 仓库 URL
            name: 技能名称（可选，默认从 URL 推断）
        
        Returns:
            安装的技能或 None
        """
        logger.info(f"Installing skill from: {url}")
        
        # 解析 URL
        if "github.com" not in url:
            logger.error("Only GitHub URLs are supported")
            return None
        
        # 从 URL 提取仓库名
        parts = url.rstrip("/").split("/")
        if len(parts) < 2:
            logger.error(f"Invalid GitHub URL: {url}")
            return None
        
        repo_name = parts[-1]
        skill_name = name or repo_name
        
        # 目标目录
        target_dir = self.skills_dir / skill_name
        
        if target_dir.exists():
            logger.warning(f"Skill directory already exists: {target_dir}")
            # 可以选择更新或跳过
        
        # 克隆仓库
        result = await self.shell.git_clone(url, str(target_dir))
        
        if not result.success:
            logger.error(f"Failed to clone repository: {result.stderr}")
            return None
        
        logger.info(f"Cloned to: {target_dir}")
        
        # 查找并加载技能
        # 优先查找 skill.py 或 main.py
        skill_file = None
        for filename in ["skill.py", "main.py", f"{skill_name}.py"]:
            file_path = target_dir / filename
            if file_path.exists():
                skill_file = file_path
                break
        
        if skill_file is None:
            # 查找任何包含 BaseSkill 的 .py 文件
            for py_file in target_dir.glob("*.py"):
                if py_file.name.startswith("_"):
                    continue
                content = py_file.read_text(encoding="utf-8")
                if "BaseSkill" in content:
                    skill_file = py_file
                    break
        
        if skill_file is None:
            logger.error(f"No skill file found in: {target_dir}")
            return None
        
        # 安装依赖（如果有 requirements.txt）
        req_file = target_dir / "requirements.txt"
        if req_file.exists():
            logger.info("Installing dependencies...")
            await self.shell.run(f"pip install -r {req_file}")
        
        # 加载技能
        skill = self.loader.load_from_file(str(skill_file))
        
        if skill:
            logger.info(f"Successfully installed skill: {skill.name}")
        
        return skill
    
    async def install_from_pip(self, package: str) -> Optional[BaseSkill]:
        """
        通过 pip 安装技能包
        
        Args:
            package: 包名
        
        Returns:
            安装的技能或 None
        """
        logger.info(f"Installing package: {package}")
        
        result = await self.shell.pip_install(package)
        
        if not result.success:
            logger.error(f"Failed to install package: {result.stderr}")
            return None
        
        # 尝试从包加载技能
        skill = self.loader.load_from_package(package)
        
        return skill
    
    async def update(self, name: str) -> Optional[BaseSkill]:
        """
        更新技能
        
        Args:
            name: 技能名称
        
        Returns:
            更新后的技能或 None
        """
        skill_dir = self.skills_dir / name
        
        if not skill_dir.exists():
            logger.error(f"Skill not found: {name}")
            return None
        
        # 检查是否是 git 仓库
        git_dir = skill_dir / ".git"
        if not git_dir.exists():
            logger.error(f"Not a git repository: {skill_dir}")
            return None
        
        # 拉取更新
        result = await self.shell.run("git pull", cwd=str(skill_dir))
        
        if not result.success:
            logger.error(f"Failed to update: {result.stderr}")
            return None
        
        # 重新加载技能
        self.registry.unregister(name)
        
        # 查找技能文件
        for py_file in skill_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            content = py_file.read_text(encoding="utf-8")
            if "BaseSkill" in content:
                return self.loader.load_from_file(str(py_file))
        
        return None
    
    async def uninstall(self, name: str) -> bool:
        """
        卸载技能
        
        Args:
            name: 技能名称
        
        Returns:
            是否成功
        """
        # 取消注册
        self.registry.unregister(name)
        
        # 删除目录
        skill_dir = self.skills_dir / name
        if skill_dir.exists():
            import shutil
            shutil.rmtree(skill_dir)
            logger.info(f"Removed skill directory: {skill_dir}")
        
        return True
    
    def list_installed(self) -> list[SkillInfo]:
        """列出已安装的技能"""
        return self.registry.list_all()
