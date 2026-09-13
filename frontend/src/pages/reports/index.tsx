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
import { reportsApi, type ReportStatus } from "@/lib/api/reports";
import { projectsApi } from "@/lib/api/projects";
import { parseApiTimestamp } from "@/lib/api/timestamps";

type StatusFilter = "all" | ReportStatus;
export default function ReportsPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [status, setStatus] = useState<StatusFilter>("all");
  const [selectedProject, setSelectedProject] = useState<string | null>(null);
  const projectId = selectedProject ?? (typeof router.query.project_id === "string" ? router.query.project_id : "");
  const [page, setPage] = useState(1);
  const projects = useSWR(["report-projects", user?.user_id], () => projectsApi.listAllProjects());
  const response = useSWR(["reports", user?.user_id, status, projectId, page], () => reportsApi.list({ status: status === "all" ? undefined : status, project_id: projectId || undefined, page, page_size: 20 }));
  const data = response.data;
  return <AuthGate><div className="mx-auto max-w-6xl space-y-6 px-4 py-8 sm:px-6">
    <header className="space-y-2"><p className="text-xs font-medium uppercase tracking-wider text-secondary">Research outputs</p><h1 className="text-3xl font-semibold">Reports</h1><p className="text-secondary">Read findings, inspect their evidence and export the result.</p></header>
    <section className="panel flex flex-wrap items-end gap-5 p-4" aria-label="Report filters">
      <fieldset><legend className="mb-2 text-sm text-secondary">Status</legend><div className="flex gap-2">{(["all", "draft", "final"] as const).map(value => <button key={value} aria-pressed={status === value} onClick={() => { setStatus(value); setPage(1); }} className={`rounded-lg border px-3 py-2 text-sm ${status === value ? "border-accent bg-accent text-on-accent" : "border-line-strong bg-surface text-secondary"}`}>{value.charAt(0).toUpperCase() + value.slice(1)}</button>)}</div></fieldset>
      <label className="min-w-0 flex-1 text-sm text-secondary">Project<select value={projectId} onChange={event => { setSelectedProject(event.target.value); setPage(1); }} className="mt-2 block w-full max-w-md rounded-lg border border-line-strong bg-surface px-3 py-2 text-foreground"><option value="">All projects</option>{projects.data?.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label>
      {projects.error && <p role="alert" className="text-sm text-danger">Project filters could not load. <button className="underline" onClick={() => void projects.mutate()}>Retry projects</button></p>}
    </section>
    {response.error ? <PageState state="error" title="Reports could not load." onRetry={() => void response.mutate()} /> : response.isLoading ? <PageState state="loading" title="Loading reports…" /> : data && <>
      <p className="text-sm text-secondary">{data.total.toLocaleString()} reports{status !== "all" ? ` · ${status}` : ""}</p>
      {data.items.length === 0 ? <section className="panel space-y-3 p-6"><h2 className="font-semibold">No reports match these filters</h2><p className="text-secondary">Choose another filter or create a report from a collection.</p><Link href="/collections" className="text-accent-text underline">Go to Collections</Link></section> : <ul className="space-y-3">{data.items.map(report => <li key={report.id} className="panel space-y-3 p-5"><div className="flex flex-wrap items-start justify-between gap-3"><Link href={`/reports/${report.id}`} className="min-w-0 flex-1 break-words text-lg font-medium text-accent-text underline underline-offset-4">{report.title}</Link><StatusBadge status={report.status} /></div><dl className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-secondary"><div><dt className="sr-only">Format</dt><dd>{report.report_type}</dd></div><div><dt className="sr-only">Excerpts</dt><dd>{report.chunk_count} excerpts</dd></div><div><dt className="sr-only">Tokens</dt><dd>{report.tokens_used.toLocaleString()} tokens</dd></div><div><dt className="sr-only">Created</dt><dd>{formatDistanceToNow(parseApiTimestamp(report.created_at), { addSuffix: true })}</dd></div></dl></li>)}</ul>}
      <PaginationBar page={page} pages={Math.ceil(data.total / (data.page_size || 20))} total={data.total} onChange={setPage} />
    </>}
  </div></AuthGate>;
}
