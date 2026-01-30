"""
SQLite 数据库封装
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import aiosqlite

from ..config import settings
from .models import (
    Conversation,
    MemoryEntry,
    Message,
    SkillRecord,
    TaskRecord,
    UserPreference,
)

logger = logging.getLogger(__name__)


class Database:
    """SQLite 数据库"""
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or settings.db_full_path
        self._connection: Optional[aiosqlite.Connection] = None
    
    async def connect(self) -> None:
        """连接数据库"""
        # 确保目录存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row
        
        await self._init_tables()
        
        logger.info(f"Database connected: {self.db_path}")
    
    async def close(self) -> None:
        """关闭数据库连接"""
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.info("Database connection closed")
    
    async def _init_tables(self) -> None:
        """初始化数据表"""
        await self._connection.executescript("""
            -- 对话表
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT DEFAULT '{}'
            );
            
            -- 消息表
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT DEFAULT '{}',
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            );
            
            -- 技能记录表
            CREATE TABLE IF NOT EXISTS skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                version TEXT,
                source TEXT,
                installed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP,
                use_count INTEGER DEFAULT 0,
                metadata TEXT DEFAULT '{}'
            );
            
            -- 记忆表
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                importance INTEGER DEFAULT 0,
                tags TEXT DEFAULT '[]',
                metadata TEXT DEFAULT '{}'
            );
            
            -- 任务记录表
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT UNIQUE NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                attempts INTEGER DEFAULT 0,
                result TEXT,
                error TEXT,
                metadata TEXT DEFAULT '{}'
            );
            
            -- 用户偏好表
            CREATE TABLE IF NOT EXISTS preferences (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            -- 索引
            CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
            CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
        """)
        await self._connection.commit()
    
    # ===== 对话相关 =====
    
    async def create_conversation(self, title: str = "") -> int:
        """创建对话"""
        cursor = await self._connection.execute(
            "INSERT INTO conversations (title) VALUES (?)",
            (title,),
        )
        await self._connection.commit()
        return cursor.lastrowid
    
    async def get_conversation(self, id: int) -> Optional[Conversation]:
        """获取对话"""
        cursor = await self._connection.execute(
            "SELECT * FROM conversations WHERE id = ?",
            (id,),
        )
        row = await cursor.fetchone()
        
        if not row:
            return None
        
        # 获取消息
        messages = await self.get_messages(id)
        
        return Conversation(
            id=row["id"],
            title=row["title"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            messages=messages,
            metadata=json.loads(row["metadata"]),
        )
    
    async def get_messages(self, conversation_id: int) -> list[Message]:
        """获取对话消息"""
        cursor = await self._connection.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY timestamp",
            (conversation_id,),
        )
        rows = await cursor.fetchall()
        
        return [
            Message(
                id=row["id"],
                conversation_id=row["conversation_id"],
                role=row["role"],
                content=row["content"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                metadata=json.loads(row["metadata"]),
            )
            for row in rows
        ]
    
    async def add_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> int:
        """添加消息"""
        cursor = await self._connection.execute(
            """INSERT INTO messages (conversation_id, role, content, metadata)
               VALUES (?, ?, ?, ?)""",
            (conversation_id, role, content, json.dumps(metadata or {})),
        )
        
        # 更新对话的 updated_at
        await self._connection.execute(
            "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (conversation_id,),
        )
        
        await self._connection.commit()
        return cursor.lastrowid
    
    # ===== 技能相关 =====
    
    async def record_skill(
        self,
        name: str,
        version: str,
        source: str,
        metadata: Optional[dict] = None,
    ) -> int:
        """记录技能安装"""
        cursor = await self._connection.execute(
            """INSERT OR REPLACE INTO skills (name, version, source, metadata)
               VALUES (?, ?, ?, ?)""",
            (name, version, source, json.dumps(metadata or {})),
        )
        await self._connection.commit()
        return cursor.lastrowid
    
    async def get_skill(self, name: str) -> Optional[SkillRecord]:
        """获取技能记录"""
        cursor = await self._connection.execute(
            "SELECT * FROM skills WHERE name = ?",
            (name,),
        )
        row = await cursor.fetchone()
        
        if not row:
            return None
        
        return SkillRecord(
            id=row["id"],
            name=row["name"],
            version=row["version"],
            source=row["source"],
            installed_at=datetime.fromisoformat(row["installed_at"]),
            last_used=datetime.fromisoformat(row["last_used"]) if row["last_used"] else None,
            use_count=row["use_count"],
            metadata=json.loads(row["metadata"]),
        )
    
    async def update_skill_usage(self, name: str) -> None:
        """更新技能使用记录"""
        await self._connection.execute(
            """UPDATE skills 
               SET last_used = CURRENT_TIMESTAMP, use_count = use_count + 1
               WHERE name = ?""",
            (name,),
        )
        await self._connection.commit()
    
    async def list_skills(self) -> list[SkillRecord]:
        """列出所有技能"""
        cursor = await self._connection.execute(
            "SELECT * FROM skills ORDER BY installed_at DESC"
        )
        rows = await cursor.fetchall()
        
        return [
            SkillRecord(
                id=row["id"],
                name=row["name"],
                version=row["version"],
                source=row["source"],
                installed_at=datetime.fromisoformat(row["installed_at"]),
                last_used=datetime.fromisoformat(row["last_used"]) if row["last_used"] else None,
                use_count=row["use_count"],
                metadata=json.loads(row["metadata"]),
            )
            for row in rows
        ]
    
    # ===== 记忆相关 =====
    
    async def add_memory(
        self,
        category: str,
        content: str,
        importance: int = 0,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
    ) -> int:
        """添加记忆"""
        cursor = await self._connection.execute(
            """INSERT INTO memories (category, content, importance, tags, metadata)
               VALUES (?, ?, ?, ?, ?)""",
            (
                category,
                content,
                importance,
                json.dumps(tags or []),
                json.dumps(metadata or {}),
            ),
        )
        await self._connection.commit()
        return cursor.lastrowid
    
    async def get_memories(
        self,
        category: Optional[str] = None,
        limit: int = 100,
        min_importance: int = 0,
    ) -> list[MemoryEntry]:
        """获取记忆"""
        query = "SELECT * FROM memories WHERE importance >= ?"
        params: list[Any] = [min_importance]
        
        if category:
            query += " AND category = ?"
            params.append(category)
        
        query += " ORDER BY importance DESC, created_at DESC LIMIT ?"
        params.append(limit)
        
        cursor = await self._connection.execute(query, params)
        rows = await cursor.fetchall()
        
        return [
            MemoryEntry(
                id=row["id"],
                category=row["category"],
                content=row["content"],
                created_at=datetime.fromisoformat(row["created_at"]),
                importance=row["importance"],
                tags=json.loads(row["tags"]),
                metadata=json.loads(row["metadata"]),
            )
            for row in rows
        ]
    
    async def search_memories(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        """搜索记忆"""
        cursor = await self._connection.execute(
            """SELECT * FROM memories 
               WHERE content LIKE ? 
               ORDER BY importance DESC, created_at DESC 
               LIMIT ?""",
            (f"%{query}%", limit),
        )
        rows = await cursor.fetchall()
        
        return [
            MemoryEntry(
                id=row["id"],
                category=row["category"],
                content=row["content"],
                created_at=datetime.fromisoformat(row["created_at"]),
                importance=row["importance"],
                tags=json.loads(row["tags"]),
                metadata=json.loads(row["metadata"]),
            )
            for row in rows
        ]
    
    # ===== 任务相关 =====
    
    async def record_task(
        self,
        task_id: str,
        description: str,
        status: str = "pending",
    ) -> int:
        """记录任务"""
        cursor = await self._connection.execute(
            """INSERT OR REPLACE INTO tasks (task_id, description, status)
               VALUES (?, ?, ?)""",
            (task_id, description, status),
        )
        await self._connection.commit()
        return cursor.lastrowid
    
    async def update_task(
        self,
        task_id: str,
        status: Optional[str] = None,
        result: Any = None,
        error: Optional[str] = None,
        attempts: Optional[int] = None,
    ) -> None:
        """更新任务"""
        updates = []
        params = []
        
        if status:
            updates.append("status = ?")
            params.append(status)
            if status == "completed":
                updates.append("completed_at = CURRENT_TIMESTAMP")
        
        if result is not None:
            updates.append("result = ?")
            params.append(json.dumps(result))
        
        if error is not None:
            updates.append("error = ?")
            params.append(error)
        
        if attempts is not None:
            updates.append("attempts = ?")
            params.append(attempts)
        
        if updates:
            params.append(task_id)
            await self._connection.execute(
                f"UPDATE tasks SET {', '.join(updates)} WHERE task_id = ?",
                params,
            )
            await self._connection.commit()
    
    # ===== 偏好相关 =====
    
    async def set_preference(self, key: str, value: Any) -> None:
        """设置偏好"""
        await self._connection.execute(
            """INSERT OR REPLACE INTO preferences (key, value, updated_at)
               VALUES (?, ?, CURRENT_TIMESTAMP)""",
            (key, json.dumps(value)),
        )
        await self._connection.commit()
    
    async def get_preference(self, key: str, default: Any = None) -> Any:
        """获取偏好"""
        cursor = await self._connection.execute(
            "SELECT value FROM preferences WHERE key = ?",
            (key,),
        )
        row = await cursor.fetchone()
        
        if row:
            return json.loads(row["value"])
        return default
    
    async def get_all_preferences(self) -> dict[str, Any]:
        """获取所有偏好"""
        cursor = await self._connection.execute("SELECT key, value FROM preferences")
        rows = await cursor.fetchall()
        
        return {row["key"]: json.loads(row["value"]) for row in rows}
