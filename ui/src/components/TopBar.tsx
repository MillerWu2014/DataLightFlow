import { NavLink } from "react-router-dom";

interface TopBarProps {
  title?: string;
  hasUnsaved?: boolean;
  onSave?: () => void;
  onExport?: () => void;
  saveDisabled?: boolean;
}

export function TopBar({ title, hasUnsaved, onSave, onExport, saveDisabled }: TopBarProps) {
  return (
    <header className="topbar">
      <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
        <span className="heading-16" style={{ fontWeight: 600 }}>DataLight</span>
        <nav style={{ display: "flex", gap: 20 }}>
          <NavLink to="/workspace" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
            工作台
          </NavLink>
          <NavLink to="/settings" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
            设置
          </NavLink>
        </nav>
        {title && (
          <span className="copy-14" style={{ color: "var(--gray-700)" }}>
            {title}
          </span>
        )}
        {hasUnsaved && <span className="unsaved-badge">未保存更改</span>}
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        {onSave && (
          <button className="btn btn-secondary btn-sm" onClick={onSave} disabled={saveDisabled}>
            保存会话
          </button>
        )}
        {onExport && (
          <button className="btn btn-primary btn-sm" onClick={onExport}>
            导出 JSONL
          </button>
        )}
      </div>
    </header>
  );
}
