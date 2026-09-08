import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Label,
  LabelList,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { api } from "../api/client";
import { ACCENT, CATEGORICAL, INK, colorForCourse } from "../lib/chartPalette";

const AXIS_STYLE = { fontSize: 12, fill: INK.muted };
const GRID_PROPS = { stroke: INK.grid, vertical: false };

function ChartCard({
  title,
  description,
  children,
  isEmpty,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
  isEmpty?: boolean;
}) {
  return (
    <section className="rounded-2xl border border-stone-100 bg-white shadow-[0_1px_2px_rgba(35,40,31,0.04),0_12px_28px_-16px_rgba(35,40,31,0.18)] p-4">
      <h2 className="text-sm font-semibold text-stone-700">{title}</h2>
      {description && <p className="text-xs text-stone-400 mb-3">{description}</p>}
      {isEmpty ? (
        <p className="py-10 text-center text-sm text-stone-400">Not enough data yet.</p>
      ) : (
        <div className="h-64">{children}</div>
      )}
    </section>
  );
}

function dateTick(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** Course names can run long ("ECON 302 - Microeconomics") - truncated to
 * the course code/short prefix so angled x-axis labels stay legible; the
 * full name is still in the tooltip and the legend below the chart. */
function courseTick(name: string): string {
  return name.length > 14 ? `${name.slice(0, 13)}…` : name;
}

export default function Analytics() {
  const overviewQuery = useQuery({ queryKey: ["analytics", "overview"], queryFn: api.courseOverview });
  const studyVsGradeQuery = useQuery({ queryKey: ["analytics", "study-vs-grade"], queryFn: api.studyVsGrade });
  const earlyStartQuery = useQuery({
    queryKey: ["analytics", "early-start-vs-grade"],
    queryFn: api.earlyStartVsGrade,
  });
  const productivityQuery = useQuery({
    queryKey: ["analytics", "weekly-productivity"],
    queryFn: () => api.weeklyProductivity(8),
  });

  const overview = overviewQuery.data ?? [];
  const courseIds = useMemo(() => overview.map((c) => c.course_id), [overview]);

  const [gradeTrendCourseId, setGradeTrendCourseId] = useState<number | "">("");
  const effectiveTrendCourseId = gradeTrendCourseId || overview[0]?.course_id || "";
  const gradeTrendQuery = useQuery({
    queryKey: ["analytics", "grade-trends", effectiveTrendCourseId],
    queryFn: () => api.gradeTrends(effectiveTrendCourseId ? Number(effectiveTrendCourseId) : undefined),
    enabled: overview.length > 0,
  });

  const gradesData = overview.filter((c) => c.avg_grade_pct != null);
  const earlyStartByCourse = useMemo(() => {
    const points = earlyStartQuery.data ?? [];
    const byCourse = new Map<string, typeof points>();
    for (const p of points) {
      const key = p.course_name ?? "Unassigned";
      if (!byCourse.has(key)) byCourse.set(key, []);
      byCourse.get(key)!.push(p);
    }
    return [...byCourse.entries()];
  }, [earlyStartQuery.data]);

  if (overviewQuery.isLoading) return <p className="text-stone-500">Loading…</p>;

  return (
    <div className="space-y-6">
      <section>
        <h1 className="font-display text-2xl font-semibold text-stone-900">Analytics</h1>
        <p className="text-sm text-stone-500 mt-1">
          How your grades, study time, and habits relate to each other, from your own tracked data.
        </p>
      </section>

      <div className="grid gap-6 md:grid-cols-2">
        <ChartCard title="Average grade by course" isEmpty={gradesData.length === 0}>
          <ResponsiveContainer>
            <BarChart data={gradesData} margin={{ top: 16, right: 8, left: 0, bottom: 8 }}>
              <CartesianGrid {...GRID_PROPS} />
              <XAxis
                dataKey="course_name"
                tickFormatter={courseTick}
                tick={AXIS_STYLE}
                interval={0}
                angle={-20}
                textAnchor="end"
                height={56}
              />
              <YAxis domain={[0, 100]} tick={AXIS_STYLE} width={32} />
              <Tooltip formatter={(v: number) => [`${v}%`, "Avg grade"]} />
              <Bar dataKey="avg_grade_pct" radius={[4, 4, 0, 0]} maxBarSize={48}>
                {gradesData.map((c) => (
                  <Cell key={c.course_id} fill={colorForCourse(c.course_id, courseIds)} />
                ))}
                <LabelList dataKey="avg_grade_pct" position="top" formatter={(v: number) => `${v}%`} style={{ fill: INK.secondary, fontSize: 11 }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Grade trend"
          description="Each graded assignment over time, for one course."
          isEmpty={(gradeTrendQuery.data ?? []).length === 0}
        >
          <div className="mb-2 -mt-1">
            <select
              value={effectiveTrendCourseId}
              onChange={(e) => setGradeTrendCourseId(Number(e.target.value))}
              className="rounded-xl border border-stone-300 px-2 py-1 text-xs"
            >
              {overview.map((c) => (
                <option key={c.course_id} value={c.course_id}>
                  {c.course_name}
                </option>
              ))}
            </select>
          </div>
          <ResponsiveContainer>
            <LineChart data={gradeTrendQuery.data ?? []} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
              <CartesianGrid {...GRID_PROPS} />
              <XAxis dataKey="graded_at" tickFormatter={dateTick} tick={AXIS_STYLE} />
              <YAxis domain={[0, 100]} tick={AXIS_STYLE} width={32} />
              <Tooltip
                labelFormatter={(v: string) => new Date(v).toLocaleDateString()}
                formatter={(v: number, _n, p) => [`${v}%`, p.payload.task_title]}
              />
              <Line
                type="monotone"
                dataKey="grade_pct"
                stroke={ACCENT}
                strokeWidth={2}
                dot={{ r: 4, fill: ACCENT }}
              />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Study hours this week, by course" isEmpty={overview.length === 0}>
          <ResponsiveContainer>
            <BarChart data={overview} margin={{ top: 16, right: 8, left: 0, bottom: 8 }}>
              <CartesianGrid {...GRID_PROPS} />
              <XAxis
                dataKey="course_name"
                tickFormatter={courseTick}
                tick={AXIS_STYLE}
                interval={0}
                angle={-20}
                textAnchor="end"
                height={56}
              />
              <YAxis tick={AXIS_STYLE} width={32}>
                <Label value="Hours" angle={-90} position="insideLeft" style={{ fontSize: 11, fill: INK.muted }} />
              </YAxis>
              <Tooltip formatter={(v: number) => [`${v}h`, "This week"]} />
              <Bar dataKey="study_hours_this_week" radius={[4, 4, 0, 0]} maxBarSize={48}>
                {overview.map((c) => (
                  <Cell key={c.course_id} fill={colorForCourse(c.course_id, courseIds)} />
                ))}
                <LabelList dataKey="study_hours_this_week" position="top" formatter={(v: number) => `${v}h`} style={{ fill: INK.secondary, fontSize: 11 }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Study time vs. grade"
          description="Weekly hours vs. average grade, one point per course."
          isEmpty={(studyVsGradeQuery.data ?? []).filter((p) => p.avg_grade_pct != null).length === 0}
        >
          <ResponsiveContainer>
            <ScatterChart margin={{ top: 16, right: 16, left: 0, bottom: 8 }}>
              <CartesianGrid {...GRID_PROPS} />
              <XAxis type="number" dataKey="avg_weekly_study_hours" name="Weekly hours" tick={AXIS_STYLE} unit="h" />
              <YAxis type="number" dataKey="avg_grade_pct" name="Avg grade" domain={[0, 100]} tick={AXIS_STYLE} width={32} />
              <ZAxis range={[120, 120]} />
              <Tooltip
                cursor={{ strokeDasharray: "3 3" }}
                formatter={(v: number, name: string) => [name === "Avg grade" ? `${v}%` : `${v}h`, name]}
              />
              <Scatter data={(studyVsGradeQuery.data ?? []).filter((p) => p.avg_grade_pct != null)}>
                {(studyVsGradeQuery.data ?? [])
                  .filter((p) => p.avg_grade_pct != null)
                  .map((c) => (
                    <Cell key={c.course_id} fill={colorForCourse(c.course_id, courseIds)} />
                  ))}
                <LabelList
                  dataKey="course_name"
                  position="top"
                  formatter={courseTick}
                  offset={10}
                  style={{ fill: INK.secondary, fontSize: 11 }}
                />
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="How early you start vs. grade"
          description="Days started before the due date vs. the grade received, per assignment."
          isEmpty={(earlyStartQuery.data ?? []).length === 0}
        >
          <ResponsiveContainer>
            <ScatterChart margin={{ top: 16, right: 16, left: 0, bottom: 8 }}>
              <CartesianGrid {...GRID_PROPS} />
              <XAxis type="number" dataKey="days_before_due" name="Days started early" tick={AXIS_STYLE} />
              <YAxis type="number" dataKey="grade_pct" name="Grade" domain={[0, 100]} tick={AXIS_STYLE} width={32} />
              <ZAxis range={[90, 90]} />
              <Tooltip
                cursor={{ strokeDasharray: "3 3" }}
                formatter={(v: number, name: string) => [name === "Grade" ? `${v}%` : `${v}d`, name]}
                labelFormatter={() => ""}
              />
              {earlyStartByCourse.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
              {earlyStartByCourse.map(([courseName, points], i) => (
                <Scatter key={courseName} name={courseName} data={points} fill={CATEGORICAL[i % CATEGORICAL.length]} />
              ))}
            </ScatterChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Weekly productivity" description="Study hours per week, last 8 weeks." isEmpty={(productivityQuery.data ?? []).length === 0}>
          <ResponsiveContainer>
            <BarChart data={productivityQuery.data ?? []} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
              <CartesianGrid {...GRID_PROPS} />
              <XAxis dataKey="week_start" tickFormatter={dateTick} tick={AXIS_STYLE} />
              <YAxis tick={AXIS_STYLE} width={32} />
              <Tooltip labelFormatter={(v: string) => `Week of ${dateTick(v)}`} formatter={(v: number) => [`${v}h`, "Study hours"]} />
              <Bar dataKey="study_hours" fill={ACCENT} radius={[4, 4, 0, 0]} maxBarSize={40} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <ChartCard title="Assignments completed per week" description="Last 8 weeks." isEmpty={(productivityQuery.data ?? []).length === 0}>
        <ResponsiveContainer>
          <BarChart data={productivityQuery.data ?? []} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
            <CartesianGrid {...GRID_PROPS} />
            <XAxis dataKey="week_start" tickFormatter={dateTick} tick={AXIS_STYLE} />
            <YAxis allowDecimals={false} tick={AXIS_STYLE} width={32} />
            <Tooltip labelFormatter={(v: string) => `Week of ${dateTick(v)}`} formatter={(v: number) => [v, "Completed"]} />
            <Bar dataKey="tasks_completed" fill={CATEGORICAL[2]} radius={[4, 4, 0, 0]} maxBarSize={40} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>
    </div>
  );
}
