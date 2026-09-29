import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import useSWR from "swr";

import { organisationApi, type AcceptedCollection, type CollectionSuggestions as Suggestions } from "@/lib/api/librarian-collections";

const button = "rounded-lg border border-line-strong px-4 py-2 text-sm font-semibold disabled:opacity-60";
type Review = { name: string; description: string; memberIds: string[]; dismissed: boolean; saved?: AcceptedCollection };
type DraftState = { proposal: Suggestions; reviews: Record<string, Review> };

/** Caller/project keys isolate drafts and late responses, as in the description panel. */
export function CollectionSuggestions({ userId, projectId, projectName }: { userId: string; projectId: string; projectName: string }) {
  const key = `tracelab.librarian.collections.v1:${userId}:${projectId}`;
  const [prompt, setPrompt] = useState("");
  const [draft, setDraft] = useState<DraftState | null>(null);
  const [restored, setRestored] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const active = useRef(true);
  const locked = useRef(false);
  const focusReview = useRef(false);
  const reviewRegion = useRef<HTMLElement>(null);

  useEffect(() => {
    active.current = true;
    try {
      const saved = JSON.parse(localStorage.getItem(key) || "null");
      if (saved?.proposal?.project_id === projectId && Array.isArray(saved.proposal.groups) && saved.reviews) {
        setDraft(saved); setPrompt(saved.proposal.prompt);
      }
    } catch { /* A stale store does not prevent a fresh request. */ }
    setRestored(true);
    return () => { active.current = false; };
  }, [key, projectId]);
  useEffect(() => {
    if (!restored) return;
    try {
      if (draft) localStorage.setItem(key, JSON.stringify(draft));
      else localStorage.removeItem(key);
    } catch { /* This visit still supports explicit review if storage is blocked. */ }
  }, [restored, key, draft]);
  useEffect(() => {
    if (draft && focusReview.current) {
      focusReview.current = false; reviewRegion.current?.focus();
    }
  }, [draft]);

  function edit(groupId: string, change: Partial<Review>) {
    setDraft(current => current ? { ...current, reviews: { ...current.reviews, [groupId]: { ...current.reviews[groupId], ...change } } } : current);
  }
  async function generate() {
    if (locked.current || !prompt.trim()) return;
    locked.current = true; setBusy(true); setError(""); setNotice("");
    try {
      const proposal = await organisationApi.draft(projectId, prompt);
      if (!active.current) return;
      focusReview.current = true;
      setDraft({ proposal, reviews: Object.fromEntries(proposal.groups.map(group => [group.group_id, {
        name: group.name, description: group.description, memberIds: group.members.map(member => member.chunk_id), dismissed: false,
      }])) });
      setNotice("Groups ready. Review their names and excerpts, then accept each collection separately.");
    } catch (failure) {
      if (active.current) setError(failure instanceof Error ? failure.message : "Groups could not be suggested. Try again.");
    } finally {
      locked.current = false; if (active.current) setBusy(false);
    }
  }
  async function accept(groupId: string) {
    if (locked.current || !draft) return;
    const group = draft.proposal.groups.find(item => item.group_id === groupId)!;
    const reviewed = draft.reviews[groupId];
    locked.current = true; setBusy(true); setError(""); setNotice("");
    try {
      const result = await organisationApi.accept(projectId, group.proposal_token, reviewed.name.trim(), reviewed.description.trim(), reviewed.memberIds);
      if (!active.current) return;
      edit(groupId, { saved: result });
      setNotice(result.state === "saved" ? "Reviewed collection saved." : result.state === "changed" ? "The collection has changed. Open it to review the current members." : "The collection was created, but saving is incomplete. Retry uses the same collection.");
    } catch (failure) {
      if (active.current) setError(failure instanceof Error ? failure.message : "The group could not be saved. Retry without regenerating.");
    } finally {
      locked.current = false; if (active.current) setBusy(false);
    }
  }

  const coverage = draft?.proposal.coverage;
  return <section className="panel min-w-0 space-y-4 p-5" aria-label="Organise research">
    <header>
      <h2 className="break-words text-lg font-semibold">Organise {projectName}</h2>
      <p className="text-sm text-secondary">Suggest collections of existing excerpts. Review exact members and save each group you choose.</p>
    </header>
    <form className="space-y-2" onSubmit={event => { event.preventDefault(); void generate(); }}>
      <label htmlFor="organisation-goal" className="form-label">How should the research be organised?</label>
      <textarea id="organisation-goal" className="form-input w-full" rows={2} maxLength={4000} value={prompt} onChange={event => setPrompt(event.target.value)} placeholder="Group feedback by pain point…" />
      <p className="text-xs text-secondary">Reads up to 20 excerpts and 24,000 characters. Empty or overlong excerpts and documents without eligible chunks are excluded. Suggestions expire after 7 days.</p>
      <button type="submit" className={button} disabled={busy || !prompt.trim()}>{busy ? "Working…" : draft ? "Suggest groups again" : "Suggest collections"}</button>
    </form>
    {draft && coverage && <section ref={reviewRegion} tabIndex={-1} className="min-w-0 space-y-4 rounded-lg border border-line p-4 focus-visible:ring-2 focus-visible:ring-focus" aria-label="Review suggested collections">
      <h3 className="font-semibold">Review suggested collections</h3>
      <p className="whitespace-pre-wrap break-words text-sm text-secondary">Goal for these suggestions: {draft.proposal.prompt}</p>
      <p className="break-words text-sm text-secondary">Destination: {draft.proposal.destination.space_name} · Owned by you. Existing Space access applies; source permissions still apply.</p>
      <p className="text-sm text-secondary">Read {coverage.used_chunks} of {coverage.readable_chunks} excerpts from {coverage.used_documents} of {coverage.readable_documents} readable documents. {coverage.readable_documents - coverage.documents_with_eligible_chunks} documents have no eligible excerpts. {coverage.excluded_chunks} empty or overlong excerpts excluded. {coverage.limited && "The context limit was reached; this is a partial sample."} Each collection can hold at most 100 excerpts.</p>
      {draft.proposal.groups.map((group, index) => {
        const value = draft.reviews[group.group_id];
        if (!value || value.dismissed) return null;
        const saved = value.saved;
        const frozen = busy || Boolean(saved);
        return <article key={group.group_id} className="min-w-0 space-y-3 rounded-lg border border-line p-4" aria-label={`Suggested collection ${index + 1}`}>
          <label className="form-label" htmlFor={`group-name-${group.group_id}`}>Collection name {index + 1}</label>
          <input id={`group-name-${group.group_id}`} className="form-input w-full" maxLength={255} disabled={frozen} value={value.name} onChange={event => edit(group.group_id, { name: event.target.value })} />
          <label className="form-label" htmlFor={`group-description-${group.group_id}`}>Collection description {index + 1}</label>
          <textarea id={`group-description-${group.group_id}`} className="form-input w-full" rows={2} maxLength={2000} disabled={frozen} value={value.description} onChange={event => edit(group.group_id, { description: event.target.value })} />
          <p className="whitespace-pre-wrap break-words text-sm text-secondary">Suggested rationale: {group.rationale}</p>
          <p className="text-xs text-secondary">The explanation describes the original suggestion. Only checked excerpts will be saved.</p>
          <p className="text-sm font-semibold">{value.memberIds.length} selected excerpts, in reading order</p>
          <ol className="space-y-3">
            {group.members.map(member => <li key={member.chunk_id} className="min-w-0 space-y-1">
              <label className="flex items-start gap-2 text-sm">
                <input className="mt-1" type="checkbox" disabled={frozen} checked={value.memberIds.includes(member.chunk_id)} aria-label={`Include excerpt ${member.marker} in collection ${index + 1}`} onChange={event => {
                  const selected = new Set(value.memberIds);
                  if (event.target.checked) selected.add(member.chunk_id); else selected.delete(member.chunk_id);
                  edit(group.group_id, { memberIds: group.members.filter(item => selected.has(item.chunk_id)).map(item => item.chunk_id) });
                }} />
                <span className="min-w-0 break-words">[{member.marker}] {member.document_name}</span>
              </label>
              <p className="whitespace-pre-wrap break-words text-sm text-secondary">{member.excerpt}</p>
              {member.href && <Link className="text-sm text-accent-text underline" href={member.href}>Open excerpt [{member.marker}]</Link>}
            </li>)}
          </ol>
          {saved && <div className="space-y-2 text-sm" role="status">
            <p><Link href={saved.href} className="text-accent-text underline">{saved.name}</Link>: {saved.completed_member_ids.length} of {value.memberIds.length} excerpts saved.</p>
            {saved.state === "saved" && <p>Machine suggested · Human accepted · {draft.proposal.model}</p>}
            {saved.state === "changed" && <p>Changed after acceptance. Review this collection directly; it will not be filled again.</p>}
            {saved.error && <p className="text-danger">{saved.error}</p>}
          </div>}
          <div className="flex flex-wrap gap-2">
            {(!saved || saved.state === "partial") && <button className={`${button} bg-accent text-on-accent`} disabled={busy || !value.name.trim() || value.memberIds.length === 0} onClick={() => void accept(group.group_id)}>{saved ? saved.missing_member_ids.length ? `Retry ${saved.missing_member_ids.length} missing excerpts` : "Recheck this collection" : "Accept this collection"}</button>}
            {!saved && <button className={button} disabled={busy} onClick={() => { edit(group.group_id, { dismissed: true }); setNotice("Group dismissed. No collection was created."); }}>Dismiss group</button>}
          </div>
        </article>;
      })}
      {draft.proposal.groups.every(group => draft.reviews[group.group_id]?.dismissed) && <p className="text-sm text-secondary">All groups dismissed. No collections were created.</p>}
    </section>}
    {error && <p role="alert" className="break-words text-sm text-danger">{error}</p>}
    {notice && <p role="status" className="text-sm text-secondary">{notice}</p>}
  </section>;
}

export function CollectionOrigin({ userId, collectionId }: { userId: string; collectionId: string }) {
  const state = useSWR(["collection-origin", userId, collectionId], () => organisationApi.provenance(collectionId));
  if (state.error) return <p className="text-sm text-danger" role="alert">Collection origin could not load. <button className="underline" onClick={() => void state.mutate()}>Retry</button></p>;
  const provenance = state.data?.provenance;
  if (!provenance) return null;
  return <section className="panel space-y-3 p-5" aria-label="Collection origin">
    <h2 className="font-semibold">Machine suggested · Human accepted</h2>
    <p className="text-sm text-secondary">{new Date(provenance.accepted_at).toLocaleString()} · {provenance.model} · {provenance.destination.space_name}</p>
    {!provenance.completed_at && <p className="text-sm text-secondary">The original save was incomplete. The collection shows its current members.</p>}
    {provenance.prompt && <p className="whitespace-pre-wrap break-words text-sm">Goal: {provenance.prompt}</p>}
    <details className="text-sm"><summary className="cursor-pointer">Originally accepted sources</summary>
      <ul className="mt-2 space-y-2">{provenance.members?.map(member => <li key={member.marker}>{member.available && member.href ? <Link className="text-accent-text underline" href={member.href}>[{member.marker}] {member.excerpt || "Open excerpt"}</Link> : <span className="text-muted">[{member.marker}] Source no longer available</span>}</li>)}</ul>
    </details>
  </section>;
}
