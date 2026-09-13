import { parseApiTimestamp } from "@/lib/api/timestamps";
import Link from "next/link";
import { useRouter } from "next/router";
import useSWR from "swr";
import { formatDistanceToNow } from "date-fns";
import { AuthGate } from "@/components/AuthGate";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { PaginationBar } from "@/components/ui/PaginationBar";
import { PageState } from "@/components/ui/PageState";
import { useAuth } from "@/contexts/AuthContext";
import { projectsApi } from "@/lib/api/projects";
import { homeApi } from "@/lib/api/home";
import { useApiMissions } from "@/lib/hooks/useMissions";
import type { ApiMission, MissionStatus } from "@/types/mission";

const STATUSES: MissionStatus[] = ["draft", "queued", "in_progress", "completed", "blocked", "cancelled", "validation_failed"];
const VIEWS = ["all", "attention", "queue"] as const;
function MissionRow({ mission }: { mission: ApiMission }) {
  return <li className="border-b border-line last:border-b-0">
    <Link href={`/missions/${mission.id}`} className="block rounded-lg p-5 hover:bg-surface-alt focus-visible:outline-focus">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1"><h2 className="break-words text-lg font-semibold">{mission.title}</h2><p className="break-all font-mono text-xs text-muted">{mission.mission_id}</p></div>
        <StatusBadge status={mission.status} />
      </div>
      <p className="mt-3 line-clamp-2 break-words text-sm text-secondary">{mission.objective}</p>
      <div className="mt-3 flex flex-wrap gap-3 text-xs text-muted">
        {mission.project_name && <span className="break-words">{mission.project_name}</span>}
        {mission.updated_at && <span>Updated {formatDistanceToNow(parseApiTimestamp(mission.updated_at), { addSuffix: true })}</span>}
      </div>
      {mission.error_message && <p className="mt-2 line-clamp-2 break-words text-sm text-danger">{mission.error_message}</p>}
    </Link>
  </li>;
}

function MissionsContent() {
  const router = useRouter();
  const { user } = useAuth();
  const view = VIEWS.find(value => value === router.query.view) ?? "all";
  const status = STATUSES.find(value => value === router.query.status);
  const projectId = typeof router.query.project_id === "string" ? router.query.project_id : undefined;
  const parsedPage = Number(router.query.page ?? 1);
  const page = Number.isInteger(parsedPage) && parsedPage > 0 ? parsedPage : 1;
  const projects = useSWR(["mission-project-options", user?.user_id], () => projectsApi.listAllProjects());
  const home = useSWR(["home", user?.user_id], () => homeApi.get(), { refreshInterval: 15000 });
  const { missions, pagination, isLoading, error, refresh } = useApiMissions({ page, pageSize: 20, status, projectId, view });
  function change(values: Record<string, string | number | undefined>) {
    const query = { ...router.query, ...values };
    Object.keys(query).forEach(key => { if (query[key] === undefined || query[key] === "") delete query[key]; });
    void router.push({ pathname: "/missions", query }, undefined, { shallow: true });
  }
  return <div className="mx-auto max-w-7xl space-y-6 px-4 py-8 sm:px-6">
    <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
      <div><h1 className="text-3xl font-bold">Missions</h1><p className="mt-2 text-secondary">Research runs, results and work that needs attention.</p></div>
      <Link className="rounded-lg bg-accent px-4 py-2 text-center text-sm font-medium text-on-accent" href="/missions/new">Create Mission</Link>
    </header>
    <section aria-label="Workspace mission totals" className="panel p-5">
      <h2 className="text-sm font-medium text-secondary">Workspace totals</h2>
      {home.error ? <p role="alert" className="mt-2 text-danger">Workspace totals unavailable. <button className="underline" onClick={() => void home.mutate()}>Retry totals</button></p> : !home.data ? <p role="status">Loading totals…</p> : <dl className="mt-3 grid grid-cols-3 gap-3">
        {[["Missions", home.data.missions.total], ["Needs attention", home.data.attention.total], ["Running", home.data.active_runs.total]].map(([label, count]) => <div key={label}><dt className="text-sm text-muted">{label}</dt><dd className="mt-1 text-2xl font-semibold">{count}</dd></div>)}
      </dl>}
    </section>
    <section className="panel p-4 sm:p-6" aria-label="Mission list">
      <nav aria-label="Mission views" className="mb-4 flex flex-wrap gap-2">{VIEWS.map(value => <button key={value} aria-current={view === value ? "page" : undefined} onClick={() => change({ view: value, status: undefined, page: 1 })} className={`rounded-lg px-4 py-2 text-sm ${view === value ? "bg-accent text-on-accent" : "border border-line"}`}>{value === "all" ? "All missions" : value === "attention" ? "Needs attention" : "Queue"}</button>)}</nav>
      <p className="mb-4 text-sm text-secondary">{view === "queue" ? "Queued and running missions. Queue position and wait time are not reported by the worker." : "Validation failures, blocked work, stalled queues and unreviewed results appear first."}</p>
      <div className="mb-5 flex flex-wrap items-end gap-3">
        <div><label htmlFor="status-filter" className="form-label">Status</label><select id="status-filter" className="form-input" value={status ?? ""} onChange={event => change({ status: event.target.value, page: 1 })}><option value="">All statuses</option>{STATUSES.map(value => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}</select></div>
        <div className="min-w-0 max-w-full"><label htmlFor="project-filter" className="form-label">Project</label><select id="project-filter" className="form-input max-w-full sm:max-w-72" value={projectId ?? ""} onChange={event => change({ project_id: event.target.value, page: 1 })}><option value="">All projects</option>{projects.data?.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></div>
        <button className="rounded-lg border border-line px-4 py-2 text-sm" onClick={() => { void refresh(); void home.mutate(); }}>Refresh</button>
      </div>
      {projects.error && <PageState state="error" title="Project filters unavailable." onRetry={() => void projects.mutate()} />}
      {error ? <PageState state="error" title="Missions could not load." onRetry={() => void refresh()} /> : isLoading ? <PageState state="loading" title="Loading missions…" /> : <>
        <p className="mb-3 text-sm text-secondary" aria-live="polite">{pagination?.total ?? 0} matching missions</p>
        {!missions.length ? <PageState state="empty" title="No missions match this view." /> : <ul>{missions.map(mission => <MissionRow key={mission.id} mission={mission} />)}</ul>}
        <PaginationBar page={page} pages={pagination?.pages ?? 0} onChange={next => change({ page: next })} />
      </>}
    </section>
  </div>;
}
export default function MissionsPage() { return <AuthGate><MissionsContent /></AuthGate>; }
