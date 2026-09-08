import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";

const LEAD_OPTIONS: { minutes: number; label: string }[] = [
  { minutes: 15, label: "15 minutes before" },
  { minutes: 60, label: "1 hour before" },
  { minutes: 180, label: "3 hours before" },
  { minutes: 720, label: "12 hours before" },
  { minutes: 1440, label: "1 day before" },
  { minutes: 2880, label: "2 days before" },
  { minutes: 4320, label: "3 days before" },
  { minutes: 10080, label: "1 week before" },
];

const CUSTOM_UNIT_MINUTES = { minutes: 1, hours: 60, days: 1440, weeks: 10080 } as const;
type CustomUnit = keyof typeof CUSTOM_UNIT_MINUTES;

/** Turns a lead time that isn't one of the presets back into a readable label
 * (e.g. a custom "5 days" or "90 minutes" someone added). Picks the largest
 * whole unit it divides evenly into, falling back to plain minutes. */
function formatCustomLead(minutes: number): string {
  const units: { unit: CustomUnit; label: string }[] = [
    { unit: "weeks", label: "week" },
    { unit: "days", label: "day" },
    { unit: "hours", label: "hour" },
  ];
  for (const { unit, label } of units) {
    const size = CUSTOM_UNIT_MINUTES[unit];
    if (minutes % size === 0) {
      const n = minutes / size;
      return `${n} ${label}${n === 1 ? "" : "s"} before`;
    }
  }
  return `${minutes} minute${minutes === 1 ? "" : "s"} before`;
}

export default function ReminderSettings() {
  const queryClient = useQueryClient();
  const settingsQuery = useQuery({ queryKey: ["settings"], queryFn: api.getSettings });
  const [selected, setSelected] = useState<number[]>([]);
  const [customValue, setCustomValue] = useState("");
  const [customUnit, setCustomUnit] = useState<CustomUnit>("hours");
  const [customError, setCustomError] = useState<string | null>(null);

  useEffect(() => {
    if (settingsQuery.data) setSelected(settingsQuery.data.reminder_lead_minutes);
  }, [settingsQuery.data]);

  const save = useMutation({
    mutationFn: (minutes: number[]) => api.updateSettings(minutes),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      queryClient.invalidateQueries({ queryKey: ["reminders"] });
    },
  });

  const toggle = (minutes: number) => {
    setSelected((prev) =>
      prev.includes(minutes) ? prev.filter((m) => m !== minutes) : [...prev, minutes],
    );
  };

  const addCustom = () => {
    const n = Number(customValue);
    if (!Number.isFinite(n) || n <= 0 || !Number.isInteger(n)) {
      setCustomError("Enter a whole number greater than 0.");
      return;
    }
    const minutes = n * CUSTOM_UNIT_MINUTES[customUnit];
    setSelected((prev) => (prev.includes(minutes) ? prev : [...prev, minutes].sort((a, b) => b - a)));
    setCustomValue("");
    setCustomError(null);
  };

  const customSelected = selected.filter((m) => !LEAD_OPTIONS.some((opt) => opt.minutes === m));

  const dirty =
    settingsQuery.data &&
    JSON.stringify([...selected].sort()) !== JSON.stringify([...settingsQuery.data.reminder_lead_minutes].sort());

  return (
    <section className="rounded-2xl border border-stone-100 bg-white shadow-[0_1px_2px_rgba(35,40,31,0.04),0_12px_28px_-16px_rgba(35,40,31,0.18)] p-4">
      <h2 className="font-medium text-stone-800 mb-1">Reminders</h2>
      <p className="text-sm text-stone-500 mb-3">
        When should Prioriton remind you about an upcoming due date? Pick as many as you like.
      </p>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {LEAD_OPTIONS.map((opt) => (
          <label
            key={opt.minutes}
            className={`flex items-center gap-2 rounded-xl border px-2 py-1.5 text-sm cursor-pointer ${
              selected.includes(opt.minutes)
                ? "border-matcha-300 bg-matcha-50 text-matcha-700"
                : "border-stone-200 text-stone-600"
            }`}
          >
            <input
              type="checkbox"
              className="accent-matcha-600"
              checked={selected.includes(opt.minutes)}
              onChange={() => toggle(opt.minutes)}
            />
            {opt.label}
          </label>
        ))}
      </div>

      {customSelected.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {customSelected.map((minutes) => (
            <span
              key={minutes}
              className="flex items-center gap-1 rounded-full border border-matcha-300 bg-matcha-50 px-2 py-1 text-sm text-matcha-700"
            >
              {formatCustomLead(minutes)}
              <button
                onClick={() => setSelected((prev) => prev.filter((m) => m !== minutes))}
                className="text-matcha-400 hover:text-matcha-700"
                aria-label="Remove"
              >
                ✕
              </button>
            </span>
          ))}
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="text-sm text-stone-600">Custom:</span>
        <input
          type="number"
          min={1}
          step={1}
          value={customValue}
          onChange={(e) => {
            setCustomValue(e.target.value);
            setCustomError(null);
          }}
          onKeyDown={(e) => e.key === "Enter" && addCustom()}
          placeholder="e.g. 5"
          className="w-20 rounded-xl border border-stone-300 px-2 py-1 text-sm"
        />
        <select
          value={customUnit}
          onChange={(e) => setCustomUnit(e.target.value as CustomUnit)}
          className="rounded-xl border border-stone-300 px-2 py-1 text-sm"
        >
          <option value="minutes">minutes before</option>
          <option value="hours">hours before</option>
          <option value="days">days before</option>
          <option value="weeks">weeks before</option>
        </select>
        <button
          onClick={addCustom}
          className="rounded-full bg-stone-100 px-3 py-1 text-sm font-medium text-stone-700 hover:bg-stone-200"
        >
          Add
        </button>
      </div>
      {customError && <p className="mt-1 text-xs text-red-600">{customError}</p>}

      <button
        onClick={() => save.mutate(selected)}
        disabled={!dirty || selected.length === 0 || save.isPending}
        className="mt-3 rounded-xl bg-matcha-600 px-4 py-2 text-sm font-medium text-white hover:bg-matcha-700 disabled:opacity-50"
      >
        {save.isPending ? "Saving…" : "Save reminder settings"}
      </button>
      {selected.length === 0 && (
        <p className="mt-1 text-xs text-amber-600">Pick at least one lead time.</p>
      )}
      {save.isSuccess && !dirty && (
        <p className="mt-1 text-xs text-emerald-600">Saved — reminders updated for all synced tasks.</p>
      )}
    </section>
  );
}
