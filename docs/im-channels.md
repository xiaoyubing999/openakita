# IM 通道集成指南

OpenAkita 支持多个即时通讯平台，每个平台通过独立的适配器 (Adapter) 接入统一的消息网关 (MessageGateway)。

## 平台概览

| 平台 | 状态 | 接入方式 | 需要公网 IP | 安装命令 |
|------|------|---------|------------|---------|
| Telegram | ✅ 稳定 | Long Polling | ❌ 不需要 | 默认包含 |
| 飞书 | ✅ 稳定 | WebSocket 长连接 | ❌ 不需要 | `pip install openakita[feishu]` |
| 钉钉 | ✅ 稳定 | Stream 模式 (WebSocket) | ❌ 不需要 | `pip install openakita[dingtalk]` |
| 企业微信 | ✅ 稳定 | HTTP 回调 | ⚠️ 需要 | `pip install openakita[wework]` |
| QQ | 🧪 Beta | OneBot WebSocket | ❌ 不需要 | `pip install openakita[qq]` |

## 媒体类型支持矩阵

### 接收消息 (平台 → OpenAkita)

| 类型 | Telegram | 飞书 | 钉钉 | 企业微信 | QQ |
|------|----------|------|------|---------|-----|
| 文字 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 图片 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 语音 | ✅ (Whisper转写) | ✅ (Whisper转写) | ✅ (Whisper转写) | ✅ (Whisper转写) | ✅ (Whisper转写) |
| 文件 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 视频 | ✅ | ✅ | ✅ | ✅ | ✅ |

### 发送消息 (OpenAkita → 平台)

| 方法 | Telegram | 飞书 | 钉钉 | 企业微信 | QQ |
|------|----------|------|------|---------|-----|
| send_text | ✅ | ✅ | ✅ | ✅ | ✅ |
| send_image | ✅ | ✅ | ✅ | ✅ | ✅ |
| send_file | ✅ | ✅ | ✅ (降级为链接) | ✅ | ✅ (upload_file API) |
| send_voice | ✅ | ✅ | ✅ (降级为文件) | ✅ | ✅ (record) |

> **注意**: 图片和语音由 MessageGateway 自动下载并预处理。语音会自动通过 Whisper 转写为文本。文件和视频不会自动下载，需要通过 `deliver_artifacts` 工具主动处理。

---

## Telegram

### 前置条件

- 一个 Telegram 账号
- 网络能访问 Telegram API（大陆环境需要代理）

### 平台侧配置

1. **创建机器人**: 在 Telegram 中搜索 [@BotFather](https://t.me/BotFather)，发送 `/newbot`
2. **获取 Token**: 按提示设置名称后，BotFather 会返回一个 Bot Token（格式如 `123456:ABC-DEF...`）
3. **（可选）设置命令**: 发送 `/setcommands` 配置机器人命令菜单

### OpenAkita 配置

```bash
# .env
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=你的Bot Token

# 代理（大陆环境需要）
TELEGRAM_PROXY=http://127.0.0.1:7890
# 或 socks5://127.0.0.1:1080
```

### 部署模式

- **Long Polling（默认）**: 无需公网 IP，适配器主动轮询 Telegram 服务器获取消息
- **Webhook**: 需要公网 HTTPS URL，配置 `TELEGRAM_WEBHOOK_URL`

### 验证方法

1. 启动 OpenAkita 后，在 Telegram 中找到你的机器人
2. 发送 `/start`，应该收到配对码提示
3. 发送配对码完成配对（如果启用了 `TELEGRAM_REQUIRE_PAIRING`）
4. 发送任意消息，观察日志输出和机器人回复

### 特有功能

- 配对安全机制（防止未授权访问）
- 全媒体类型支持最完整
- Markdown 格式消息
- 内联键盘

---

## 飞书 (Lark)

### 前置条件

- 企业飞书账号
- 在 [飞书开发者后台](https://open.feishu.cn/) 创建企业自建应用

### 平台侧配置

1. **创建应用**: 进入 [开发者后台](https://open.feishu.cn/app) → 创建企业自建应用
2. **获取凭证**: 在「凭证与基础信息」页面获取 App ID 和 App Secret
3. **配置权限**: 在「权限管理」中添加以下权限：
   - `im:message` — 获取与发送消息
   - `im:message.create_v1` — 以应用身份发消息
   - `im:resource` — 获取消息中的资源文件
   - `im:file` — 上传/下载文件
4. **配置事件订阅**:
   - 进入「事件与回调」页面
   - **选择「使用长连接接收事件」**（关键步骤！）
   - 添加事件：`im.message.receive_v1`（接收消息）
5. **发布应用**: 在「版本管理与发布」中创建版本并发布

### OpenAkita 配置

```bash
# 安装飞书依赖
pip install openakita[feishu]

# .env
FEISHU_ENABLED=true
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
```

### 部署模式

- **WebSocket 长连接（默认/推荐）**: 无需公网 IP，SDK 自动管理连接和重连
- 每个应用最多支持 50 个长连接
- 多实例部署时，消息会随机分发到其中一个连接

### 验证方法

1. 启动 OpenAkita，日志应显示 `Feishu adapter: WebSocket started in background`
2. 在飞书中搜索并打开机器人对话
3. 发送消息，观察日志和机器人回复

### 常见问题

- **消息收不到**: 检查是否在飞书后台启用了"长连接模式"而非 Webhook
- **权限不足**: 确认所有必要权限已申请且应用已发布
- **Token 过期**: SDK 会自动管理 Token 刷新，无需手动处理

---

## 钉钉

### 前置条件

- 企业钉钉账号
- 在 [钉钉开发者后台](https://open-dev.dingtalk.com/) 创建应用

### 平台侧配置

1. **创建应用**: 进入 [开发者后台](https://open-dev.dingtalk.com/) → 应用开发 → 企业内部开发 → 创建应用
2. **获取凭证**: 在「基础信息」→「应用凭证」中获取 AppKey 和 AppSecret
3. **配置机器人**:
   - 进入「应用功能」→「机器人」
   - 开启机器人功能
   - **消息接收模式选择「Stream 模式」**（关键步骤！）
4. **配置权限**: 根据需要添加消息相关权限
5. **发布应用**: 发布应用版本

### OpenAkita 配置

```bash
# 安装钉钉依赖
pip install openakita[dingtalk]

# .env
DINGTALK_ENABLED=true
DINGTALK_CLIENT_ID=xxx
DINGTALK_CLIENT_SECRET=xxx
```

### 部署模式

- **Stream 模式（WebSocket）**: 无需公网 IP，通过 WebSocket 长连接接收消息
- dingtalk-stream SDK 自动管理连接、重连和心跳

### 验证方法

1. 启动 OpenAkita，日志应显示 `DingTalk Stream client starting...`
2. 在钉钉中搜索并打开机器人对话（或在群中 @机器人）
3. 发送消息，观察日志和机器人回复

### 消息回复方式

- **Session Webhook**: 收到消息时会携带 `sessionWebhook`，用于回复当前会话（推荐）
- **机器人单聊 API**: 使用 `robot/oToMessages/batchSend` 主动发送（需要用户 ID）

### 常见问题

- **收不到消息**: 确认在钉钉后台已选择 Stream 模式（不是 HTTP 模式）
- **Stream 连接失败**: 检查 AppKey 和 AppSecret 是否正确
- **图片/文件发送**: 钉钉机器人消息对富媒体支持有限，部分会降级为链接

---

## 企业微信

### 前置条件

- 企业微信管理员账号
- 在 [企业微信管理后台](https://work.weixin.qq.com/) 创建自建应用
- **公网可访问的 URL**（用于接收回调消息）

### 平台侧配置

1. **创建应用**: 进入管理后台 → 应用管理 → 自建 → 创建应用
2. **获取凭证**:
   - 企业 ID (Corp ID): 在「我的企业」→「企业信息」页面底部
   - Agent ID 和 Secret: 在应用详情页面获取
3. **配置消息接收**:
   - 进入应用 → 「接收消息」→ 设置 API 接收
   - **URL**: 填写你的回调 URL，如 `https://your-domain.com/callback`
   - **Token**: 自动生成或自定义，记下来
   - **EncodingAESKey**: 自动生成或自定义，记下来
   - 点击保存（企业微信会向 URL 发送验证请求）
4. **配置权限**: 在「API 接口权限」中确认消息发送/接收权限

### OpenAkita 配置

```bash
# 安装企业微信依赖
pip install openakita[wework]

# .env
WEWORK_ENABLED=true
WEWORK_CORP_ID=ww_xxx
WEWORK_AGENT_ID=1000001
WEWORK_SECRET=xxx

# 回调加解密（必填！否则无法接收消息）
WEWORK_TOKEN=xxx
WEWORK_ENCODING_AES_KEY=xxx
WEWORK_CALLBACK_PORT=9880
```

### 部署模式

企业微信 **不支持** WebSocket/长连接模式，只能通过 HTTP 回调接收消息。

- **公网服务器**: 直接在服务器上运行，回调 URL 指向服务器 IP
- **内网穿透（无公网 IP）**: 使用以下工具将本地端口映射到公网：

#### ngrok

```bash
# 安装 ngrok: https://ngrok.com/download
ngrok http 9880
# 获取公网 URL（如 https://abc123.ngrok-free.app）
# 将 https://abc123.ngrok-free.app/callback 填入企业微信后台
```

#### frp

```bash
# 在有公网 IP 的服务器上部署 frps
# 在本地配置 frpc:
[wework]
type = http
local_port = 9880
custom_domains = your-domain.com
```

#### cpolar

```bash
# 安装 cpolar: https://www.cpolar.com/
cpolar http 9880
```

### 验证方法

1. 启动 OpenAkita，日志应显示 `WeWork callback server listening on 0.0.0.0:9880`
2. 确保回调 URL 可从公网访问（`curl https://your-domain.com/health` 应返回 `{"status":"ok"}`)
3. 在企业微信中找到应用并发消息
4. 观察日志中的消息解密和处理记录

### 常见问题

- **URL 验证失败**: 确认 Token 和 EncodingAESKey 与企业微信后台一致
- **签名校验失败**: 检查 Corp ID 是否正确
- **端口被占用**: 修改 `WEWORK_CALLBACK_PORT` 为其他端口
- **内网穿透不稳定**: 建议使用付费版 ngrok 或自建 frp

---

## QQ (OneBot 协议)

### 前置条件

- 一个 QQ 账号
- 部署 OneBot v11 实现（如 NapCat、Lagrange.OneBot）

### 部署 OneBot 服务器

OpenAkita 通过 OneBot v11 协议与 QQ 通信，需要先部署一个 OneBot 实现：

#### NapCat（推荐）

```bash
# 参考: https://github.com/NapNeko/NapCatQQ
# 下载并配置 NapCat，启用正向 WebSocket
# 配置文件中设置 WebSocket 地址为 ws://127.0.0.1:8080
```

#### Lagrange.OneBot

```bash
# 参考: https://github.com/LagrangeDev/Lagrange.Core
# 下载并配置，启用正向 WebSocket
```

### OpenAkita 配置

```bash
# 安装 QQ 依赖
pip install openakita[qq]

# .env
QQ_ENABLED=true
QQ_ONEBOT_URL=ws://127.0.0.1:8080
```

### 部署模式

- **WebSocket 正向连接**: OpenAkita 连接到本地 OneBot 服务器，无需公网 IP
- 支持自动断线重连（指数退避策略）

### 验证方法

1. 先启动 OneBot 服务器（如 NapCat），确认 WebSocket 监听正常
2. 启动 OpenAkita，日志应显示 `QQ adapter connected to ws://127.0.0.1:8080`
3. 在 QQ 中给机器人发消息（私聊或群聊 @机器人）
4. 观察日志和回复

### 文件发送说明

QQ（OneBot v11）的文件发送不支持 CQ 码，必须使用专用 API：
- 群文件: `upload_group_file`
- 私聊文件: `upload_private_file`

适配器已自动处理，通过 `deliver_artifacts` 工具发送文件时无需特别操作。

### 常见问题

- **连接失败**: 确认 OneBot 服务器已启动且 WebSocket 地址正确
- **断线重连**: 适配器支持自动重连，初始延迟 1 秒，最大延迟 60 秒
- **群/私聊判断**: 适配器会根据消息来源自动判断群聊或私聊

---

## 语音识别 (Whisper)

所有 IM 通道的语音消息都会经过 MessageGateway 统一预处理：

1. 适配器将语音消息解析为 `UnifiedMessage`（包含 `MediaFile`）
2. Gateway 自动下载语音文件到本地
3. Gateway 调用 Whisper 模型进行语音转文字
4. 转写结果存入 `MediaFile.transcription`，传递给 Agent

### ffmpeg 依赖

Whisper 需要 `ffmpeg` 来解码音频文件。OpenAkita 支持自动检测和安装：

- **已安装 ffmpeg**: 自动检测系统 PATH 中的 ffmpeg
- **未安装 ffmpeg**: 自动通过 `static-ffmpeg` 包下载静态二进制

```bash
# 手动安装 ffmpeg（推荐）
# Windows: winget install FFmpeg
# macOS: brew install ffmpeg
# Linux: sudo apt install ffmpeg

# 或通过 Python 自动安装
pip install static-ffmpeg
```

### Whisper 模型选择

```bash
# .env
WHISPER_MODEL=base  # tiny/base/small/medium/large
```

| 模型 | 大小 | 速度 | 精度 |
|------|------|------|------|
| tiny | ~39MB | 最快 | 一般 |
| base | ~74MB | 快 | 较好 |
| small | ~244MB | 中等 | 好 |
| medium | ~769MB | 慢 | 很好 |
| large | ~1.5GB | 最慢 | 最好 |

---

## 统一安装

安装所有 IM 通道依赖：

```bash
pip install openakita[all]
```

或按需安装：

```bash
pip install openakita[feishu]      # 飞书
pip install openakita[dingtalk]    # 钉钉
pip install openakita[wework]      # 企业微信
pip install openakita[qq]          # QQ
pip install openakita[whisper]     # 语音识别（含 ffmpeg）

# 组合安装
pip install openakita[feishu,dingtalk,whisper]
```

---

## 架构说明

```
平台消息 → Adapter (解析) → UnifiedMessage → Gateway (预处理) → Agent
                                                    ↓
Agent 回复 ← Adapter (发送) ← OutgoingMessage ← Gateway (路由)
```

- **ChannelAdapter**: 基类定义在 `src/openakita/channels/base.py`，各平台实现在 `src/openakita/channels/adapters/`
- **MessageGateway**: 统一消息路由、会话管理、媒体预处理，定义在 `src/openakita/channels/gateway.py`
- **deliver_artifacts**: Agent 工具，用于主动发送文件/图片/语音，定义在 `src/openakita/tools/handlers/im_channel.py`
