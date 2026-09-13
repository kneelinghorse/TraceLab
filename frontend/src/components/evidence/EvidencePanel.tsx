import Link from "next/link";
import useSWR from "swr";
import { useAuth } from "@/contexts/AuthContext";
import { evidenceApi, evidenceHref, type EvidenceFilters } from "@/lib/api/evidence";

/** The same scoped evidence destination on reports, missions and documents. */
export function EvidencePanel({ projectId, filters }: { projectId: string | null | undefined; filters: EvidenceFilters }) {
  const { user } = useAuth();
  const ledger = useSWR(projectId ? ["related-evidence", user?.user_id, projectId, filters] : null, () => evidenceApi.list(projectId!, 1, filters));
  return <section className="panel my-6 space-y-3 p-5" aria-label="Related evidence">
    <h2 className="text-lg font-semibold">Evidence</h2>
    {!projectId && <p className="text-secondary">No project is linked to this output, so its evidence cannot be resolved.</p>}
    {ledger.isLoading && <p role="status">Loading evidence…</p>}
    {ledger.error && <div role="alert"><p>Unable to load evidence.</p><button className="text-accent-text underline" onClick={() => void ledger.mutate()}>Retry evidence</button></div>}
    {ledger.data && <>
      <Link href={evidenceHref(projectId!, filters)} className="text-accent-text underline">Browse evidence ({ledger.data.entry_total.toLocaleString()})</Link>
      {ledger.data.entry_total === 0 ? <p className="text-secondary">No accessible evidence is linked to this output.</p> : <ul className="space-y-2">{ledger.data.entries.slice(0, 3).map(entry => <li key={entry.id}><Link className="break-words text-sm text-accent-text underline" href={`/evidence/${entry.id}`}>{entry.claim}</Link></li>)}</ul>}
    </>}
  </section>;
}
