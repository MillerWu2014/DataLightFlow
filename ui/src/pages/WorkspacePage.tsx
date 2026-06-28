import { useCallback, useEffect, useMemo, useState } from "react";
import { TaskHistorySidebar } from "../components/TaskHistorySidebar";
import { WorkspaceTopBar } from "../components/WorkspaceTopBar";
import { PipelineConfigPanel, defaultParams } from "../components/PipelineConfigPanel";
import { QACard } from "../components/QACard";
import { QADetailPanel } from "../components/QADetailPanel";
import { ExportDialog } from "../components/ExportDialog";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { useToast } from "../hooks/useToast";
import {
  loadTasks,
  saveTasks,
  loadSessions,
  saveSessions,
  initWorkspaceData,
} from "../lib/storage";
import {
  uploadMarkdown,
  createQaJob,
  getJobStatus,
  fetchJobQa,
  buildSessionFromRecords,
  saveSession,
  shouldSimulateFailure,
} from "../lib/api";
import { toAlpacaRow, downloadJsonl, pipelineStages } from "../lib/qa-utils";
import type {
  GeneratorType,
  PipelineParamsSnapshot,
  PipelineType,
  TaskHistoryEntry,
  WorkspaceSession,
  ExportScope,
} from "../types";

type WorkspaceFilter = "all" | "passed" | "flagged";

export function WorkspacePage() {
  const { showToast } = useToast();
  const [tasks, setTasks] = useState<TaskHistoryEntry[]>([]);
  const [sessions, setSessions] = useState<Record<string, WorkspaceSession>>({});
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [selectedQaId, setSelectedQaId] = useState<string | null>(null);
  const [listFilter, setListFilter] = useState<WorkspaceFilter>("all");
  const [qaSearch, setQaSearch] = useState("");
  const [showExport, setShowExport] = useState(false);
  const [pendingSwitch, setPendingSwitch] = useState<string | null>(null);

  const [isNewTask, setIsNewTask] = useState(false);
  const [uploadFileName, setUploadFileName] = useState<string | null>(null);
  const [uploadFileSize, setUploadFileSize] = useState<number | null>(null);
  const [uploadContent, setUploadContent] = useState("");
  const [uploadId, setUploadId] = useState<string | null>(null);
  const [pipeline, setPipeline] = useState<PipelineType>("singlehop");
  const [generator, setGenerator] = useState<GeneratorType>("default");
  const [params, setParams] = useState<PipelineParamsSnapshot>(defaultParams());
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    const { tasks: t, sessions: s } = initWorkspaceData();
    setTasks(t);
    setSessions(s);
    if (t.length > 0) {
      setSelectedJobId(t[0].jobId);
      setIsNewTask(false);
      const firstSession = t[0].sessionId ? s[t[0].sessionId] : null;
      if (firstSession?.items.length) {
        setSelectedQaId(firstSession.items[0].id);
      }
    }
  }, []);

  const currentTask = tasks.find((t) => t.jobId === selectedJobId) ?? null;
  const currentSession = currentTask?.sessionId ? sessions[currentTask.sessionId] ?? null : null;

  const hasUnsaved = useMemo(
    () => currentSession?.items.some((i) => i.local.dirty || i.local.deleted) ?? false,
    [currentSession],
  );

  const persist = useCallback((newTasks: TaskHistoryEntry[], newSessions: Record<string, WorkspaceSession>) => {
    setTasks(newTasks);
    setSessions(newSessions);
    saveTasks(newTasks);
    saveSessions(newSessions);
  }, []);

  const handleSelectTask = (jobId: string) => {
    if (hasUnsaved) {
      setPendingSwitch(jobId);
      return;
    }
    setSelectedJobId(jobId);
    setIsNewTask(false);
    const task = tasks.find((t) => t.jobId === jobId);
    const session = task?.sessionId ? sessions[task.sessionId] : null;
    setSelectedQaId(session?.items[0]?.id ?? null);
  };

  const handleNewTask = () => {
    if (hasUnsaved) {
      setPendingSwitch("__new__");
      return;
    }
    setIsNewTask(true);
    setSelectedJobId(null);
    setSelectedQaId(null);
    setUploadFileName(null);
    setUploadFileSize(null);
    setUploadContent("");
    setUploadId(null);
    setParams(defaultParams());
  };

  const handleFileSelect = async (file: File) => {
    try {
      const result = await uploadMarkdown(file);
      const text = await file.text();
      setUploadFileName(result.fileName);
      setUploadFileSize(result.size);
      setUploadContent(text);
      setUploadId(result.uploadId);
    } catch (e) {
      showToast(e instanceof Error ? e.message : "上传失败", "error");
    }
  };

  const handleStartGenerate = async () => {
    if (!uploadFileName || !uploadId) return;
    setGenerating(true);
    const jobParams = { ...params, chunkWords: pipeline === "multihop" ? params.chunkWords || 800 : params.chunkWords };

    try {
      if (shouldSimulateFailure(uploadFileName)) {
        throw new Error("大模型连接失败。请在设置中检查 base_url 与 model。");
      }

      const { jobId } = await createQaJob({
        uploadId,
        fileName: uploadFileName,
        uploadContent,
        pipeline,
        generator: pipeline === "singlehop" ? generator : undefined,
        params: jobParams,
      });

      const entry: TaskHistoryEntry = {
        jobId,
        sessionId: null,
        sourceFileName: uploadFileName,
        pipeline,
        generator: pipeline === "singlehop" ? generator : undefined,
        status: "running",
        stage: "切块",
        createdAt: new Date().toISOString(),
        params: jobParams,
        uploadContent,
      };

      persist([entry, ...tasks], sessions);
      setSelectedJobId(jobId);
      setIsNewTask(false);
      pollJob(jobId, entry);
    } catch (e) {
      showToast(e instanceof Error ? e.message : "任务创建失败", "error");
      setGenerating(false);
    }
  };

  const pollJob = (jobId: string, entry: TaskHistoryEntry) => {
    const interval = setInterval(async () => {
      try {
        const status = await getJobStatus(jobId, {
          pipeline: entry.pipeline,
          generator: entry.generator,
          params: entry.params!,
        });

        setTasks((prev) => {
          const updated = prev.map((t) =>
            t.jobId === jobId
              ? { ...t, status: status.status, stage: status.stage, qaCount: status.qaCount }
              : t,
          );
          saveTasks(updated);
          return updated;
        });

        if (status.status === "succeeded") {
          clearInterval(interval);
          const records = await fetchJobQa(jobId, entry.params!.minScore, entry.generator, entry.pipeline);
          const session = buildSessionFromRecords(
            jobId,
            entry.sourceFileName,
            entry.pipeline,
            entry.generator,
            entry.params!,
            records,
          );
          const newSessions = { ...loadSessions(), [session.id]: session };
          const newTasks = loadTasks().map((t) =>
            t.jobId === jobId
              ? {
                  ...t,
                  sessionId: session.id,
                  status: "succeeded" as const,
                  qaCount: records.length,
                  finishedAt: new Date().toISOString(),
                }
              : t,
          );
          persist(newTasks, newSessions);
          setSelectedQaId(session.items[0]?.id ?? null);
          setGenerating(false);
          showToast(`已生成 ${records.length} 条 QA`);
        } else if (status.status === "failed") {
          clearInterval(interval);
          const msg = typeof status.error === "string" ? status.error : "任务失败";
          const newTasks = loadTasks().map((t) =>
            t.jobId === jobId
              ? { ...t, status: "failed" as const, errorMessage: msg, finishedAt: new Date().toISOString() }
              : t,
          );
          persist(newTasks, sessions);
          setGenerating(false);
          showToast(msg, "error");
        }
      } catch (e) {
        clearInterval(interval);
        const msg = e instanceof Error ? e.message : "任务失败";
        const newTasks = loadTasks().map((t) =>
          t.jobId === jobId
            ? { ...t, status: "failed" as const, errorMessage: msg, finishedAt: new Date().toISOString() }
            : t,
        );
        persist(newTasks, sessions);
        setGenerating(false);
        showToast(msg, "error");
      }
    }, 600);
  };

  const handleRetry = () => {
    if (!currentTask?.params || !currentTask.uploadContent) return;
    setUploadFileName(currentTask.sourceFileName);
    setUploadContent(currentTask.uploadContent);
    setUploadId("retry");
    setPipeline(currentTask.pipeline);
    if (currentTask.generator) setGenerator(currentTask.generator);
    setParams(currentTask.params);
    setIsNewTask(true);
  };

  const handleSave = async () => {
    if (!currentSession) return;
    const updated = {
      ...currentSession,
      updatedAt: new Date().toISOString(),
      items: currentSession.items.map((i) => ({
        ...i,
        local: { ...i.local, dirty: false },
        record: { ...i.record, user_modified: i.local.dirty || i.record.user_modified },
      })),
    };
    try {
      await saveSession(updated);
      persist(tasks, { ...sessions, [updated.id]: updated });
      showToast("会话已保存");
    } catch {
      showToast("保存失败。请重试或导出本地备份。", "error");
    }
  };

  const handleExport = (scope: ExportScope) => {
    if (!currentSession) return;
    let items = currentSession.items.filter((i) => !i.local.deleted);
    if (scope === "passed") items = items.filter((i) => i.local.filterPassed !== false);
    else if (scope === "selected" && selectedQaId) items = items.filter((i) => i.id === selectedQaId);
    const rows = items.map((i) => toAlpacaRow(i.record));
    downloadJsonl(rows, `${currentSession.sourceFileName.replace(/\.md$/, "")}_export.jsonl`);
    setShowExport(false);
    showToast(`已导出 ${rows.length} 条`);
  };

  const updateQa = (id: string, patch: { question?: string; answer?: string }) => {
    if (!currentSession) return;
    const updated: WorkspaceSession = {
      ...currentSession,
      items: currentSession.items.map((i) =>
        i.id === id
          ? { ...i, local: { ...i.local, dirty: true }, record: { ...i.record, ...patch, user_modified: true } }
          : i,
      ),
    };
    persist(tasks, { ...sessions, [updated.id]: updated });
  };

  const deleteQa = (id: string) => {
    if (!currentSession) return;
    const updated: WorkspaceSession = {
      ...currentSession,
      items: currentSession.items.map((i) =>
        i.id === id ? { ...i, local: { ...i.local, deleted: true, dirty: true } } : i,
      ),
    };
    persist(tasks, { ...sessions, [updated.id]: updated });
    setSelectedQaId(null);
  };

  const markReviewed = (id: string) => {
    if (!currentSession) return;
    const updated: WorkspaceSession = {
      ...currentSession,
      items: currentSession.items.map((i) =>
        i.id === id ? { ...i, local: { ...i.local, dirty: true } } : i,
      ),
    };
    persist(tasks, { ...sessions, [updated.id]: updated });
    showToast("已标记为已审核");
  };

  const filteredItems = useMemo(() => {
    if (!currentSession) return [];
    return currentSession.items.filter((i) => {
      const local = i.local ?? { deleted: false, dirty: false, selected: false };
      if (local.deleted) return false;
      if (listFilter === "passed" && local.filterPassed === false) return false;
      if (listFilter === "flagged" && local.filterPassed !== false) return false;
      const q = (i.record?.question || "").toLowerCase();
      const s = qaSearch.toLowerCase();
      if (s && !q.includes(s)) return false;
      return true;
    });
  }, [currentSession, listFilter, qaSearch]);

  const totalItems = currentSession?.items.filter((i) => !i.local?.deleted).length ?? 0;
  const selectedItem = currentSession?.items.find((i) => i.id === selectedQaId) ?? null;
  const showConfig = isNewTask || selectedJobId === null;
  const showDetail = !showConfig;
  const showProgress = currentTask?.status === "running";
  const showFailed = currentTask?.status === "failed";

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "s") {
        e.preventDefault();
        if (hasUnsaved) handleSave();
      }
      if (!currentSession || !selectedQaId) return;
      const idx = filteredItems.findIndex((i) => i.id === selectedQaId);
      if (e.key === "j" && idx < filteredItems.length - 1) setSelectedQaId(filteredItems[idx + 1].id);
      if (e.key === "k" && idx > 0) setSelectedQaId(filteredItems[idx - 1].id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <div className="workspace-root">
      <TaskHistorySidebar
        tasks={tasks}
        selectedJobId={selectedJobId}
        onSelect={handleSelectTask}
        onNewTask={handleNewTask}
      />

      <div className="wb-workspace-row" style={{ flex: 1, minWidth: 0 }}>
        <main className="wb-main">
          <WorkspaceTopBar
            qaSearch={qaSearch}
            onQaSearchChange={setQaSearch}
            onExport={currentSession ? () => setShowExport(true) : undefined}
            hasUnsaved={hasUnsaved}
            onSave={currentSession ? handleSave : undefined}
          />

          {showConfig ? (
            <div className="custom-scroll" style={{ flex: 1, overflow: "auto" }}>
              <PipelineConfigPanel
                pipeline={pipeline}
                generator={generator}
                params={params}
                disabled={generating}
                onPipelineChange={setPipeline}
                onGeneratorChange={setGenerator}
                onParamsChange={setParams}
                onStart={handleStartGenerate}
                fileName={uploadFileName}
                fileSize={uploadFileSize}
                onFileSelect={handleFileSelect}
              />
            </div>
          ) : (
            <>
              {showFailed && (
                <div className="error-banner" style={{ margin: "12px 24px 0" }}>
                  任务失败：{currentTask?.errorMessage || "未知错误"}
                  <button className="btn btn-secondary btn-sm" style={{ marginLeft: 12 }} onClick={handleRetry}>
                    重试
                  </button>
                </div>
              )}
              {showProgress && currentTask?.params && (() => {
                const stages = pipelineStages(currentTask.pipeline, currentTask.generator, currentTask.params);
                const currentIdx = stages.indexOf(currentTask.stage || "");
                return (
                  <div style={{ padding: "12px 24px", borderBottom: "1px solid #c1c6d7" }}>
                    <p className="copy-14" style={{ marginBottom: 8 }}>
                      正在处理 QA 对…（{currentTask.stage}）
                    </p>
                    <div className="progress-stages">
                      {stages.map((s) => (
                        <span
                          key={s}
                          className={`progress-stage ${s === currentTask.stage ? "active" : ""} ${currentIdx >= 0 && stages.indexOf(s) < currentIdx ? "done" : ""}`}
                        >
                          {s}
                        </span>
                      ))}
                    </div>
                  </div>
                );
              })()}

              <div className="wb-subheader">
                <div>
                  <div className="wb-context-label">当前上下文</div>
                  <h2 className="wb-context-title">{currentTask?.sourceFileName}</h2>
                </div>
                <div className="wb-filter-group">
                  {(["all", "passed", "flagged"] as WorkspaceFilter[]).map((f) => (
                    <button
                      key={f}
                      type="button"
                      className={`wb-filter-btn ${listFilter === f ? "active" : ""}`}
                      onClick={() => setListFilter(f)}
                    >
                      {f === "all" ? "全部" : f === "passed" ? "已通过" : "待复核"}
                    </button>
                  ))}
                </div>
              </div>

              <div className="wb-qa-list custom-scroll">
                {!currentSession ? (
                  <div className="empty-state">
                    <h2 className="heading-16">会话未加载</h2>
                    <p className="copy-14">
                      {currentTask?.status === "running"
                        ? "生成进行中…任务完成后将显示 QA 列表。"
                        : "该任务无会话数据。请选择其他任务或新建任务。"}
                    </p>
                  </div>
                ) : filteredItems.length === 0 ? (
                  <div className="empty-state">
                    <h2 className="heading-16">
                      {totalItems === 0 ? "尚无 QA 对" : "无匹配结果"}
                    </h2>
                    <p className="copy-14">
                      {totalItems === 0
                        ? "上传 Markdown 并开始生成以创建 QA 对。"
                        : `当前筛选下 0 / ${totalItems} 条。请清除搜索或切换筛选（全部 / 已通过 / 待复核）。`}
                    </p>
                  </div>
                ) : (
                  <div className="wb-qa-list-inner">
                    {filteredItems.map((item) => (
                      <QACard
                        key={item.id}
                        item={item}
                        selected={item.id === selectedQaId}
                        generator={currentSession?.generator}
                        onClick={() => setSelectedQaId(item.id)}
                      />
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </main>

        <QADetailPanel
          visible={!!showDetail}
          item={selectedItem}
          session={currentSession}
          onClose={() => setSelectedQaId(null)}
          onUpdate={updateQa}
          onDelete={deleteQa}
          onMarkReviewed={markReviewed}
        />
      </div>

      {showExport && <ExportDialog onExport={handleExport} onClose={() => setShowExport(false)} />}

      {pendingSwitch && (
        <ConfirmDialog
          title="未保存的更改"
          message="当前更改尚未保存。保存并切换、放弃更改，或取消。"
          confirmLabel="放弃更改"
          destructive
          extraAction={{
            label: "保存并切换",
            onClick: async () => {
              await handleSave();
              if (pendingSwitch === "__new__") handleNewTask();
              else setSelectedJobId(pendingSwitch);
              setPendingSwitch(null);
            },
          }}
          onConfirm={() => {
            if (pendingSwitch === "__new__") {
              setIsNewTask(true);
              setSelectedJobId(null);
            } else {
              setSelectedJobId(pendingSwitch);
            }
            setPendingSwitch(null);
            setSelectedQaId(null);
          }}
          onCancel={() => setPendingSwitch(null)}
        />
      )}
    </div>
  );
}
