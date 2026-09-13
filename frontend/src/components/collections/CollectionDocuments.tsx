import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { useAuth } from "@/contexts/AuthContext";
import { collectionsApi } from "@/lib/api/collections";
import { PageState } from "@/components/ui/PageState";
import { PaginationBar } from "@/components/ui/PaginationBar";
import { useFeedback } from "@/components/ui/useFeedback";

export function CollectionDocuments({ collectionId, onChange }: { collectionId: string; onChange: () => Promise<unknown> }) {
  const { user } = useAuth();
  const [page, setPage] = useState(1);
  const [removing, setRemoving] = useState<string | null>(null);
  const { feedback, askConfirmation, notify } = useFeedback();
  const documents = useSWR(["collection-documents", user?.user_id, collectionId, page], () => collectionsApi.documents(collectionId, page));
  async function remove(id: string) {
    if (!await askConfirmation("Remove this document and its excerpts from this collection? The original document will remain available.")) return;
    setRemoving(id);
    try {
      await collectionsApi.removeDocument(collectionId, id);
      if (page > 1 && documents.data?.items.length === 1) setPage(page - 1);
      await Promise.all([documents.mutate(), onChange()]);
    } catch (error) { notify(error instanceof Error ? error.message : "The document could not be removed."); }
    finally { setRemoving(null); }
  }
  return <section className="panel mb-6 space-y-4 p-6" aria-label="Collection documents">
    {feedback}
    <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-lg font-semibold">Documents{documents.data && ` (${documents.data.total.toLocaleString()})`}</h2><Link href="/documents" className="text-sm text-accent-text underline">Browse documents to add</Link></div>
    <p className="text-sm text-secondary">Documents added here and documents with saved excerpts form the context for a seeded mission.</p>
    {documents.error ? <PageState state="error" title="Collection documents could not load." onRetry={() => void documents.mutate()} /> : documents.isLoading ? <PageState state="loading" title="Loading collection documents…" /> : documents.data && <>
      {documents.data.items.length === 0 ? <p className="text-secondary">No documents in this collection yet. Open a document and choose Add document to collection.</p> : <ul className="divide-y divide-line">{documents.data.items.map(doc => <li key={doc.id} className="flex flex-wrap items-center justify-between gap-3 py-3"><div className="min-w-0 flex-1"><Link href={`/documents/${doc.id}`} className="break-words font-medium text-accent-text underline">{doc.name}</Link><p className="mt-1 text-xs text-secondary">{doc.file_type || "Document"} · {doc.embedded ? "Search ready" : doc.chunked ? "Excerpts ready" : "Source document"}</p></div><button disabled={removing !== null} onClick={() => void remove(doc.id)} aria-label={`Remove ${doc.name} from collection`} className="rounded border border-line px-3 py-2 text-sm text-danger disabled:opacity-50">{removing === doc.id ? "Removing…" : "Remove"}</button></li>)}</ul>}
      <PaginationBar label="Collection document pages" page={page} pages={Math.ceil(documents.data.total / documents.data.page_size)} total={documents.data.total} onChange={setPage} />
    </>}
  </section>;
}
