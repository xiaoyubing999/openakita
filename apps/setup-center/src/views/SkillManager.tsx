// ─── SkillManager: 技能管理页面 ───
// 支持已安装技能列表、配置表单自动生成、启用/禁用、技能市场浏览与安装

import { useEffect, useMemo, useState, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import { useTranslation } from "react-i18next";
import type { SkillInfo, SkillConfigField, MarketplaceSkill, EnvMap } from "../types";
import { envGet, envSet } from "../utils";
import { IconGear, IconZap, IconPackage, IconStar, IconCheck, IconX, IconDownload, IconSearch, IconConfig } from "../icons";

// ─── 配置表单自动生成 ───

function SkillConfigForm({
  fields,
  envDraft,
  onEnvChange,
}: {
  fields: SkillConfigField[];
  envDraft: EnvMap;
  onEnvChange: (fn: (prev: EnvMap) => EnvMap) => void;
}) {
  const [secretShown, setSecretShown] = useState<Record<string, boolean>>({});
  const { t } = useTranslation();

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: "8px 0" }}>
      {fields.map((field) => {
        const value = envGet(envDraft, field.key, String(field.default ?? ""));
        const isSecret = field.type === "secret";
        const shown = secretShown[field.key] ?? false;

        return (
          <div key={field.key} className="field">
            <div className="labelRow">
              <div className="label">
                {field.label}
                {field.required && <span style={{ color: "var(--danger)", marginLeft: 4 }}>*</span>}
              </div>
              {field.help && <div className="help">{field.help}</div>}
            </div>

            {field.type === "select" && field.options ? (
              <select
                value={value}
                onChange={(e) => onEnvChange((m) => envSet(m, field.key, e.target.value))}
                style={{ width: "100%", padding: "8px 12px", borderRadius: 10, border: "1px solid var(--line)", background: "rgba(255,255,255,0.7)", fontSize: 14 }}
              >
                {field.options.map((opt) => (
                  <option key={opt} value={opt}>{opt}</option>
                ))}
              </select>
            ) : field.type === "bool" ? (
              <label className="pill" style={{ cursor: "pointer", userSelect: "none", alignSelf: "flex-start" }}>
                <input
                  type="checkbox"
                  checked={value.toLowerCase() === "true"}
                  onChange={(e) => onEnvChange((m) => envSet(m, field.key, String(e.target.checked)))}
                  style={{ width: 16, height: 16 }}
                />
                {field.label}
              </label>
            ) : field.type === "number" ? (
              <input
                type="number"
                value={value}
                min={field.min}
                max={field.max}
                onChange={(e) => onEnvChange((m) => envSet(m, field.key, e.target.value))}
                placeholder={String(field.default ?? "")}
                style={{ width: "100%" }}
              />
            ) : (
              <div style={{ display: "flex", gap: 6 }}>
                <input
                  type={isSecret && !shown ? "password" : "text"}
                  value={value}
                  onChange={(e) => onEnvChange((m) => envSet(m, field.key, e.target.value))}
                  placeholder={field.type === "secret" ? t("skills.secretPlaceholder") : String(field.default ?? "")}
                  style={{ flex: 1 }}
                />
                {isSecret && (
                  <button
                    type="button"
                    onClick={() => setSecretShown((s) => ({ ...s, [field.key]: !s[field.key] }))}
                    style={{ padding: "6px 10px", borderRadius: 8, border: "1px solid var(--line)", background: "transparent", cursor: "pointer", fontSize: 12 }}
                  >
                    {shown ? t("skills.hide") : t("skills.show")}
                  </button>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── 技能卡片 ───

function SkillCard({
  skill,
  expanded,
  onToggleExpand,
  onToggleEnabled,
  envDraft,
  onEnvChange,
  onSaveConfig,
  saving,
}: {
  skill: SkillInfo;
  expanded: boolean;
  onToggleExpand: () => void;
  onToggleEnabled: () => void;
  envDraft: EnvMap;
  onEnvChange: (fn: (prev: EnvMap) => EnvMap) => void;
  onSaveConfig: () => void;
  saving: boolean;
}) {
  const hasConfig = skill.config && skill.config.length > 0;
  const configComplete = skill.configComplete ?? true;
  const statusColor = skill.enabled === false
    ? "var(--muted)"
    : configComplete
      ? "rgba(16,185,129,1)"
      : "rgba(245,158,11,1)";
  const { t } = useTranslation();
  const statusText = skill.enabled === false
    ? t("skills.disabled")
    : configComplete
      ? t("skills.configComplete")
      : t("skills.configIncomplete");

  return (
    <div className="card" style={{ marginTop: 0 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div style={{ width: 36, height: 36, borderRadius: 10, background: skill.system ? "rgba(14,165,233,0.1)" : "rgba(124,58,237,0.1)", display: "grid", placeItems: "center", fontSize: 18, flexShrink: 0 }}>
          {skill.system ? <IconGear size={18} /> : <IconZap size={18} />}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontWeight: 800, fontSize: 14 }}>{skill.name}</span>
            <span className="pill" style={{ fontSize: 11, borderColor: statusColor + "33" }}>
              <span style={{ display: "inline-block", width: 6, height: 6, borderRadius: 3, background: statusColor, marginRight: 4 }} />
              {statusText}
            </span>
            <span style={{ fontSize: 11, opacity: 0.5 }}>{skill.system ? t("skills.system") : t("skills.external")}</span>
          </div>
          <div style={{ fontSize: 12, opacity: 0.6, marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {skill.description}
          </div>
        </div>
        <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
          <label style={{ cursor: "pointer", display: "flex", alignItems: "center", gap: 4, fontSize: 12 }}>
            <input
              type="checkbox"
              checked={skill.enabled !== false}
              onChange={onToggleEnabled}
              style={{ width: 16, height: 16 }}
            />
            {t("skills.enabled")}
          </label>
          {hasConfig && (
            <button
              onClick={onToggleExpand}
              style={{ padding: "4px 10px", borderRadius: 8, border: "1px solid var(--line)", background: expanded ? "rgba(14,165,233,0.08)" : "transparent", cursor: "pointer", fontSize: 12, fontWeight: 700 }}
            >
              {expanded ? t("chat.collapse") : t("skills.configure")}
            </button>
          )}
        </div>
      </div>

      {expanded && hasConfig && skill.config && (
        <div style={{ marginTop: 10, borderTop: "1px solid var(--line)", paddingTop: 10 }}>
          <SkillConfigForm fields={skill.config} envDraft={envDraft} onEnvChange={onEnvChange} />
          <button
            className="btnPrimary"
            onClick={onSaveConfig}
            disabled={saving}
            style={{ marginTop: 10, fontSize: 13, padding: "6px 20px" }}
          >
            {saving ? t("skills.saving") : t("skills.saveConfig")}
          </button>
        </div>
      )}
    </div>
  );
}

// ─── 市场技能卡片 ───

function MarketplaceSkillCard({
  skill,
  onInstall,
  installing,
}: {
  skill: MarketplaceSkill;
  onInstall: () => void;
  installing: boolean;
}) {
  const { t } = useTranslation();
  return (
    <div className="card" style={{ marginTop: 0 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div style={{ width: 36, height: 36, borderRadius: 10, background: "rgba(124,58,237,0.08)", display: "grid", placeItems: "center", fontSize: 18, flexShrink: 0 }}>
          <IconPackage size={18} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontWeight: 800, fontSize: 14 }}>{skill.name}</span>
            {skill.installed && <span className="pill" style={{ fontSize: 11, borderColor: "rgba(16,185,129,0.25)" }}>{t("skills.installed")}</span>}
            {skill.stars != null && <span style={{ fontSize: 11, opacity: 0.5, display: "inline-flex", alignItems: "center", gap: 4 }}><IconStar size={11} />{skill.stars}</span>}
          </div>
          <div style={{ fontSize: 12, opacity: 0.6, marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{skill.description}</div>
          <div style={{ fontSize: 11, opacity: 0.4, marginTop: 2 }}>by {skill.author}</div>
          {skill.tags && skill.tags.length > 0 && (
            <div style={{ display: "flex", gap: 4, marginTop: 4, flexWrap: "wrap" }}>
              {skill.tags.map((tag) => (
                <span key={tag} style={{ fontSize: 10, padding: "2px 6px", borderRadius: 4, background: "rgba(14,165,233,0.08)", color: "var(--brand)" }}>
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>
        <button
          className={skill.installed ? "" : "btnPrimary"}
          onClick={onInstall}
          disabled={skill.installed || installing}
          style={{ fontSize: 12, padding: "6px 14px", flexShrink: 0 }}
        >
          {installing ? t("common.loading") : skill.installed ? t("skills.installed") : t("skills.install")}
        </button>
      </div>
    </div>
  );
}

// ─── 主组件 ───

export function SkillManager({
  venvDir,
  currentWorkspaceId,
  envDraft,
  onEnvChange,
  onSaveEnvKeys,
}: {
  venvDir: string;
  currentWorkspaceId: string | null;
  envDraft: EnvMap;
  onEnvChange: (fn: (prev: EnvMap) => EnvMap) => void;
  onSaveEnvKeys: (keys: string[]) => Promise<void>;
}) {
  const [tab, setTab] = useState<"installed" | "marketplace">("installed");
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedSkill, setExpandedSkill] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [marketplace, setMarketplace] = useState<MarketplaceSkill[]>([]);
  const [marketLoading, setMarketLoading] = useState(false);
  const [marketSearch, setMarketSearch] = useState("");
  const [installing, setInstalling] = useState<string | null>(null);
  const { t } = useTranslation();

  // ── 加载已安装技能 ──
  const loadSkills = useCallback(async () => {
    if (!venvDir || !currentWorkspaceId) return;
    setLoading(true);
    setError(null);
    try {
      const raw = await invoke<string>("openakita_list_skills", { venvDir, workspaceId: currentWorkspaceId });
      const data = JSON.parse(raw);
      const list: SkillInfo[] = (data.skills || []).map((s: Record<string, unknown>) => ({
        name: s.name as string,
        description: s.description as string || "",
        system: s.system as boolean || false,
        enabled: s.enabled as boolean | undefined,
        toolName: s.tool_name as string | null,
        category: s.category as string | null,
        path: s.path as string | null,
        config: (s.config as SkillConfigField[] | null) || null,
        configComplete: true,  // 由 useMemo 动态计算，这里先占位
      }));
      setSkills(list);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [venvDir, currentWorkspaceId]);  // 移除 envDraft 依赖，避免每次按键都触发后端调用

  useEffect(() => {
    loadSkills();
  }, [loadSkills]);

  // ── 检查配置是否完整（纯函数，不依赖于状态） ──
  function checkConfigComplete(config: SkillConfigField[] | null | undefined, env: EnvMap): boolean {
    if (!config || config.length === 0) return true;
    return config.filter((f) => f.required).every((f) => {
      const v = env[f.key];
      return v != null && v.trim() !== "";
    });
  }

  // 动态计算每个技能的 configComplete 状态（响应 envDraft 变化，但不触发后端调用）
  const skillsWithConfig = useMemo(() =>
    skills.map((s) => ({
      ...s,
      configComplete: checkConfigComplete(s.config, envDraft),
    })),
    [skills, envDraft],
  );

  // ── 保存技能配置 ──
  const handleSaveConfig = useCallback(async (skill: SkillInfo) => {
    if (!skill.config) return;
    setSaving(true);
    try {
      // 确保未手动修改但有默认值的字段也写入 envDraft，否则 saveEnvKeys 会跳过它们
      for (const f of skill.config) {
        if (f.default != null) {
          onEnvChange((m) => {
            if (Object.prototype.hasOwnProperty.call(m, f.key)) return m;  // 用户已修改过，不覆盖
            return envSet(m, f.key, String(f.default));
          });
        }
      }
      const keys = skill.config.map((f) => f.key);
      await onSaveEnvKeys(keys);
      // 刷新
      await loadSkills();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }, [onSaveEnvKeys, loadSkills, onEnvChange]);

  // ── 切换启用/禁用 ──
  const handleToggleEnabled = useCallback(async (skill: SkillInfo) => {
    // TODO: 通过 bridge 更新 skills.json 的 external_allowlist
    setSkills((prev) => prev.map((s) =>
      s.name === skill.name ? { ...s, enabled: !(s.enabled !== false) } : s
    ));
  }, []);

  // ── 加载市场技能 ──
  const loadMarketplace = useCallback(async () => {
    setMarketLoading(true);
    try {
      // TODO: 从 bridge 获取市场技能列表
      // 暂用占位数据
      setMarketplace([
        {
          name: "web-search",
          description: "使用 Serper/Google 进行网络搜索",
          author: "openakita",
          url: "github:openakita/skills/web-search",
          stars: 42,
          tags: ["搜索", "网络"],
          installed: skills.some((s) => s.name === "web-search"),
        },
        {
          name: "code-interpreter",
          description: "Python 代码解释器，支持数据分析和可视化",
          author: "openakita",
          url: "github:openakita/skills/code-interpreter",
          stars: 38,
          tags: ["代码", "数据分析"],
          installed: skills.some((s) => s.name === "code-interpreter"),
        },
        {
          name: "browser-use",
          description: "浏览器自动化，支持网页操作和数据抓取",
          author: "openakita",
          url: "github:openakita/skills/browser-use",
          stars: 25,
          tags: ["浏览器", "自动化"],
          installed: skills.some((s) => s.name === "browser-use"),
        },
      ]);
    } finally {
      setMarketLoading(false);
    }
  }, [skills]);

  useEffect(() => {
    if (tab === "marketplace") {
      loadMarketplace();
    }
  }, [tab, loadMarketplace]);

  // ── 安装技能 ──
  const handleInstall = useCallback(async (skill: MarketplaceSkill) => {
    if (!venvDir || !currentWorkspaceId) {
      setError("环境未就绪：请先完成 Python 环境和工作区配置");
      return;
    }
    setInstalling(skill.name);
    try {
      await invoke<string>("openakita_install_skill", {
        venvDir,
        workspaceId: currentWorkspaceId,
        url: skill.url,
      });
      setMarketplace((prev) => prev.map((s) =>
        s.name === skill.name ? { ...s, installed: true } : s
      ));
      await loadSkills();
      // 安装后自动切换到「已安装」标签并展开配置面板
      setTab("installed");
      setExpandedSkill(skill.name);
    } catch (e) {
      setError(String(e));
    } finally {
      setInstalling(null);
    }
  }, [loadSkills, venvDir, currentWorkspaceId]);

  const filteredMarketplace = useMemo(() => {
    if (!marketSearch.trim()) return marketplace;
    const q = marketSearch.toLowerCase();
    return marketplace.filter((s) =>
      s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q) || (s.tags || []).some((t) => t.includes(q))
    );
  }, [marketplace, marketSearch]);

  return (
    <>
      {/* Tab 切换 */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <button
          className={tab === "installed" ? "btnPrimary" : ""}
          onClick={() => setTab("installed")}
          style={{ fontSize: 13, padding: "6px 20px" }}
        >
          {t("skills.installed")} ({skillsWithConfig.length})
        </button>
        <button
          className={tab === "marketplace" ? "btnPrimary" : ""}
          onClick={() => setTab("marketplace")}
          style={{ fontSize: 13, padding: "6px 20px" }}
        >
          {t("skills.marketplace")}
        </button>
        <div style={{ flex: 1 }} />
        <button
          onClick={loadSkills}
          disabled={loading}
          style={{ fontSize: 12, padding: "6px 14px", borderRadius: 8, border: "1px solid var(--line)", cursor: "pointer" }}
        >
          {loading ? t("common.loading") : t("topbar.refresh")}
        </button>
      </div>

      {error && <div className="errorBox" style={{ marginBottom: 12 }}>{error}</div>}

      {/* 已安装技能 */}
      {tab === "installed" && (
        <div style={{ display: "grid", gap: 10 }}>
          {loading && skillsWithConfig.length === 0 && <div className="cardHint">{t("skills.loading")}</div>}
          {!loading && skillsWithConfig.length === 0 && (
            <div className="card" style={{ textAlign: "center", padding: "30px 20px" }}>
              <div style={{ marginBottom: 8, display: "flex", justifyContent: "center" }}><IconZap size={36} /></div>
              <div style={{ fontWeight: 700, marginBottom: 4 }}>{t("skills.noSkills")}</div>
              <div className="help">{t("skills.noSkillsHint")}</div>
            </div>
          )}
          {skillsWithConfig.map((skill) => (
            <SkillCard
              key={skill.name}
              skill={skill}
              expanded={expandedSkill === skill.name}
              onToggleExpand={() => setExpandedSkill(expandedSkill === skill.name ? null : skill.name)}
              onToggleEnabled={() => handleToggleEnabled(skill)}
              envDraft={envDraft}
              onEnvChange={onEnvChange}
              onSaveConfig={() => handleSaveConfig(skill)}
              saving={saving}
            />
          ))}
        </div>
      )}

      {/* 技能市场 */}
      {tab === "marketplace" && (
        <>
          <div style={{ marginBottom: 12 }}>
            <input
              value={marketSearch}
              onChange={(e) => setMarketSearch(e.target.value)}
              placeholder={t("skills.searchPlaceholder")}
              style={{ width: "100%", fontSize: 14 }}
            />
          </div>
          <div style={{ display: "grid", gap: 10 }}>
            {marketLoading && <div className="cardHint">{t("common.loading")}</div>}
            {filteredMarketplace.map((skill) => (
              <MarketplaceSkillCard
                key={skill.name}
                skill={skill}
                onInstall={() => handleInstall(skill)}
                installing={installing === skill.name}
              />
            ))}
            {!marketLoading && filteredMarketplace.length === 0 && (
              <div className="cardHint" style={{ textAlign: "center", padding: 20 }}>
                {marketSearch ? "没有匹配的技能" : "暂无可用技能"}
              </div>
            )}
          </div>
        </>
      )}
    </>
  );
}
