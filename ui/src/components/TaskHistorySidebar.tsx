import type { TaskHistoryEntry } from "../types";
import { formatRelativeTime } from "../lib/qa-utils";

interface TaskHistorySidebarProps {
  tasks: TaskHistoryEntry[];
  selectedJobId: string | null;
  onSelect: (jobId: string) => void;
  onNewTask: () => void;
}

function taskIcon(status: TaskHistoryEntry["status"]): string {
  switch (status) {
    case "running":
    case "queued":
      return "sync";
    case "succeeded":
      return "assignment";
    case "failed":
      return "error";
    default:
      return "check_circle";
  }
}

function taskMeta(task: TaskHistoryEntry): { text: string; className: string } {
  if (task.status === "running" || task.status === "queued") {
    return { text: `运行中 · ${task.stage || "…"}`, className: "running" };
  }
  if (task.status === "failed") {
    const err = task.errorMessage ? task.errorMessage.slice(0, 24) : "错误";
    return { text: `失败 · ${err}`, className: "failed" };
  }
  if (task.status === "succeeded") {
    return { text: `已完成 · ${formatRelativeTime(task.createdAt)}`, className: "completed" };
  }
  return { text: task.status, className: "" };
}

export function TaskHistorySidebar({
  tasks,
  selectedJobId,
  onSelect,
  onNewTask,
}: TaskHistorySidebarProps) {
  return (
    <aside className="wb-sidebar">
      <div style={{ padding: "24px 16px 8px" }}>
        <h1 className="wb-sidebar-title">QA 数据工作台</h1>
        <p className="wb-sidebar-subtitle">生成任务</p>
      </div>
      <div style={{ padding: "0 16px 16px" }}>
        <button type="button" className="wb-new-job-btn" onClick={onNewTask}>
          <span className="material-symbols-outlined" style={{ fontSize: 20 }}>add</span>
          新建任务
        </button>
      </div>
      <nav className="custom-scroll" style={{ flex: 1, overflowY: "auto" }}>
        <div style={{ padding: "0 16px 8px" }}>
          <p className="wb-history-label">历史记录</p>
          {tasks.length === 0 ? (
            <p style={{ padding: "8px 16px", fontSize: 13, color: "#717786" }}>
              暂无任务。上传 Markdown 开始生成 QA。
            </p>
          ) : (
            tasks.map((task) => {
              const meta = taskMeta(task);
              const active = selectedJobId === task.jobId;
              return (
                <div
                  key={task.jobId}
                  className={`wb-task-item ${active ? "active" : ""}`}
                  onClick={() => onSelect(task.jobId)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => e.key === "Enter" && onSelect(task.jobId)}
                >
                  <span className={`wb-task-icon material-symbols-outlined ${active ? "" : ""}`}>
                    {taskIcon(task.status)}
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="wb-task-name">{task.sourceFileName}</div>
                    <div className={`wb-task-meta ${meta.className}`}>{meta.text}</div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </nav>
      <div className="wb-sidebar-footer">
        <div className="wb-footer-item">
          <span className="material-symbols-outlined">archive</span>
          <span>归档</span>
        </div>
        <div className="wb-footer-item">
          <span className="material-symbols-outlined">delete</span>
          <span>回收站</span>
        </div>
      </div>
    </aside>
  );
}
