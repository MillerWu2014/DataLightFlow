import { useRef, useState } from "react";
import type { GeneratorType, PipelineParamsSnapshot, PipelineType } from "../types";
import { defaultParams } from "../lib/qa-utils";

interface PipelineConfigProps {
  pipeline: PipelineType;
  generator: GeneratorType;
  params: PipelineParamsSnapshot;
  disabled?: boolean;
  onPipelineChange: (p: PipelineType) => void;
  onGeneratorChange: (g: GeneratorType) => void;
  onParamsChange: (p: PipelineParamsSnapshot) => void;
  onStart: () => void;
  fileName: string | null;
  fileSize: number | null;
  onFileSelect: (file: File) => void;
}

export function PipelineConfigPanel({
  pipeline,
  generator,
  params,
  disabled,
  onPipelineChange,
  onGeneratorChange,
  onParamsChange,
  onStart,
  fileName,
  fileSize,
  onFileSelect,
}: PipelineConfigProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) onFileSelect(file);
  };

  const isMultihop = pipeline === "multihop";
  const hideMinScore = generator === "atomic" || isMultihop;

  return (
    <div style={{ padding: 24, maxWidth: 640, margin: "0 auto" }}>
      <h2 className="heading-20" style={{ marginBottom: 8 }}>上传并配置</h2>
      <p className="copy-14" style={{ color: "var(--gray-900)", marginBottom: 24 }}>
        尚无 QA。上传 Markdown 并选择生成模式以创建第一批问答对。
      </p>

      <div
        className={`upload-zone ${dragOver ? "dragover" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".md"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onFileSelect(f);
          }}
        />
        {fileName ? (
          <>
            <p className="copy-14" style={{ fontWeight: 500 }}>{fileName}</p>
            <p className="copy-14" style={{ color: "var(--gray-700)" }}>
              {(fileSize ?? 0) > 0 ? `${((fileSize ?? 0) / 1024).toFixed(1)} KB` : ""} · 点击或拖拽替换
            </p>
          </>
        ) : (
          <>
            <p className="copy-14">拖拽或点击上传 .md 文件</p>
            <p className="copy-14" style={{ color: "var(--gray-700)", marginTop: 4 }}>仅支持单个 Markdown 文件</p>
          </>
        )}
      </div>

      <div style={{ marginTop: 24 }}>
        <span className="field-label">流水线类型</span>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {([
            ["singlehop", "default", "单跳 · 通用"],
            ["singlehop", "atomic", "单跳 · 原子任务（高验证）"],
            ["singlehop", "taxonomy", "单跳 · 分类体系"],
            ["multihop", "default", "多跳推理"],
          ] as const).map(([p, g, label]) => {
            const checked = pipeline === p && (p === "multihop" ? true : generator === g);
            return (
              <label key={`${p}-${g}`} className="copy-14" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input
                  type="radio"
                  name="pipeline"
                  checked={checked}
                  onChange={() => {
                    onPipelineChange(p);
                    if (p === "singlehop") onGeneratorChange(g as GeneratorType);
                  }}
                />
                {label}
              </label>
            );
          })}
        </div>
      </div>

      <div style={{ marginTop: 16, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <div className="field-row">
          <label className="field-label">目标语言</label>
          <select
            className="select"
            value={params.language}
            onChange={(e) => onParamsChange({ ...params, language: e.target.value as PipelineParamsSnapshot["language"] })}
          >
            <option value="zh">中文</option>
            <option value="en">英文</option>
            <option value="auto">自动</option>
          </select>
        </div>
        <div className="field-row">
          <label className="field-label">每 chunk 最多 QA 数</label>
          <input
            className="input"
            type="number"
            min={1}
            value={params.questionNum}
            onChange={(e) => onParamsChange({ ...params, questionNum: Number(e.target.value) })}
          />
        </div>
      </div>

      <button
        className="btn btn-tertiary btn-sm"
        style={{ marginTop: 8 }}
        onClick={() => setAdvancedOpen(!advancedOpen)}
      >
        {advancedOpen ? "收起" : "展开"}高级参数
      </button>

      {advancedOpen && (
        <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="field-row">
            <label className="field-label">每块最大词数</label>
            <input
              className="input"
              type="number"
              value={params.chunkWords}
              onChange={(e) => onParamsChange({ ...params, chunkWords: Number(e.target.value) })}
            />
          </div>
          <div className="field-row">
            <label className="field-label">块重叠词数{isMultihop ? "（多跳语义切块未使用）" : ""}</label>
            <input
              className="input"
              type="number"
              value={params.overlapWords}
              disabled={isMultihop}
              onChange={(e) => onParamsChange({ ...params, overlapWords: Number(e.target.value) })}
            />
          </div>
          {!hideMinScore && (
            <div className="field-row">
              <label className="field-label">最低质量分 ({params.minScore})</label>
              <input
                type="range"
                min={1}
                max={5}
                step={0.5}
                value={params.minScore}
                onChange={(e) => onParamsChange({ ...params, minScore: Number(e.target.value) })}
                style={{ width: "100%" }}
              />
            </div>
          )}
          {generator === "atomic" && (
            <div className="field-row">
              <label className="field-label">atomic 每块结论上限</label>
              <input
                className="input"
                type="number"
                value={params.atomicMaxPerTask ?? 10}
                onChange={(e) => onParamsChange({ ...params, atomicMaxPerTask: Number(e.target.value) })}
              />
            </div>
          )}
          {!isMultihop && (
            <>
              <p className="field-label" style={{ marginTop: 4 }}>后处理（可选）</p>
              <label className="copy-14" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input
                  type="checkbox"
                  checked={params.expandQa}
                  onChange={(e) => onParamsChange({ ...params, expandQa: e.target.checked })}
                />
                生成后扩写（expand_qa）
              </label>
              {params.expandQa && (
                <select
                  className="select"
                  value={params.expandMode}
                  onChange={(e) => onParamsChange({ ...params, expandMode: e.target.value as PipelineParamsSnapshot["expandMode"] })}
                >
                  <option value="detail">细节（detail）</option>
                  <option value="contextual">上下文（contextual）</option>
                  <option value="reasoning">推理（reasoning）</option>
                </select>
              )}
              <label className="copy-14" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input
                  type="checkbox"
                  checked={params.addThink}
                  onChange={(e) => onParamsChange({ ...params, addThink: e.target.checked })}
                />
                生成 Think（add_think）
              </label>

              <p className="field-label" style={{ marginTop: 8 }}>Agentic 增强（单跳生成后）</p>
              <p className="copy-14" style={{ color: "var(--gray-700)", marginBottom: 8 }}>
                深挖 / 扩宽在 <code>qa_generated.jsonl</code> 之后执行，与扩写、Think 同为可选后处理；产物默认写入同目录 <code>qa_depth.jsonl</code> / <code>qa_width.jsonl</code>。
              </p>
              <label className="copy-14" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input
                  type="checkbox"
                  checked={params.addDepthQa}
                  onChange={(e) => onParamsChange({ ...params, addDepthQa: e.target.checked })}
                />
                Agentic 深挖（depth_qa）
              </label>
              {params.addDepthQa && (
                <div className="field-row">
                  <label className="field-label">深挖轮数 n_rounds</label>
                  <input
                    className="input"
                    type="number"
                    min={1}
                    max={5}
                    value={params.depthRounds}
                    onChange={(e) => onParamsChange({ ...params, depthRounds: Number(e.target.value) })}
                  />
                </div>
              )}
              <label className="copy-14" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input
                  type="checkbox"
                  checked={params.addWidthQa}
                  onChange={(e) => onParamsChange({ ...params, addWidthQa: e.target.checked })}
                />
                Agentic 扩宽（width_qa）
              </label>
              {params.addWidthQa && (
                <p className="copy-14" style={{ color: "var(--gray-700)" }}>
                  需要过滤后至少 2 条有效 QA；不足时后端输出空文件。
                </p>
              )}
            </>
          )}
        </div>
      )}

      <button
        className="btn btn-primary"
        style={{ marginTop: 24, width: "100%" }}
        disabled={disabled || !fileName}
        onClick={onStart}
      >
        {disabled ? "正在生成…" : "开始生成"}
      </button>
    </div>
  );
}

export { defaultParams };
