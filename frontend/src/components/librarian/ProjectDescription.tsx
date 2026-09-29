import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import useSWR from "swr";

import { descriptionApi, type DescriptionCitation, type DescriptionProposal } from "@/lib/api/librarian-descriptions";

const button = "rounded-lg border border-line-strong px-4 py-2 text-sm font-semibold disabled:opacity-60";
const storageKey = (userId: string, projectId: string) => `tracelab.librarian.description.v1:${userId}:${projectId}`;

function Sources({ citations }: { citations: DescriptionCitation[] }) {
  return <ul className="space-y-2 text-sm" aria-label="Description sources">
    {citations.map((citation) => <li key={citation.marker}>
      {citation.available && citation.href
        ? <Link className="text-accent-text underline" href={citation.href}>[{citation.marker}] {citation.excerpt || "Open source"}</Link>
        : <span className="text-muted">[{citation.marker}] Source no longer available</span>}
    </li>)}
  </ul>;
}

/** The parent keys this panel by user and project so in-flight results stay with their owner. */
export function ProjectDescription({ userId, projectId, projectName }: { userId: string; projectId: string; projectName: string }) {
  const state = useSWR(["librarian-description", userId, projectId], () => descriptionApi.state(projectId));
  const [prompt, setPrompt] = useState("");
  const [proposal, setProposal] = useState<DescriptionProposal | null>(null);
  const [edited, setEdited] = useState("");
  const [restored, setRestored] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const review = useRef<HTMLElement>(null);
  const focusReview = useRef(false);
  const active = useRef(true);
  const locked = useRef(false);
  const key = storageKey(userId, projectId);

  useEffect(() => {
    active.current = true;
    try {
      const saved = JSON.parse(localStorage.getItem(key) || "null");
      if (saved?.proposal?.project_id === projectId && typeof saved.proposal.proposal_token === "string" && typeof saved.edited === "string") {
        setProposal(saved.proposal);
        setEdited(saved.edited);
        setPrompt(saved.proposal.prompt);
      }
    } catch { /* A blocked or stale store must not prevent a fresh draft. */ }
    setRestored(true);
    return () => { active.current = false; };
  }, [key, projectId]);

  useEffect(() => {
    if (!restored) return;
    try {
      if (proposal) localStorage.setItem(key, JSON.stringify({ proposal, edited }));
      else localStorage.removeItem(key);
    } catch { /* Without storage, review is available for this visit. */ }
  }, [restored, key, proposal, edited]);

  useEffect(() => {
    if (proposal && focusReview.current) {
      focusReview.current = false;
      review.current?.focus();
    }
  }, [proposal]);

  async function run(action: "draft" | "accept" | "restore") {
    if (locked.current) return;
    locked.current = true;
    setBusy(true); setError(""); setNotice("");
    try {
      if (action === "draft") {
        const result = await descriptionApi.draft(projectId, prompt);
        if (!active.current) return;
        focusReview.current = true;
        setProposal(result); setEdited(result.description);
        setNotice("Draft ready. Review and edit it before accepting.");
      } else {
        const result = action === "accept" && proposal
          ? await descriptionApi.accept(projectId, proposal.proposal_token, edited)
          : await descriptionApi.restore(projectId, state.data!.provenance!.proposal_id);
        if (!active.current) return;
        await state.mutate(result, false);
        if (action === "accept") setProposal(null);
        setNotice(action === "accept" ? "Description accepted." : "Previous description restored.");
      }
    } catch (err) {
      if (active.current) {
        setError(err instanceof Error ? err.message : "The description could not be updated. Try again.");
        void state.mutate();
      }
    } finally {
      locked.current = false;
      if (active.current) setBusy(false);
    }
  }

  const provenance = state.data?.provenance;
  return <section className="panel space-y-4 p-5" aria-label="Project description">
    <header>
      <h2 className="text-lg font-semibold">Describe {projectName}</h2>
      <p className="text-sm text-secondary">Draft from this project&apos;s readable material or your planning brief. You review every change.</p>
    </header>
    {state.error && <p role="alert" className="text-danger">Description could not load. <button className="underline" onClick={() => void state.mutate()}>Retry</button></p>}
    <div>
      <h3 className="text-sm font-semibold">Current description</h3>
      <p className="whitespace-pre-wrap break-words text-secondary">{state.isLoading ? "Loading…" : state.data?.description || "No description yet."}</p>
      {provenance?.current && <p className="mt-2 text-sm text-secondary">Machine drafted · Human accepted{provenance.edited ? " with edits" : ""} · {new Date(provenance.accepted_at).toLocaleString()} · {provenance.model}</p>}
      {provenance?.current && provenance.basis === "planning_brief" && <p className="text-sm text-secondary">Based on the planning brief; no corpus evidence was supplied.</p>}
      {provenance?.current && <Sources citations={provenance.citations} />}
      {provenance && !provenance.current && <p className="mt-2 text-sm text-secondary">{provenance.restored_at ? "Previous description restored." : "The description was edited after acceptance."}</p>}
      {provenance && !provenance.current && <details className="mt-2 space-y-2 text-sm">
        <summary className="cursor-pointer">Last accepted draft and sources</summary>
        <p className="whitespace-pre-wrap break-words text-secondary">{provenance.accepted_value}</p>
        <p className="whitespace-pre-wrap break-words text-secondary">Brief: {provenance.prompt}</p>
        <Sources citations={provenance.citations} />
      </details>}
      {state.data?.can_restore && <div className="mt-3 space-y-2">
        <details><summary className="cursor-pointer text-sm">Previous description and drafting context</summary>
          <p className="whitespace-pre-wrap break-words text-sm text-secondary">{provenance?.previous_value || "No previous description."}</p>
          <p className="mt-2 whitespace-pre-wrap break-words text-sm text-secondary">Brief: {provenance?.prompt}</p>
        </details>
        <button className={button} disabled={busy} onClick={() => void run("restore")}>Restore previous description</button>
      </div>}
    </div>
    <form className="space-y-2" onSubmit={(event) => { event.preventDefault(); void run("draft"); }}>
      <label className="form-label" htmlFor="description-brief">What should the description explain?</label>
      <textarea id="description-brief" className="form-input w-full" rows={3} maxLength={4000} value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="Purpose, audience and questions this project explores…" />
      <p className="text-xs text-secondary">Reads up to 12 chunks and 24,000 characters. Empty or overlong chunks are excluded. Drafts expire after 7 days.</p>
      <button className={button} disabled={busy || !prompt.trim() || !state.data} type="submit">{busy ? "Working…" : proposal ? "Draft again" : "Draft description"}</button>
    </form>
    {proposal && <section ref={review} tabIndex={-1} className="space-y-3 rounded-lg border border-line p-4 focus-visible:ring-2 focus-visible:ring-focus" aria-label="Review description">
      <h3 className="font-semibold">Review proposed description</h3>
      <p className="text-sm text-secondary">{proposal.basis === "planning_brief" ? "Based on your planning brief; no corpus evidence was supplied." : `Based on ${proposal.coverage.used_chunks} of ${proposal.coverage.readable_chunks} readable chunks.`} {proposal.coverage.excluded_chunks > 0 && `${proposal.coverage.excluded_chunks} empty or overlong chunks excluded.`} {proposal.coverage.limited && "The context limit was reached; this is a partial view."}</p>
      <p className="whitespace-pre-wrap break-words text-sm text-secondary">Brief: {proposal.prompt}</p>
      <label className="form-label" htmlFor="description-proposal">Proposed description (editable)</label>
      <textarea id="description-proposal" className="form-input w-full" rows={5} maxLength={6000} value={edited} onChange={(event) => setEdited(event.target.value)} />
      <Sources citations={proposal.citations} />
      {proposal.basis === "corpus" && <p className="text-xs text-secondary">Keep supporting citation markers in each paragraph when editing.</p>}
      <div className="flex flex-wrap gap-3">
        <button className={`${button} bg-accent text-on-accent`} disabled={busy || !edited.trim()} onClick={() => void run("accept")}>Accept description</button>
        <button className={button} disabled={busy} onClick={() => { setProposal(null); setNotice("Draft dismissed. The project description is unchanged."); }}>Dismiss draft</button>
      </div>
    </section>}
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    {notice && <p role="status" className="text-sm text-secondary">{notice}</p>}
  </section>;
}
