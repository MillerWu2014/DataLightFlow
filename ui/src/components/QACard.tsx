import type { QAWorkspaceItem, GeneratorType } from "../types";
import { averageScore } from "../lib/qa-utils";

function miniSegments(avg: number) {
  const filled = Math.round(avg);
  const isLow = avg < 3.5;
  const isHigh = avg >= 4;
  return [1, 2, 3, 4, 5].map((n) => {
    let cls = "wb-mini-segment fill-muted";
    if (n <= filled) {
      cls = isLow ? "wb-mini-segment fill-tertiary" : "wb-mini-segment fill-primary";
    } else if (isHigh && n === filled + 1) {
      cls = "wb-mini-segment fill-primary-dim";
    }
    return <div key={n} className={cls} />;
  });
}

interface QACardProps {
  item: QAWorkspaceItem;
  selected: boolean;
  generator?: GeneratorType;
  onClick: () => void;
}

export function QACard({ item, selected, generator, onClick }: QACardProps) {
  const { record } = item;
  const local = item.local ?? { deleted: false, dirty: false, selected: false };
  const isAtomic = generator === "atomic" || record.qa_type === "atomic";
  const avg = averageScore(record);
  const scoreClass = avg === null ? "" : avg >= 4 ? "high" : avg >= 3 ? "mid" : "low";
  const displayId = item.id.replace("qa-", "QA-");

  return (
    <div
      className={`wb-qa-card ${selected ? "selected" : ""} ${local.deleted ? "deleted" : ""}`}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onClick()}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            {record.hop_type && (
              <span className={`wb-hop-badge ${selected ? "primary" : "muted"}`}>
                {record.hop_type}
              </span>
            )}
            <span className="wb-qa-id">编号：{displayId}</span>
          </div>
          <p className={`wb-qa-question ${selected ? "selected" : "muted"}`}>
            {record.question}
          </p>
        </div>
        {!isAtomic && avg !== null && (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4, flexShrink: 0 }}>
            <span className={`wb-score-lg ${scoreClass}`}>
              {avg}
              <span className="wb-score-suffix">/5.0</span>
            </span>
            <div className="wb-mini-segments">{miniSegments(avg)}</div>
          </div>
        )}
        {isAtomic && (
          <span style={{ fontSize: 12, color: "#717786", fontFamily: "var(--font-mono)" }}>已验证</span>
        )}
      </div>
    </div>
  );
}
