import { NavLink } from "react-router-dom";

interface WorkspaceTopBarProps {
  qaSearch: string;
  onQaSearchChange: (q: string) => void;
  onExport?: () => void;
  hasUnsaved?: boolean;
  onSave?: () => void;
}

export function WorkspaceTopBar({
  qaSearch,
  onQaSearchChange,
  onExport,
  hasUnsaved,
  onSave,
}: WorkspaceTopBarProps) {
  return (
    <header className="wb-topbar">
      <div style={{ display: "flex", alignItems: "center" }}>
        <div className="wb-search-wrap">
          <span className="material-symbols-outlined" style={{ fontSize: 18, color: "#717786" }}>
            search
          </span>
          <input
            type="text"
            placeholder="搜索 QA 对…"
            value={qaSearch}
            onChange={(e) => onQaSearchChange(e.target.value)}
          />
        </div>
        <nav className="wb-nav-tabs">
          <NavLink to="/workspace" className={({ isActive }) => `wb-nav-tab ${isActive ? "active" : ""}`}>
            工作台
          </NavLink>
          <NavLink to="/settings" className={({ isActive }) => `wb-nav-tab ${isActive ? "active" : ""}`}>
            设置
          </NavLink>
        </nav>
      </div>
      <div className="wb-topbar-actions">
        {hasUnsaved && onSave && (
          <button type="button" className="wb-export-btn" style={{ background: "#414755" }} onClick={onSave}>
            保存
          </button>
        )}
        <button type="button" className="wb-icon-btn material-symbols-outlined" aria-label="通知">
          notifications
        </button>
        <button type="button" className="wb-icon-btn material-symbols-outlined" aria-label="帮助">
          help
        </button>
        <div className="wb-avatar" aria-hidden="true">U</div>
        {onExport && (
          <button type="button" className="wb-export-btn" onClick={onExport}>
            导出
          </button>
        )}
      </div>
    </header>
  );
}
