import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { useAuth } from "@/contexts/AuthContext";
import { Dialog } from "@/components/ui/Dialog";
import { evidenceApi, type PromotionResult } from "@/lib/api/evidence";

export function SessionNotes({ projectId, sessionKey }: { projectId: string; sessionKey: string }) {
  const { user } = useAuth();
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PromotionResult | null>(null);
  const [title, setTitle] = useState("");
  const [target, setTarget] = useState<"report" | "document">("report");
  const notes = useSWR(["ledger-notes", user?.user_id, projectId, sessionKey, page], () => evidenceApi.list(projectId, page, { session_key: sessionKey }));
  async function promote() {
    setBusy(true); setError(null);
    try { setResult(await evidenceApi.promote({ project_id: projectId, session_key: sessionKey, target, title: title.trim() || undefined })); setOpen(false); }
    catch (e) { setError(e instanceof Error ? e.message : "Promotion failed. Try again."); }
    finally { setBusy(false); }
  }
  return <section className="panel space-y-4 p-5" aria-label="Session working notes">
    <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-lg font-semibold">Working notes</h2><button type="button" className="rounded border border-line px-3 py-2 text-sm" onClick={() => { setError(null); setOpen(true); }}>Promote session</button></div>
    <p className="break-words text-sm text-secondary">Session: {sessionKey}</p>
    {notes.isLoading && <p role="status">Loading notes…</p>}
    {notes.error && <p role="alert">Unable to load working notes. <button className="underline" onClick={() => void notes.mutate()}>Retry notes</button></p>}
    {notes.data?.note_total === 0 && <p className="text-secondary">No working notes for this session.</p>}
    {notes.data?.notes.map(note => <article key={note.id} className="space-y-2 border-t border-line pt-3"><h3 className="break-words font-medium">{note.note_key}</h3><p className="whitespace-pre-wrap break-words text-secondary">{note.content}</p></article>)}
    {notes.data && notes.data.note_total > notes.data.page_size && <nav className="flex flex-wrap gap-3" aria-label="Working note pages"><button disabled={page === 1} onClick={() => setPage(page - 1)}>Previous notes</button><span>Page {page} of {Math.ceil(notes.data.note_total / notes.data.page_size)}</span><button disabled={page * notes.data.page_size >= notes.data.note_total} onClick={() => setPage(page + 1)}>Next notes</button></nav>}
    {result && <p role="status">Promoted {result.entry_count} evidence entries and {result.note_count} notes to <Link className="text-accent-text underline" href={result.document_id ? `/documents/${result.document_id}` : `/reports/${result.report_id}`}>{result.title}</Link>.</p>}
    <Dialog open={open} title="Promote evidence session" onClose={() => { if (!busy) setOpen(false); }}>
      <p className="mb-4 text-secondary">Create a new artifact from all evidence and notes in this session, including findings hidden by your current filters. Each promotion creates a new report; a document is also indexed for search.</p>
      <label className="form-label">Title (optional)<input className="form-input mb-4 mt-2" value={title} maxLength={255} onChange={e => setTitle(e.target.value)} /></label>
      <label className="form-label">Create<select className="form-input mb-4 mt-2" value={target} onChange={e => setTarget(e.target.value as "report" | "document")}><option value="report">Report</option><option value="document">Searchable document and report</option></select></label>
      {error && <p role="alert" className="mb-3 break-words text-danger">{error}</p>}
      <div className="flex gap-3"><button disabled={busy} className="rounded border border-line px-3 py-2" onClick={() => setOpen(false)}>Cancel</button><button disabled={busy} className="rounded bg-accent px-3 py-2 text-on-accent" onClick={() => void promote()}>{busy ? "Creating…" : "Create artifact"}</button></div>
    </Dialog>
  </section>;
}
