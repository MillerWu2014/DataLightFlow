import type { QARecord } from "../types";
import { SCORE_DIMENSIONS } from "../types";
import { averageScore } from "../lib/qa-utils";

function MetricSegments({ grade }: { grade: number }) {
  const filled = Math.round(grade);
  const isLow = grade < 3.5;
  return (
    <div style={{ display: "flex", gap: 4 }}>
      {[1, 2, 3, 4, 5].map((n) => (
        <div
          key={n}
          className={`wb-score-segment ${n <= filled ? (isLow ? "fill-tertiary" : "fill-primary") : ""}`}
        />
      ))}
    </div>
  );
}

interface QualityMetricsProps {
  record: QARecord;
  showAtomicNote?: boolean;
}

export function QualityMetrics({ record, showAtomicNote }: QualityMetricsProps) {
  if (showAtomicNote) {
    return (
      <p style={{ fontSize: 14, color: "#414755" }}>
        生成阶段已完成召回 / 黄金文档验证，无四维质量评分。
      </p>
    );
  }

  const avg = averageScore(record);
  if (avg === null) return null;

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <h4 className="wb-metrics-title">质量指标</h4>
        <span className="wb-metrics-overall">
          {avg}
          <span> 综合</span>
        </span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {SCORE_DIMENSIONS.map((dim) => {
          const grade = record[dim.gradeKey as keyof QARecord] as number | undefined;
          if (typeof grade !== "number") return null;
          const isLow = grade < 3.5;
          return (
            <div key={dim.key} className="wb-metric-row">
              <div className="wb-metric-label">
                <span>{dim.label}</span>
                <span className={`wb-metric-value ${isLow ? "low" : ""}`}>{grade.toFixed(1)}</span>
              </div>
              <MetricSegments grade={grade} />
            </div>
          );
        })}
      </div>
    </section>
  );
}
