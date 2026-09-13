import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { useAuth } from "@/contexts/AuthContext";
import { evidenceApi, evidenceHref } from "@/lib/api/evidence";
import { PaginationBar } from "@/components/ui/PaginationBar";
import { PageState } from "@/components/ui/PageState";
import { EntryCard } from "@/components/evidence/EntryCard";

/** Only the scoped evidence response may supply a citation's destination. */
export function ReportCitations({ reportId, projectId }: { reportId: string; projectId: string | null }) {
  const { user } = useAuth();
  const [page, setPage] = useState(1);
  const filters = { report_id: reportId };
  const result = useSWR(projectId ? ["report-citations", user?.user_id, projectId, reportId, page] : null, () => evidenceApi.list(projectId!, page, filters));
  return <section className="panel my-6 space-y-4 p-6" aria-label="Evidence citations">
    <h2 className="text-lg font-semibold">Evidence citations{result.data && ` (${result.data.entry_total.toLocaleString()})`}</h2>
    {!projectId ? <p className="text-secondary">Link this report to a project to resolve evidence citations.</p> : result.error ? <PageState state="error" title="Evidence citations could not load." onRetry={() => void result.mutate()} /> : result.isLoading ? <PageState state="loading" title="Loading evidence citations…" /> : result.data && <>
      <Link href={evidenceHref(projectId, filters)} className="text-sm text-accent-text underline">Browse evidence ({result.data.entry_total.toLocaleString()})</Link>
      {result.data.entry_total === 0 ? <p className="text-secondary">No accessible evidence is linked to this report.</p> : <div className="space-y-3">{result.data.entries.map(entry => <EntryCard key={entry.id} entry={entry} />)}</div>}
      <PaginationBar label="Citation pages" page={page} pages={Math.ceil(result.data.entry_total / result.data.page_size)} total={result.data.entry_total} onChange={setPage} />
    </>}
  </section>;
}
