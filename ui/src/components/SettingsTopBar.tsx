import { NavLink } from "react-router-dom";

interface SettingsTopBarProps {
  paramSearch: string;
  onParamSearchChange: (q: string) => void;
  onExport?: () => void;
}

export function SettingsTopBar({ paramSearch, onParamSearchChange, onExport }: SettingsTopBarProps) {
  return (
    <header className="st-topbar">
      <div className="st-topbar-left">
        <span className="st-title">QA 数据工作台</span>
        <nav className="st-nav">
          <NavLink to="/workspace" className={({ isActive }) => `st-nav-link ${isActive ? "active" : ""}`}>
            工作台
          </NavLink>
          <NavLink to="/settings" className={({ isActive }) => `st-nav-link ${isActive ? "active" : ""}`}>
            设置
          </NavLink>
        </nav>
      </div>
      <div className="st-topbar-right">
        <div className="st-search">
          <span className="material-symbols-outlined st-search-icon">search</span>
          <input
            type="text"
            placeholder="搜索参数…"
            value={paramSearch}
            onChange={(e) => onParamSearchChange(e.target.value)}
          />
        </div>
        <button type="button" className="st-icon-btn material-symbols-outlined" aria-label="通知">
          notifications
        </button>
        <button type="button" className="st-icon-btn material-symbols-outlined" aria-label="帮助">
          help
        </button>
        <div className="st-topbar-divider">
          <button type="button" className="st-export-btn" onClick={onExport}>
            <span className="material-symbols-outlined" style={{ fontSize: 20 }}>publish</span>
            <span>导出</span>
          </button>
          <div className="st-avatar" aria-hidden="true">U</div>
        </div>
      </div>
    </header>
  );
}
