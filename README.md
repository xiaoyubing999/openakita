# MyAgent - 全能自进化AI Agent

一个基于 **Ralph Wiggum 模式** 的全能AI助手，具备自我进化能力，永不放弃。

## 核心特性

- **永不放弃** (Ralph Wiggum模式): 任务未完成绝不终止，遇到困难自己解决
- **自我进化**: 自动搜索GitHub安装新技能，没有就自己写
- **持续学习**: 记录经验教训，不断优化
- **MCP集成**: 支持调用各种MCP服务器工具
- **300个自动测试**: 自动验证功能，失败自动修复

## 核心文档

| 文档 | 作用 |
|------|------|
| `AGENT.md` | Agent行为规范 - 操作指令、工作流程 |
| `SOUL.md` | Agent灵魂 - 核心哲学、价值观 |
| `USER.md` | 用户档案 - 偏好、习惯 |
| `MEMORY.md` | 关键记忆 - 任务进度、经验教训 |

## 快速开始

```bash
# 安装依赖
pip install -e .

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入 ANTHROPIC_API_KEY

# 启动Agent
myagent
```

## 使用示例

```
> 帮我写一个爬虫抓取某网站的数据
Agent: 检测到需要爬虫能力，正在搜索GitHub...
Agent: 找到 scrapy，正在安装...
Agent: 安装完成，开始编写爬虫...
Agent: [完成] 爬虫已创建并测试通过

> /selfcheck
Agent: 开始自检...
Agent: [测试] 运行300个测试用例...
Agent: [结果] 300/300 通过
Agent: 自检完成，系统状态良好。
```

## 项目结构

```
myagent/
├── AGENT.md                # Agent行为规范
├── SOUL.md                 # Agent灵魂文件
├── USER.md                 # 用户档案
├── MEMORY.md               # 关键记忆
├── src/myagent/
│   ├── main.py            # CLI入口
│   ├── core/              # 核心模块
│   │   ├── agent.py       # Agent主类
│   │   ├── brain.py       # LLM交互
│   │   ├── ralph.py       # Ralph循环引擎
│   │   └── identity.py    # 身份系统
│   ├── skills/            # 技能系统
│   ├── tools/             # 工具层
│   ├── storage/           # 持久化
│   ├── evolution/         # 自我进化
│   └── testing/           # 测试系统
├── skills/                 # 本地技能
├── plugins/                # 插件
└── data/                   # 数据存储
```

## 参考项目

- [Claude Soul Document](https://gist.github.com/Richard-Weiss/efe157692991535403bd7e7fb20b6695)
- [Ralph Playbook](https://claytonfarr.github.io/ralph-playbook/)
- [AGENTS.md Standard](https://agentsmd.io/)
- [Anthropic Claude Code Ralph Plugin](https://github.com/anthropics/claude-code/tree/main/plugins/ralph-wiggum)

## License

MIT
