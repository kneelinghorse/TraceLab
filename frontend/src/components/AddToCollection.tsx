import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { useAuth } from "@/contexts/AuthContext";
import { collectionsApi, type Collection } from "@/lib/api/collections";
import { Dialog } from "@/components/ui/Dialog";
import { PageState } from "@/components/ui/PageState";
import { PaginationBar } from "@/components/ui/PaginationBar";

type AddToCollectionProps = ({ chunkId: string; documentId?: never } | { documentId: string; chunkId?: never }) & {
  onAdded?: () => void | Promise<void>;
  className?: string;
  variant?: "default" | "compact";
};

/** Documents and excerpts share a complete, scoped collection picker. */
export function AddToCollection({ chunkId, documentId, onAdded, className = "", variant = "default" }: AddToCollectionProps) {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [created, setCreated] = useState<Collection | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const response = useSWR(open ? ["collections-picker", user?.user_id, page] : null, () => collectionsApi.list({ page, page_size: 20 }));

  async function attach(collection: Collection) {
    if (documentId) await collectionsApi.addDocument(collection.id, documentId);
    else await collectionsApi.addChunk(collection.id, { chunk_id: chunkId! });
    setOpen(false); setCreated(null); setName(""); setMessage(`Added to ${collection.name}.`);
    try { await onAdded?.(); } catch { setMessage(`Added to ${collection.name}. Refresh the collection to see its current contents.`); }
  }
  async function add(collection: Collection) {
    if (busy) return;
    setBusy(true); setFailure(null);
    try { await attach(collection); }
    catch (error) { setFailure(error instanceof Error ? error.message : "Source could not be added."); }
    finally { setBusy(false); }
  }
  async function createAndAdd(event: React.FormEvent) {
    event.preventDefault();
    if (busy || !name.trim()) return;
    setBusy(true); setFailure(null);
    try {
      const collection = created ?? await collectionsApi.create({ name: name.trim() });
      setCreated(collection); // An attachment retry must not create a duplicate collection.
      await attach(collection);
    } catch (error) { setFailure(error instanceof Error ? error.message : "Collection could not be created or populated."); }
    finally { setBusy(false); }
  }
  return <div className={`min-w-0 ${className}`}>
    <button type="button" aria-label={documentId ? "Add document to collection" : "Add excerpt to collection"} onClick={() => { setOpen(true); setFailure(null); setMessage(null); }} className={`rounded-lg border border-line-strong text-secondary hover:text-accent-text ${variant === "compact" ? "px-2 py-1 text-xs" : "px-3 py-2 text-sm"}`}>+ Collection</button>
    {message && <p role="status" className="mt-2 break-words text-sm text-secondary">{message}</p>}
    <Dialog open={open} title="Add to collection" onClose={() => { if (!busy) setOpen(false); }}>
      <div className="max-h-[70vh] space-y-4 overflow-y-auto">
        {failure && <p role="alert" className="break-words text-sm text-danger">{failure}</p>}
        {created && <div className="panel space-y-2 p-3 text-sm"><p>Created <Link className="underline" href={`/collections/${created.id}`}>{created.name}</Link>. Its source still needs to be added.</p><button disabled={busy} className="text-accent-text underline" onClick={() => void add(created)}>Retry adding to {created.name}</button></div>}
        {response.error ? <PageState state="error" title="Collections could not load." onRetry={() => void response.mutate().catch(() => {})} /> : response.isLoading ? <PageState state="loading" title="Loading collections…" /> : response.data && <>
          <p className="text-sm text-secondary">{response.data.total.toLocaleString()} collections</p>
          {response.data.total === 0 ? <PageState state="empty" title="No collections available." /> : <ul className="divide-y divide-line">{response.data.data.map(collection => <li key={collection.id}><button disabled={busy} type="button" aria-label={`Add to ${collection.name}`} className="w-full break-words py-3 text-left font-medium hover:text-accent-text disabled:opacity-50" onClick={() => void add(collection)}>{collection.name}</button></li>)}</ul>}
          <PaginationBar label="Collection picker pages" page={page} pages={Math.ceil(response.data.total / 20)} onChange={next => { if (!busy) setPage(next); }} />
        </>}
        {!created && <details className="panel p-3"><summary className="cursor-pointer font-medium">Create a collection</summary><form className="mt-3 space-y-3" onSubmit={event => void createAndAdd(event)}><label className="block space-y-1 text-sm"><span>New collection name</span><input className="w-full rounded border border-line-strong bg-background px-3 py-2" value={name} disabled={busy} maxLength={255} onChange={event => setName(event.target.value)} /></label><button disabled={busy || !name.trim()} className="rounded bg-accent px-3 py-2 text-on-accent disabled:opacity-50">Create and add</button></form></details>}
        <button type="button" disabled={busy} className="rounded border border-line-strong px-3 py-2 disabled:opacity-50" onClick={() => setOpen(false)}>Cancel</button>
      </div>
    </Dialog>
  </div>;
}
