import { parseApiTimestamp } from "@/lib/api/timestamps";
import useSWR from "swr";
import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { httpClient } from "@/lib/api/http";
import type { ApiMission } from "@/types/mission";
import type { MissionEvent } from "@/types/mission-events";

type LogEntry = {
  id: string; level: string; message: string; logged_at: string;
  created_at?: string; attempt_count?: number | null; event_id?: string | null; sequence?: number | null;
};
const PHASE_LABELS: Record<string, string> = {
  loading: "Loading mission", compiled: "Mission prepared", running: "Researching",
  critique: "Reviewing findings", upload: "Saving results", complete: "Run finished", error: "Run error",
};
const LOG_EVENT_LABELS: Record<string, string> = {
  mission_progress: "Observation", mission_warning: "Warning", mission_error: "Error",
  phase_started: "Started", phase_completed: "Finished", artifact_persisted: "Artifact saved",
  validation_result: "Validation result",
};
function observation(message: string): { label: string; phase: string } | null {
  try {
    const value = JSON.parse(message);
    if (!value || typeof value !== "object" || typeof value.phase !== "string"
      || typeof value.event !== "string" || !Object.hasOwn(PHASE_LABELS, value.phase)
      || !Object.hasOwn(LOG_EVENT_LABELS, value.event)) return null;
    const measurements = [
      typeof value.count === "number" && Number.isFinite(value.count) && value.count >= 0 ? `count: ${value.count}` : null,
      typeof value.duration_seconds === "number" && Number.isFinite(value.duration_seconds) && value.duration_seconds >= 0 ? `${value.duration_seconds}s` : null,
    ].filter(Boolean);
    return { phase: PHASE_LABELS[value.phase], label: `${PHASE_LABELS[value.phase]} · ${LOG_EVENT_LABELS[value.event]}${measurements.length ? ` · ${measurements.join(" · ")}` : ""}` };
  } catch { return null; }
}
function accessDenied(error: unknown): boolean {
  return typeof error === "object" && error !== null && "status" in error && [401, 403, 404].includes(Number(error.status));
}
const EVENT_LABELS: Record<string, string> = {
  "mission.queued": "Mission queued", "mission.started": "Mission started",
  "mission.completed": "Mission completed", "mission.failed": "Mission failed",
  "mission.status_changed": "Status changed",
};

/** Only explicit observations are progress; plan fields and old loop metrics are not. */
export function MissionRunActivity({ mission }: { mission: ApiMission }) {
  const { user } = useAuth();
  // Remount local timers and state on either identity boundary. SWR uses the
  // same pair so a late response for a previous mission cannot appear here.
  return <RunActivity key={`${user?.user_id ?? "anonymous"}:${mission.id}`} mission={mission} userId={user?.user_id} />;
}

function RunActivity({ mission, userId }: { mission: ApiMission; userId?: string }) {
  const active = mission.status === "queued" || mission.status === "in_progress";
  const options = { refreshInterval: active ? 5000 : 0, keepPreviousData: false };
  const events = useSWR<MissionEvent[]>(userId ? ["mission-events", userId, mission.id] : null,
    () => httpClient.get("/missions/events/recent", { params: { mission_id: mission.id, limit: 50 } }), options);
  const logs = useSWR<LogEntry[]>(userId ? ["mission-logs", userId, mission.id] : null,
    () => httpClient.get(`/missions/${mission.id}/logs`, { params: { limit: 100 } }), options);
  const [now, setNow] = useState(() => Date.now());
  const refreshLogs = logs.mutate;
  const terminal = ["completed", "validation_failed", "blocked", "cancelled"].includes(mission.status);
  useEffect(() => {
    if (!userId) return;
    if (active) {
      const clock = setInterval(() => setNow(Date.now()), 5000);
      return () => clearInterval(clock);
    }
    if (!terminal) return;
    // Terminal row persistence precedes the worker's final flush. Revalidate
    // for a bounded 45s window (three 10s requests plus retry backoff).
    void refreshLogs();
    const poll = setInterval(() => void refreshLogs(), 5000);
    const stop = setTimeout(() => clearInterval(poll), 45000);
    return () => { clearInterval(poll); clearTimeout(stop); };
  }, [active, terminal, userId, refreshLogs]);
  const denied = !userId || accessDenied(logs.error) || accessDenied(events.error);
  const entries = denied ? [] : (logs.data ?? []);
  const visibleEvents = denied ? [] : (events.data ?? []);
  const latest = entries.at(-1);
  const received = entries.reduce<number | null>((last, entry) => {
    const timestamp = entry.created_at ? parseApiTimestamp(entry.created_at).getTime() : NaN;
    return Number.isFinite(timestamp) ? Math.max(last ?? timestamp, timestamp) : last;
  }, null);
  const quiet = active && received !== null && now - received >= 30000;
  const observedPhase = entries.findLast(entry => entry.attempt_count === latest?.attempt_count && observation(entry.message))?.message;
  const metadata = mission.execution_metadata ?? {};
  const phase = typeof metadata.current_phase === "string" && metadata.current_phase.trim() ? metadata.current_phase : observedPhase ? observation(observedPhase)?.phase : null;
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
      {!events.error && !events.isLoading && !visibleEvents.length && <p className="text-secondary">No recent activity is available for this mission.</p>}
      {Boolean(visibleEvents.length) && <ol className="space-y-3">{visibleEvents.map((event, index) => <li key={`${event.timestamp}-${index}`} className="border-l-2 border-line pl-3 text-sm break-words">
        <p>{EVENT_LABELS[event.event_type] ?? event.event_type}</p>
        {event.status && <p className="text-secondary">{event.previous_status ? `${event.previous_status.replaceAll("_", " ")} → ` : ""}{event.status.replaceAll("_", " ")}</p>}
        {event.error && <p className="text-danger">{event.error}</p>}
        <time className="text-muted" dateTime={event.timestamp}>{parseApiTimestamp(event.timestamp).toLocaleString()}</time>
      </li>)}</ol>}
    </section>
    <section aria-label="Runner logs" className="min-w-0 space-y-3 lg:col-span-2">
      <h2 className="text-lg font-semibold">Runner logs</h2>
      {denied ? <p role="alert" className="text-danger">Run activity is unavailable for this account.</p> : <>
        <p role="status" aria-live="polite" className="text-sm text-secondary">
          {logs.isLoading ? "Checking for runner observations…" : logs.error
            ? "Log refresh failed. Retained observations may be out of date."
            : !entries.length ? active ? "Waiting for the first runner observation." : "No runner observations were recorded for this run."
            : !active ? "Retained observations from this run."
            : received === null ? "Recorded observations; receipt time unavailable."
            : quiet ? "No new observations for at least 30 seconds. The runner may be working quietly."
            : "Receiving runner observations."}
        </p>
        {received !== null && <p className="text-sm text-muted">Last received <time dateTime={new Date(received).toISOString()}>{new Date(received).toLocaleString()}</time></p>}
        <button className="text-sm underline" onClick={() => void refreshLogs()}>Refresh logs</button>
        {Boolean(entries.length) && <>
          <p className="text-sm text-muted">Last {entries.length} recorded lines. Timestamps on lines show when observations were emitted.</p>
          <div tabIndex={0} role="region" aria-label="Recorded log lines" className="max-h-96 overflow-auto rounded-lg bg-background p-4 font-mono text-xs space-y-2">
            {entries.map((log, index) => <div key={log.id}>
              {(index === 0 || entries[index - 1].attempt_count !== log.attempt_count) && <p className="pt-2 pb-1 font-semibold">{log.attempt_count ? `Attempt ${log.attempt_count}` : "Earlier observations · attempt unavailable"}</p>}
              <p className="break-words whitespace-pre-wrap"><time dateTime={log.logged_at}>{parseApiTimestamp(log.logged_at).toLocaleString()}</time> [{log.level}] {observation(log.message)?.label ?? log.message}</p>
            </div>)}
          </div>
        </>}
      </>}

    </section>
  </div>;
}
