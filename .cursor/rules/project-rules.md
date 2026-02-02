# OpenAkita 项目执行规则

## 禁止随意截断

**重要原则：不允许随意截断数据**

1. **禁止截断的场景**：
   - 工具描述、技能描述 - LLM 需要完整信息才能正确调用
   - 浏览器页面内容 - LLM 需要看到完整页面
   - Session 历史记录 - 保持上下文完整性
   - 文件内容提取 - 用户发送的文件应完整处理
   - 任务描述、错误信息 - 调试和追踪需要完整信息
   - 日志输出 - 便于排查问题

2. **允许的例外**：
   - UUID 截取生成短 ID（如 `uuid[:8]`）
   - 平台 API 限制（如 Telegram 4096 字符限制，需分割发送）
   - 文件格式检测（只需前几字节判断 MIME 类型）
   - MEMORY.md 压缩（有专门的 LLM 压缩逻辑）

3. **如果确实需要截断**：
   - 必须有明确的技术原因
   - 优先使用 LLM 压缩/摘要而非硬截断
   - 在代码中注释说明原因

---

## 大文件修改规则

### agent.py 修改规则

`src/openakita/core/agent.py` 是核心文件，行数超过 2500 行。修改此文件时：

1. **禁止使用 StrReplace 工具** - 文件太大，StrReplace 可能匹配失败或超时
2. **必须使用 Python 脚本修改** - 创建临时脚本执行批量修改
3. **脚本位置**: `scripts/` 目录下创建临时修改脚本
4. **执行后删除**: 修改完成后删除临时脚本

### 示例脚本模板

```python
"""临时修改脚本 - 执行后删除"""
import re
from pathlib import Path

agent_file = Path("src/openakita/core/agent.py")
content = agent_file.read_text(encoding="utf-8")

# 批量替换
replacements = [
    (r'old_pattern_1', 'new_value_1'),
    (r'old_pattern_2', 'new_value_2'),
]

for pattern, replacement in replacements:
    content = re.sub(pattern, replacement, content)

agent_file.write_text(content, encoding="utf-8")
print("修改完成")
```

## 其他规则

### 截断相关

- MEMORY.md 的 800 字符限制保留不修改
- UUID 截取 (`[:8]`, `[:12]`) 是 ID 生成，不是信息截断，保留
- Telegram 消息分割是平台 API 限制，保留
