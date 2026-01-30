"""
Identity 模块 - 加载和管理 SOUL.md 和 AGENT.md

负责:
- 加载核心文档
- 生成系统提示词
- 提供行为规则
"""

from pathlib import Path
from typing import Optional
import logging

from ..config import settings

logger = logging.getLogger(__name__)


class Identity:
    """Agent 身份管理器"""
    
    def __init__(
        self,
        soul_path: Optional[Path] = None,
        agent_path: Optional[Path] = None,
    ):
        self.soul_path = soul_path or settings.soul_path
        self.agent_path = agent_path or settings.agent_path
        
        self._soul: Optional[str] = None
        self._agent: Optional[str] = None
        
    def load(self) -> None:
        """加载核心文档"""
        self._soul = self._load_file(self.soul_path, "SOUL.md")
        self._agent = self._load_file(self.agent_path, "AGENT.md")
        logger.info("Identity loaded: SOUL.md and AGENT.md")
    
    def _load_file(self, path: Path, name: str) -> str:
        """加载单个文件"""
        try:
            if path.exists():
                return path.read_text(encoding="utf-8")
            else:
                logger.warning(f"{name} not found at {path}")
                return ""
        except Exception as e:
            logger.error(f"Failed to load {name}: {e}")
            return ""
    
    @property
    def soul(self) -> str:
        """获取 SOUL.md 内容"""
        if self._soul is None:
            self.load()
        return self._soul or ""
    
    @property
    def agent(self) -> str:
        """获取 AGENT.md 内容"""
        if self._agent is None:
            self.load()
        return self._agent or ""
    
    def get_system_prompt(self) -> str:
        """生成系统提示词"""
        return f"""# MyAgent System

## Soul (核心哲学)

{self.soul}

## Agent Behavior (行为规范)

{self.agent}

## 核心指令

你是 MyAgent，一个全能自进化AI助手。请遵循以上 Soul 和 Agent 文档中的指导原则。

关键原则:
1. **永不放弃** - 任务未完成绝不终止，遇到困难自己想办法解决
2. **持续学习** - 记录经验教训，不断进化
3. **诚实透明** - 清楚说明正在做什么，遇到什么问题
4. **真正帮助** - 把用户当作聪明的成年人，提供实质性帮助

当遇到无法解决的问题时:
1. 分析失败原因
2. 搜索 GitHub 找现有解决方案
3. 如果找到，下载安装并使用
4. 如果没找到，自己编写代码实现
5. 测试验证
6. 重试任务
"""

    def get_behavior_rules(self) -> list[str]:
        """提取行为规则"""
        rules = [
            "任务未完成，绝不退出",
            "遇到错误，分析并重试",
            "缺少能力，自动获取",
            "每次迭代保存进度到 MEMORY.md",
            "不删除用户数据（除非明确要求）",
            "不访问敏感系统路径",
            "不在未告知的情况下安装收费软件",
            "不放弃任务（除非用户明确取消）",
        ]
        return rules
    
    def get_prohibited_actions(self) -> list[str]:
        """获取禁止的行为"""
        return [
            "提供创建大规模杀伤性武器的详细说明",
            "生成涉及未成年人的不当内容",
            "生成可能直接促进攻击关键基础设施的内容",
            "创建旨在造成重大损害的恶意代码",
            "破坏AI监督机制",
            "对用户撒谎或隐瞒重要信息",
        ]
