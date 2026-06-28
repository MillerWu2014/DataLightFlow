import type { ExportScope } from "../types";

interface ExportDialogProps {
  onExport: (scope: ExportScope) => void;
  onClose: () => void;
}

export function ExportDialog({ onExport, onClose }: ExportDialogProps) {
  return (
    <div className="modal-overlay" role="dialog" aria-modal="true">
      <div className="modal">
        <h2 className="heading-16" style={{ marginBottom: 8 }}>导出 Alpaca JSONL</h2>
        <p className="copy-14" style={{ color: "var(--gray-900)", marginBottom: 16 }}>
          选择导出范围。软删除项不会包含在「仅通过阈值」结果中。
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <button className="btn btn-secondary" onClick={() => onExport("passed")}>
            仅通过阈值
          </button>
          <button className="btn btn-secondary" onClick={() => onExport("all")}>
            全部未删除
          </button>
          <button className="btn btn-secondary" onClick={() => onExport("selected")}>
            当前选中
          </button>
        </div>
        <div className="modal-actions">
          <button className="btn btn-tertiary btn-sm" onClick={onClose}>取消</button>
        </div>
      </div>
    </div>
  );
}
