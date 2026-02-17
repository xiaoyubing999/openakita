"""
在线语音识别 (STT) 客户端

支持 OpenAI 兼容的 /audio/transcriptions API:
- OpenAI Whisper API (gpt-4o-transcribe, whisper-1)
- DashScope Paraformer (paraformer-v2)
- 其他兼容服务商

特性:
- 多端点 failover（按 priority 排序）
- 重试和超时
- 支持格式: mp3, mp4, wav, webm, m4a, ogg
"""

import asyncio
import logging
from pathlib import Path

from .types import EndpointConfig

logger = logging.getLogger(__name__)

# OpenAI /audio/transcriptions 支持的格式
SUPPORTED_AUDIO_FORMATS = {"mp3", "mp4", "mpeg", "mpga", "m4a", "wav", "webm", "ogg", "flac"}


class STTClient:
    """在线语音识别客户端"""

    def __init__(self, endpoints: list[EndpointConfig] | None = None):
        self._endpoints = sorted(endpoints or [], key=lambda x: x.priority)
        if self._endpoints:
            names = [ep.name for ep in self._endpoints]
            logger.info(f"[STT] Initialized with {len(self._endpoints)} endpoints: {names}")

    @property
    def is_available(self) -> bool:
        """检查是否有可用的 STT 端点"""
        return bool(self._endpoints)

    @property
    def endpoints(self) -> list[EndpointConfig]:
        return self._endpoints

    def reload(self, endpoints: list[EndpointConfig] | None = None) -> None:
        """重载端点配置"""
        self._endpoints = sorted(endpoints or [], key=lambda x: x.priority)
        if self._endpoints:
            names = [ep.name for ep in self._endpoints]
            logger.info(f"[STT] Reloaded with {len(self._endpoints)} endpoints: {names}")

    async def transcribe(
        self,
        audio_path: str,
        language: str | None = None,
        timeout: int = 60,
    ) -> str | None:
        """语音转文字

        Args:
            audio_path: 音频文件路径
            language: 语言代码（如 "zh", "en"），可选
            timeout: 请求超时时间（秒）

        Returns:
            转写文本，失败返回 None
        """
        if not self._endpoints:
            logger.warning("[STT] No STT endpoints configured")
            return None

        audio_file = Path(audio_path)
        if not audio_file.exists():
            logger.error(f"[STT] Audio file not found: {audio_path}")
            return None

        last_error = None
        for endpoint in self._endpoints:
            try:
                result = await self._call_endpoint(endpoint, audio_file, language, timeout)
                if result:
                    logger.info(
                        f"[STT] Transcription successful via {endpoint.name}: "
                        f"{result[:50]}{'...' if len(result) > 50 else ''}"
                    )
                    return result
            except Exception as e:
                last_error = e
                logger.warning(f"[STT] Endpoint {endpoint.name} failed: {e}")
                continue

        logger.error(f"[STT] All {len(self._endpoints)} endpoints failed. Last error: {last_error}")
        return None

    async def _call_endpoint(
        self,
        endpoint: EndpointConfig,
        audio_file: Path,
        language: str | None,
        timeout: int,
    ) -> str | None:
        """调用单个 STT 端点"""
        import httpx

        api_key = endpoint.get_api_key()
        if not api_key:
            logger.warning(f"[STT] No API key for endpoint {endpoint.name}")
            return None

        base_url = endpoint.base_url.rstrip("/")
        url = f"{base_url}/audio/transcriptions"
        model = endpoint.model or "whisper-1"

        headers = {"Authorization": f"Bearer {api_key}"}

        # multipart/form-data
        files = {"file": (audio_file.name, audio_file.read_bytes(), "application/octet-stream")}
        data: dict = {"model": model}
        if language:
            data["language"] = language

        loop = asyncio.get_event_loop()

        def _do_request():
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(url, headers=headers, files=files, data=data)
                resp.raise_for_status()
                result = resp.json()
                return result.get("text", "")

        return await loop.run_in_executor(None, _do_request)
