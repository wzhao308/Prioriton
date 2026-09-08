import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Task } from "../api/client";
import TaskCard from "../components/TaskCard";
import { effectiveDueDate } from "../lib/date";

const CARD = "rounded-2xl border border-stone-100 bg-white shadow-[0_1px_2px_rgba(35,40,31,0.04),0_12px_28px_-16px_rgba(35,40,31,0.18)]";

type Bucket = "Overdue" | "Today" | "This week" | "Later" | "No due date" | "Done" | "Dismissed";
const BUCKET_ORDER: Bucket[] = ["Overdue", "Today", "This week", "Later", "No due date", "Done", "Dismissed"];

/** Buckets by the effective deadline (the regular due date, or the
 * late-submission cutoff once that's passed - see effectiveDueDate), so a
 * Gradescope task with a late option isn't dropped into "Overdue" the moment
 * its regular due date passes if it can still be submitted late. */
function bucketOf(task: Task): Bucket {
  if (task.status === "done") return "Done";
  if (task.status === "dismissed") return "Dismissed";
  const due = effectiveDueDate(task);
  if (!due) return "No due date";
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const diffDays = (due.getTime() - startOfToday.getTime()) / (1000 * 60 * 60 * 24);
  if (diffDays < 0) return "Overdue";
  if (diffDays < 1) return "Today";
  if (diffDays < 7) return "This week";
  return "Later";
}

function StatTile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className={`${CARD} p-4`}>
      <p className="text-xs font-medium uppercase tracking-wide text-stone-400">{label}</p>
      <p className="font-display text-3xl font-semibold text-stone-900 mt-1">{value}</p>
      {sub && <p className="text-xs text-stone-400 mt-0.5">{sub}</p>}
    </div>
  );
}

export default function Home() {
  const tasksQuery = useQuery({ queryKey: ["tasks"], queryFn: () => api.listTasks() });
  const activeQuery = useQuery({ queryKey: ["study-sessions", "active"], queryFn: api.activeStudySession });
  const recommendationsQuery = useQuery({ queryKey: ["recommendations"], queryFn: api.getRecommendations });
  const overviewQuery = useQuery({ queryKey: ["analytics", "overview"], queryFn: api.courseOverview });
  const [activeTab, setActiveTab] = useState<Bucket | null>(null);

  const tasks = tasksQuery.data ?? [];
  const topRecommendation = recommendationsQuery.data?.items?.[0];
  const active = activeQuery.data;
  const overview = overviewQuery.data ?? [];

  const hoursThisWeek = overview.reduce((sum, c) => sum + c.study_hours_this_week, 0);
  const gradedCourses = overview.filter((c) => c.avg_grade_pct != null);
  const avgGrade = gradedCourses.length
    ? Math.round(gradedCourses.reduce((sum, c) => sum + (c.avg_grade_pct ?? 0), 0) / gradedCourses.length)
    : null;
  const dueThisWeek = tasks.filter((t) => {
    if (t.status !== "pending") return false;
    const due = effectiveDueDate(t);
    return due && due.getTime() - Date.now() < 7 * 86400 * 1000;
  }).length;

  const grouped = new Map<Bucket, Task[]>();
  for (const bucket of BUCKET_ORDER) grouped.set(bucket, []);
  for (const task of tasks) grouped.get(bucketOf(task))!.push(task);
  // Default to whichever bucket has something in it first, in priority order,
  // rather than always landing on an empty "Overdue" tab.
  const defaultTab = BUCKET_ORDER.find((b) => grouped.get(b)!.length > 0) ?? BUCKET_ORDER[0];
  const selectedTab = activeTab ?? defaultTab;
  const selectedTasks = grouped.get(selectedTab) ?? [];

  return (
    <div className="max-w-3xl space-y-8">
      <section>
        <h1 className="font-display text-2xl font-semibold text-stone-900">This week</h1>
        <p className="text-sm text-stone-500 mt-1">Your snapshot - what's due, what to focus on next.</p>
      </section>

      <section className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <StatTile label="Study hours" value={hoursThisWeek.toFixed(1)} sub="this week" />
        <StatTile label="Avg. grade" value={avgGrade != null ? `${avgGrade}%` : "—"} sub="across courses" />
        <StatTile label="Due soon" value={String(dueThisWeek)} sub="in the next 7 days" />
      </section>

      {active ? (
        <Link
          to="/study-timer"
          className="block rounded-2xl border border-matcha-200 bg-matcha-50 px-4 py-3 hover:bg-matcha-100"
        >
          <p className="text-sm font-medium text-matcha-700">
            Studying {active.course_name} right now - open the timer →
          </p>
        </Link>
      ) : (
        <Link to="/study-timer" className={`${CARD} block px-4 py-3 hover:border-matcha-300`}>
          <p className="text-sm font-medium text-stone-700">Start a study session →</p>
        </Link>
      )}

      {topRecommendation && (
        <section className={`${CARD} p-4`}>
          <div className="flex items-center justify-between mb-1">
            <h2 className="text-sm font-semibold text-stone-700">Top recommendation</h2>
            <Link to="/recommendations" className="text-xs text-matcha-600 hover:text-matcha-700">
              See all
            </Link>
          </div>
          <p className="text-sm text-stone-700">{topRecommendation.message}</p>
        </section>
      )}

      <section>
        <div className="flex items-center justify-between mb-2">
          <h2 className="font-medium text-stone-800">Assignments</h2>
          <Link to="/courses" className="text-xs text-matcha-600 hover:text-matcha-700">
            Browse by class →
          </Link>
        </div>

        {tasksQuery.isLoading && <p className="text-sm text-stone-400">Loading…</p>}
        {!tasksQuery.isLoading && tasks.length === 0 && (
          <p className="text-sm text-stone-400">
            Nothing tracked yet - connect an assignment source or add a class in Settings.
          </p>
        )}

        {tasks.length > 0 && (
          <>
            <div className="flex gap-1 overflow-x-auto border-b border-stone-200 pb-px mb-3">
              {BUCKET_ORDER.map((bucket) => (
                <button
                  key={bucket}
                  onClick={() => setActiveTab(bucket)}
                  className={`shrink-0 px-3 py-2 text-sm font-medium rounded-t-lg border-b-2 ${
                    bucket === selectedTab
                      ? "border-matcha-600 text-matcha-700"
                      : "border-transparent text-stone-500 hover:text-stone-700"
                  }`}
                >
                  {bucket} ({grouped.get(bucket)!.length})
                </button>
              ))}
            </div>

            <div className="space-y-2">
              {selectedTasks.length === 0 && <p className="text-sm text-stone-400">Nothing here.</p>}
              {selectedTasks.map((task) => (
                <TaskCard key={task.id} task={task} compact />
              ))}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
