import { parseApiTimestamp } from "@/lib/api/timestamps";
import { RelationshipLink } from "@/components/graph/RelationshipLink";
import { PaginationBar } from "@/components/ui/PaginationBar";
import Link from "next/link";
import { useRouter } from "next/router";
import { useState } from "react";
import useSWR from "swr";
import { AuthGate } from "@/components/AuthGate";
import { EntryCard } from "@/components/evidence/EntryCard";
import { SessionNotes } from "@/components/evidence/SessionNotes";
import { useAuth } from "@/contexts/AuthContext";
import { evidenceApi, evidenceHref, sourceDomain } from "@/lib/api/evidence";

export default function EvidenceDetailPage() {
  const router = useRouter();
  const id = typeof router.query.id === "string" ? router.query.id : undefined;
  return <AuthGate>{id && <EvidenceDetail key={id} id={id} />}</AuthGate>;
}
function EvidenceDetail({ id }: { id: string }) {
  const { user } = useAuth();
  const [page, setPage] = useState(1);
  const detail = useSWR(["evidence-detail", user?.user_id, id], () => evidenceApi.get(id));
  const entry = detail.data?.entry;
  const sightings = useSWR(entry ? ["evidence-sightings", user?.user_id, entry.project_id, entry.source_id, page] : null, () => evidenceApi.list(entry!.project_id, page, { source_id: entry!.source_id }));
  return <div className="mx-auto max-w-4xl space-y-6 px-4 py-8 sm:px-6">
    <Link href={entry ? evidenceHref(entry.project_id) : "/evidence"} className="text-accent-text underline">← Evidence</Link>
    {detail.isLoading && <p role="status">Loading evidence…</p>}
    {detail.error && <div role="alert"><h1 className="text-xl font-semibold">Evidence unavailable</h1><p>This entry could not be loaded. It may have been removed, or you may not have access.</p><button className="text-accent-text underline" onClick={() => void detail.mutate()}>Retry entry</button></div>}
    {entry && <>
      <header className="space-y-3"><div className="flex flex-wrap gap-2 text-sm text-secondary"><span>{entry.disposition}</span><span>· {sourceDomain(entry.source_url)}</span></div><h1 className="break-words text-2xl font-semibold">{entry.claim}</h1><p className="text-sm text-muted">Captured {parseApiTimestamp(entry.created_at).toLocaleString()} · {entry.origin === "deepsearch-worker" ? "DeepSearch" : "Research agent"}</p>{detail.data!.links.filter(link => link.kind === "report" && link.mission_result).slice(0, 1).map(link => <p key={link.id}><Link className="text-sm text-accent-text underline underline-offset-4" href={link.href} title={link.title}>Open report</Link></p>)}<RelationshipLink type="evidence" id={entry.id} /></header>
      <section className="panel space-y-4 p-5" aria-label="Claim and source">
        {entry.summary && <div><h2 className="font-semibold">Summary</h2><p className="mt-2 whitespace-pre-wrap break-words text-secondary">{entry.summary}</p></div>}
        <div><h2 className="font-semibold">Source snippet</h2>{entry.snippet ? <blockquote className="mt-2 whitespace-pre-wrap break-words border-l-2 border-line-strong pl-4 text-secondary">{entry.snippet}</blockquote> : <p className="mt-2 text-muted">No snippet was captured.</p>}</div>
        <a href={entry.source_url} target="_blank" rel="noreferrer" className="block break-all text-accent-text underline">{entry.source_url}<span className="sr-only"> (opens in a new tab)</span></a>
        {entry.query && <p className="break-words text-sm text-secondary">Research query: {entry.query}</p>}
        <div className="flex flex-wrap gap-2">{entry.tags.map(tag => <Link href={evidenceHref(entry.project_id, { tag })} key={tag} className="rounded bg-surface-alt px-2 py-1 text-sm text-accent-text underline">{tag}</Link>)}</div>
      </section>
      <section className="panel space-y-3 p-5" aria-label="Evidence provenance"><h2 className="text-lg font-semibold">Provenance and outputs</h2><Link className="block break-words text-accent-text underline" href={evidenceHref(entry.project_id, { session_key: entry.session_key })}>Session: {entry.session_key}</Link>{detail.data!.links.map(link => <p key={`${link.kind}:${link.id}`}><Link className="break-words text-accent-text underline" href={link.href}>{link.title}</Link><span className="block text-xs text-secondary">{link.relationship}</span></p>)}{!detail.data!.links.length && <p className="text-secondary">No accessible mission or report relationship is recorded.</p>}</section>
      <section className="space-y-4" aria-label="Source sightings"><h2 className="text-xl font-semibold">Sightings of this source</h2><p className="text-sm text-secondary">Claims that cite the same canonical URL within this project.</p>{sightings.isLoading && <p role="status">Loading sightings…</p>}{sightings.error && <p role="alert">Unable to load source history. <button className="underline" onClick={() => void sightings.mutate()}>Retry sightings</button></p>}{sightings.data && <><p>{sightings.data.entry_total} accessible sightings</p>{sightings.data.entries.map(item => <EntryCard key={item.id} entry={item} />)}{sightings.data.entry_total > sightings.data.page_size && <PaginationBar label="Source sighting pages" page={page} pages={Math.ceil(sightings.data.entry_total / sightings.data.page_size)} onChange={setPage} previousLabel="Previous sightings" nextLabel="Next sightings" />}</>}</section>
      <SessionNotes projectId={entry.project_id} sessionKey={entry.session_key} />
    </>}
  </div>;
}
