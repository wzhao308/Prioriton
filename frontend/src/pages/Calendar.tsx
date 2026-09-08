import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import CalendarGrid from "../components/CalendarGrid";

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

export default function Calendar() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth());

  const tasksQuery = useQuery({ queryKey: ["tasks"], queryFn: () => api.listTasks() });

  const shift = (delta: number) => {
    let m = month + delta;
    let y = year;
    if (m < 0) {
      m = 11;
      y -= 1;
    } else if (m > 11) {
      m = 0;
      y += 1;
    }
    setMonth(m);
    setYear(y);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl font-semibold text-stone-900">
          {MONTH_NAMES[month]} {year}
        </h1>
        <div className="flex gap-2">
          <button
            onClick={() => shift(-1)}
            className="px-3 py-1.5 rounded-xl border border-stone-300 text-sm hover:bg-stone-100"
          >
            ← Prev
          </button>
          <button
            onClick={() => {
              setMonth(now.getMonth());
              setYear(now.getFullYear());
            }}
            className="px-3 py-1.5 rounded-xl border border-stone-300 text-sm hover:bg-stone-100"
          >
            Today
          </button>
          <button
            onClick={() => shift(1)}
            className="px-3 py-1.5 rounded-xl border border-stone-300 text-sm hover:bg-stone-100"
          >
            Next →
          </button>
        </div>
      </div>
      {tasksQuery.isLoading ? (
        <p className="text-stone-500">Loading…</p>
      ) : (
        <CalendarGrid year={year} month={month} tasks={tasksQuery.data ?? []} />
      )}
    </div>
  );
}
