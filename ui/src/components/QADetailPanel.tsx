import { useState } from "react";
import type { QAWorkspaceItem, WorkspaceSession } from "../types";
import { QualityMetrics } from "./ScoreDetails";
import { getContext } from "../lib/qa-utils";
import { ConfirmDialog } from "./ConfirmDialog";

interface QADetailPanelProps {
  item: QAWorkspaceItem | null;
  session: WorkspaceSession | null;
  visible: boolean;
  onClose?: () => void;
  onUpdate: (id: string, patch: { question?: string; answer?: string }) => void;
  onDelete: (id: string) => void;
  onMarkReviewed?: (id: string) => void;
}

export function QADetailPanel({
  item,
  session,
  visible,
  onClose,
  onUpdate,
  onDelete,
  onMarkReviewed,
}: QADetailPanelProps) {
  const [confirmDelete, setConfirmDelete] = useState(false);

  if (!visible) return null;

  const isAtomic = session?.generator === "atomic";
  const context = item ? getContext(item.record) : "";

  return (
    <aside className="wb-detail">
      <div className="wb-detail-header">
        <h3 style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>详情</h3>
        <div style={{ display: "flex", gap: 4 }}>
          <button type="button" className="wb-icon-btn material-symbols-outlined" aria-label="标记">
            flag
          </button>
          {onClose && (
            <button type="button" className="wb-icon-btn material-symbols-outlined" aria-label="关闭" onClick={onClose}>
              close
            </button>
          )}
        </div>
      </div>

      {!session || !item ? (
        <div className="wb-detail-placeholder">
          <p style={{ fontWeight: 600, marginBottom: 8 }}>选择一条 QA</p>
          <p style={{ fontSize: 14 }}>点击列表中的卡片查看质量指标并编辑。</p>
        </div>
      ) : (
        <>
          <div className="wb-detail-body custom-scroll">
            <QualityMetrics record={item.record} showAtomicNote={isAtomic} />

            <section style={{ display: "flex", flexDirection: "column", gap: 24 }}>
              <div>
                <label className="wb-field-label">问题</label>
                <textarea
                  className="wb-field-textarea"
                  style={{ minHeight: 80 }}
                  value={item.record.question || ""}
                  onChange={(e) => onUpdate(item.id, { question: e.target.value })}
                />
              </div>
              <div>
                <label className="wb-field-label">答案</label>
                <textarea
                  className="wb-field-textarea"
                  style={{ minHeight: 160 }}
                  value={item.record.answer || ""}
                  onChange={(e) => onUpdate(item.id, { answer: e.target.value })}
                />
              </div>
            </section>

            {context && (
              <section>
                <h4 className="wb-metrics-title" style={{ marginBottom: 12 }}>来源上下文</h4>
                <div className="wb-source-block">
                  {context.split("\n")[0]?.startsWith("#") && (
                    <p className="wb-source-heading">{context.split("\n")[0]}</p>
                  )}
                  <p>{context}</p>
                </div>
              </section>
            )}
          </div>

          <div className="wb-detail-footer">
            <div style={{ display: "flex", gap: 8 }}>
              <button type="button" className="wb-btn-regenerate">
                <span className="material-symbols-outlined" style={{ fontSize: 18 }}>refresh</span>
                重新生成
              </button>
              <button
                type="button"
                className="wb-btn-delete-icon material-symbols-outlined"
                aria-label="删除 QA"
                onClick={() => setConfirmDelete(true)}
              >
                delete
              </button>
            </div>
            <button
              type="button"
              className="wb-btn-reviewed"
              onClick={() => onMarkReviewed?.(item.id)}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 18 }}>done_all</span>
              标记为已审核
            </button>
          </div>
        </>
      )}

      {confirmDelete && item && (
        <ConfirmDialog
          title="删除这条 QA？"
          message="删除后可在保存前通过重新加载会话恢复（若未保存）。"
          confirmLabel="删除 QA"
          destructive
          onConfirm={() => {
            onDelete(item.id);
            setConfirmDelete(false);
          }}
          onCancel={() => setConfirmDelete(false)}
        />
      )}
    </aside>
  );
}
