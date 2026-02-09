"""
企业微信适配器

基于企业微信 API 实现:
- 内置 aiohttp HTTP 服务器接收回调消息
- 消息加解密（官方 WXBizMsgCrypt 算法，基于 PyCryptodome）
- 文本/图片/语音/文件/视频收发

参考文档:
- 接收消息: https://developer.work.weixin.qq.com/document/path/90930
- 加解密方案: https://developer.work.weixin.qq.com/document/path/90968
- 发送消息: https://developer.work.weixin.qq.com/document/path/90236
"""

import asyncio
import base64
import hashlib
import logging
import struct
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..base import ChannelAdapter
from ..types import (
    MediaFile,
    MediaStatus,
    MessageContent,
    OutgoingMessage,
    UnifiedMessage,
)

logger = logging.getLogger(__name__)

# 延迟导入
httpx = None
aiohttp = None


def _import_httpx():
    global httpx
    if httpx is None:
        import httpx as hx

        httpx = hx


def _import_aiohttp():
    global aiohttp
    if aiohttp is None:
        try:
            import aiohttp as ah

            aiohttp = ah
        except ImportError:
            raise ImportError(
                "aiohttp not installed. Run: pip install aiohttp"
            )


# ==================== 消息加解密工具 ====================


class WXBizMsgCrypt:
    """
    企业微信消息加解密工具

    基于官方 Python 示例实现，使用 PyCryptodome 进行 AES-256-CBC 加解密。
    参考: https://developer.work.weixin.qq.com/document/path/90968
    """

    def __init__(self, token: str, encoding_aes_key: str, corp_id: str):
        self.token = token
        self.corp_id = corp_id
        # EncodingAESKey 是 Base64 编码的 AES 密钥（43 字符 -> 32 字节）
        self.aes_key = base64.b64decode(encoding_aes_key + "=")

    def _get_sha1(self, *args: str) -> str:
        """计算签名"""
        items = sorted(args)
        return hashlib.sha1("".join(items).encode("utf-8")).hexdigest()

    def _encrypt(self, plaintext: str) -> str:
        """加密消息"""
        try:
            from Crypto.Cipher import AES
        except ImportError:
            raise ImportError(
                "pycryptodome not installed. Run: pip install pycryptodome"
            )

        import os

        # 16 字节随机字符串
        random_str = os.urandom(16)
        text = plaintext.encode("utf-8")
        # 网络字节序的消息长度
        text_length = struct.pack("!I", len(text))
        corp_id = self.corp_id.encode("utf-8")

        # 明文 = random(16B) + msg_len(4B) + msg + corp_id
        plain = random_str + text_length + text + corp_id

        # PKCS#7 填充到 AES block size 的整数倍
        block_size = 32
        pad_len = block_size - (len(plain) % block_size)
        plain += bytes([pad_len]) * pad_len

        # AES-256-CBC 加密
        iv = self.aes_key[:16]
        cipher = AES.new(self.aes_key, AES.MODE_CBC, iv)
        encrypted = cipher.encrypt(plain)

        return base64.b64encode(encrypted).decode("utf-8")

    def _decrypt(self, ciphertext: str) -> str:
        """解密消息"""
        try:
            from Crypto.Cipher import AES
        except ImportError:
            raise ImportError(
                "pycryptodome not installed. Run: pip install pycryptodome"
            )

        encrypted = base64.b64decode(ciphertext)

        # AES-256-CBC 解密
        iv = self.aes_key[:16]
        cipher = AES.new(self.aes_key, AES.MODE_CBC, iv)
        decrypted = cipher.decrypt(encrypted)

        # 去 PKCS#7 填充
        pad_len = decrypted[-1]
        content = decrypted[:-pad_len]

        # 解析: random(16B) + msg_len(4B) + msg + corp_id
        msg_len = struct.unpack("!I", content[16:20])[0]
        msg = content[20 : 20 + msg_len].decode("utf-8")
        from_corp_id = content[20 + msg_len :].decode("utf-8")

        if from_corp_id != self.corp_id:
            raise ValueError(
                f"CorpId mismatch: expected {self.corp_id}, got {from_corp_id}"
            )

        return msg

    def verify_url(
        self, msg_signature: str, timestamp: str, nonce: str, echostr: str
    ) -> str:
        """
        验证回调 URL（GET 请求）

        Returns:
            解密后的 echostr
        """
        signature = self._get_sha1(self.token, timestamp, nonce, echostr)
        if signature != msg_signature:
            raise ValueError("URL verification signature mismatch")
        return self._decrypt(echostr)

    def decrypt_msg(
        self, post_data: str, msg_signature: str, timestamp: str, nonce: str
    ) -> str:
        """
        解密回调消息（POST 请求）

        Args:
            post_data: POST 请求的 XML body
            msg_signature: 签名
            timestamp: 时间戳
            nonce: 随机数

        Returns:
            解密后的 XML 消息体
        """
        root = ET.fromstring(post_data)
        encrypt_elem = root.find("Encrypt")
        if encrypt_elem is None:
            raise ValueError("Missing <Encrypt> in callback XML")

        encrypted = encrypt_elem.text

        # 验证签名
        signature = self._get_sha1(self.token, timestamp, nonce, encrypted)
        if signature != msg_signature:
            raise ValueError("Message signature mismatch")

        return self._decrypt(encrypted)

    def encrypt_msg(self, reply_msg: str, nonce: str, timestamp: str = None) -> str:
        """
        加密回复消息

        Returns:
            加密后的 XML 响应
        """
        timestamp = timestamp or str(int(time.time()))
        encrypted = self._encrypt(reply_msg)
        signature = self._get_sha1(self.token, timestamp, nonce, encrypted)

        return (
            f"<xml>"
            f"<Encrypt><![CDATA[{encrypted}]]></Encrypt>"
            f"<MsgSignature><![CDATA[{signature}]]></MsgSignature>"
            f"<TimeStamp>{timestamp}</TimeStamp>"
            f"<Nonce><![CDATA[{nonce}]]></Nonce>"
            f"</xml>"
        )


# ==================== 配置 ====================


@dataclass
class WeWorkConfig:
    """企业微信配置"""

    corp_id: str
    agent_id: str
    secret: str
    token: str = ""
    encoding_aes_key: str = ""
    callback_port: int = 9880
    callback_host: str = "0.0.0.0"


class WeWorkAdapter(ChannelAdapter):
    """
    企业微信适配器

    支持:
    - 内置 HTTP 回调服务器（接收消息）
    - 消息加解密（AES-256-CBC）
    - 文本/图片/语音/文件/视频消息收发
    - Markdown 消息

    注意: 企业微信回调需要公网可访问的 URL。
    如果没有公网 IP，需要使用 ngrok / frp / cpolar 等内网穿透工具。
    """

    channel_name = "wework"

    API_BASE = "https://qyapi.weixin.qq.com/cgi-bin"

    def __init__(
        self,
        corp_id: str,
        agent_id: str,
        secret: str,
        token: str = "",
        encoding_aes_key: str = "",
        callback_port: int = 9880,
        callback_host: str = "0.0.0.0",
        media_dir: Path | None = None,
    ):
        """
        Args:
            corp_id: 企业 ID
            agent_id: 应用 AgentId
            secret: 应用 Secret
            token: 回调 Token (在企业微信后台配置)
            encoding_aes_key: 回调加密 AES Key (在企业微信后台配置)
            callback_port: 回调 HTTP 服务器端口
            callback_host: 回调 HTTP 服务器绑定地址
            media_dir: 媒体文件存储目录
        """
        super().__init__()

        self.config = WeWorkConfig(
            corp_id=corp_id,
            agent_id=agent_id,
            secret=secret,
            token=token,
            encoding_aes_key=encoding_aes_key,
            callback_port=callback_port,
            callback_host=callback_host,
        )
        self.media_dir = Path(media_dir) if media_dir else Path("data/media/wework")
        self.media_dir.mkdir(parents=True, exist_ok=True)

        self._access_token: str | None = None
        self._token_expires_at: float = 0
        self._http_client: Any | None = None

        # 回调服务器
        self._callback_app: Any | None = None
        self._callback_runner: Any | None = None
        self._callback_site: Any | None = None
        self._crypt: WXBizMsgCrypt | None = None

    async def start(self) -> None:
        """启动企业微信适配器（含 HTTP 回调服务器）"""
        _import_httpx()

        self._http_client = httpx.AsyncClient()
        await self._refresh_token()

        self._running = True

        # 初始化加解密工具
        if self.config.token and self.config.encoding_aes_key:
            self._crypt = WXBizMsgCrypt(
                token=self.config.token,
                encoding_aes_key=self.config.encoding_aes_key,
                corp_id=self.config.corp_id,
            )
            logger.info("WeWork: message encryption enabled")

            # 启动 HTTP 回调服务器
            await self._start_callback_server()
        else:
            logger.warning(
                "WeWork: token/encoding_aes_key not configured, "
                "callback server not started. Only outbound messages available."
            )

        logger.info("WeWork adapter started")

    async def stop(self) -> None:
        """停止企业微信适配器"""
        self._running = False

        # 关闭 HTTP 服务器
        if self._callback_site:
            await self._callback_site.stop()
        if self._callback_runner:
            await self._callback_runner.cleanup()

        if self._http_client:
            await self._http_client.aclose()

        logger.info("WeWork adapter stopped")

    # ==================== HTTP 回调服务器 ====================

    async def _start_callback_server(self) -> None:
        """启动 aiohttp HTTP 回调服务器"""
        _import_aiohttp()

        app = aiohttp.web.Application()
        app.router.add_get("/callback", self._handle_get_callback)
        app.router.add_post("/callback", self._handle_post_callback)

        # 健康检查
        app.router.add_get("/health", self._handle_health)

        self._callback_app = app
        self._callback_runner = aiohttp.web.AppRunner(app)
        await self._callback_runner.setup()

        self._callback_site = aiohttp.web.TCPSite(
            self._callback_runner,
            self.config.callback_host,
            self.config.callback_port,
        )

        try:
            await self._callback_site.start()
            logger.info(
                f"WeWork callback server listening on "
                f"{self.config.callback_host}:{self.config.callback_port}"
            )
        except OSError as e:
            if e.errno == 10048 or "Address already in use" in str(e):  # EADDRINUSE
                logger.error(
                    f"WeWork: Port {self.config.callback_port} already in use. "
                    f"Change WEWORK_CALLBACK_PORT in .env"
                )
            raise

    async def _handle_health(self, request: "aiohttp.web.Request") -> "aiohttp.web.Response":
        """健康检查端点"""
        return aiohttp.web.json_response({"status": "ok", "channel": "wework"})

    async def _handle_get_callback(
        self, request: "aiohttp.web.Request"
    ) -> "aiohttp.web.Response":
        """处理 GET 回调 — 企业微信 URL 验证"""
        if not self._crypt:
            return aiohttp.web.Response(text="Encryption not configured", status=500)

        msg_signature = request.query.get("msg_signature", "")
        timestamp = request.query.get("timestamp", "")
        nonce = request.query.get("nonce", "")
        echostr = request.query.get("echostr", "")

        try:
            reply_echostr = self._crypt.verify_url(
                msg_signature, timestamp, nonce, echostr
            )
            logger.info("WeWork: URL verification successful")
            return aiohttp.web.Response(text=reply_echostr)
        except Exception as e:
            logger.error(f"WeWork: URL verification failed: {e}")
            return aiohttp.web.Response(text="Verification failed", status=403)

    async def _handle_post_callback(
        self, request: "aiohttp.web.Request"
    ) -> "aiohttp.web.Response":
        """处理 POST 回调 — 接收加密消息"""
        if not self._crypt:
            return aiohttp.web.Response(text="Encryption not configured", status=500)

        msg_signature = request.query.get("msg_signature", "")
        timestamp = request.query.get("timestamp", "")
        nonce = request.query.get("nonce", "")

        body = await request.text()

        try:
            # 解密消息
            decrypted_xml = self._crypt.decrypt_msg(
                body, msg_signature, timestamp, nonce
            )
            logger.debug(f"WeWork: Decrypted message: {decrypted_xml[:200]}")

            # 解析并处理消息（异步）
            asyncio.create_task(self._process_decrypted_message(decrypted_xml))

            # 回复 success（企业微信要求）
            return aiohttp.web.Response(text="success")

        except Exception as e:
            logger.error(f"WeWork: Message processing failed: {e}", exc_info=True)
            return aiohttp.web.Response(text="Error", status=500)

    async def _process_decrypted_message(self, xml_str: str) -> None:
        """处理解密后的 XML 消息"""
        try:
            root = ET.fromstring(xml_str)
            msg_type = root.find("MsgType")
            if msg_type is None:
                logger.warning("WeWork: Missing MsgType in callback message")
                return

            msg_type_text = msg_type.text

            if msg_type_text == "text":
                await self._handle_text_message(root)
            elif msg_type_text == "image":
                await self._handle_image_message(root)
            elif msg_type_text == "voice":
                await self._handle_voice_message(root)
            elif msg_type_text == "video":
                await self._handle_video_message(root)
            elif msg_type_text == "file":
                await self._handle_file_message(root)
            elif msg_type_text == "event":
                event_type = root.find("Event")
                if event_type is not None:
                    await self._emit_event(
                        event_type.text,
                        {"xml": ET.tostring(root, encoding="unicode")},
                    )
            else:
                logger.info(f"WeWork: Unhandled message type: {msg_type_text}")

        except Exception as e:
            logger.error(f"WeWork: Error processing message: {e}", exc_info=True)

    # ==================== 消息处理 ====================

    async def _handle_text_message(self, root: ET.Element) -> None:
        """处理文本消息"""
        content = MessageContent(text=root.find("Content").text)

        from_user = root.find("FromUserName").text
        unified = UnifiedMessage.create(
            channel=self.channel_name,
            channel_message_id=root.find("MsgId").text,
            user_id=f"ww_{from_user}",
            channel_user_id=from_user,
            chat_id=from_user,
            content=content,
            chat_type="private",
            raw={"xml": ET.tostring(root, encoding="unicode")},
        )

        self._log_message(unified)
        await self._emit_message(unified)

    async def _handle_image_message(self, root: ET.Element) -> None:
        """处理图片消息"""
        media_id = root.find("MediaId").text
        pic_url_elem = root.find("PicUrl")

        media = MediaFile.create(
            filename=f"{media_id}.jpg",
            mime_type="image/jpeg",
            file_id=media_id,
            url=pic_url_elem.text if pic_url_elem is not None else None,
        )

        content = MessageContent(images=[media])

        from_user = root.find("FromUserName").text
        unified = UnifiedMessage.create(
            channel=self.channel_name,
            channel_message_id=root.find("MsgId").text,
            user_id=f"ww_{from_user}",
            channel_user_id=from_user,
            chat_id=from_user,
            content=content,
            chat_type="private",
            raw={"xml": ET.tostring(root, encoding="unicode")},
        )

        self._log_message(unified)
        await self._emit_message(unified)

    async def _handle_voice_message(self, root: ET.Element) -> None:
        """处理语音消息"""
        media_id = root.find("MediaId").text
        format_elem = root.find("Format")
        audio_format = format_elem.text if format_elem is not None else "amr"

        media = MediaFile.create(
            filename=f"{media_id}.{audio_format}",
            mime_type=f"audio/{audio_format}",
            file_id=media_id,
        )

        content = MessageContent(voices=[media])

        from_user = root.find("FromUserName").text
        unified = UnifiedMessage.create(
            channel=self.channel_name,
            channel_message_id=root.find("MsgId").text,
            user_id=f"ww_{from_user}",
            channel_user_id=from_user,
            chat_id=from_user,
            content=content,
            chat_type="private",
            raw={"xml": ET.tostring(root, encoding="unicode")},
        )

        self._log_message(unified)
        await self._emit_message(unified)

    async def _handle_video_message(self, root: ET.Element) -> None:
        """处理视频消息"""
        media_id = root.find("MediaId").text
        thumb_media_id_elem = root.find("ThumbMediaId")

        media = MediaFile.create(
            filename=f"{media_id}.mp4",
            mime_type="video/mp4",
            file_id=media_id,
        )
        if thumb_media_id_elem is not None:
            media.thumbnail_url = thumb_media_id_elem.text

        content = MessageContent(videos=[media])

        from_user = root.find("FromUserName").text
        unified = UnifiedMessage.create(
            channel=self.channel_name,
            channel_message_id=root.find("MsgId").text,
            user_id=f"ww_{from_user}",
            channel_user_id=from_user,
            chat_id=from_user,
            content=content,
            chat_type="private",
            raw={"xml": ET.tostring(root, encoding="unicode")},
        )

        self._log_message(unified)
        await self._emit_message(unified)

    async def _handle_file_message(self, root: ET.Element) -> None:
        """处理文件消息"""
        media_id = root.find("MediaId").text
        file_name_elem = root.find("FileName")
        file_name = file_name_elem.text if file_name_elem is not None else "file"

        media = MediaFile.create(
            filename=file_name,
            mime_type="application/octet-stream",
            file_id=media_id,
        )

        content = MessageContent(files=[media])

        from_user = root.find("FromUserName").text
        unified = UnifiedMessage.create(
            channel=self.channel_name,
            channel_message_id=root.find("MsgId").text,
            user_id=f"ww_{from_user}",
            channel_user_id=from_user,
            chat_id=from_user,
            content=content,
            chat_type="private",
            raw={"xml": ET.tostring(root, encoding="unicode")},
        )

        self._log_message(unified)
        await self._emit_message(unified)

    # ==================== 消息发送 ====================

    async def send_message(self, message: OutgoingMessage) -> str:
        """发送消息"""
        await self._refresh_token()

        url = f"{self.API_BASE}/message/send"
        params = {"access_token": self._access_token}

        # 构建消息体
        data = {
            "touser": message.chat_id,
            "agentid": self.config.agent_id,
        }

        if message.content.text and not message.content.has_media:
            # 文本消息
            data["msgtype"] = "text"
            data["text"] = {"content": message.content.text}
        elif message.content.images:
            # 图片消息
            image = message.content.images[0]
            if image.file_id:
                data["msgtype"] = "image"
                data["image"] = {"media_id": image.file_id}
            elif image.local_path:
                media_id = await self._upload_media(image.local_path, "image")
                data["msgtype"] = "image"
                data["image"] = {"media_id": media_id}
            else:
                data["msgtype"] = "text"
                data["text"] = {"content": message.content.text or "[图片]"}
        elif message.content.voices:
            # 语音消息
            voice = message.content.voices[0]
            if voice.file_id:
                data["msgtype"] = "voice"
                data["voice"] = {"media_id": voice.file_id}
            elif voice.local_path:
                media_id = await self._upload_media(voice.local_path, "voice")
                data["msgtype"] = "voice"
                data["voice"] = {"media_id": media_id}
            else:
                data["msgtype"] = "text"
                data["text"] = {"content": message.content.text or "[语音]"}
        elif message.content.files:
            # 文件消息
            file = message.content.files[0]
            if file.file_id:
                data["msgtype"] = "file"
                data["file"] = {"media_id": file.file_id}
            elif file.local_path:
                media_id = await self._upload_media(file.local_path, "file")
                data["msgtype"] = "file"
                data["file"] = {"media_id": media_id}
            else:
                data["msgtype"] = "text"
                data["text"] = {"content": message.content.text or "[文件]"}
        elif message.content.videos:
            # 视频消息
            video = message.content.videos[0]
            if video.file_id:
                data["msgtype"] = "video"
                data["video"] = {"media_id": video.file_id}
            elif video.local_path:
                media_id = await self._upload_media(video.local_path, "video")
                data["msgtype"] = "video"
                data["video"] = {"media_id": media_id}
            else:
                data["msgtype"] = "text"
                data["text"] = {"content": message.content.text or "[视频]"}
        else:
            data["msgtype"] = "text"
            data["text"] = {"content": message.content.text or ""}

        response = await self._http_client.post(url, params=params, json=data)
        result = response.json()

        if result.get("errcode", 0) != 0:
            raise RuntimeError(f"Failed to send message: {result.get('errmsg')}")

        return result.get("msgid", "")

    async def send_file(
        self,
        chat_id: str,
        file_path: str,
        caption: str | None = None,
    ) -> str:
        """发送文件"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        media_id = await self._upload_media(str(path), "file")

        # 先发送文件
        msg = OutgoingMessage(
            chat_id=chat_id,
            content=MessageContent(
                files=[
                    MediaFile.create(
                        filename=path.name,
                        mime_type="application/octet-stream",
                        file_id=media_id,
                    )
                ]
            ),
        )
        result = await self.send_message(msg)

        # 如果有 caption，追发文本
        if caption:
            await self.send_text(chat_id, caption)

        return result

    async def send_voice(
        self,
        chat_id: str,
        voice_path: str,
        caption: str | None = None,
    ) -> str:
        """发送语音"""
        path = Path(voice_path)
        if not path.exists():
            raise FileNotFoundError(f"Voice file not found: {voice_path}")

        media_id = await self._upload_media(str(path), "voice")

        msg = OutgoingMessage(
            chat_id=chat_id,
            content=MessageContent(
                voices=[
                    MediaFile.create(
                        filename=path.name,
                        mime_type="audio/amr",
                        file_id=media_id,
                    )
                ]
            ),
        )
        result = await self.send_message(msg)

        if caption:
            await self.send_text(chat_id, caption)

        return result

    async def send_markdown(
        self,
        user_id: str,
        content: str,
    ) -> str:
        """发送 Markdown 消息"""
        await self._refresh_token()

        url = f"{self.API_BASE}/message/send"
        params = {"access_token": self._access_token}

        data = {
            "touser": user_id,
            "agentid": self.config.agent_id,
            "msgtype": "markdown",
            "markdown": {"content": content},
        }

        response = await self._http_client.post(url, params=params, json=data)
        result = response.json()

        if result.get("errcode", 0) != 0:
            raise RuntimeError(f"Failed to send markdown: {result.get('errmsg')}")

        return result.get("msgid", "")

    # ==================== 媒体处理 ====================

    async def _upload_media(self, path: str, media_type: str) -> str:
        """上传临时素材到企业微信"""
        await self._refresh_token()

        url = f"{self.API_BASE}/media/upload"
        params = {
            "access_token": self._access_token,
            "type": media_type,
        }

        with open(path, "rb") as f:
            files = {"media": f}
            response = await self._http_client.post(url, params=params, files=files)

        result = response.json()

        if result.get("errcode", 0) != 0:
            raise RuntimeError(f"Failed to upload media: {result.get('errmsg')}")

        return result["media_id"]

    async def download_media(self, media: MediaFile) -> Path:
        """下载媒体文件"""
        if media.local_path and Path(media.local_path).exists():
            return Path(media.local_path)

        # 优先使用 URL
        if media.url:
            response = await self._http_client.get(media.url)
        elif media.file_id:
            await self._refresh_token()
            url = f"{self.API_BASE}/media/get"
            params = {
                "access_token": self._access_token,
                "media_id": media.file_id,
            }
            response = await self._http_client.get(url, params=params)
        else:
            raise ValueError("Media has no url or file_id")

        # 保存文件
        local_path = self.media_dir / media.filename
        with open(local_path, "wb") as f:
            f.write(response.content)

        media.local_path = str(local_path)
        media.status = MediaStatus.READY

        logger.info(f"Downloaded media: {media.filename}")
        return local_path

    async def upload_media(self, path: Path, mime_type: str) -> MediaFile:
        """上传媒体文件"""
        if mime_type.startswith("image/"):
            media_type = "image"
        elif mime_type.startswith("audio/"):
            media_type = "voice"
        elif mime_type.startswith("video/"):
            media_type = "video"
        else:
            media_type = "file"

        media_id = await self._upload_media(str(path), media_type)

        return MediaFile.create(
            filename=path.name,
            mime_type=mime_type,
            file_id=media_id,
        )

    # ==================== Token 管理 ====================

    async def _refresh_token(self) -> str:
        """刷新 access token"""
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        url = f"{self.API_BASE}/gettoken"
        params = {
            "corpid": self.config.corp_id,
            "corpsecret": self.config.secret,
        }

        response = await self._http_client.get(url, params=params)
        data = response.json()

        if data.get("errcode", 0) != 0:
            raise RuntimeError(f"Failed to get access token: {data.get('errmsg')}")

        self._access_token = data["access_token"]
        self._token_expires_at = time.time() + data["expires_in"] - 60

        return self._access_token
