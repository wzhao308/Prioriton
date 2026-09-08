import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { parseApiDate } from "../lib/date";

function formatElapsed(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = totalSeconds % 60;
  return [h, m, s].map((n) => String(n).padStart(2, "0")).join(":");
}

export default function StudyTimer() {
  const queryClient = useQueryClient();
  const coursesQuery = useQuery({ queryKey: ["courses", "all"], queryFn: () => api.listCourses(true) });
  const activeQuery = useQuery({ queryKey: ["study-sessions", "active"], queryFn: api.activeStudySession });
  const overviewQuery = useQuery({ queryKey: ["analytics", "overview"], queryFn: api.courseOverview });

  const [selectedCourseId, setSelectedCourseId] = useState<number | "">("");
  const [addingSubject, setAddingSubject] = useState(false);
  const [newSubject, setNewSubject] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const active = activeQuery.data ?? null;

  useEffect(() => {
    if (!active) return;
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, [active]);

  const invalidateAfterChange = () => {
    queryClient.invalidateQueries({ queryKey: ["study-sessions"] });
    queryClient.invalidateQueries({ queryKey: ["analytics"] });
    queryClient.invalidateQueries({ queryKey: ["recommendations"] });
  };

  const start = useMutation({
    mutationFn: (courseId: number) => api.startStudySession(courseId),
    onSuccess: invalidateAfterChange,
  });
  const stop = useMutation({
    mutationFn: (id: number) => api.stopStudySession(id),
    onSuccess: invalidateAfterChange,
  });
  const addSubject = useMutation({
    mutationFn: () => api.createCourse(newSubject.trim()),
    onSuccess: (course) => {
      queryClient.invalidateQueries({ queryKey: ["courses"] });
      setSelectedCourseId(course.id);
      setNewSubject("");
      setAddingSubject(false);
    },
  });

  const allCourses = coursesQuery.data ?? [];
  const activeCourses = allCourses.filter((c) => !c.archived);
  const archivedCourses = allCourses.filter((c) => c.archived);
  const overview = overviewQuery.data ?? [];
  const maxWeeklyHours = Math.max(1, ...overview.map((c) => c.study_hours_this_week));

  const elapsedMs = active ? now - parseApiDate(active.started_at).getTime() : 0;

  return (
    <div className="max-w-xl space-y-8">
      <section>
        <h1 className="font-display text-2xl font-semibold text-stone-900">Study Timer</h1>
        <p className="text-sm text-stone-500 mt-1">
          Pick a class, hit start, and Prioriton tracks your hours per course automatically.
        </p>
      </section>

      <section className="rounded-2xl border border-stone-100 bg-white shadow-[0_1px_2px_rgba(35,40,31,0.04),0_12px_28px_-16px_rgba(35,40,31,0.18)] p-8 text-center">
        <div className="relative mx-auto mb-6 grid h-52 w-52 place-items-center">
          {active && <span className="absolute inset-0 rounded-full bg-matcha-100 animate-pulse" />}
          <span className={`absolute inset-2 rounded-full border-[3px] ${active ? "border-matcha-500" : "border-dashed border-stone-200"}`} />
          <div className="relative flex flex-col items-center px-4">
            {active ? (
              <>
                <span className="text-xs font-medium uppercase tracking-wide text-matcha-600">Studying</span>
                <span className="mt-1 max-w-[9rem] truncate font-display text-lg font-semibold text-stone-900">
                  {active.course_name}
                </span>
                <span className="mt-2 font-mono text-3xl font-semibold text-stone-800 tabular-nums">
                  {formatElapsed(elapsedMs)}
                </span>
              </>
            ) : (
              <>
                <svg viewBox="0 0 24 24" width="28" height="28" className="text-stone-300">
                  <path d="M8 5v14l11-7z" fill="currentColor" />
                </svg>
                <span className="mt-2 text-sm text-stone-400">Ready when you are</span>
              </>
            )}
          </div>
        </div>

        {active ? (
          <button
            onClick={() => stop.mutate(active.id)}
            disabled={stop.isPending}
            className="rounded-xl bg-red-600 px-8 py-2.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
          >
            {stop.isPending ? "Stopping…" : "Stop"}
          </button>
        ) : (
          <>
            <div className="flex items-center justify-center gap-2 mb-2">
              <select
                value={selectedCourseId}
                onChange={(e) => setSelectedCourseId(e.target.value ? Number(e.target.value) : "")}
                className="rounded-xl border border-stone-300 px-3 py-2 text-sm min-w-[14rem]"
              >
                <option value="">Choose a class…</option>
                <optgroup label="Active">
                  {activeCourses.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.display_name}
                    </option>
                  ))}
                </optgroup>
                {showArchived && archivedCourses.length > 0 && (
                  <optgroup label="Archived">
                    {archivedCourses.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.display_name}
                      </option>
                    ))}
                  </optgroup>
                )}
              </select>
              {!addingSubject ? (
                <button
                  onClick={() => setAddingSubject(true)}
                  className="text-sm text-matcha-600 hover:text-matcha-700 whitespace-nowrap"
                >
                  + Add subject
                </button>
              ) : null}
            </div>

            {archivedCourses.length > 0 && (
              <button
                onClick={() => setShowArchived((s) => !s)}
                className="mb-6 block text-xs text-stone-400 hover:text-stone-600"
              >
                {showArchived ? "Hide" : "Show"} archived classes ({archivedCourses.length})
              </button>
            )}

            {addingSubject && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  if (newSubject.trim()) addSubject.mutate();
                }}
                className="flex items-center justify-center gap-2 mb-6"
              >
                <input
                  autoFocus
                  value={newSubject}
                  onChange={(e) => setNewSubject(e.target.value)}
                  placeholder="e.g. MCAT Prep"
                  className="rounded-xl border border-stone-300 px-3 py-1.5 text-sm"
                />
                <button
                  type="submit"
                  disabled={!newSubject.trim() || addSubject.isPending}
                  className="text-sm rounded-xl bg-matcha-600 px-3 py-1.5 text-white hover:bg-matcha-700 disabled:opacity-50"
                >
                  Add
                </button>
                <button
                  type="button"
                  onClick={() => setAddingSubject(false)}
                  className="text-sm text-stone-400 hover:text-stone-600"
                >
                  Cancel
                </button>
              </form>
            )}

            <button
              onClick={() => typeof selectedCourseId === "number" && start.mutate(selectedCourseId)}
              disabled={typeof selectedCourseId !== "number" || start.isPending}
              className="rounded-xl bg-matcha-600 px-6 py-2.5 text-sm font-medium text-white hover:bg-matcha-700 disabled:opacity-50"
            >
              {start.isPending ? "Starting…" : "Start studying"}
            </button>
          </>
        )}
        {(start.isError || stop.isError) && (
          <p className="mt-3 text-sm text-red-600">
            {((start.error ?? stop.error) as Error)?.message}
          </p>
        )}
      </section>

      <section>
        <h2 className="font-medium text-stone-800 mb-2">This week</h2>
        <div className="space-y-2">
          {overview.length === 0 && <p className="text-sm text-stone-400">No classes yet.</p>}
          {overview.map((c) => (
            <div key={c.course_id} className="flex items-center gap-3">
              <span className="w-40 shrink-0 truncate text-sm text-stone-700">{c.course_name}</span>
              <div className="flex-1 h-2 rounded-full bg-stone-100 overflow-hidden">
                <div
                  className="h-full rounded-full bg-matcha-500"
                  style={{ width: `${(c.study_hours_this_week / maxWeeklyHours) * 100}%` }}
                />
              </div>
              <span className="w-16 shrink-0 text-right text-sm text-stone-500 tabular-nums">
                {c.study_hours_this_week.toFixed(1)}h
              </span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
