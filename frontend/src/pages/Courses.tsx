import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Course } from "../api/client";
import TaskCard from "../components/TaskCard";

export default function Courses() {
  const coursesQuery = useQuery({ queryKey: ["courses", "all"], queryFn: () => api.listCourses(true) });
  const tasksQuery = useQuery({ queryKey: ["tasks"], queryFn: () => api.listTasks() });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [showArchived, setShowArchived] = useState(false);

  const courses = coursesQuery.data ?? [];
  const tasks = tasksQuery.data ?? [];

  if (!coursesQuery.isLoading && courses.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-stone-300 p-8 text-center">
        <p className="text-stone-600 font-medium">No classes yet.</p>
        <p className="text-sm text-stone-500 mt-1">
          Connect an assignment source or add a class by hand in Settings.
        </p>
      </div>
    );
  }
  if (coursesQuery.isLoading) return <p className="text-stone-500">Loading…</p>;

  // The backend already folds the same real class synced from more than one
  // platform into a single row (see app.course_merge) - one course here is
  // always one tab, no client-side grouping needed.
  const active = courses.filter((c) => !c.archived);
  const archived = courses.filter((c) => c.archived);
  const defaultCourse = active[0] ?? archived[0];
  const selectedCourse = courses.find((c) => c.id === selectedId) ?? defaultCourse;

  const courseTasks = tasks.filter((t) => t.course_id === selectedCourse.id);
  const todo = courseTasks.filter((t) => t.status === "pending");
  const done = courseTasks.filter((t) => t.status !== "pending");

  const tabClass = (course: Course) =>
    `shrink-0 px-3 py-2 text-sm font-medium rounded-t-lg border-b-2 ${
      course.id === selectedCourse.id
        ? "border-matcha-600 text-matcha-700"
        : "border-transparent text-stone-500 hover:text-stone-700"
    }`;

  return (
    <div className="space-y-4">
      <section>
        <h1 className="font-display text-2xl font-semibold text-stone-900">Courses</h1>
        <p className="text-sm text-stone-500 mt-1">Every class's assignments, to-do and done, in one board.</p>
      </section>

      <div className="flex gap-1 overflow-x-auto border-b border-stone-200 pb-px">
        {active.map((course) => (
          <button key={course.id} onClick={() => setSelectedId(course.id)} className={tabClass(course)}>
            {course.display_name}
          </button>
        ))}
      </div>

      {archived.length > 0 && (
        <div className="rounded-2xl border border-stone-100 bg-stone-50/60">
          <button
            onClick={() => setShowArchived((v) => !v)}
            className="flex w-full items-center justify-between px-3 py-2 text-sm font-medium text-stone-500 hover:text-stone-700"
          >
            <span>
              Archived / past classes ({archived.length}) {showArchived ? "▲" : "▼"}
            </span>
          </button>
          {showArchived && (
            <div className="flex flex-wrap gap-1 border-t border-stone-200 px-3 py-2">
              {archived.map((course) => (
                <button
                  key={course.id}
                  onClick={() => setSelectedId(course.id)}
                  className={`rounded-full px-2.5 py-1 text-xs ${
                    course.id === selectedCourse.id
                      ? "bg-matcha-100 text-matcha-800 font-medium"
                      : "bg-white text-stone-500 hover:bg-stone-100"
                  }`}
                  title={course.term ?? undefined}
                >
                  {course.display_name}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {selectedCourse.sources.length > 1 && (
        <p className="text-xs text-stone-400">
          Combining data from {selectedCourse.sources.join(" + ")} - same real class, tracked on more than one
          platform.
        </p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <section>
          <h2 className="text-sm font-semibold text-stone-500 uppercase tracking-wide mb-2">
            To do ({todo.length})
          </h2>
          <div className="space-y-2">
            {todo.length === 0 && <p className="text-sm text-stone-400">Nothing pending 🎉</p>}
            {todo.map((task) => (
              <TaskCard key={task.id} task={task} />
            ))}
          </div>
        </section>
        <section>
          <h2 className="text-sm font-semibold text-stone-400 uppercase tracking-wide mb-2">
            Done / dismissed ({done.length})
          </h2>
          <div className="space-y-2">
            {done.map((task) => (
              <TaskCard key={task.id} task={task} />
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
