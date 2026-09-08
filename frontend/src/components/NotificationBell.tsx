import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { parseApiDate } from "../lib/date";

function timeAgo(iso: string): string {
  const diffMs = Date.now() - parseApiDate(iso).getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

export default function NotificationBell() {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();

  const remindersQuery = useQuery({
    queryKey: ["reminders", "active"],
    queryFn: () => api.listReminders(true),
    refetchInterval: 60_000, // poll every minute so the badge stays current without a push channel
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["reminders"] });
  };

  const dismissOne = useMutation({
    mutationFn: (id: number) => api.updateReminderStatus(id, "dismissed"),
    onSuccess: invalidate,
  });
  const dismissAll = useMutation({
    mutationFn: api.dismissActiveReminders,
    onSuccess: invalidate,
  });

  const reminders = remindersQuery.data ?? [];
  const count = reminders.length;

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="relative rounded-full p-2 text-stone-500 hover:bg-stone-100"
        aria-label="Notifications"
      >
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M6 8a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6" />
          <path d="M10 21a2 2 0 0 0 4 0" />
        </svg>
        {count > 0 && (
          <span className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold text-white">
            {count > 9 ? "9+" : count}
          </span>
        )}
      </button>

      {open && (
        <>
          {/* backdrop to close on outside click */}
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute right-0 z-20 mt-2 w-80 rounded-2xl border border-stone-100 bg-white shadow-[0_1px_2px_rgba(35,40,31,0.04),0_12px_28px_-16px_rgba(35,40,31,0.18)] shadow-lg">
            <div className="flex items-center justify-between border-b border-stone-100 px-3 py-2">
              <span className="text-sm font-semibold text-stone-700">Reminders</span>
              {count > 0 && (
                <button
                  onClick={() => dismissAll.mutate()}
                  className="text-xs text-stone-400 hover:text-stone-600"
                >
                  Clear all
                </button>
              )}
            </div>
            <div className="max-h-80 overflow-y-auto">
              {count === 0 && (
                <p className="px-3 py-6 text-center text-sm text-stone-400">You're all caught up.</p>
              )}
              {reminders.map((r) => (
                <div
                  key={r.id}
                  className="flex items-start justify-between gap-2 border-b border-stone-50 px-3 py-2 last:border-0"
                >
                  <div className="min-w-0">
                    {r.task_url ? (
                      <a
                        href={r.task_url}
                        target="_blank"
                        rel="noreferrer"
                        className="block truncate text-sm font-medium text-stone-800 hover:text-matcha-600 hover:underline"
                      >
                        {r.task_title}
                      </a>
                    ) : (
                      <p className="truncate text-sm font-medium text-stone-800">{r.task_title}</p>
                    )}
                    <p className="text-xs text-stone-500">
                      {r.task_due_at
                        ? `Due ${parseApiDate(r.task_due_at).toLocaleString(undefined, {
                            month: "short",
                            day: "numeric",
                            hour: "numeric",
                            minute: "2-digit",
                          })}`
                        : "No due date"}{" "}
                      · reminder fired {timeAgo(r.remind_at)}
                    </p>
                  </div>
                  <button
                    onClick={() => dismissOne.mutate(r.id)}
                    className="shrink-0 text-xs text-stone-400 hover:text-stone-600"
                    aria-label="Dismiss"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
