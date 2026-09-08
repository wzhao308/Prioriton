import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import CourseManager from "../components/CourseManager";
import ConnectCanvasForm from "../components/ConnectCanvasForm";
import ConnectPlatformButton from "../components/ConnectPlatformButton";
import ReminderSettings from "../components/ReminderSettings";
import { parseApiDate } from "../lib/date";

/** Where the Assignment Tracker's connections live - connecting Canvas/
 * Gradescope/PrairieLearn here is what feeds Home, Calendar, Courses,
 * Analytics, and Recommendations everywhere else in the app. */
export default function Settings() {
  const queryClient = useQueryClient();
  const healthQuery = useQuery({ queryKey: ["health"], queryFn: api.getHealth, staleTime: Infinity });
  const isDemo = healthQuery.data?.demo_mode ?? false;
  const integrationsQuery = useQuery({ queryKey: ["integrations"], queryFn: api.listIntegrations });
  const disconnect = useMutation({
    mutationFn: (id: number) => api.disconnectIntegration(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["integrations"] }),
  });
  const syncNow = useMutation({
    mutationFn: api.syncNow,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["integrations"] });
      queryClient.invalidateQueries({ queryKey: ["courses"] });
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
    },
  });

  return (
    <div className="max-w-xl space-y-8">
      <section>
        <h1 className="font-display text-2xl font-semibold text-stone-900">Settings</h1>
        <p className="text-sm text-stone-500 mt-1">
          Connect an assignment source to sync due dates and grades automatically (every 15
          minutes, or hit "Sync now" any time), and manage the classes Prioriton knows about.
        </p>
      </section>

      <CourseManager />

      {isDemo && (
        <p className="text-xs text-stone-400 -mb-4">
          Public demo - connecting below is simulated: nothing you type is read, used, or stored,
          and Gradescope/PrairieLearn skip the real browser-based login entirely. Each drops in a
          small sample "synced" class so you can see what a real connection looks like once it
          works. Try it yourself with a real account by running Prioriton locally - see the
          project's README/DEPLOY.md.
        </p>
      )}

      <section className="rounded-2xl border border-stone-100 bg-white shadow-[0_1px_2px_rgba(35,40,31,0.04),0_12px_28px_-16px_rgba(35,40,31,0.18)] p-4">
        <h2 className="font-medium text-stone-800 mb-3">Canvas</h2>
        <ConnectCanvasForm />
      </section>

      <ConnectPlatformButton
        platform="gradescope"
        title="Gradescope"
        description="Your school routes Gradescope through SSO, so this opens a real browser window for you to log in once (including any Duo prompt). It reuses that session afterward for periodic syncs."
        startLogin={api.startGradescopeLogin}
      />

      <ConnectPlatformButton
        platform="prairielearn"
        title="PrairieLearn"
        description="Same approach as Gradescope: a real browser window opens for you to log in once through your school's SSO, then this reuses that session for periodic syncs."
        startLogin={api.startPrairieLearnLogin}
      />

      <ReminderSettings />

      <section>
        <h2 className="font-medium text-stone-800 mb-2">Connected sources</h2>
        <div className="space-y-2">
          {integrationsQuery.data?.length === 0 && (
            <p className="text-sm text-stone-400">Nothing connected yet.</p>
          )}
          {integrationsQuery.data?.map((integration) => (
            <div
              key={integration.id}
              className="flex items-center justify-between rounded-xl border border-stone-100 bg-white px-3 py-2"
            >
              <div>
                <p className="text-sm font-medium capitalize">{integration.type}</p>
                <p className="text-xs text-stone-500">
                  {integration.status === "connected" && integration.last_synced_at
                    ? `Last synced ${parseApiDate(integration.last_synced_at).toLocaleString()}`
                    : integration.status}
                </p>
                {integration.last_error && (
                  <p className="text-xs text-red-600">{integration.last_error}</p>
                )}
              </div>
              <button
                onClick={() => disconnect.mutate(integration.id)}
                className="text-xs px-2.5 py-1 rounded-full bg-red-50 text-red-600 hover:bg-red-100"
              >
                Disconnect
              </button>
            </div>
          ))}
        </div>
        <button
          onClick={() => syncNow.mutate()}
          disabled={syncNow.isPending}
          className="mt-4 text-sm px-3 py-2 rounded-xl bg-stone-800 text-white hover:bg-stone-700 disabled:opacity-50"
        >
          {syncNow.isPending ? "Syncing…" : "Sync now"}
        </button>
        {syncNow.data && (
          <p className="mt-2 text-xs text-stone-500">
            Synced {syncNow.data.integrations_synced} source(s), {syncNow.data.tasks_upserted} task(s).
            {syncNow.data.tasks_auto_dismissed > 0 &&
              ` Auto-dismissed ${syncNow.data.tasks_auto_dismissed} task(s) over a month past due.`}
            {syncNow.data.courses_archive_changed > 0 &&
              ` Updated ${syncNow.data.courses_archive_changed} class(es) to match the current semester.`}
            {syncNow.data.courses_merged > 0 &&
              ` Merged ${syncNow.data.courses_merged} class(es) tracked on more than one platform.`}
          </p>
        )}
      </section>
    </div>
  );
}
