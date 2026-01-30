"""
技能基类
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class SkillResult:
    """技能执行结果"""
    success: bool
    data: Any = None
    error: Optional[str] = None
    duration_ms: float = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class SkillInfo:
    """技能信息"""
    name: str
    description: str
    version: str
    author: str = ""
    tags: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    source: str = ""  # github url or local
    installed_at: Optional[datetime] = None


class BaseSkill(ABC):
    """
    技能基类
    
    所有技能必须继承此类并实现 execute 方法。
    
    示例:
    ```python
    class MySkill(BaseSkill):
        name = "my_skill"
        description = "我的技能"
        version = "1.0.0"
        
        async def execute(self, **kwargs) -> SkillResult:
            # 实现技能逻辑
            return SkillResult(success=True, data="result")
    ```
    """
    
    # 子类必须定义这些属性
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    tags: list[str] = []
    dependencies: list[str] = []
    
    def __init__(self):
        if not self.name:
            raise ValueError("Skill must have a name")
    
    @abstractmethod
    async def execute(self, **kwargs: Any) -> SkillResult:
        """
        执行技能
        
        Args:
            **kwargs: 技能参数
        
        Returns:
            SkillResult
        """
        pass
    
    def get_info(self) -> SkillInfo:
        """获取技能信息"""
        return SkillInfo(
            name=self.name,
            description=self.description,
            version=self.version,
            author=self.author,
            tags=self.tags,
            dependencies=self.dependencies,
        )
    
    def get_schema(self) -> dict:
        """
        获取参数 Schema
        
        子类可以重写此方法提供参数验证 schema
        """
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }
    
    def validate_params(self, params: dict) -> tuple[bool, Optional[str]]:
        """
        验证参数
        
        Args:
            params: 参数字典
        
        Returns:
            (是否有效, 错误消息)
        """
        schema = self.get_schema()
        required = schema.get("required", [])
        
        for key in required:
            if key not in params:
                return False, f"Missing required parameter: {key}"
        
        return True, None
    
    async def __call__(self, **kwargs: Any) -> SkillResult:
        """允许直接调用技能实例"""
        return await self.execute(**kwargs)
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name='{self.name}' version='{self.version}'>"
