import { useEffect, useMemo, useState } from "react";
import { SettingsTopBar } from "../components/SettingsTopBar";
import { TaxonomyPreviewTable } from "../components/TaxonomyPreviewTable";
import { fetchConfig, updateConfig } from "../lib/api";
import { defaultSettings, saveSettings } from "../lib/storage";
import { useToast } from "../hooks/useToast";
import type { AppSettings } from "../types";

const PROVIDER_OPTIONS = [
  { value: "openai-compatible", label: "OpenAI 兼容 API" },
  { value: "lmstudio", label: "LM Studio（本地部署）" },
];

const SECTIONS = [
  {
    id: "llm",
    label: "大模型连接",
    icon: "hub",
    keywords: ["provider", "model", "url", "endpoint", "timeout", "temperature", "llm", "大模型", "服务商", "模型", "超时", "温度", "接口"],
  },
  {
    id: "presets",
    label: "生成预设",
    icon: "tune",
    keywords: ["output", "directory", "path", "archive", "preset", "输出", "目录", "归档"],
  },
  {
    id: "taxonomy",
    label: "分类体系",
    icon: "account_tree",
    keywords: ["taxonomy", "classification", "node", "schema", "hierarchy", "分类", "体系", "节点", "层级"],
  },
] as const;

function sectionMatchesSearch(sectionId: string, query: string): boolean {
  if (!query.trim()) return true;
  const q = query.toLowerCase();
  const section = SECTIONS.find((s) => s.id === sectionId);
  if (!section) return true;
  return (
    section.label.includes(query) ||
    section.label.toLowerCase().includes(q) ||
    section.keywords.some((k) => k.includes(q) || k.includes(query))
  );
}

export function SettingsPage() {
  const { showToast } = useToast();
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [activeSection, setActiveSection] = useState<string>("llm");
  const [paramSearch, setParamSearch] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchConfig().then(setSettings);
  }, []);

  const visibleSections = useMemo(
    () => SECTIONS.filter((s) => sectionMatchesSearch(s.id, paramSearch)),
    [paramSearch],
  );

  const scrollToSection = (id: string) => {
    setActiveSection(id);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const handleReset = () => {
    setSettings(defaultSettings());
    showToast("已恢复默认配置（尚未保存）");
  };

  const handleSave = async () => {
    if (!settings) return;
    setSaving(true);
    try {
      await updateConfig(settings);
      saveSettings(settings);
      showToast("配置已保存");
    } catch {
      showToast("保存失败，请重试", "error");
    } finally {
      setSaving(false);
    }
  };

  const handleExport = () => {
    if (!settings) return;
    const blob = new Blob([JSON.stringify(settings, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "datalight-settings.json";
    a.click();
    URL.revokeObjectURL(url);
    showToast("配置已导出");
  };

  if (!settings) {
    return (
      <div className="settings-root">
        <SettingsTopBar paramSearch={paramSearch} onParamSearchChange={setParamSearch} />
        <div className="settings-body" style={{ alignItems: "center", justifyContent: "center" }}>
          <p className="copy-14">加载配置中…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="settings-root">
      <SettingsTopBar
        paramSearch={paramSearch}
        onParamSearchChange={setParamSearch}
        onExport={handleExport}
      />

      <div className="settings-body">
        <aside className="settings-sidebar">
          <div className="settings-sidebar-header">
            <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 24 }}>
              <div className="settings-sidebar-icon">
                <span className="material-symbols-outlined" style={{ fontSize: 22 }}>settings</span>
              </div>
              <div>
                <h2 className="heading-16" style={{ fontWeight: 700, fontSize: 16 }}>设置</h2>
                <p className="label-12-mono" style={{ color: "#414755", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                  配置
                </p>
              </div>
            </div>
            <nav>
              {SECTIONS.map((s) => (
                <a
                  key={s.id}
                  className={`settings-nav-item ${activeSection === s.id ? "active" : ""}`}
                  href={`#${s.id}`}
                  onClick={(e) => {
                    e.preventDefault();
                    scrollToSection(s.id);
                  }}
                >
                  <span className="material-symbols-outlined settings-nav-icon">{s.icon}</span>
                  <span>{s.label}</span>
                </a>
              ))}
            </nav>
          </div>
          <div className="settings-sidebar-footer">
            <div className="wb-footer-item">
              <span className="material-symbols-outlined">archive</span>
              <span>归档</span>
            </div>
            <div className="wb-footer-item">
              <span className="material-symbols-outlined">delete</span>
              <span>回收站</span>
            </div>
          </div>
        </aside>

        <main className="settings-main custom-scroll">
          <div className="settings-main-inner">
            {visibleSections.length === 0 ? (
              <div className="empty-state">
                <p className="copy-14">没有匹配的参数</p>
              </div>
            ) : (
              <>
                {visibleSections.some((s) => s.id === "llm") && (
                  <section className="settings-section-block" id="llm">
                    <div className="settings-section-header">
                      <div>
                        <h3 className="settings-section-title">大模型连接</h3>
                        <p className="settings-section-desc">
                          配置大语言模型引擎与 API 连接（密钥仅存服务端，此处不含密钥字段）。
                        </p>
                      </div>
                      <span className="status-badge-ready">系统就绪</span>
                    </div>
                    <div className="glass-panel settings-grid-2">
                      <div>
                        <label className="settings-field-label">服务商选择</label>
                        <div className="settings-select-wrap">
                          <select
                            className="settings-select"
                            value={settings.llm.provider}
                            onChange={(e) =>
                              setSettings({ ...settings, llm: { ...settings.llm, provider: e.target.value } })
                            }
                          >
                            {PROVIDER_OPTIONS.map((o) => (
                              <option key={o.value} value={o.value}>{o.label}</option>
                            ))}
                          </select>
                          <span className="material-symbols-outlined settings-select-arrow">expand_more</span>
                        </div>
                      </div>
                      <div>
                        <label className="settings-field-label">模型名称</label>
                        <input
                          className="settings-input"
                          value={settings.llm.model}
                          onChange={(e) =>
                            setSettings({ ...settings, llm: { ...settings.llm, model: e.target.value } })
                          }
                        />
                      </div>
                      <div style={{ gridColumn: "1 / -1" }}>
                        <label className="settings-field-label">接口地址（Base URL）</label>
                        <input
                          className="settings-input"
                          value={settings.llm.baseUrl}
                          onChange={(e) =>
                            setSettings({ ...settings, llm: { ...settings.llm, baseUrl: e.target.value } })
                          }
                        />
                      </div>
                      <div style={{ gridColumn: "1 / -1" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                          <label className="settings-field-label" style={{ marginBottom: 0 }}>
                            超时时间
                          </label>
                          <span className="label-12-mono" style={{ color: "#0058bc", fontSize: 12 }}>
                            {settings.llm.timeoutSec} 秒
                          </span>
                        </div>
                        <input
                          type="range"
                          className="settings-range"
                          min={10}
                          max={300}
                          step={5}
                          value={settings.llm.timeoutSec}
                          onChange={(e) =>
                            setSettings({
                              ...settings,
                              llm: { ...settings.llm, timeoutSec: Number(e.target.value) },
                            })
                          }
                        />
                        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
                          <span className="label-12-mono" style={{ fontSize: 10, color: "#414755" }}>10 秒</span>
                          <span className="label-12-mono" style={{ fontSize: 10, color: "#414755" }}>300 秒（上限）</span>
                        </div>
                      </div>
                      <div style={{ gridColumn: "1 / -1" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                          <label className="settings-field-label" style={{ marginBottom: 0 }}>
                            温度
                          </label>
                          <span className="label-12-mono" style={{ color: "#0058bc", fontSize: 12 }}>
                            {settings.llm.temperature.toFixed(1)}
                          </span>
                        </div>
                        <input
                          type="range"
                          className="settings-range"
                          min={0}
                          max={2}
                          step={0.1}
                          value={settings.llm.temperature}
                          onChange={(e) =>
                            setSettings({
                              ...settings,
                              llm: { ...settings.llm, temperature: Number(e.target.value) },
                            })
                          }
                        />
                        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
                          <span className="label-12-mono" style={{ fontSize: 10, color: "#414755" }}>0</span>
                          <span className="label-12-mono" style={{ fontSize: 10, color: "#414755" }}>2（上限）</span>
                        </div>
                      </div>
                    </div>
                  </section>
                )}

                {visibleSections.some((s) => s.id === "presets") && (
                  <section className="settings-section-block" id="presets">
                    <div>
                      <h3 className="settings-section-title">输出配置</h3>
                      <p className="settings-section-desc">
                        定义生成数据集与日志的默认持久化路径。
                      </p>
                    </div>
                    <div className="glass-panel">
                      <label className="settings-field-label">根目录路径</label>
                      <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
                        <div className="path-input-wrap">
                          <span className="material-symbols-outlined path-input-icon">folder_open</span>
                          <input
                            className="settings-input path-input"
                            style={{ paddingLeft: 40 }}
                            value={settings.output.root}
                            onChange={(e) =>
                              setSettings({ ...settings, output: { ...settings.output, root: e.target.value } })
                            }
                          />
                        </div>
                        <button
                          type="button"
                          className="settings-browse-btn"
                          onClick={() => showToast("演示环境不支持浏览目录")}
                        >
                          浏览
                        </button>
                      </div>
                      <div className="toggle-row">
                        <div>
                          <h4 className="heading-16" style={{ fontSize: 14, fontWeight: 700 }}>完成后自动归档</h4>
                          <p className="copy-14" style={{ color: "#414755", marginTop: 4 }}>
                            任务空闲 30 天后自动归档至云存储。
                          </p>
                        </div>
                        <label className="toggle-switch">
                          <input
                            type="checkbox"
                            checked={settings.output.autoArchive}
                            onChange={(e) =>
                              setSettings({
                                ...settings,
                                output: { ...settings.output, autoArchive: e.target.checked },
                              })
                            }
                          />
                          <span className="toggle-slider" />
                        </label>
                      </div>
                    </div>
                  </section>
                )}

                {visibleSections.some((s) => s.id === "taxonomy") && (
                  <section className="settings-section-block" id="taxonomy">
                    <div>
                      <h3 className="settings-section-title">分类体系预览</h3>
                      <p className="settings-section-desc">
                        当前用于合成生成的数据分类层级只读预览。
                      </p>
                    </div>
                    <TaxonomyPreviewTable nodes={settings.taxonomy.nodes} />
                  </section>
                )}

                <div className="settings-footer">
                  <button type="button" className="settings-reset-btn" onClick={handleReset}>
                    恢复默认
                  </button>
                  <button type="button" className="settings-save-btn" onClick={handleSave} disabled={saving}>
                    {saving ? "保存中…" : "保存配置"}
                  </button>
                </div>
              </>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
