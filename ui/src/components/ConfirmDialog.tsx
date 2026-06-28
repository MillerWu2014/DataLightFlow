interface ConfirmDialogProps {
  title: string;
  message: string;
  confirmLabel: string;
  cancelLabel?: string;
  destructive?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  extraAction?: { label: string; onClick: () => void };
}

export function ConfirmDialog({
  title,
  message,
  confirmLabel,
  cancelLabel = "取消",
  destructive,
  onConfirm,
  onCancel,
  extraAction,
}: ConfirmDialogProps) {
  return (
    <div className="modal-overlay" role="dialog" aria-modal="true">
      <div className="modal">
        <h2 className="heading-16" style={{ marginBottom: 8 }}>{title}</h2>
        <p className="copy-14" style={{ color: "var(--gray-900)" }}>{message}</p>
        <div className="modal-actions">
          <button className="btn btn-secondary btn-sm" onClick={onCancel}>{cancelLabel}</button>
          {extraAction && (
            <button className="btn btn-secondary btn-sm" onClick={extraAction.onClick}>
              {extraAction.label}
            </button>
          )}
          <button
            className={`btn btn-sm ${destructive ? "btn-error" : "btn-primary"}`}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
