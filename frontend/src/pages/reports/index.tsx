import { activityTitleClass, ActivityDot } from "@/components/activity/ActivityState";
import { markViewed, useActivityState } from "@/lib/hooks/useActivitySummary";
import { PageContainer, PageHeader } from "@/components/ui/PageHeader";
import Link from "next/link";
import { useRouter } from "next/router";
import { useState } from "react";
import useSWR from "swr";
import { formatDistanceToNow } from "date-fns";
import { AuthGate } from "@/components/AuthGate";
import { useAuth } from "@/contexts/AuthContext";
import { PaginationBar } from "@/components/ui/PaginationBar";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { PageState } from "@/components/ui/PageState";
import { reportsApi, type ReportOrigin as Origin } from "@/lib/api/reports";
import { ReportOrigin } from "@/components/reports/ReportOrigin";
import { projectsApi } from "@/lib/api/projects";
import { parseApiTimestamp } from "@/lib/api/timestamps";

const FILTERS = [
  { label: "Reports", one: "report", origins: ["written", "librarian"] },
  { label: "Evidence briefs", one: "evidence brief", origins: ["agent_brief"] },
  { label: "Mission results", one: "mission result", origins: ["mission"] },
] satisfies { label: string; one: string; origins: Origin[] }[];
export default function ReportsPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [filter, setFilter] = useState(0);
  const [selectedProject, setSelectedProject] = useState<string | null>(null);
  const projectId = selectedProject ?? (typeof router.query.project_id === "string" ? router.query.project_id : "");
  const [page, setPage] = useState(1);
  const projects = useSWR(["report-projects", user?.user_id], () => projectsApi.listAllProjects());
  const response = useSWR(["reports", user?.user_id, filter, projectId, page], () => reportsApi.list({ origin: FILTERS[filter].origins, project_id: projectId || undefined, page, page_size: 20 }));
  const data = response.data;
  const state = useActivityState((data?.items ?? []).map(report => ({ type: "report", id: report.id })));
  return <AuthGate><PageContainer>
    <PageHeader title="Reports" description="Read findings, inspect their evidence and export the result." />
    <section className="panel flex flex-wrap items-end gap-4 p-4" aria-label="Report filters">
      <fieldset><legend className="mb-2 text-sm text-secondary">Source</legend><div className="flex flex-wrap gap-2">{FILTERS.map(({ label }, index) => <button key={label} aria-pressed={filter === index} onClick={() => { setFilter(index); setPage(1); }} className={`rounded-lg border px-3 py-2 text-sm ${filter === index ? "border-accent bg-accent text-on-accent" : "border-line-strong bg-surface text-secondary"}`}>{label}</button>)}</div></fieldset>
      <label className="min-w-0 flex-1 text-sm text-secondary">Project<select value={projectId} onChange={event => { setSelectedProject(event.target.value); setPage(1); }} className="mt-2 block w-full max-w-md rounded-lg border border-line-strong bg-surface px-3 py-2 text-foreground"><option value="">All projects</option>{projects.data?.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label>
      {projects.error && <p role="alert" className="text-sm text-danger">Project filters could not load. <button className="underline" onClick={() => void projects.mutate()}>Retry projects</button></p>}
    </section>
    {state.error && <p role="alert" className="text-sm text-secondary">Seen-state could not load. <button className="underline" onClick={() => void state.mutate()}>Retry seen-state</button></p>}
    {response.error ? <PageState state="error" title="Reports could not load." onRetry={() => void response.mutate()} /> : response.isLoading ? <PageState state="loading" title="Loading reports…" /> : data && <>
      <p className="text-sm text-secondary">{data.total.toLocaleString()} {data.total === 1 ? FILTERS[filter].one : FILTERS[filter].label.toLowerCase()}</p>
      {data.items.length === 0 ? <section className="panel space-y-3 p-6"><h2 className="font-semibold">No reports match these filters</h2><p className="text-secondary">Choose another filter or create a report from a collection.</p><Link href="/collections" className="text-accent-text underline">Go to Collections</Link></section> : <ul className="space-y-3">{data.items.map(report => {
        const itemState = state.data?.items?.find(item => item.id === report.id);
        const titleClass = `min-w-0 flex-1 break-words text-lg ${activityTitleClass(itemState)}`;
        const href = report.origin === "mission" ? report.origin_href : `/reports/${report.id}`;
        return <li key={report.id} className="panel space-y-3 px-4 py-3" data-viewed={itemState?.viewed} data-new={itemState?.new || undefined}><div className="flex flex-wrap items-start justify-between gap-3">{href ? <Link href={href} onClick={() => { if (!itemState?.viewed) void markViewed([{ type: "report", id: report.id, occurred_at: report.updated_at }]); }} className={`${titleClass} underline underline-offset-4 hover:text-accent-text`}><ActivityDot isNew={itemState?.new} />{report.title}</Link> : <span className={titleClass}><ActivityDot isNew={itemState?.new} />{report.title}</span>}{report.status === "final" && <StatusBadge status="final" />}</div><div className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-secondary"><ReportOrigin report={report} />{report.project_name && <Link href={`/projects/${report.project_id}`} className="underline">{report.project_name}</Link>}<span>{formatDistanceToNow(parseApiTimestamp(report.created_at), { addSuffix: true })}</span></div></li>;
      })}</ul>}
      <PaginationBar page={page} pages={Math.ceil(data.total / (data.page_size || 20))} total={data.total} onChange={setPage} />
    </>}
  </PageContainer></AuthGate>;
}
