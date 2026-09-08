import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { RecommendationItem } from "../api/client";
import { parseApiDate } from "../lib/date";

const KIND_LABEL: Record<string, string> = {
  study_time: "Study time",
  grade: "Grades",
  assignment_start: "Get started",
  productivity: "Productivity",
  general: "General",
};

const PRIORITY_STYLE: Record<number, string> = {
  1: "border-l-4 border-l-red-400",
  2: "border-l-4 border-l-matcha-300",
  3: "border-l-4 border-l-stone-200",
};

function RecommendationCard({ item }: { item: RecommendationItem }) {
  return (
    <div className={`rounded-2xl border border-stone-100 bg-white shadow-[0_1px_2px_rgba(35,40,31,0.04),0_12px_28px_-16px_rgba(35,40,31,0.18)] px-4 py-3 ${PRIORITY_STYLE[item.priority] ?? ""}`}>
      <div className="flex items-center gap-2 mb-1">
        <span className="text-[10px] uppercase tracking-wide font-semibold text-matcha-500">
          {KIND_LABEL[item.kind] ?? item.kind}
        </span>
        {item.course_name && (
          <span className="text-[10px] uppercase tracking-wide text-stone-400">{item.course_name}</span>
        )}
      </div>
      <p className="text-sm text-stone-700">{item.message}</p>
    </div>
  );
}

export default function Recommendations() {
  const queryClient = useQueryClient();
  const healthQuery = useQuery({ queryKey: ["health"], queryFn: api.getHealth, staleTime: Infinity });
  const isDemo = healthQuery.data?.demo_mode ?? false;
  const query = useQuery({ queryKey: ["recommendations"], queryFn: api.getRecommendations });

  const generate = useMutation({
    mutationFn: api.generateRecommendations,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["recommendations"] }),
  });

  if (query.isLoading) return <p className="text-stone-500">Loading…</p>;
  if (query.isError) return <p className="text-red-600">{(query.error as Error).message}</p>;

  const data = query.data!;
  const items = [...data.items].sort((a, b) => a.priority - b.priority);

  return (
    <div className="max-w-xl space-y-6">
      <section>
        <h1 className="font-display text-2xl font-semibold text-stone-900">Recommendations</h1>
        <p className="text-sm text-stone-500 mt-1">
          AI-generated study advice, grounded in your own tracked hours, grades, and assignment
          timing - never invented.
        </p>
      </section>

      {!data.eligible && (
        <div className="rounded-2xl border border-dashed border-stone-300 p-8 text-center">
          <p className="text-stone-600 font-medium">
            {data.days_until_eligible == null
              ? "Nothing tracked yet."
              : `Come back in ${Math.ceil(data.days_until_eligible)} day(s).`}
          </p>
          <p className="text-sm text-stone-500 mt-1">
            {data.days_until_eligible == null
              ? "Start a study session or sync an assignment source, then check back after a week of activity."
              : "Prioriton needs about a week of real activity before it has anything grounded to say."}
          </p>
        </div>
      )}

      {data.eligible && (
        <>
          <button
            onClick={() => generate.mutate()}
            disabled={generate.isPending}
            className="rounded-xl bg-matcha-600 px-4 py-2 text-sm font-medium text-white hover:bg-matcha-700 disabled:opacity-50"
          >
            {generate.isPending ? "Generating…" : data.id ? "Regenerate" : "Generate now"}
          </button>
          {isDemo && (
            <p className="text-xs text-stone-400">
              Public demo - live generation here is a real AI call, rate-limited so one shared
              instance can't be spammed.
            </p>
          )}
          {generate.isError && <p className="text-sm text-red-600">{(generate.error as Error).message}</p>}

          {data.generated_at && (
            <p className="text-xs text-stone-400">
              Last generated {parseApiDate(data.generated_at).toLocaleString()}
            </p>
          )}

          <div className="space-y-2">
            {items.length === 0 && (
              <p className="text-sm text-stone-400">No recommendations yet - click "Generate now".</p>
            )}
            {items.map((item, i) => (
              <RecommendationCard key={i} item={item} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
