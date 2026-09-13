import Link from "next/link";
import { evidenceHref, sourceDomain, type LedgerEntry } from "@/lib/api/evidence";

export function EntryCard({ entry }: { entry: LedgerEntry }) {
  return <article className="panel min-w-0 space-y-3 p-5">
    <div className="flex flex-wrap items-center gap-2 text-xs text-secondary">
      <span className="rounded-full bg-surface-alt px-2 py-1">{entry.disposition}</span>
      <span>{sourceDomain(entry.source_url)}</span>
      <time dateTime={entry.created_at}>{new Date(entry.created_at).toLocaleDateString()}</time>
    </div>
    <h2 className="break-words text-lg font-medium"><Link className="text-accent-text underline underline-offset-4" href={`/evidence/${entry.id}`}>{entry.claim}</Link></h2>
    {entry.summary && <p className="break-words text-secondary">{entry.summary}</p>}
    <div className="flex flex-wrap gap-2 text-xs">{entry.tags?.map(tag => <span key={tag} className="rounded bg-surface-alt px-2 py-1">{tag}</span>)}</div>
    <a href={entry.source_url} target="_blank" rel="noreferrer" className="block break-all text-sm text-accent-text underline underline-offset-4">{entry.source_url}<span className="sr-only"> (opens in a new tab)</span></a>
    <Link href={evidenceHref(entry.project_id, { session_key: entry.session_key })} className="block break-words text-xs text-accent-text underline">Session: {entry.session_key}</Link>
  </article>;
}
