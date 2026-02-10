"""
统一记忆存储

提供 MemoryStorage 接口，统一管理 ChromaDB 和 SQLite 双存储：
- ChromaDB: 向量索引 + 元数据（语义搜索）
- SQLite: 结构化查询 + 全量记忆备份（取代 memories.json）

设计原则:
- 写入时同时写入两处（事务）
- 语义搜索用 ChromaDB
- 精确查询/导出用 SQLite
- 提供 JSON 导出用于备份/迁移
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MemoryStorage:
    """
    统一记忆存储管理器。

    替代 memories.json，使用 SQLite 作为结构化存储，
    与 ChromaDB 向量存储协同工作。

    Usage:
        storage = MemoryStorage(db_path="data/memory/memories.db")
        storage.save_memory(memory_dict)
        memories = storage.load_all()
        results = storage.query(memory_type="FACT", limit=10)
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self) -> None:
        """初始化 SQLite 数据库表"""
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'FACT',
                priority TEXT NOT NULL DEFAULT 'SHORT_TERM',
                source TEXT DEFAULT '',
                importance_score REAL DEFAULT 0.5,
                access_count INTEGER DEFAULT 0,
                tags TEXT DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at TEXT,
                metadata TEXT DEFAULT '{}'
            )
        """)

        # 索引
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memories_priority ON memories(priority)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance_score)"
        )

        self._conn.commit()
        logger.debug(f"MemoryStorage initialized: {self._db_path}")

    def save_memory(self, memory: dict) -> None:
        """
        保存单条记忆到 SQLite。

        Args:
            memory: 记忆字典，包含 id, content, type, priority 等字段
        """
        if not self._conn:
            return

        now = datetime.now().isoformat()
        try:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO memories
                (id, content, type, priority, source, importance_score,
                 access_count, tags, created_at, updated_at, expires_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory.get("id", ""),
                    memory.get("content", ""),
                    memory.get("type", "FACT"),
                    memory.get("priority", "SHORT_TERM"),
                    memory.get("source", ""),
                    memory.get("importance_score", 0.5),
                    memory.get("access_count", 0),
                    json.dumps(memory.get("tags", []), ensure_ascii=False),
                    memory.get("created_at", now),
                    now,
                    memory.get("expires_at"),
                    json.dumps(memory.get("metadata", {}), ensure_ascii=False),
                ),
            )
            self._conn.commit()
        except Exception as e:
            logger.error(f"Failed to save memory to SQLite: {e}")

    def save_memories_batch(self, memories: list[dict]) -> None:
        """批量保存记忆"""
        if not self._conn or not memories:
            return

        now = datetime.now().isoformat()
        try:
            self._conn.executemany(
                """
                INSERT OR REPLACE INTO memories
                (id, content, type, priority, source, importance_score,
                 access_count, tags, created_at, updated_at, expires_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        m.get("id", ""),
                        m.get("content", ""),
                        m.get("type", "FACT"),
                        m.get("priority", "SHORT_TERM"),
                        m.get("source", ""),
                        m.get("importance_score", 0.5),
                        m.get("access_count", 0),
                        json.dumps(m.get("tags", []), ensure_ascii=False),
                        m.get("created_at", now),
                        now,
                        m.get("expires_at"),
                        json.dumps(m.get("metadata", {}), ensure_ascii=False),
                    )
                    for m in memories
                ],
            )
            self._conn.commit()
            logger.debug(f"Batch saved {len(memories)} memories to SQLite")
        except Exception as e:
            logger.error(f"Failed to batch save memories: {e}")

    def load_all(self) -> list[dict]:
        """加载所有记忆"""
        if not self._conn:
            return []

        try:
            cursor = self._conn.execute(
                "SELECT * FROM memories ORDER BY created_at DESC"
            )
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()

            memories = []
            for row in rows:
                memory = dict(zip(columns, row, strict=False))
                # 反序列化 JSON 字段
                memory["tags"] = json.loads(memory.get("tags", "[]"))
                memory["metadata"] = json.loads(memory.get("metadata", "{}"))
                memories.append(memory)

            return memories
        except Exception as e:
            logger.error(f"Failed to load memories from SQLite: {e}")
            return []

    def get_memory(self, memory_id: str) -> dict | None:
        """获取单条记忆"""
        if not self._conn:
            return None

        try:
            cursor = self._conn.execute(
                "SELECT * FROM memories WHERE id = ?", (memory_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None

            columns = [desc[0] for desc in cursor.description]
            memory = dict(zip(columns, row, strict=False))
            memory["tags"] = json.loads(memory.get("tags", "[]"))
            memory["metadata"] = json.loads(memory.get("metadata", "{}"))
            return memory
        except Exception as e:
            logger.error(f"Failed to get memory {memory_id}: {e}")
            return None

    def delete_memory(self, memory_id: str) -> bool:
        """删除单条记忆"""
        if not self._conn:
            return False

        try:
            self._conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            self._conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to delete memory {memory_id}: {e}")
            return False

    def query(
        self,
        *,
        memory_type: str | None = None,
        priority: str | None = None,
        source: str | None = None,
        min_importance: float | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """
        结构化查询记忆。

        Args:
            memory_type: 记忆类型过滤
            priority: 优先级过滤
            source: 来源过滤
            min_importance: 最小重要性分数
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            匹配的记忆列表
        """
        if not self._conn:
            return []

        conditions = []
        params: list[Any] = []

        if memory_type:
            conditions.append("type = ?")
            params.append(memory_type)
        if priority:
            conditions.append("priority = ?")
            params.append(priority)
        if source:
            conditions.append("source = ?")
            params.append(source)
        if min_importance is not None:
            conditions.append("importance_score >= ?")
            params.append(min_importance)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        params.extend([limit, offset])

        try:
            cursor = self._conn.execute(
                f"SELECT * FROM memories WHERE {where_clause} "
                f"ORDER BY importance_score DESC, created_at DESC "
                f"LIMIT ? OFFSET ?",
                params,
            )
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()

            memories = []
            for row in rows:
                memory = dict(zip(columns, row, strict=False))
                memory["tags"] = json.loads(memory.get("tags", "[]"))
                memory["metadata"] = json.loads(memory.get("metadata", "{}"))
                memories.append(memory)

            return memories
        except Exception as e:
            logger.error(f"Failed to query memories: {e}")
            return []

    def count(self, memory_type: str | None = None) -> int:
        """统计记忆数量"""
        if not self._conn:
            return 0

        try:
            if memory_type:
                cursor = self._conn.execute(
                    "SELECT COUNT(*) FROM memories WHERE type = ?", (memory_type,)
                )
            else:
                cursor = self._conn.execute("SELECT COUNT(*) FROM memories")
            return cursor.fetchone()[0]
        except Exception:
            return 0

    def export_json(self, output_path: str | Path) -> int:
        """
        导出所有记忆为 JSON 文件（用于备份/迁移）。

        Args:
            output_path: 输出文件路径

        Returns:
            导出的记忆数量
        """
        memories = self.load_all()
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(memories, f, ensure_ascii=False, indent=2)

        logger.info(f"Exported {len(memories)} memories to {output_path}")
        return len(memories)

    def import_from_json(self, json_path: str | Path) -> int:
        """
        从 JSON 文件导入记忆（用于从 memories.json 迁移）。

        Args:
            json_path: JSON 文件路径

        Returns:
            导入的记忆数量
        """
        json_path = Path(json_path)
        if not json_path.exists():
            logger.warning(f"Import file not found: {json_path}")
            return 0

        try:
            with open(json_path, encoding="utf-8") as f:
                memories = json.load(f)

            if not isinstance(memories, list):
                logger.error(f"Invalid memories format in {json_path}")
                return 0

            self.save_memories_batch(memories)
            logger.info(f"Imported {len(memories)} memories from {json_path}")
            return len(memories)
        except Exception as e:
            logger.error(f"Failed to import memories from {json_path}: {e}")
            return 0

    def cleanup_expired(self) -> int:
        """清理过期记忆"""
        if not self._conn:
            return 0

        now = datetime.now().isoformat()
        try:
            cursor = self._conn.execute(
                "DELETE FROM memories WHERE expires_at IS NOT NULL AND expires_at < ?",
                (now,),
            )
            self._conn.commit()
            count = cursor.rowcount
            if count > 0:
                logger.info(f"Cleaned up {count} expired memories")
            return count
        except Exception as e:
            logger.error(f"Failed to cleanup expired memories: {e}")
            return 0

    def close(self) -> None:
        """关闭数据库连接"""
        if self._conn:
            self._conn.close()
            self._conn = None
