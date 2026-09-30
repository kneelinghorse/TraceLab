import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { MarkdownRenderer } from "@/components/MarkdownRenderer";
import { collectionsApi, type CollectionListResponse } from "@/lib/api/collections";
import { librarianReportsApi, type ReportFormat, type ReportInputs, type ReportPreview, type SavedReport } from "@/lib/api/librarian-reports";

const button = "rounded-lg border border-line-strong px-4 py-2 text-sm font-semibold disabled:opacity-60";
type State = { title: string; prompt: string; format: ReportFormat; collectionId: string; sources: ReportInputs | null; selected: string[]; reviewed: boolean; preview: ReportPreview | null; saved: SavedReport | null };
const initial: State = { title: "", prompt: "", format: "summary", collectionId: "", sources: null, selected: [], reviewed: false, preview: null, saved: null };

/** The page mounts a fresh keyed panel for every caller/project identity. */
export function ReportDraft({ userId, projectId, projectName }: { userId: string; projectId: string; projectName: string }) {
  const key = `tracelab.librarian.reports.v1:${userId}:${projectId}`;
  const [state, setState] = useState<State>(initial);
  const [restored, setRestored] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [collections, setCollections] = useState<CollectionListResponse | null>(null);
  const [collectionPage, setCollectionPage] = useState(1);
  const active = useRef(true);
  const locked = useRef(false);
  const focusPreview = useRef(false);
  const previewRegion = useRef<HTMLElement>(null);
  useEffect(() => {
    active.current = true;
    try {
      const saved = JSON.parse(localStorage.getItem(key) || "null");
      if (saved && typeof saved.title === "string" && typeof saved.prompt === "string" && Array.isArray(saved.selected)
        && (saved.sources?.project_id === projectId || !saved.sources) && (saved.preview?.project_id === projectId || !saved.preview)) setState(saved);
    } catch { /* A corrupt draft must not prevent a fresh review. */ }
    setRestored(true);
    return () => { active.current = false; };
  }, [key, projectId]);
  useEffect(() => {
    if (!restored) return;
    try { localStorage.setItem(key, JSON.stringify(state)); } catch { /* Explicit review still works for this visit. */ }
  }, [restored, key, state]);
  useEffect(() => {
    if (state.preview && focusPreview.current) { focusPreview.current = false; previewRegion.current?.focus(); }
  }, [state.preview]);
  function edit(change: Partial<State>) { setState(current => ({ ...current, ...change })); }
  async function run(action: () => Promise<void>) {
    if (locked.current) return;
    locked.current = true; setBusy(true); setError(""); setNotice("");
    try { await action(); }
    catch (failure) { if (active.current) setError(failure instanceof Error ? failure.message : "The request failed. Your reviewed draft is retained; retry without regenerating."); }
    finally { locked.current = false; if (active.current) setBusy(false); }
  }
  async function loadCollections(page = 1) {
    await run(async () => {
      const result = await collectionsApi.list({ project_id: projectId, page, page_size: 20 });
      if (active.current) { setCollections(result); setCollectionPage(page); }
    });
  }
  async function loadSources() {
    await run(async () => {
      const sources = await librarianReportsApi.sources(projectId, state.collectionId || undefined);
      if (active.current) {
        edit({ sources, selected: [], reviewed: false, preview: null, saved: null });
        setNotice("Choose the excerpts to read. Loading sources does not generate or save a report.");
      }
    });
  }
  async function generate() {
    if (!state.sources || !canDraft) return;
    const sourceToken = state.sources.source_token;
    await run(async () => {
      // Once a new request starts, an older preview cannot be mistaken for it.
      edit({ preview: null, saved: null });
      const preview = await librarianReportsApi.draft({ project_id: projectId, source_token: sourceToken, chunk_ids: state.selected,
        reviewed_sources: true, title: state.title.trim(), prompt: state.prompt.trim(), format: state.format });
      if (active.current) { focusPreview.current = true; edit({ preview }); setNotice("Draft ready. Review its content and citations before saving."); }
    });
  }
  async function save() {
    if (!state.preview || changed) return;
    const token = state.preview.proposal_token;
    await run(async () => {
      const saved = await librarianReportsApi.accept(projectId, token);
      if (active.current) { edit({ saved }); setNotice("Reviewed report saved. No new generation was needed."); }
    });
  }
  const sources = state.sources;
  const selected = sources?.members.filter(member => state.selected.includes(member.chunk_id)) ?? [];
  const characters = selected.reduce((total, member) => total + member.characters, 0);
  const canDraft = Boolean(sources && state.reviewed && selected.length > 0 && selected.length <= sources.coverage.chunk_limit && characters <= sources.coverage.character_limit && state.title.trim() && state.prompt.trim());
  const preview = state.preview;
  const changed = Boolean(preview && (preview.title !== state.title.trim() || preview.prompt !== state.prompt.trim() || preview.format !== state.format || JSON.stringify(preview.input_chunk_ids) !== JSON.stringify(state.selected)));

  return <section aria-label="Draft a report" className="panel min-w-0 space-y-4 p-5">
    <header><h2 className="break-words text-lg font-semibold">Report from {projectName}</h2>
      <p className="text-sm text-secondary">Choose existing excerpts, review a cited draft, then save it as a Report.</p></header>
    <div className="space-y-2">
      <label className="form-label" htmlFor="report-title">Report title</label>
      <input id="report-title" className="form-input w-full" maxLength={255} disabled={busy} value={state.title} onChange={event => edit({ title: event.target.value })} />
      <label className="form-label" htmlFor="report-prompt">What should the report explain?</label>
      <textarea id="report-prompt" className="form-input w-full" rows={2} maxLength={4000} disabled={busy} value={state.prompt} onChange={event => edit({ prompt: event.target.value })} />
      <label className="form-label" htmlFor="report-format">Report format</label>
      <select id="report-format" className="form-input w-full" value={state.format} disabled={busy} onChange={event => edit({ format: event.target.value as ReportFormat })}>
        <option value="summary">Summary</option><option value="report">Report</option><option value="bullets">Bullet points</option><option value="markdown">Markdown</option>
      </select>
      <div className="flex flex-wrap gap-2"><button className={button} disabled={busy} onClick={() => void loadCollections()}>Browse collections</button></div>
      <label className="form-label" htmlFor="report-source-set">Report source set</label>
      <select id="report-source-set" className="form-input w-full" disabled={busy} value={state.collectionId} onChange={event => edit({ collectionId: event.target.value, sources: null, selected: [], reviewed: false, preview: null, saved: null })}>
        <option value="">Project excerpts</option>
        {state.collectionId && !collections?.data.some(c => c.id === state.collectionId) && <option value={state.collectionId}>{sources?.collection_name || "Selected collection"}</option>}
        {collections?.data.map(collection => <option key={collection.id} value={collection.id}>{collection.name}</option>)}
      </select>
      {collections && <div className="flex flex-wrap items-center gap-2 text-sm"><span>{collections.total} readable collections with context in this project · Page {collectionPage}</span>
        <button className={button} disabled={busy || collectionPage === 1} onClick={() => void loadCollections(collectionPage - 1)}>Previous collections</button>
        <button className={button} disabled={busy || collectionPage * 20 >= collections.total} onClick={() => void loadCollections(collectionPage + 1)}>Next collections</button>
      </div>}
      <button className={button} disabled={busy} onClick={() => void loadSources()}>Load excerpts for review</button>
    </div>
    {sources && <section aria-label="Review report inputs" className="min-w-0 space-y-3 rounded-lg border border-line p-4">
      <h3 className="font-semibold">Review report inputs</h3>
      <p className="text-sm text-secondary">Showing {sources.coverage.listed_chunks} of {sources.coverage.eligible_chunks} eligible excerpts in {projectName}. {sources.coverage.excluded_chunks} empty or overlong excerpts excluded. {sources.coverage.other_project_chunks} readable excerpts from other projects excluded. {sources.coverage.limited && `Only the first ${sources.coverage.candidate_limit} eligible excerpts are listed.`} Only saved excerpts are used; whole-document membership is not expanded.</p>
      <p className="text-sm font-semibold">{selected.length} of {sources.coverage.chunk_limit} excerpts · {characters.toLocaleString()} of {sources.coverage.character_limit.toLocaleString()} characters selected. Each excerpt is at most 4,000 characters.</p>
      {sources.members.length === 0 && <p className="text-sm text-secondary">No eligible excerpts. Choose another source set or process source documents first.</p>}
      <ol className="max-h-96 space-y-3 overflow-y-auto p-1">{sources.members.map(member => <li className="min-w-0 space-y-1" key={member.chunk_id}>
        <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" disabled={busy} checked={state.selected.includes(member.chunk_id)} aria-label={`Use report excerpt ${member.marker}`} onChange={event => {
          const ids = new Set(state.selected); if (event.target.checked) ids.add(member.chunk_id); else ids.delete(member.chunk_id);
          edit({ selected: sources.members.filter(item => ids.has(item.chunk_id)).map(item => item.chunk_id), reviewed: false });
        }} /><span className="min-w-0 break-words">[{member.marker}] {member.document_name} · {member.characters.toLocaleString()} characters</span></label>
        <details className="text-sm"><summary className="cursor-pointer">Read supplied excerpt [{member.marker}]</summary><p className="whitespace-pre-wrap break-words text-secondary">{member.text}</p></details>
        <Link className="text-sm text-accent-text underline" href={member.href}>Open input excerpt [{member.marker}]</Link>
      </li>)}</ol>
      <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" disabled={busy || selected.length === 0} checked={state.reviewed} onChange={event => edit({ reviewed: event.target.checked })} /><span>I reviewed the selected excerpts from {projectName}.</span></label>
      <p className="text-xs text-secondary">Drafts expire after 7 days. Generation reads only the selected text; exceeding a limit requires removing excerpts.</p>
      <button className={button} disabled={busy || !canDraft} onClick={() => void generate()}>{busy ? "Working…" : preview ? "Draft report again" : "Draft cited report"}</button>
    </section>}
    {preview && <section ref={previewRegion} tabIndex={-1} aria-label="Review report draft" className="min-w-0 space-y-4 rounded-lg border border-line p-4 focus-visible:ring-2 focus-visible:ring-focus">
      <h3 className="break-words font-semibold">{preview.title}</h3>
      <p className="whitespace-pre-wrap break-words text-sm text-secondary">Draft request: {preview.prompt} · {preview.format} · {preview.model}</p>
      <MarkdownRenderer content={preview.content} />
      <ul className="space-y-2 text-sm">{preview.citations.map(citation => <li key={citation.marker}>{citation.available && citation.href ? <Link className="text-accent-text underline" href={citation.href}>[{citation.marker}] Open report source excerpt</Link> : <span>Source [{citation.marker}] unavailable</span>}</li>)}</ul>
      <p className="text-xs text-secondary">Saving retains this exact content and citation mapping as a draft Report owned by you in {projectName}. Existing project access applies. No new generation occurs.</p>
      {state.saved ? <p role="status" className="text-sm"><Link className="text-accent-text underline" href={state.saved.href}>{state.saved.title}</Link> · Machine drafted · Human accepted</p> : <>
        {changed && <p className="text-sm text-secondary">Inputs changed. Generate a new draft before saving.</p>}
        <div className="flex flex-wrap gap-2"><button className={`${button} bg-accent text-on-accent`} disabled={busy || changed} onClick={() => void save()}>Save reviewed report</button>
          <button className={button} disabled={busy} onClick={() => { edit({ preview: null, saved: null }); setNotice("Draft dismissed. No report was saved."); }}>Dismiss report draft</button></div>
      </>}
    </section>}
    {error && <p role="alert" className="break-words text-sm text-danger">{error}</p>}
    {notice && <p role="status" className="text-sm text-secondary">{notice}</p>}
  </section>;
}
