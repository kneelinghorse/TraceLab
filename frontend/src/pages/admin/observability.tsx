import Head from "next/head";
import Link from "next/link";
import type { ReactNode } from "react";
import useSWR from "swr";

import { AuthGate } from "@/components/AuthGate";
import { RequireAdmin } from "@/components/RequireAdmin";
import { StatCard, StatGrid } from "@/components/console/StatCard";
import { useAuth } from "@/contexts/AuthContext";
import { adminStatsApi } from "@/lib/api/admin-stats";

const button = "rounded-lg border border-line-strong px-4 py-2 text-sm text-secondary hover:bg-surface-alt disabled:opacity-50";
function timestamp(value: string | null | undefined) {
  if (!value) return "Not observed";
  return new Date(/(?:Z|[+-]\d\d:\d\d)$/.test(value) ? value : `${value}Z`).toLocaleString();
}
function Panel({ title, children }: { title: string; children: ReactNode }) {
  return <section aria-label={title} className="panel min-w-0 p-5"><h2 className="mb-4 text-lg font-semibold">{title}</h2>{children}</section>;
}
function Counts({ values, empty = "No records." }: { values: Record<string, number>; empty?: string }) {
  return Object.keys(values).length ? <dl className="space-y-2">{Object.entries(values).map(([key, count]) => <div key={key} className="flex justify-between gap-4 border-b border-line pb-2 text-sm"><dt className="break-words text-secondary">{key.replaceAll("_", " ")}</dt><dd className="font-medium tabular-nums">{count.toLocaleString()}</dd></div>)}</dl> : <p className="text-sm text-secondary">{empty}</p>;
}
export function ObservabilityContent() {
  const { user } = useAuth();
  const { data, error, isLoading, isValidating, mutate } = useSWR(["admin-stats", user?.user_id], adminStatsApi.get, { refreshInterval: snapshot => (snapshot?.refresh_seconds ?? 30) * 1000 });
  return <div className="mx-auto max-w-7xl space-y-6 px-4 py-8 sm:px-6">
    <Head><title>Observability · TraceLab</title></Head>
    <header className="flex flex-wrap items-start justify-between gap-4"><div><p className="mb-2 text-xs font-semibold uppercase tracking-widest text-muted">Administration</p><h1 className="text-3xl font-semibold tracking-tight">Observability</h1><p className="mt-2 text-secondary">System totals and the latest runtime observations.</p></div><div className="flex flex-wrap gap-2"><Link href="/admin/corrections" className={button}>Manage corrections</Link><button className={button} onClick={() => void mutate()} disabled={isValidating}>{isValidating ? "Refreshing…" : "Refresh"}</button></div></header>
    {isLoading && <p className="panel p-6 text-secondary" role="status">Loading system observations…</p>}
    {error && <div role="alert" className="rounded-lg bg-danger-surface p-5 text-danger"><p>{data ? "Refresh failed. The last successful snapshot is shown below." : "System observations could not load."}</p><button onClick={() => void mutate()} className="mt-3 rounded border border-current px-3 py-2 text-sm">Retry</button></div>}
    {data && <>
      <p className="text-sm text-muted">Updated <time dateTime={data.generated_at}>{timestamp(data.generated_at)}</time> · refreshes every {data.refresh_seconds}s · system-wide counts</p>
      <StatGrid><StatCard label="Missions" value={data.missions.total.toLocaleString()} sublabel="All recorded statuses" /><StatCard label="Projects" value={data.projects.toLocaleString()} sublabel="Excludes deleted projects" /><StatCard label="Documents" value={data.documents.toLocaleString()} sublabel="Excludes deleted documents" /><StatCard label="Chunks" value={data.chunks.toLocaleString()} sublabel="In non-deleted documents" /></StatGrid>
      <div className="grid items-start gap-6 lg:grid-cols-3">
        <Panel title="Mission statuses"><Counts values={data.missions.by_status} /><Link className="mt-4 inline-block text-sm text-accent-text underline" href="/missions">Browse missions</Link></Panel>
        <Panel title="Ingestion"><p className="mb-3 text-sm text-secondary">{data.ingestion_jobs.total.toLocaleString()} recorded jobs</p><Counts values={data.ingestion_jobs.by_status} /></Panel>
        <Panel title="Knowledge graph"><p className="mb-3 text-sm text-secondary">{data.graph_edges.toLocaleString()} persisted edges</p><Counts values={data.graph_edges_by_type} /></Panel>
        <Panel title="DeepSearch worker"><dl className="space-y-3 text-sm">
          <div><dt className="text-muted">Status</dt><dd className="mt-1 font-medium">{data.worker?.status ?? "Unavailable"}</dd></div>
          {data.worker?.error && <div className="rounded bg-warning-surface p-3 text-warning"><dt className="sr-only">Health check</dt><dd>{data.worker.error}</dd></div>}
          {([ ["Processed", data.worker?.missions_processed], ["Completed", data.worker?.missions_completed], ["Failed", data.worker?.missions_failed], ["Uptime (seconds)", data.worker?.uptime_seconds] ] as const).map(([label, value]) => <div key={label} className="flex justify-between gap-3"><dt className="text-secondary">{label}</dt><dd>{value == null ? "Not reported" : value.toLocaleString()}</dd></div>)}
          <div><dt className="text-muted">Current mission</dt><dd className="break-all">{data.worker?.current_mission_id ?? "Not reported"}</dd></div>
        </dl><p className="mt-4 text-xs text-muted">Checked {timestamp(data.worker?.checked_at)}. Worker counters describe its current process lifetime.</p></Panel>
        <Panel title="Reconciler"><dl className="space-y-3 text-sm"><div><dt className="text-muted">Scheduler</dt><dd>{data.reconciler.enabled == null ? "Not reported" : data.reconciler.enabled ? "Enabled" : "Disabled"}</dd></div><div><dt className="text-muted">Last run</dt><dd>{timestamp(data.reconciler.last_run_at)}</dd></div><div><dt className="text-muted">Last status</dt><dd>{data.reconciler.last_status ?? "Not observed"}</dd></div><div><dt className="text-muted">Runs in this API process</dt><dd>{data.reconciler.runs ?? "Not reported"}</dd></div></dl>{data.reconciler.last_counts && <div className="mt-4"><Counts values={data.reconciler.last_counts} /></div>}</Panel>
        <Panel title="Correction queue">{data.corrections ? <Counts values={data.corrections} /> : <p className="text-sm text-warning">{data.corrections_error ?? "Queue observations unavailable."}</p>}<Link href="/admin/corrections" className="mt-4 inline-block text-sm text-accent-text underline">Open correction queue</Link></Panel>
      </div>
      <p className="text-sm text-muted">{data.process_scope}</p>
      <StatGrid><StatCard label="Reports" value={data.reports.toLocaleString()} /><StatCard label="Evidence entries" value={data.evidence_entries.toLocaleString()} /><StatCard label="Evidence sources" value={data.evidence_sources.toLocaleString()} /><StatCard label="Session notes" value={data.evidence_notes.toLocaleString()} /></StatGrid>
      <p className="text-xs text-muted">Reports, evidence, ingestion jobs and graph edges count all retained records, including records associated with deleted projects.</p>
      <Panel title="Recently updated missions"><ul className="divide-y divide-line">{data.recent_missions.map(mission => <li key={mission.id} className="flex flex-wrap items-center justify-between gap-3 py-3"><div className="min-w-0"><Link href={`/missions/${mission.id}`} className="break-words font-medium hover:text-accent-text">{mission.title}</Link><p className="mt-1 break-all text-xs text-muted">{mission.mission_id} · {timestamp(mission.updated_at)}</p></div><span className="rounded-full bg-surface-alt px-2.5 py-1 text-xs text-secondary">{mission.status.replaceAll("_", " ")}</span></li>)}</ul>{!data.recent_missions.length && <p className="text-sm text-secondary">No missions recorded.</p>}<p className="mt-3 text-xs text-muted">Showing {data.recent_missions.length} of {data.missions.total.toLocaleString()} missions.</p></Panel>
    </>}
  </div>;
}
export default function ObservabilityPage() { return <AuthGate><RequireAdmin><ObservabilityContent /></RequireAdmin></AuthGate>; }
