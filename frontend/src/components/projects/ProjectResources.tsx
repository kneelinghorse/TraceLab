import Link from "next/link";
import { useState } from "react";
import useSWR, { mutate as globalMutate } from "swr";
import { useAuth } from "@/contexts/AuthContext";
import { useFeedback } from "@/components/ui/useFeedback";
import { PageState } from "@/components/ui/PageState";
import { PaginationBar } from "@/components/ui/PaginationBar";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { DocumentRows } from "@/components/documents/DocumentRows";
import { DocumentUpload } from "@/components/documents/DocumentUpload";
import { EntryCard } from "@/components/evidence/EntryCard";
import { documentsApi } from "@/lib/api/documents";
import { evidenceApi } from "@/lib/api/evidence";
import { collectionsApi } from "@/lib/api/collections";
import { missionsApi } from "@/lib/api/missions";
import { reportsApi } from "@/lib/api/reports";

export const PROJECT_TABS = ["Overview", "Documents", "Evidence", "Collections", "Missions", "Reports"] as const;
type ResourceTab = Exclude<typeof PROJECT_TABS[number], "Overview">;
const PAGE_SIZE = 20;

async function load(tab: ResourceTab, projectId: string, page: number) {
  if (tab === "Documents") {
    const result = await documentsApi.listDocuments({ projectId, page, pageSize: PAGE_SIZE });
    return { total: result.pagination.total, documents: result.data };
  }
  if (tab === "Evidence") {
    const result = await evidenceApi.list(projectId, page);
    return { total: result.entry_total, evidence: result.entries };
  }
  if (tab === "Collections") {
    const result = await collectionsApi.list({ project_id: projectId, page, page_size: PAGE_SIZE });
    return { total: result.total, rows: result.data.map(row => ({ id: row.id, title: row.name, href: `/collections/${row.id}`, summary: row.description, status: undefined })) };
  }
  if (tab === "Missions") {
    const result = await missionsApi.list({ project_id: projectId, page, page_size: PAGE_SIZE, view: "all" });
    return { total: result.pagination.total, rows: result.data.map(row => ({ id: row.id, title: row.title, href: `/missions/${row.id}`, summary: row.objective, status: row.status })) };
  }
  const result = await reportsApi.list({ project_id: projectId, page, page_size: PAGE_SIZE });
  return { total: result.total, rows: result.items.map(row => ({ id: row.id, title: row.title, href: `/reports/${row.id}`, summary: row.report_type, status: row.status })) };
}

export function ProjectResources({ projectId, tab, refreshStats, onBusyChange }: { projectId: string; tab: ResourceTab; refreshStats: () => Promise<unknown>; onBusyChange: (busy: boolean) => void }) {
  const { user } = useAuth();
  const { askConfirmation, notify, feedback } = useFeedback();
  const [page, setPage] = useState(1);
  const response = useSWR(["project-resources", user?.user_id, projectId, tab, page], () => load(tab, projectId, page));
  async function refresh() {
    await Promise.all([response.mutate(), refreshStats(), globalMutate(key => Array.isArray(key) && key[0] === "documents")]);
  }
  async function remove(id: string) {
    if (!await askConfirmation("Delete this document?")) return;
    try { await documentsApi.deleteDocument(id); await refresh(); } catch (error) { notify(error instanceof Error ? error.message : "Document could not be deleted."); }
  }
  const data = response.data;
  return <div className="space-y-6">
    {feedback}
    <section className="panel p-5">
      <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-xl font-semibold">{tab}</h2>{data && <p className="text-sm text-secondary">{data.total.toLocaleString()} {tab.toLowerCase()}</p>}<button className="rounded border border-line px-3 py-2 text-sm" onClick={() => void refresh().catch(() => {})}>Refresh {tab.toLowerCase()}</button></div>
      {tab === "Collections" && <p className="mt-2 text-sm text-secondary">Collections containing readable chunks from this project.</p>}
      {response.error ? <PageState state="error" title={`${tab} could not load.`} onRetry={() => void response.mutate()} /> : response.isLoading ? <PageState state="loading" title={`Loading ${tab.toLowerCase()}…`} /> : data?.total === 0 ? <PageState state="empty" title={`No accessible ${tab.toLowerCase()} in this project.`} /> : data && <>
        {data.documents && <DocumentRows documents={data.documents} onDelete={id => void remove(id)} />}
        {data.evidence && <div className="mt-4 space-y-4">{data.evidence.map(entry => <EntryCard key={entry.id} entry={entry} />)}</div>}
        {data.rows && <ul className="divide-y divide-line">{data.rows.map(row => <li key={row.id} className="flex flex-wrap items-start justify-between gap-3 py-5"><div className="min-w-0 flex-1"><Link className="block break-words font-semibold hover:text-accent-text" href={row.href}>{row.title}</Link>{row.summary && <p className="mt-2 line-clamp-3 break-words text-sm text-secondary">{row.summary}</p>}</div>{row.status && <StatusBadge status={row.status} />}</li>)}</ul>}
        <PaginationBar label={`Project ${tab.toLowerCase()} pages`} page={page} pages={Math.ceil(data.total / PAGE_SIZE)} onChange={setPage} />
      </>}
    </section>
    {tab === "Documents" && <DocumentUpload projectId={projectId} onComplete={refresh} onBusyChange={onBusyChange} />}
  </div>;
}
