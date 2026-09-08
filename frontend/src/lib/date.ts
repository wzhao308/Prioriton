/** Every timestamp the backend returns (due_at, remind_at, last_synced_at, ...)
 * is a naive ISO string that already represents true UTC (see
 * backend/app/adapters/base.py's SyncedTask.due_at docstring for why) - but a
 * naive ISO string with no "Z"/offset is ambiguous to JavaScript's Date
 * constructor, which treats it as LOCAL time instead. Parsing one directly
 * silently shifts it by the browser's UTC offset (e.g. a due date meant as
 * 11:59 PM Central shows up as 4:59 AM the next day). Always parse API
 * dates through this helper instead of calling `new Date(...)` directly. */
export function parseApiDate(value: string): Date;
export function parseApiDate(value: string | null | undefined): Date | null;
export function parseApiDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const hasTimezone = /Z$|[+-]\d{2}:\d{2}$/.test(value);
  return new Date(hasTimezone ? value : `${value}Z`);
}

/** Some platforms (confirmed on Gradescope) offer a hard late-submission
 * cutoff beyond the regular due date. Before the regular due date passes,
 * that's the one that matters; once it's passed, the late cutoff becomes the
 * relevant deadline instead (there's no third stage - once both have passed,
 * this keeps returning the late one, which is the more accurate "how overdue
 * is this" reference point). Returns null only if there's no due date at all. */
export function effectiveDueDate(task: { due_at: string | null; late_due_at: string | null }): Date | null {
  const due = parseApiDate(task.due_at);
  const late = parseApiDate(task.late_due_at);
  if (!due) return late;
  if (!late) return due;
  return Date.now() < due.getTime() ? due : late;
}
