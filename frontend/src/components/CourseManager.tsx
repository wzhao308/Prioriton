import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";

/** Lets a student add/rename/archive classes by hand - what makes the Study
 * Timer (and manual grade tracking) work fully even before any assignment
 * source is connected, and covers subjects that will never come from one
 * (test prep, a self-study track, etc). Synced courses (source != "manual")
 * can still be archived here, just not renamed - their name comes from the
 * platform on the next sync. */
export default function CourseManager() {
  const queryClient = useQueryClient();
  const coursesQuery = useQuery({ queryKey: ["courses", "all"], queryFn: () => api.listCourses(true) });
  const [name, setName] = useState("");
  const [term, setTerm] = useState("");

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["courses"] });
  };

  const create = useMutation({
    mutationFn: () => api.createCourse(name.trim(), term.trim() || undefined),
    onSuccess: () => {
      invalidate();
      setName("");
      setTerm("");
    },
  });
  const setArchived = useMutation({
    mutationFn: ({ id, archived }: { id: number; archived: boolean }) => api.updateCourse(id, { archived }),
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.deleteCourse(id),
    onSuccess: invalidate,
  });

  const confirmDelete = (id: number, name: string) => {
    if (window.confirm(`Delete "${name}"? This also removes its study sessions and any tasks tracked under it.`)) {
      remove.mutate(id);
    }
  };

  const courses = coursesQuery.data ?? [];
  const active = courses.filter((c) => !c.archived);
  const archived = courses.filter((c) => c.archived);

  return (
    <section className="rounded-2xl border border-stone-100 bg-white shadow-[0_1px_2px_rgba(35,40,31,0.04),0_12px_28px_-16px_rgba(35,40,31,0.18)] p-4">
      <h2 className="font-medium text-stone-800 mb-1">Your classes</h2>
      <p className="text-sm text-stone-500 mb-3">
        Synced classes show up here automatically. Add any others by hand - the Study Timer and
        Analytics work the same either way.
      </p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim()) create.mutate();
        }}
        className="flex flex-wrap items-end gap-2 mb-4"
      >
        <div className="flex-1 min-w-[10rem]">
          <label className="block text-xs font-medium text-stone-600">Class / subject name</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. MCAT Prep"
            className="mt-1 w-full rounded-xl border border-stone-300 px-3 py-1.5 text-sm"
          />
        </div>
        <div className="w-32">
          <label className="block text-xs font-medium text-stone-600">Term (optional)</label>
          <input
            value={term}
            onChange={(e) => setTerm(e.target.value)}
            placeholder="Fall 2026"
            className="mt-1 w-full rounded-xl border border-stone-300 px-3 py-1.5 text-sm"
          />
        </div>
        <button
          type="submit"
          disabled={!name.trim() || create.isPending}
          className="rounded-xl bg-matcha-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-matcha-700 disabled:opacity-50"
        >
          Add
        </button>
      </form>

      <ul className="space-y-1.5">
        {active.map((c) => (
          <li
            key={c.id}
            className="flex items-center justify-between rounded-xl border border-stone-100 px-3 py-1.5 text-sm"
          >
            <span className="truncate">
              {c.display_name}
              {c.term && <span className="text-stone-400"> · {c.term}</span>}
              <span className="ml-2 text-[10px] uppercase tracking-wide text-stone-400">
                {c.sources.join(" + ")}
              </span>
            </span>
            <span className="flex shrink-0 items-center gap-2">
              <button
                onClick={() => setArchived.mutate({ id: c.id, archived: true })}
                className="text-xs text-stone-400 hover:text-stone-600"
              >
                Archive
              </button>
              {c.source === "manual" && (
                <button
                  onClick={() => confirmDelete(c.id, c.display_name)}
                  className="text-xs text-red-400 hover:text-red-600"
                >
                  Delete
                </button>
              )}
            </span>
          </li>
        ))}
        {active.length === 0 && <li className="text-sm text-stone-400">No classes yet.</li>}
      </ul>

      {archived.length > 0 && (
        <details className="mt-3">
          <summary className="cursor-pointer text-xs text-stone-400 hover:text-stone-600">
            Archived ({archived.length})
          </summary>
          <ul className="mt-2 space-y-1.5">
            {archived.map((c) => (
              <li
                key={c.id}
                className="flex items-center justify-between rounded-xl border border-stone-100 px-3 py-1.5 text-sm text-stone-400"
              >
                <span className="truncate">{c.display_name}</span>
                <span className="flex shrink-0 items-center gap-2">
                  <button
                    onClick={() => setArchived.mutate({ id: c.id, archived: false })}
                    className="text-xs text-stone-400 hover:text-stone-600"
                  >
                    Unarchive
                  </button>
                  {c.source === "manual" && (
                    <button
                      onClick={() => confirmDelete(c.id, c.display_name)}
                      className="text-xs text-red-400 hover:text-red-600"
                    >
                      Delete
                    </button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
