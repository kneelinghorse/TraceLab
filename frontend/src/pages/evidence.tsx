import { useState } from "react";
import useSWR from "swr";
import { useRouter } from "next/router";

import { AuthGate } from "@/components/AuthGate";
import { evidenceApi } from "@/lib/api/evidence";
import { projectsApi } from "@/lib/api/projects";

export default function EvidencePage() {
  return <AuthGate><EvidenceBrowser /></AuthGate>;
}

function EvidenceBrowser() {
  const router = useRouter();
  const [selectedProject, setProjectId] = useState<string | null>(null);
  const projectId = selectedProject ?? (typeof router.query.project_id === "string" ? router.query.project_id : "");
  const missionId = selectedProject === null && typeof router.query.mission_id === "string" ? router.query.mission_id : undefined;
  const sessionKey = selectedProject === null && typeof router.query.session_key === "string" ? router.query.session_key : undefined;
  const [projectSearch, setProjectSearch] = useState("");
  const [projectPage, setProjectPage] = useState(1);
  const [page, setPage] = useState(1);
  const projects = useSWR(["evidence-projects", projectSearch, projectPage], () => projectsApi.listProjects({ search: projectSearch.trim() || undefined, page: projectPage, pageSize: 20 }));
  const ledger = useSWR(projectId ? ["evidence", projectId, missionId, sessionKey, page] : null, () => evidenceApi.list(projectId, page, { mission_id: missionId, session_key: sessionKey }));
  const error = projects.error || ledger.error;

  return <div className="mx-auto max-w-6xl space-y-6 px-4 py-8 sm:px-6">
    <header><h1 className="text-3xl font-semibold">Evidence</h1><p className="mt-2 text-secondary">Sourced claims and research context, organized by project.</p></header>
    {(missionId || sessionKey) && <p className="break-words text-sm text-secondary">Showing evidence for {sessionKey ? `session ${sessionKey}` : "the selected mission"}. Choose a project below to browse without these filters.</p>}
    <section className="panel space-y-4 p-5" aria-label="Choose a project">
      <label className="form-label">Find a project<input className="form-input mt-2" value={projectSearch} onChange={(event) => { setProjectSearch(event.target.value); setProjectPage(1); }} placeholder="Search project names" /></label>
      <label className="form-label">Project<select aria-label="Project" className="form-input mt-2" value={projectId} onChange={(event) => { setProjectId(event.target.value); setPage(1); }}>
        <option value="">Select a project</option>
        {projectId && !projects.data?.data.some((project) => project.id === projectId) && <option value={projectId}>Selected project</option>}
        {projects.data?.data.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
      </select></label>
      {projects.isLoading && <p role="status" className="text-sm text-muted">Loading projects…</p>}
      {projects.data && projects.data.pagination.pages > 1 && <div className="flex flex-wrap items-center gap-3 text-sm">
        <button type="button" disabled={projectPage === 1} onClick={() => setProjectPage(projectPage - 1)} className="rounded border border-line px-3 py-2 disabled:opacity-50">Previous projects</button>
        <span>Page {projectPage} of {projects.data.pagination.pages}</span>
        <button type="button" disabled={projectPage >= projects.data.pagination.pages} onClick={() => setProjectPage(projectPage + 1)} className="rounded border border-line px-3 py-2 disabled:opacity-50">Next projects</button>
      </div>}
    </section>
    {error && <p role="alert" className="rounded-lg bg-danger-surface p-4 text-danger">{error instanceof Error ? error.message : "Unable to load evidence."}</p>}
    {!projectId && <p className="text-secondary">Choose a project to browse its evidence ledger.</p>}
    {ledger.isLoading && <p role="status">Loading evidence…</p>}
    {ledger.data && <section aria-label="Evidence entries" className="space-y-4">
      <p className="text-sm text-muted">{ledger.data.entry_total} evidence entries</p>
      {ledger.data.entries.map((entry) => <article key={entry.id} className="panel space-y-3 p-5">
        <div className="flex flex-wrap items-center gap-2 text-xs text-secondary"><span className="rounded-full bg-surface-alt px-2 py-1">{entry.disposition}</span><time dateTime={entry.created_at}>{new Date(entry.created_at).toLocaleDateString()}</time></div>
        <h2 className="text-lg font-medium">{entry.claim}</h2>
        {entry.summary && <p className="text-secondary">{entry.summary}</p>}
        <a href={entry.source_url} target="_blank" rel="noreferrer" className="block break-all text-sm text-accent-text underline underline-offset-4">{entry.source_url}<span className="sr-only"> (opens in a new tab)</span></a>
        <p className="text-xs text-muted">Session: {entry.session_key} · Sightings: {entry.source_sighting_count}</p>
      </article>)}
      {ledger.data.entry_total === 0 && <p>No evidence has been captured in this project yet.</p>}
      {ledger.data.entry_total > ledger.data.page_size && <nav aria-label="Evidence pages" className="flex flex-wrap items-center gap-3 text-sm">
        <button type="button" disabled={page === 1} onClick={() => setPage(page - 1)} className="rounded border border-line px-3 py-2 disabled:opacity-50">Previous</button>
        <span>Page {page} of {Math.ceil(ledger.data.entry_total / ledger.data.page_size)}</span>
        <button type="button" disabled={page * ledger.data.page_size >= ledger.data.entry_total} onClick={() => setPage(page + 1)} className="rounded border border-line px-3 py-2 disabled:opacity-50">Next</button>
      </nav>}
    </section>}
  </div>;
}
