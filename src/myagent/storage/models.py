"""
数据模型
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class Message:
    """消息"""
    id: Optional[int] = None
    conversation_id: Optional[int] = None
    role: str = "user"  # user, assistant, system
    content: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)


@dataclass
class Conversation:
    """对话"""
    id: Optional[int] = None
    title: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    messages: list[Message] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class SkillRecord:
    """技能记录"""
    id: Optional[int] = None
    name: str = ""
    version: str = ""
    source: str = ""  # github url, pip, local
    installed_at: datetime = field(default_factory=datetime.now)
    last_used: Optional[datetime] = None
    use_count: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class MemoryEntry:
    """记忆条目"""
    id: Optional[int] = None
    category: str = ""  # task, experience, discovery, error
    content: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    importance: int = 0  # 0-10
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class TaskRecord:
    """任务记录"""
    id: Optional[int] = None
    task_id: str = ""
    description: str = ""
    status: str = "pending"  # pending, in_progress, completed, failed
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    attempts: int = 0
    result: Any = None
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class UserPreference:
    """用户偏好"""
    key: str
    value: Any
    updated_at: datetime = field(default_factory=datetime.now)
