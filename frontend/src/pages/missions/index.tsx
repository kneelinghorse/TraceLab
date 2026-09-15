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
import { useApiMissions } from "@/lib/hooks/useMissions";
import type { ApiMission, MissionSort, MissionStatus } from "@/types/mission";

const STATUSES: MissionStatus[] = ["draft", "queued", "in_progress", "completed", "blocked", "cancelled", "validation_failed"];
const SORTS: { value: MissionSort; label: string }[] = [
  { value: "created_desc", label: "Newest first" },
  { value: "updated_desc", label: "Recently updated" },
  { value: "created_asc", label: "Oldest first" },
  { value: "updated_asc", label: "Least recently updated" },
];
function MissionCard({ mission }: { mission: ApiMission }) {
  return <li className="panel flex min-w-0 flex-col hover:border-line-strong">
    <Link href={`/missions/${mission.id}`} className="flex h-full flex-col gap-3 rounded-2xl p-5 focus-visible:outline-focus">
      <div className="flex items-start justify-between gap-3">
        <h2 className="line-clamp-2 min-w-0 break-words text-base font-semibold leading-snug">{mission.title}</h2>
        <StatusBadge status={mission.status} />
      </div>
      <p className="break-all font-mono text-xs text-muted">{mission.mission_id}</p>
      <p className="line-clamp-3 break-words text-sm text-secondary">{mission.objective}</p>
      {mission.error_message && <p className="line-clamp-2 break-words text-sm text-danger">{mission.error_message}</p>}
      <div className="mt-auto flex flex-wrap items-center justify-between gap-2 pt-2 text-xs text-muted">
        <span className="min-w-0 truncate">{mission.project_name ?? "No project"}</span>
        {mission.updated_at && <span className="shrink-0">Updated {formatDistanceToNow(parseApiTimestamp(mission.updated_at), { addSuffix: true })}</span>}
      </div>
    </Link>
  </li>;
}

function MissionsContent() {
  const router = useRouter();
  const { user } = useAuth();
  const sort = SORTS.find(option => option.value === router.query.sort)?.value ?? "created_desc";
  const status = STATUSES.find(value => value === router.query.status);
  const projectId = typeof router.query.project_id === "string" ? router.query.project_id : undefined;
  const parsedPage = Number(router.query.page ?? 1);
  const page = Number.isInteger(parsedPage) && parsedPage > 0 ? parsedPage : 1;
  const projects = useSWR(["mission-project-options", user?.user_id], () => projectsApi.listAllProjects());
  const { missions, pagination, isLoading, error, refresh } = useApiMissions({ page, pageSize: 20, status, projectId, sort });
  function change(values: Record<string, string | string[] | number | undefined>) {
    const query = { ...router.query, ...values };
    Object.keys(query).forEach(key => { if (query[key] === undefined || query[key] === "") delete query[key]; });
    void router.push({ pathname: "/missions", query }, undefined, { shallow: true });
  }
  return <div className="mx-auto max-w-7xl space-y-6 px-4 py-8 sm:px-6">
    <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
      <div><h1 className="text-3xl font-bold">Missions</h1><p className="mt-2 text-secondary">Research runs and their results, newest first.</p></div>
      <Link className="rounded-lg bg-accent px-4 py-2 text-center text-sm font-medium text-on-accent" href="/missions/new">Create Mission</Link>
    </header>
    <section aria-label="Mission filters" className="panel flex flex-wrap items-end gap-3 p-4">
      <div><label htmlFor="status-filter" className="form-label">Status</label><select id="status-filter" className="form-input" value={status ?? ""} onChange={event => change({ status: event.target.value, page: 1 })}><option value="">All statuses</option>{STATUSES.map(value => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}</select></div>
      <div className="min-w-0 max-w-full"><label htmlFor="project-filter" className="form-label">Project</label><select id="project-filter" className="form-input max-w-full sm:max-w-72" value={projectId ?? ""} onChange={event => change({ project_id: event.target.value, page: 1 })}><option value="">All projects</option>{projects.data?.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></div>
      <div><label htmlFor="sort-order" className="form-label">Sort</label><select id="sort-order" className="form-input" value={sort} onChange={event => change({ sort: event.target.value === "created_desc" ? undefined : event.target.value, page: 1 })}>{SORTS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></div>
      <button className="rounded-lg border border-line px-4 py-2.5 text-sm" onClick={() => void refresh()}>Refresh</button>
      {!isLoading && !error && <p className="ml-auto text-sm text-secondary" aria-live="polite">{pagination?.total ?? 0} matching missions</p>}
    </section>
    {projects.error && <PageState state="error" title="Project filters unavailable." onRetry={() => void projects.mutate()} />}
    <section aria-label="Mission list">
      {error ? <PageState state="error" title="Missions could not load." onRetry={() => void refresh()} /> : isLoading ? <PageState state="loading" title="Loading missions…" /> : <>
        {!missions.length ? <PageState state="empty" title="No missions match these filters." /> : <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{missions.map(mission => <MissionCard key={mission.id} mission={mission} />)}</ul>}
        <PaginationBar page={page} pages={pagination?.pages ?? 0} onChange={next => change({ page: next })} />
      </>}
    </section>
  </div>;
}
export default function MissionsPage() { return <AuthGate><MissionsContent /></AuthGate>; }
