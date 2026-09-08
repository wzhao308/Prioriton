import { useEffect, useState } from "react";
import { NavLink, Route, Routes, Navigate, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api/client";
import { parseApiDate } from "./lib/date";
import Home from "./pages/Home";
import StudyTimer from "./pages/StudyTimer";
import CalendarPage from "./pages/Calendar";
import Courses from "./pages/Courses";
import Analytics from "./pages/Analytics";
import Recommendations from "./pages/Recommendations";
import Settings from "./pages/Settings";
import NotificationBell from "./components/NotificationBell";
import {
  CalendarIcon,
  ChartIcon,
  GearIcon,
  HomeIcon,
  LeafIcon,
  SparkleIcon,
  StackIcon,
  TimerIcon,
} from "./components/icons";

const NAV_ITEMS = [
  { to: "/", end: true, label: "Home", Icon: HomeIcon },
  { to: "/study-timer", label: "Study Timer", Icon: TimerIcon },
  { to: "/calendar", label: "Calendar", Icon: CalendarIcon },
  { to: "/courses", label: "Courses", Icon: StackIcon },
  { to: "/analytics", label: "Analytics", Icon: ChartIcon },
  { to: "/recommendations", label: "Recommendations", Icon: SparkleIcon },
  { to: "/settings", label: "Settings", Icon: GearIcon },
];

/** Live "h:mm:ss" (or "m:ss") label for the sidebar's active-session pill -
 * ticks once a second on its own so the app shell doesn't need the full
 * timer state StudyTimer.tsx owns. Returns null when nothing is running. */
function useElapsedLabel(startedAt: string | undefined): string | null {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!startedAt) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [startedAt]);

  if (!startedAt) return null;
  const totalSeconds = Math.max(0, Math.floor((now - parseApiDate(startedAt).getTime()) / 1000));
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = totalSeconds % 60;
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`;
}

export default function App() {
  const activeQuery = useQuery({
    queryKey: ["study-sessions", "active"],
    queryFn: api.activeStudySession,
    refetchInterval: 15_000,
  });
  const elapsed = useElapsedLabel(activeQuery.data?.started_at);
  const healthQuery = useQuery({ queryKey: ["health"], queryFn: api.getHealth, staleTime: Infinity });
  const isDemo = healthQuery.data?.demo_mode ?? false;

  return (
    <div className="min-h-full flex">
      <aside className="hidden md:flex w-60 shrink-0 flex-col border-r border-stone-200/80 bg-white/70 backdrop-blur-sm px-4 py-5">
        <Link to="/" className="flex items-center gap-2.5 px-2 mb-8">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-matcha-600 text-white">
            <LeafIcon />
          </span>
          <span className="flex flex-col leading-tight">
            <span className="font-display text-lg font-semibold text-stone-900">Prioriton</span>
            <span className="text-[11px] text-stone-400">know what to work on next</span>
          </span>
        </Link>

        <nav className="flex flex-col gap-1">
          {NAV_ITEMS.map(({ to, end, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-2.5 rounded-xl px-3 py-2 text-sm font-medium transition-colors ${
                  isActive ? "bg-matcha-100 text-matcha-800" : "text-stone-600 hover:bg-stone-100"
                }`
              }
            >
              <Icon />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="mt-auto">
          {activeQuery.data && (
            <Link
              to="/study-timer"
              className="flex items-center gap-2 rounded-xl border border-matcha-200 bg-matcha-50 px-3 py-2 text-xs"
            >
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-matcha-500 opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-matcha-600" />
              </span>
              <span className="min-w-0 flex-1 truncate text-matcha-800">{activeQuery.data.course_name}</span>
              <span className="font-mono text-matcha-700 tabular-nums">{elapsed}</span>
            </Link>
          )}
        </div>
      </aside>

      <div className="flex-1 min-w-0 flex flex-col">
        {isDemo && (
          <div className="bg-matcha-600 px-4 py-1.5 text-center text-xs font-medium text-white">
            Public demo with sample data - Canvas/Gradescope/PrairieLearn syncing and live AI
            recommendations are disabled here, and the data resets on a timer.
          </div>
        )}
        <div className="flex items-center justify-between border-b border-stone-200/80 bg-white/70 backdrop-blur-sm px-4 py-2.5 md:px-8">
          <Link to="/" className="md:hidden flex items-center gap-2">
            <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-matcha-600 text-white">
              <LeafIcon />
            </span>
            <span className="font-display text-base font-semibold text-stone-900">Prioriton</span>
          </Link>
          <span className="hidden md:block" />
          <NotificationBell />
        </div>
        <main className="flex-1 max-w-5xl w-full mx-auto px-4 py-8 md:px-8">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/study-timer" element={<StudyTimer />} />
            <Route path="/calendar" element={<CalendarPage />} />
            <Route path="/courses" element={<Courses />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/recommendations" element={<Recommendations />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
        {/* Icon-only on mobile - 7 items is one too many for labels to fit a
            phone-width bottom bar without clipping (verified at 390px). */}
        <nav className="md:hidden sticky bottom-0 flex justify-around border-t border-stone-200 bg-white/90 backdrop-blur-sm py-2.5">
          {NAV_ITEMS.map(({ to, end, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              aria-label={label}
              title={label}
              className={({ isActive }) =>
                `flex items-center justify-center rounded-full p-2.5 ${
                  isActive ? "bg-matcha-100 text-matcha-700" : "text-stone-500"
                }`
              }
            >
              <Icon />
            </NavLink>
          ))}
        </nav>
      </div>
    </div>
  );
}
