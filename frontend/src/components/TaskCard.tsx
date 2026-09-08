import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Task } from "../api/client";
import { parseApiDate } from "../lib/date";
import { sourceColorClasses } from "../lib/sourceColors";

const fmt = (d: Date) =>
  d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

/** Accounts for Gradescope's late-submission cutoff: before the regular due
 * date, shows that (with a note that a late option exists); once it's
 * passed but the late cutoff hasn't, shows the late cutoff as the now-relevant
 * deadline instead of just saying "overdue". */
function formatDue(task: Pick<Task, "due_at" | "late_due_at">): { label: string; tone: string } {
  if (!task.due_at) return { label: "No due date", tone: "text-stone-400" };
  const due = parseApiDate(task.due_at);
  const late = parseApiDate(task.late_due_at);
  const now = new Date();

  if (late && now >= due) {
    const diffHrs = (late.getTime() - now.getTime()) / (1000 * 60 * 60);
    if (diffHrs < 0) return { label: `Overdue • late cutoff was ${fmt(late)}`, tone: "text-red-600" };
    return { label: `Due date passed • late submission until ${fmt(late)}`, tone: "text-amber-600" };
  }

  const diffHrs = (due.getTime() - now.getTime()) / (1000 * 60 * 60);
  const lateNote = late ? ` (late until ${fmt(late)})` : "";
  if (diffHrs < 0) return { label: `Overdue • was ${fmt(due)}${lateNote}`, tone: "text-red-600" };
  if (diffHrs < 24) return { label: `Due soon • ${fmt(due)}${lateNote}`, tone: "text-amber-600" };
  return { label: `Due ${fmt(due)}${lateNote}`, tone: "text-stone-500" };
}

function gradeBadge(task: Task): { label: string; tone: string } | null {
  if (task.score == null || !task.points_possible) return null;
  const pct = Math.round((task.score / task.points_possible) * 100);
  const tone = pct >= 90 ? "text-emerald-700 bg-emerald-50" : pct >= 75 ? "text-amber-700 bg-amber-50" : "text-red-700 bg-red-50";
  return { label: `${pct}%`, tone };
}

export default function TaskCard({ task, compact = false }: { task: Task; compact?: boolean }) {
  const queryClient = useQueryClient();
  const statusMutation = useMutation({
    mutationFn: (status: Task["status"]) => api.updateTaskStatus(task.id, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["tasks"] }),
  });
  const startMutation = useMutation({
    mutationFn: () => api.startTask(task.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["tasks"] }),
  });

  const due = formatDue(task);
  const grade = gradeBadge(task);
  const isDone = task.status === "done";
  const isDismissed = task.status === "dismissed";
  const isPending = task.status === "pending";

  return (
    <div
      className={`flex items-center justify-between gap-3 rounded-2xl border border-stone-100 bg-white shadow-[0_1px_2px_rgba(35,40,31,0.04),0_12px_28px_-16px_rgba(35,40,31,0.18)] px-4 ${compact ? "py-2" : "py-3"} ${
        isDone || isDismissed ? "opacity-60" : ""
      }`}
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span
            className={`text-[10px] uppercase tracking-wide font-semibold rounded px-1.5 py-0.5 ${sourceColorClasses(task.source).badge}`}
          >
            {task.source}
          </span>
          <span className="text-[10px] uppercase tracking-wide text-stone-400">{task.type}</span>
          {grade && (
            <span className={`text-[10px] font-semibold rounded px-1.5 py-0.5 ${grade.tone}`}>{grade.label}</span>
          )}
          {isPending && task.started_at && (
            <span className="text-[10px] uppercase tracking-wide text-matcha-500">Started</span>
          )}
        </div>
        {task.url ? (
          <a
            href={task.url}
            target="_blank"
            rel="noreferrer"
            className="font-medium text-stone-800 hover:text-matcha-600 hover:underline truncate block"
          >
            {task.title}
          </a>
        ) : (
          <p className="font-medium text-stone-800 truncate">{task.title}</p>
        )}
        <p className={`text-sm ${due.tone}`}>{due.label}</p>
      </div>
      <div className="flex gap-1 shrink-0">
        {isPending && !task.started_at && (
          <button
            onClick={() => startMutation.mutate()}
            disabled={startMutation.isPending}
            className="text-xs px-2.5 py-1 rounded-full bg-matcha-50 text-matcha-700 hover:bg-matcha-100 disabled:opacity-50"
          >
            Start
          </button>
        )}
        {!isDone && (
          <button
            onClick={() => statusMutation.mutate("done")}
            className="text-xs px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
          >
            Done
          </button>
        )}
        {!isDismissed && (
          <button
            onClick={() => statusMutation.mutate("dismissed")}
            className="text-xs px-2.5 py-1 rounded-full bg-stone-100 text-stone-600 hover:bg-stone-200"
          >
            Dismiss
          </button>
        )}
        {(isDone || isDismissed) && (
          <button
            onClick={() => statusMutation.mutate("pending")}
            className="text-xs px-2.5 py-1 rounded-full bg-stone-100 text-stone-600 hover:bg-stone-200"
          >
            Undo
          </button>
        )}
      </div>
    </div>
  );
}
