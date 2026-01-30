"""
MyAgent 配置模块
"""

from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """应用配置"""
    
    # Anthropic API
    anthropic_api_key: str = Field(default="", description="Anthropic API Key")
    anthropic_base_url: str = Field(
        default="https://api.anthropic.com",
        description="Anthropic API Base URL (支持云雾AI等转发服务)"
    )
    default_model: str = Field(
        default="claude-opus-4-5-20251101-thinking",
        description="默认使用的模型"
    )
    max_tokens: int = Field(default=8192, description="最大输出 token 数")
    
    # Agent 配置
    agent_name: str = Field(default="MyAgent", description="Agent 名称")
    max_iterations: int = Field(default=100, description="Ralph 循环最大迭代次数")
    auto_confirm: bool = Field(default=False, description="是否自动确认危险操作")
    
    # 路径配置
    project_root: Path = Field(
        default_factory=lambda: Path.cwd(),
        description="项目根目录 (默认为当前工作目录)"
    )
    database_path: str = Field(default="data/agent.db", description="数据库路径")
    
    # 日志
    log_level: str = Field(default="INFO", description="日志级别")
    
    # GitHub
    github_token: str = Field(default="", description="GitHub Token")
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }
    
    @property
    def soul_path(self) -> Path:
        """SOUL.md 路径"""
        return self.project_root / "SOUL.md"
    
    @property
    def agent_path(self) -> Path:
        """AGENT.md 路径"""
        return self.project_root / "AGENT.md"
    
    @property
    def user_path(self) -> Path:
        """USER.md 路径"""
        return self.project_root / "USER.md"
    
    @property
    def memory_path(self) -> Path:
        """MEMORY.md 路径"""
        return self.project_root / "MEMORY.md"
    
    @property
    def skills_path(self) -> Path:
        """技能目录路径"""
        return self.project_root / "skills"
    
    @property
    def specs_path(self) -> Path:
        """规格文档目录路径"""
        return self.project_root / "specs"
    
    @property
    def db_full_path(self) -> Path:
        """数据库完整路径"""
        return self.project_root / self.database_path


# 全局配置实例
settings = Settings()
