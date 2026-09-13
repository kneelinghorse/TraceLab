import { parseApiTimestamp } from "@/lib/api/timestamps";
import useSWR from "swr";
import { useAuth } from "@/contexts/AuthContext";
import { httpClient } from "@/lib/api/http";
import type { ApiMission } from "@/types/mission";
import type { MissionEvent } from "@/types/mission-events";

type LogEntry = { id: string; level: string; message: string; logged_at: string };
const EVENT_LABELS: Record<string, string> = {
  "mission.queued": "Mission queued", "mission.started": "Mission started",
  "mission.completed": "Mission completed", "mission.failed": "Mission failed",
  "mission.status_changed": "Status changed",
};

/** Only explicit observations are progress; plan fields and old loop metrics are not. */
export function MissionRunActivity({ mission }: { mission: ApiMission }) {
  const { user } = useAuth();
  const active = mission.status === "queued" || mission.status === "in_progress";
  const options = { refreshInterval: active ? 5000 : 0 };
  const events = useSWR<MissionEvent[]>(["mission-events", user?.user_id, mission.id],
    () => httpClient.get("/missions/events/recent", { params: { mission_id: mission.id, limit: 50 } }), options);
  const logs = useSWR<LogEntry[]>(["mission-logs", user?.user_id, mission.id],
    () => httpClient.get(`/missions/${mission.id}/logs`, { params: { limit: 100 } }), options);
  const metadata = mission.execution_metadata ?? {};
  const phase = typeof metadata.current_phase === "string" && metadata.current_phase.trim() ? metadata.current_phase : null;
  const percent = typeof metadata.progress_percent === "number" && Number.isFinite(metadata.progress_percent)
    && metadata.progress_percent >= 0 && metadata.progress_percent <= 100 ? metadata.progress_percent : null;
  const step = metadata.current_step;
  const total = metadata.total_steps;
  const stepsKnown = typeof step === "number" && typeof total === "number" && Number.isInteger(step)
    && Number.isInteger(total) && total > 0 && step >= 0 && step <= total;
  return <div className="grid gap-6 p-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
    <section aria-label="Run progress" className="min-w-0 space-y-3">
      <h2 className="text-lg font-semibold">Run progress</h2>
      <p className="break-words">{phase ?? "Phase unknown"}</p>
      <p className="text-sm text-secondary">{stepsKnown ? `Step ${step} of ${total}` : "Step progress unknown"}</p>
      {percent !== null ? <><div role="progressbar" aria-label="Reported progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent} className="h-2 w-full overflow-hidden rounded-full bg-surface-alt"><div className="h-full rounded-full bg-accent" style={{ width: `${percent}%` }} /></div><p className="text-sm">{percent}% reported</p></> : <p className="text-sm text-muted">Percentage unknown</p>}
      <p className="text-sm text-muted">{active ? "Refreshes every 5 seconds while queued or running." : "Last reported observations for this run."}</p>
    </section>
    <section aria-label="Recent activity" className="min-w-0 space-y-3">
      <h2 className="text-lg font-semibold">Recent activity</h2>
      <p className="text-sm text-muted">Recent events retained by this server. Earlier events may be unavailable.</p>
      {events.error && <p role="alert" className="text-danger">Recent activity unavailable. <button className="underline" onClick={() => void events.mutate()}>Retry activity</button></p>}
      {events.isLoading && <p role="status">Loading activity…</p>}
      {!events.error && !events.isLoading && !events.data?.length && <p className="text-secondary">No recent activity is available for this mission.</p>}
      {Boolean(events.data?.length) && <ol className="space-y-3">{events.data!.map((event, index) => <li key={`${event.timestamp}-${index}`} className="border-l-2 border-line pl-3 text-sm break-words">
        <p>{EVENT_LABELS[event.event_type] ?? event.event_type}</p>
        {event.status && <p className="text-secondary">{event.previous_status ? `${event.previous_status.replaceAll("_", " ")} → ` : ""}{event.status.replaceAll("_", " ")}</p>}
        {event.error && <p className="text-danger">{event.error}</p>}
        <time className="text-muted" dateTime={event.timestamp}>{parseApiTimestamp(event.timestamp).toLocaleString()}</time>
      </li>)}</ol>}
    </section>
    <section aria-label="Runner logs" className="min-w-0 space-y-3 lg:col-span-2">
      <h2 className="text-lg font-semibold">Runner logs</h2>
      {logs.isLoading && <p role="status">Checking log availability…</p>}
      {!logs.isLoading && (logs.error || !logs.data?.length) && <p className="text-secondary">Logs unavailable — no runner log stream is available for this run. <button className="underline" onClick={() => void logs.mutate()}>Check again</button></p>}
      {Boolean(logs.data?.length) && <><p className="text-sm text-muted">Last {logs.data!.length} recorded lines{logs.error ? "; refresh failed" : ""}.</p><div tabIndex={0} role="region" aria-label="Recorded log lines" className="max-h-96 overflow-auto rounded-lg bg-background p-4 font-mono text-xs space-y-2">
        {logs.data!.map(log => <p key={log.id} className="break-words whitespace-pre-wrap"><time dateTime={log.logged_at}>{parseApiTimestamp(log.logged_at).toLocaleString()}</time> [{log.level}] {log.message}</p>)}
      </div></>}
    </section>
  </div>;
}
