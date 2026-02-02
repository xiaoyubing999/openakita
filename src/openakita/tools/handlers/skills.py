"""
技能管理处理器

处理技能管理相关的系统技能：
- list_skills: 列出技能
- get_skill_info: 获取技能信息
- run_skill_script: 运行技能脚本
- get_skill_reference: 获取参考文档
- install_skill: 安装技能
- load_skill: 加载新创建的技能
- reload_skill: 重新加载已修改的技能

注意: generate_skill 和 improve_skill 功能已移至外部技能 skill-creator
"""

import logging
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.agent import Agent

logger = logging.getLogger(__name__)


class SkillsHandler:
    """技能管理处理器"""
    
    TOOLS = [
        "list_skills",
        "get_skill_info",
        "run_skill_script",
        "get_skill_reference",
        "install_skill",
        "load_skill",
        "reload_skill",
    ]
    
    def __init__(self, agent: "Agent"):
        self.agent = agent
    
    async def handle(self, tool_name: str, params: dict[str, Any]) -> str:
        """处理工具调用"""
        if tool_name == "list_skills":
            return self._list_skills(params)
        elif tool_name == "get_skill_info":
            return self._get_skill_info(params)
        elif tool_name == "run_skill_script":
            return self._run_skill_script(params)
        elif tool_name == "get_skill_reference":
            return self._get_skill_reference(params)
        elif tool_name == "install_skill":
            return await self._install_skill(params)
        elif tool_name == "load_skill":
            return self._load_skill(params)
        elif tool_name == "reload_skill":
            return self._reload_skill(params)
        else:
            return f"❌ Unknown skills tool: {tool_name}"
    
    def _list_skills(self, params: dict) -> str:
        """列出所有技能"""
        skills = self.agent.skill_registry.list_all()
        if not skills:
            return "当前没有已安装的技能\n\n提示: 技能应放在 skills/ 目录下，每个技能是一个包含 SKILL.md 的文件夹"
        
        # 分类显示
        system_skills = [s for s in skills if s.system]
        external_skills = [s for s in skills if not s.system]
        
        output = f"已安装 {len(skills)} 个技能 (遵循 Agent Skills 规范):\n\n"
        
        if system_skills:
            output += f"**系统技能 ({len(system_skills)})**:\n"
            for skill in system_skills:
                auto = "自动" if not skill.disable_model_invocation else "手动"
                output += f"- {skill.name} [{auto}] - {skill.description}\n"
            output += "\n"
        
        if external_skills:
            output += f"**外部技能 ({len(external_skills)})**:\n"
            for skill in external_skills:
                auto = "自动" if not skill.disable_model_invocation else "手动"
                output += f"- {skill.name} [{auto}]\n"
                output += f"  {skill.description}\n\n"
        
        return output
    
    def _get_skill_info(self, params: dict) -> str:
        """获取技能详细信息"""
        skill_name = params["skill_name"]
        skill = self.agent.skill_registry.get(skill_name)
        
        if not skill:
            return f"❌ 未找到技能: {skill_name}"
        
        body = skill.get_body()
        
        output = f"# 技能: {skill.name}\n\n"
        output += f"**描述**: {skill.description}\n"
        if skill.system:
            output += f"**类型**: 系统技能\n"
            output += f"**工具名**: {skill.tool_name}\n"
            output += f"**处理器**: {skill.handler}\n"
        if skill.license:
            output += f"**许可证**: {skill.license}\n"
        if skill.compatibility:
            output += f"**兼容性**: {skill.compatibility}\n"
        output += f"\n---\n\n"
        output += body or "(无详细指令)"
        
        return output
    
    def _run_skill_script(self, params: dict) -> str:
        """运行技能脚本"""
        skill_name = params["skill_name"]
        script_name = params["script_name"]
        args = params.get("args", [])
        
        success, output = self.agent.skill_loader.run_script(
            skill_name, script_name, args
        )
        
        if success:
            return f"✅ 脚本执行成功:\n{output}"
        else:
            # 提供详细错误信息和可操作建议
            error_msg = f"❌ 脚本执行失败:\n{output}\n\n"
            
            # 根据错误类型提供建议
            if "timed out" in output.lower() or "超时" in output:
                error_msg += "**建议**: 脚本执行超时。可以尝试:\n"
                error_msg += "1. 检查脚本是否有死循环或长时间阻塞操作\n"
                error_msg += "2. 使用 `get_skill_info` 查看技能详情确认用法\n"
                error_msg += "3. 尝试使用其他方法完成任务"
            elif "not found" in output.lower() or "未找到" in output:
                error_msg += "**建议**: 脚本或资源未找到。可以尝试:\n"
                error_msg += "1. 使用 `list_skills` 确认技能是否已安装\n"
                error_msg += "2. 使用 `get_skill_info` 查看可用脚本列表\n"
                error_msg += "3. 检查脚本名称是否正确"
            elif "permission" in output.lower() or "权限" in output:
                error_msg += "**建议**: 权限不足。可以尝试:\n"
                error_msg += "1. 检查文件/目录权限\n"
                error_msg += "2. 使用管理员权限运行"
            else:
                error_msg += "**建议**: 请检查脚本参数是否正确，或使用 `get_skill_info` 查看技能使用说明"
            
            return error_msg
    
    def _get_skill_reference(self, params: dict) -> str:
        """获取技能参考文档"""
        skill_name = params["skill_name"]
        ref_name = params.get("ref_name", "REFERENCE.md")
        
        content = self.agent.skill_loader.get_reference(skill_name, ref_name)
        
        if content:
            return f"# 参考文档: {ref_name}\n\n{content}"
        else:
            return f"❌ 未找到参考文档: {skill_name}/{ref_name}"
    
    async def _install_skill(self, params: dict) -> str:
        """安装技能"""
        source = params["source"]
        name = params.get("name")
        subdir = params.get("subdir")
        extra_files = params.get("extra_files", [])
        
        result = await self.agent._install_skill(source, name, subdir, extra_files)
        return result
    
    def _load_skill(self, params: dict) -> str:
        """加载新创建的技能"""
        skill_name = params["skill_name"]
        
        # 查找技能目录
        skills_dir = Path("skills")
        skill_dir = skills_dir / skill_name
        
        if not skill_dir.exists():
            return f"❌ 技能目录不存在: {skill_dir}\n\n请确保技能已保存到 skills/{skill_name}/ 目录"
        
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            return f"❌ 技能定义文件不存在: {skill_md}\n\n请确保目录中包含 SKILL.md 文件"
        
        # 检查是否已加载
        existing = self.agent.skill_registry.get(skill_name)
        if existing:
            return f"⚠️ 技能 '{skill_name}' 已存在。如需更新，请使用 reload_skill"
        
        try:
            # 加载技能
            loaded = self.agent.skill_loader.load_skill(skill_dir)
            
            if loaded:
                # 刷新技能目录缓存
                self.agent._skill_catalog_text = self.agent.skill_catalog.generate_catalog()
                
                logger.info(f"Skill loaded: {skill_name}")
                
                return f"""✅ 技能加载成功！

**技能名称**: {loaded.metadata.name}
**描述**: {loaded.metadata.description}
**类型**: {"系统技能" if loaded.metadata.system else "外部技能"}
**路径**: {skill_dir}

技能已可用，可以通过 `get_skill_info("{skill_name}")` 查看详情。"""
            else:
                return f"❌ 技能加载失败，请检查 SKILL.md 格式是否正确"
                
        except Exception as e:
            logger.error(f"Failed to load skill {skill_name}: {e}")
            return f"❌ 加载技能时出错: {e}"
    
    def _reload_skill(self, params: dict) -> str:
        """重新加载已存在的技能"""
        skill_name = params["skill_name"]
        
        # 检查技能是否已加载
        existing = self.agent.skill_loader.get_skill(skill_name)
        if not existing:
            return f"❌ 技能 '{skill_name}' 未加载。如需加载新技能，请使用 load_skill"
        
        try:
            # 重新加载
            reloaded = self.agent.skill_loader.reload_skill(skill_name)
            
            if reloaded:
                # 刷新技能目录缓存
                self.agent._skill_catalog_text = self.agent.skill_catalog.generate_catalog()
                
                logger.info(f"Skill reloaded: {skill_name}")
                
                return f"""✅ 技能重新加载成功！

**技能名称**: {reloaded.metadata.name}
**描述**: {reloaded.metadata.description}
**类型**: {"系统技能" if reloaded.metadata.system else "外部技能"}

修改已生效。"""
            else:
                return f"❌ 技能重新加载失败"
                
        except Exception as e:
            logger.error(f"Failed to reload skill {skill_name}: {e}")
            return f"❌ 重新加载技能时出错: {e}"


def create_handler(agent: "Agent"):
    """创建技能管理处理器"""
    handler = SkillsHandler(agent)
    return handler.handle
