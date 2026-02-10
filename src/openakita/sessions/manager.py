"""
会话管理器

职责:
- 根据 (channel, chat_id, user_id) 获取或创建会话
- 管理会话生命周期
- 隔离不同会话的上下文
- 会话持久化
"""

import asyncio
import contextlib
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .session import Session, SessionConfig, SessionState
from .user import UserManager

# Session 恢复时的上下文清理阈值
SESSION_CONTEXT_STALE_HOURS = 1  # 超过 1 小时未活跃，清理上下文

logger = logging.getLogger(__name__)


class SessionManager:
    """
    会话管理器

    管理所有活跃会话，提供:
    - 会话的创建和获取
    - 会话过期清理
    - 会话持久化
    """

    def __init__(
        self,
        storage_path: Path | None = None,
        default_config: SessionConfig | None = None,
        cleanup_interval_seconds: int = 300,  # 5 分钟清理一次
    ):
        """
        Args:
            storage_path: 会话存储目录
            default_config: 默认会话配置
            cleanup_interval_seconds: 清理间隔（秒）
        """
        self.storage_path = Path(storage_path) if storage_path else Path("data/sessions")
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.default_config = default_config or SessionConfig()
        self.cleanup_interval = cleanup_interval_seconds

        # 活跃会话缓存 {session_key: Session}
        self._sessions: dict[str, Session] = {}

        # 用户管理器
        self.user_manager = UserManager(self.storage_path / "users")

        # 清理任务
        self._cleanup_task: asyncio.Task | None = None
        self._save_task: asyncio.Task | None = None
        self._running = False

        # 脏标志和防抖保存
        self._dirty = False
        self._save_delay_seconds = 5  # 防抖延迟：5 秒内的多次修改只保存一次

        # 加载持久化的会话
        self._load_sessions()

    async def start(self) -> None:
        """启动会话管理器"""
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self._save_task = asyncio.create_task(self._save_loop())
        logger.info("SessionManager started")

    def mark_dirty(self) -> None:
        """标记会话数据已修改，需要保存"""
        self._dirty = True

    async def stop(self) -> None:
        """停止会话管理器"""
        self._running = False

        # 取消清理任务
        if self._cleanup_task:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task

        # 取消保存任务
        if self._save_task:
            self._save_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._save_task

        # 最终保存所有会话
        self._save_sessions()
        logger.info("SessionManager stopped")

    def get_session(
        self,
        channel: str,
        chat_id: str,
        user_id: str,
        create_if_missing: bool = True,
        config: SessionConfig | None = None,
    ) -> Session | None:
        """
        获取或创建会话

        Args:
            channel: 来源通道
            chat_id: 聊天 ID
            user_id: 用户 ID
            create_if_missing: 如果不存在是否创建
            config: 会话配置（创建时使用）

        Returns:
            Session 或 None
        """
        session_key = f"{channel}:{chat_id}:{user_id}"

        # 检查缓存
        if session_key in self._sessions:
            session = self._sessions[session_key]

            # 检查是否过期
            if session.is_expired():
                logger.info(f"Session expired: {session_key}")
                session.mark_expired()
                del self._sessions[session_key]
            else:
                session.touch()
                return session

        # 创建新会话
        if create_if_missing:
            session = self._create_session(channel, chat_id, user_id, config)
            self._sessions[session_key] = session
            logger.info(f"Created new session: {session_key}")
            return session

        return None

    def get_session_by_id(self, session_id: str) -> Session | None:
        """通过 session_id 获取会话"""
        for session in self._sessions.values():
            if session.id == session_id:
                return session
        return None

    def _create_session(
        self,
        channel: str,
        chat_id: str,
        user_id: str,
        config: SessionConfig | None = None,
    ) -> Session:
        """创建新会话"""
        # 合并配置
        session_config = (
            config.merge_with_defaults(self.default_config) if config else self.default_config
        )

        session = Session.create(
            channel=channel,
            chat_id=chat_id,
            user_id=user_id,
            config=session_config,
        )

        # 设置记忆范围
        session.context.memory_scope = f"session_{session.id}"

        return session

    def close_session(self, session_key: str) -> bool:
        """关闭会话"""
        if session_key in self._sessions:
            session = self._sessions[session_key]
            session.close()
            del self._sessions[session_key]
            self.mark_dirty()  # 标记需要保存
            logger.info(f"Closed session: {session_key}")
            return True
        return False

    def list_sessions(
        self,
        channel: str | None = None,
        user_id: str | None = None,
        state: SessionState | None = None,
    ) -> list[Session]:
        """
        列出会话

        Args:
            channel: 过滤通道
            user_id: 过滤用户
            state: 过滤状态
        """
        sessions = list(self._sessions.values())

        if channel:
            sessions = [s for s in sessions if s.channel == channel]
        if user_id:
            sessions = [s for s in sessions if s.user_id == user_id]
        if state:
            sessions = [s for s in sessions if s.state == state]

        return sessions

    def get_session_count(self) -> dict[str, int]:
        """获取会话统计"""
        stats = {
            "total": len(self._sessions),
            "active": 0,
            "idle": 0,
            "by_channel": {},
        }

        for session in self._sessions.values():
            if session.state == SessionState.ACTIVE:
                stats["active"] += 1
            elif session.state == SessionState.IDLE:
                stats["idle"] += 1

            channel = session.channel
            stats["by_channel"][channel] = stats["by_channel"].get(channel, 0) + 1

        return stats

    async def cleanup_expired(self) -> int:
        """清理过期会话"""
        expired_keys = []

        for key, session in self._sessions.items():
            if session.is_expired():
                expired_keys.append(key)

        for key in expired_keys:
            session = self._sessions[key]
            session.mark_expired()
            del self._sessions[key]
            logger.debug(f"Cleaned up expired session: {key}")

        if expired_keys:
            logger.info(f"Cleaned up {len(expired_keys)} expired sessions")

        return len(expired_keys)

    async def _cleanup_loop(self) -> None:
        """定期清理循环"""
        while self._running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self.cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")

    async def _save_loop(self) -> None:
        """
        防抖保存循环

        检测到 dirty 标志后，等待一小段时间再保存，
        这样短时间内的多次修改只会触发一次保存。
        """
        while self._running:
            try:
                await asyncio.sleep(self._save_delay_seconds)

                if self._dirty:
                    self._dirty = False
                    self._save_sessions()

            except asyncio.CancelledError:
                # 退出前最后保存一次
                if self._dirty:
                    self._save_sessions()
                break
            except Exception as e:
                logger.error(f"Error in save loop: {e}")

    def _load_sessions(self) -> None:
        """从文件加载会话"""
        sessions_file = self.storage_path / "sessions.json"

        if not sessions_file.exists():
            return

        try:
            with open(sessions_file, encoding="utf-8") as f:
                data = json.load(f)

            now = datetime.now()
            stale_threshold = now - timedelta(hours=SESSION_CONTEXT_STALE_HOURS)
            cleaned_count = 0

            for item in data:
                try:
                    session = Session.from_dict(item)
                    # 只加载未过期的会话
                    if not session.is_expired() and session.state != SessionState.CLOSED:
                        # 检查上下文是否过期
                        if session.last_active < stale_threshold:
                            # 上下文过期，清理 messages 但保留 session
                            old_count = len(session.context.messages)
                            session.context.clear_messages()
                            session.context.summary = "之前的对话已归档（超过 1 小时未活跃）"
                            cleaned_count += 1
                            logger.info(
                                f"Cleared stale context for session {session.session_key}: "
                                f"{old_count} messages removed (last_active: {session.last_active})"
                            )
                        else:
                            # 上下文未过期，但清理大型数据（如 base64）
                            self._clean_large_content_in_messages(session.context.messages)

                        self._sessions[session.session_key] = session
                except Exception as e:
                    logger.warning(f"Failed to load session: {e}")

            logger.info(
                f"Loaded {len(self._sessions)} sessions from storage (cleaned {cleaned_count} stale contexts)"
            )

        except Exception as e:
            logger.error(f"Failed to load sessions: {e}")

    def _clean_large_content_in_messages(self, messages: list[dict]) -> None:
        """
        清理消息中的大型数据（如 base64 截图）

        这是一个安全措施，防止大型数据在 session 恢复时导致上下文爆炸
        """
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        # 检查 tool_result 中的大型内容
                        if block.get("type") == "tool_result":
                            result_content = block.get("content", "")
                            if isinstance(result_content, str) and len(result_content) > 10000:
                                # 大型内容，检查是否是 base64 图片
                                if "base64" in result_content.lower() or result_content.startswith(
                                    "data:image"
                                ):
                                    block["content"] = "[图片数据已清理，请重新截图]"
                                else:
                                    # 其他大型内容，保留前 2000 字符
                                    block["content"] = (
                                        result_content[:2000]
                                        + f"\n...[内容已截断，原长度: {len(result_content)}]"
                                    )

    def _save_sessions(self) -> None:
        """
        保存会话到文件（原子写入）

        使用临时文件 + 重命名的方式，确保写入过程中断不会损坏原文件
        """
        sessions_file = self.storage_path / "sessions.json"
        temp_file = self.storage_path / "sessions.json.tmp"
        backup_file = self.storage_path / "sessions.json.bak"

        try:
            data = [session.to_dict() for session in self._sessions.values()]

            # 1. 先写入临时文件
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # 2. 验证临时文件可以正确解析
            with open(temp_file, encoding="utf-8") as f:
                json.load(f)  # 验证 JSON 格式正确

            # 3. 备份旧文件（如果存在）
            if sessions_file.exists():
                try:
                    if backup_file.exists():
                        backup_file.unlink()
                    sessions_file.rename(backup_file)
                except Exception as e:
                    logger.warning(f"Failed to backup sessions file: {e}")

            # 4. 原子重命名临时文件为正式文件
            temp_file.rename(sessions_file)

            logger.debug(f"Saved {len(data)} sessions to storage (atomic)")

        except Exception as e:
            logger.error(f"Failed to save sessions: {e}")
            # 清理临时文件
            if temp_file.exists():
                with contextlib.suppress(Exception):
                    temp_file.unlink()

    async def _save_sessions_async(self) -> None:
        """异步保存会话（在线程池中执行同步 I/O）"""
        await asyncio.to_thread(self._save_sessions)

    # ==================== 会话操作快捷方法 ====================

    def add_message(
        self,
        channel: str,
        chat_id: str,
        user_id: str,
        role: str,
        content: str,
        **metadata,
    ) -> Session:
        """添加消息到会话"""
        session = self.get_session(channel, chat_id, user_id)
        session.add_message(role, content, **metadata)
        self.mark_dirty()  # 标记需要保存
        return session

    def get_history(
        self,
        channel: str,
        chat_id: str,
        user_id: str,
        limit: int | None = None,
    ) -> list[dict]:
        """获取会话历史"""
        session = self.get_session(channel, chat_id, user_id, create_if_missing=False)
        if session:
            return session.context.get_messages(limit)
        return []

    def clear_history(
        self,
        channel: str,
        chat_id: str,
        user_id: str,
    ) -> bool:
        """清空会话历史"""
        session = self.get_session(channel, chat_id, user_id, create_if_missing=False)
        if session:
            session.context.clear_messages()
            self.mark_dirty()  # 标记需要保存
            return True
        return False

    def set_variable(
        self,
        channel: str,
        chat_id: str,
        user_id: str,
        key: str,
        value: Any,
    ) -> bool:
        """设置会话变量"""
        session = self.get_session(channel, chat_id, user_id, create_if_missing=False)
        if session:
            session.context.set_variable(key, value)
            self.mark_dirty()  # 标记需要保存
            return True
        return False

    def get_variable(
        self,
        channel: str,
        chat_id: str,
        user_id: str,
        key: str,
        default: Any = None,
    ) -> Any:
        """获取会话变量"""
        session = self.get_session(channel, chat_id, user_id, create_if_missing=False)
        if session:
            return session.context.get_variable(key, default)
        return default
