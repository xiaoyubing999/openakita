"""
技能生成器

使用 LLM 自动生成技能代码。
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..core.brain import Brain
from ..skills.base import BaseSkill
from ..skills.loader import SkillLoader
from ..skills.registry import SkillRegistry
from ..tools.file import FileTool
from ..tools.shell import ShellTool
from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class GenerationResult:
    """生成结果"""
    success: bool
    skill_name: str
    code: str
    file_path: Optional[str] = None
    error: Optional[str] = None
    test_passed: bool = False


class SkillGenerator:
    """
    技能生成器
    
    使用 LLM 根据描述自动生成技能代码。
    """
    
    def __init__(
        self,
        brain: Brain,
        skills_dir: Optional[Path] = None,
        skill_registry: Optional[SkillRegistry] = None,
    ):
        self.brain = brain
        self.skills_dir = skills_dir or settings.skills_path
        self.registry = skill_registry or SkillRegistry()
        self.loader = SkillLoader(self.registry)
        self.file_tool = FileTool()
        self.shell = ShellTool()
    
    async def generate(self, description: str, name: Optional[str] = None) -> GenerationResult:
        """
        生成技能
        
        Args:
            description: 技能描述
            name: 技能名称（可选）
        
        Returns:
            GenerationResult
        """
        logger.info(f"Generating skill: {description[:100]}...")
        
        # 生成技能名称
        if not name:
            name = await self._generate_name(description)
        
        # 生成代码
        code = await self._generate_code(name, description)
        
        if not code:
            return GenerationResult(
                success=False,
                skill_name=name,
                code="",
                error="代码生成失败",
            )
        
        # 保存文件
        file_path = self.skills_dir / f"{name}.py"
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        
        await self.file_tool.write(str(file_path), code)
        
        # 测试代码
        test_passed = await self._test_code(file_path)
        
        if not test_passed:
            # 尝试修复
            logger.info("Initial test failed, attempting to fix...")
            code = await self._fix_code(code, name)
            
            if code:
                await self.file_tool.write(str(file_path), code)
                test_passed = await self._test_code(file_path)
        
        # 加载技能
        if test_passed:
            try:
                self.loader.load_from_file(str(file_path))
            except Exception as e:
                logger.error(f"Failed to load generated skill: {e}")
                test_passed = False
        
        return GenerationResult(
            success=test_passed,
            skill_name=name,
            code=code,
            file_path=str(file_path),
            test_passed=test_passed,
        )
    
    async def _generate_name(self, description: str) -> str:
        """生成技能名称"""
        prompt = f"""为以下功能生成一个简短的 Python 模块名称（snake_case 格式）:

{description}

只返回名称，不要解释。例如: web_scraper, data_processor, file_converter"""

        response = await self.brain.think(prompt)
        name = response.content.strip().lower().replace("-", "_").replace(" ", "_")
        
        # 清理名称
        import re
        name = re.sub(r"[^a-z0-9_]", "", name)
        
        if not name:
            name = "custom_skill"
        
        return name
    
    async def _generate_code(self, name: str, description: str) -> str:
        """生成技能代码"""
        prompt = f'''请生成一个 Python 技能模块，实现以下功能:

功能描述: {description}
技能名称: {name}

要求:
1. 必须继承 BaseSkill 类
2. 实现 execute 方法
3. 包含完整的类型提示
4. 包含 docstring
5. 处理可能的异常

模板:
```python
"""
{name} 技能
"""

from typing import Any, Optional
from myagent.skills.base import BaseSkill, SkillResult


class {name.title().replace("_", "")}Skill(BaseSkill):
    """
    {description}
    """
    
    name = "{name}"
    description = "{description}"
    version = "1.0.0"
    
    async def execute(self, **kwargs: Any) -> SkillResult:
        """
        执行技能
        
        Args:
            **kwargs: 参数
        
        Returns:
            SkillResult
        """
        try:
            # 实现逻辑
            result = ...
            
            return SkillResult(success=True, data=result)
        except Exception as e:
            return SkillResult(success=False, error=str(e))
```

请生成完整的代码。只输出代码，不要解释。'''

        response = await self.brain.think(prompt)
        
        # 提取代码
        code = response.content
        if "```python" in code:
            start = code.find("```python") + 9
            end = code.find("```", start)
            if end > start:
                code = code[start:end].strip()
        elif "```" in code:
            start = code.find("```") + 3
            end = code.find("```", start)
            if end > start:
                code = code[start:end].strip()
        
        return code
    
    async def _test_code(self, file_path: Path) -> bool:
        """测试生成的代码"""
        logger.info(f"Testing code: {file_path}")
        
        # 语法检查
        result = await self.shell.run(f"python -m py_compile {file_path}")
        
        if not result.success:
            logger.error(f"Syntax error: {result.stderr}")
            return False
        
        # 尝试导入
        test_code = f'''
import sys
sys.path.insert(0, "{file_path.parent}")
try:
    import {file_path.stem}
    print("Import OK")
except Exception as e:
    print(f"Import Error: {{e}}")
    sys.exit(1)
'''
        
        result = await self.shell.run(f'python -c "{test_code}"')
        
        if not result.success:
            logger.error(f"Import error: {result.output}")
            return False
        
        logger.info("Code test passed")
        return True
    
    async def _fix_code(self, code: str, name: str) -> Optional[str]:
        """尝试修复代码错误"""
        prompt = f"""以下 Python 代码有错误，请修复:

```python
{code}
```

要求:
1. 修复所有语法错误
2. 修复导入错误
3. 确保可以正常导入和执行
4. 保持原有功能

只输出修复后的完整代码，不要解释。"""

        response = await self.brain.think(prompt)
        
        fixed_code = response.content
        if "```python" in fixed_code:
            start = fixed_code.find("```python") + 9
            end = fixed_code.find("```", start)
            if end > start:
                fixed_code = fixed_code[start:end].strip()
        
        return fixed_code
    
    async def improve(self, skill_name: str, feedback: str) -> GenerationResult:
        """
        根据反馈改进技能
        
        Args:
            skill_name: 技能名称
            feedback: 反馈
        
        Returns:
            GenerationResult
        """
        file_path = self.skills_dir / f"{skill_name}.py"
        
        if not file_path.exists():
            return GenerationResult(
                success=False,
                skill_name=skill_name,
                code="",
                error="技能文件不存在",
            )
        
        current_code = await self.file_tool.read(str(file_path))
        
        prompt = f"""请根据反馈改进以下技能代码:

当前代码:
```python
{current_code}
```

反馈:
{feedback}

请输出改进后的完整代码，不要解释。"""

        response = await self.brain.think(prompt)
        
        improved_code = response.content
        if "```python" in improved_code:
            start = improved_code.find("```python") + 9
            end = improved_code.find("```", start)
            if end > start:
                improved_code = improved_code[start:end].strip()
        
        # 保存并测试
        await self.file_tool.write(str(file_path), improved_code)
        test_passed = await self._test_code(file_path)
        
        return GenerationResult(
            success=test_passed,
            skill_name=skill_name,
            code=improved_code,
            file_path=str(file_path),
            test_passed=test_passed,
        )
