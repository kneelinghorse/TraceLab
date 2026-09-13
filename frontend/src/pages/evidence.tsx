import { useState, type FormEvent } from "react";
import useSWR from "swr";
import { useRouter } from "next/router";
import { AuthGate } from "@/components/AuthGate";
import { useAuth } from "@/contexts/AuthContext";
import { EntryCard } from "@/components/evidence/EntryCard";
import { SessionNotes } from "@/components/evidence/SessionNotes";
import { evidenceApi, sourceDomain, type EvidenceFilters } from "@/lib/api/evidence";
import { projectsApi } from "@/lib/api/projects";

const filterKeys = ["mission_id", "session_key", "disposition", "tag", "created_from", "created_until", "source_id", "report_id", "document_id"] as const;
export default function EvidencePage() {
  const router = useRouter();
  return <AuthGate><EvidenceBrowser key={JSON.stringify(router.query)} initial={router.query} /></AuthGate>;
}
function EvidenceBrowser({ initial }: { initial: Record<string, string | string[] | undefined> }) {
  const { user } = useAuth();
  const initialFilters = Object.fromEntries(filterKeys.flatMap(key => typeof initial[key] === "string" ? [[key, initial[key]]] : [])) as EvidenceFilters;
  const [projectId, setProjectId] = useState(typeof initial.project_id === "string" ? initial.project_id : "");
  const [filters, setFilters] = useState<EvidenceFilters>(initialFilters);
  const [draft, setDraft] = useState<EvidenceFilters>(initialFilters);
  const [query, setQuery] = useState(typeof initial.q === "string" ? initial.q : "");
  const [draftQuery, setDraftQuery] = useState(query);
  const [projectSearch, setProjectSearch] = useState("");
  const [projectPage, setProjectPage] = useState(1);
  const [page, setPage] = useState(1);
  const [grouped, setGrouped] = useState(false);
  const projects = useSWR(["evidence-projects", user?.user_id, projectSearch, projectPage], () => projectsApi.listProjects({ search: projectSearch.trim() || undefined, page: projectPage, pageSize: 20 }));
  const ledger = useSWR(projectId ? ["evidence", user?.user_id, projectId, query, filters, page] : null, () => query ? evidenceApi.search(projectId, query, page, filters) : evidenceApi.list(projectId, page, filters));
  const error = projects.error || ledger.error;
  function apply(event: FormEvent) {
    event.preventDefault();
    setFilters(Object.fromEntries(Object.entries(draft).map(([key, value]) => [key, value?.trim() || undefined])));
    setQuery(draftQuery.trim()); setPage(1);
  }
  const groups = new Map<string, NonNullable<typeof ledger.data>["entries"]>();
  for (const entry of ledger.data?.entries || []) {
    const key = grouped ? entry.source_id : "entries";
    groups.set(key, [...(groups.get(key) || []), entry]);
  }
  return <div className="mx-auto max-w-6xl space-y-6 px-4 py-8 sm:px-6">
    <header><h1 className="text-3xl font-semibold">Evidence</h1><p className="mt-2 text-secondary">Follow a claim back to its source, research session and outputs.</p></header>
    <section className="panel space-y-4 p-5" aria-label="Choose a project">
      <label className="form-label">Find a project<input className="form-input mt-2" value={projectSearch} onChange={e => { setProjectSearch(e.target.value); setProjectPage(1); }} placeholder="Search project names" /></label>
      <label className="form-label">Project<select aria-label="Project" className="form-input mt-2" value={projectId} onChange={e => { setProjectId(e.target.value); setPage(1); setFilters({}); setDraft({}); setQuery(""); setDraftQuery(""); }}>
        <option value="">Select a project</option>
        {projectId && !projects.data?.data.some(project => project.id === projectId) && <option value={projectId}>Selected project</option>}
        {projects.data?.data.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}
      </select></label>
      {projects.isLoading && <p role="status">Loading projects…</p>}
      {projects.data && projects.data.pagination.pages > 1 && <nav aria-label="Project pages" className="flex flex-wrap items-center gap-3 text-sm"><button disabled={projectPage === 1} onClick={() => setProjectPage(projectPage - 1)} className="rounded border border-line px-3 py-2 disabled:opacity-50">Previous projects</button><span>Page {projectPage} of {projects.data.pagination.pages}</span><button disabled={projectPage >= projects.data.pagination.pages} onClick={() => setProjectPage(projectPage + 1)} className="rounded border border-line px-3 py-2 disabled:opacity-50">Next projects</button></nav>}
    </section>
    {projectId && <form onSubmit={apply} className="panel space-y-4 p-5" aria-label="Evidence filters">
      <label className="form-label">Search evidence<input className="form-input mt-2" type="search" value={draftQuery} onChange={e => setDraftQuery(e.target.value)} placeholder="Search claims, snippets and sources" /></label>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <label className="form-label">Disposition<select aria-label="Disposition" className="form-input mt-2" value={draft.disposition || ""} onChange={e => setDraft({ ...draft, disposition: e.target.value as EvidenceFilters["disposition"] })}><option value="">All dispositions</option>{["supporting", "contradicting", "background", "rejected"].map(value => <option key={value} value={value}>{value}</option>)}</select></label>
        {([['session_key', 'Session'], ['mission_id', 'Mission ID'], ['tag', 'Tag'], ['created_from', 'From date (UTC)'], ['created_until', 'Through date (UTC)']] as const).map(([key, label]) => <label key={key} className="form-label">{label}<input type={key.startsWith('created_') ? 'date' : 'text'} className="form-input mt-2" value={draft[key] || ""} onChange={e => setDraft({ ...draft, [key]: e.target.value })} /></label>)}
      </div>
      {(filters.source_id || filters.report_id || filters.document_id) && <p className="text-sm text-secondary">Scoped to the linked {filters.source_id ? "source" : filters.report_id ? "report" : "document"}. Clear filters to browse the whole project.</p>}
      <div className="flex flex-wrap gap-3"><button className="rounded bg-accent px-4 py-2 text-on-accent" type="submit">Apply filters</button><button className="rounded border border-line px-4 py-2" type="button" onClick={() => { setFilters({}); setDraft({}); setQuery(""); setDraftQuery(""); setPage(1); }}>Clear filters</button></div>
    </form>}
    {error && <div role="alert" className="rounded-lg bg-danger-surface p-4 text-danger"><p className="break-words">{error instanceof Error ? error.message : "Unable to load evidence."}</p><button className="mt-2 underline" onClick={() => { void projects.mutate(); void ledger.mutate(); }}>Retry</button></div>}
    {!projectId && <p className="text-secondary">Choose a project to browse its evidence ledger.</p>}
    {ledger.isLoading && <p role="status">Loading evidence…</p>}
    {ledger.data && <section aria-label="Evidence entries" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3"><p className="text-sm text-muted">{ledger.data.entry_total} evidence entries</p><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={grouped} onChange={e => setGrouped(e.target.checked)} />Group this page by source</label></div>
      {Array.from(groups, ([key, entries]) => <div key={key} className="space-y-4">{grouped && <h2 className="break-all text-lg font-semibold">{sourceDomain(entries[0].source_url)} <span className="text-sm font-normal text-secondary">· {entries.length} on this page</span></h2>}{entries.map(entry => <EntryCard key={entry.id} entry={entry} />)}</div>)}
      {ledger.data.entry_total === 0 && <p>No evidence matches these filters.</p>}
      {ledger.data.entry_total > ledger.data.page_size && <nav aria-label="Evidence pages" className="flex flex-wrap items-center gap-3 text-sm"><button disabled={page === 1} onClick={() => setPage(page - 1)} className="rounded border border-line px-3 py-2 disabled:opacity-50">Previous</button><span>Page {page} of {Math.ceil(ledger.data.entry_total / ledger.data.page_size)}</span><button disabled={page * ledger.data.page_size >= ledger.data.entry_total} onClick={() => setPage(page + 1)} className="rounded border border-line px-3 py-2 disabled:opacity-50">Next</button></nav>}
    </section>}
    {projectId && filters.session_key && <SessionNotes key={`${projectId}:${filters.session_key}`} projectId={projectId} sessionKey={filters.session_key} />}
  </div>;
}
