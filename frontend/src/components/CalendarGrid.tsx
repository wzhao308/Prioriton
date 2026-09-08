import type { Task } from "../api/client";
import { effectiveDueDate, parseApiDate } from "../lib/date";
import { sourceColorClasses } from "../lib/sourceColors";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function dateKey(d: Date): string {
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

export default function CalendarGrid({
  year,
  month, // 0-indexed
  tasks,
}: {
  year: number;
  month: number;
  tasks: Task[];
}) {
  // Placed on whichever date is currently the relevant deadline: the regular
  // due date until it passes, then the late-submission cutoff (if the
  // platform offers one) - see effectiveDueDate's docstring. `showingLate`
  // records, per task, whether that placement is actually the late date (vs.
  // just the only date it has), so the tooltip can say so accurately.
  const tasksByDay = new Map<string, { task: Task; showingLate: boolean }[]>();
  for (const task of tasks) {
    const effective = effectiveDueDate(task);
    if (!effective) continue;
    const key = dateKey(effective);
    const showingLate = !!task.late_due_at && effective.getTime() === parseApiDate(task.late_due_at)!.getTime();
    if (!tasksByDay.has(key)) tasksByDay.set(key, []);
    tasksByDay.get(key)!.push({ task, showingLate });
  }

  const firstOfMonth = new Date(year, month, 1);
  const startWeekday = firstOfMonth.getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const daysInPrevMonth = new Date(year, month, 0).getDate();
  const today = new Date();

  // Leading/trailing cells show the adjacent month's real dates (muted) instead
  // of sitting blank - both for a fuller-looking grid and so a task due on one
  // of those days is still visible without flipping pages. `new Date(year,
  // month ± 1, day)` correctly rolls over into the neighboring year on its own.
  const cells: { date: Date; inMonth: boolean }[] = [];
  for (let i = startWeekday - 1; i >= 0; i--) {
    cells.push({ date: new Date(year, month - 1, daysInPrevMonth - i), inMonth: false });
  }
  for (let d = 1; d <= daysInMonth; d++) cells.push({ date: new Date(year, month, d), inMonth: true });
  let nextMonthDay = 1;
  while (cells.length % 7 !== 0) cells.push({ date: new Date(year, month + 1, nextMonthDay++), inMonth: false });

  return (
    <div className="rounded-2xl border border-stone-100 bg-white shadow-[0_1px_2px_rgba(35,40,31,0.04),0_12px_28px_-16px_rgba(35,40,31,0.18)] overflow-hidden">
      <div className="grid grid-cols-7 border-b border-stone-100 bg-stone-50/60">
        {WEEKDAYS.map((w) => (
          <div key={w} className="px-2 py-2 text-xs font-semibold text-stone-500 text-center">
            {w}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7">
        {cells.map(({ date, inMonth }, idx) => {
          const isToday = dateKey(date) === dateKey(today);
          const dayTasks = tasksByDay.get(dateKey(date)) ?? [];
          return (
            <div
              key={idx}
              className={`min-h-[96px] border-b border-r border-stone-100 p-1.5 ${
                inMonth ? "" : "bg-stone-50/60"
              }`}
            >
              <span
                className={`text-xs inline-flex h-5 w-5 items-center justify-center rounded-full ${
                  isToday
                    ? "bg-matcha-600 text-white font-semibold"
                    : inMonth
                      ? "text-stone-500"
                      : "text-stone-300"
                }`}
              >
                {date.getDate()}
              </span>
              <div className="mt-1 space-y-1">
                {dayTasks.slice(0, 3).map(({ task, showingLate }) => (
                  <a
                    key={task.id}
                    href={task.url ?? undefined}
                    target="_blank"
                    rel="noreferrer"
                    title={showingLate ? `${task.title} (late submission cutoff)` : task.title}
                    className={`block truncate rounded px-1 py-0.5 text-[10px] font-medium ${
                      inMonth ? "" : "opacity-60"
                    } ${
                      task.status === "pending"
                        ? sourceColorClasses(task.source).pill
                        : "bg-stone-100 text-stone-400 line-through"
                    }`}
                  >
                    {showingLate ? `⏰ ${task.title}` : task.title}
                  </a>
                ))}
                {dayTasks.length > 3 && (
                  <p className="text-[10px] text-stone-400 px-1">+{dayTasks.length - 3} more</p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
