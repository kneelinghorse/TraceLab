import Link from "next/link";
import { useState, type FormEvent } from "react";
import useSWR from "swr";

import { AddToCollection } from "@/components/AddToCollection";
import { SaveSearchButton } from "@/components/SaveSearchButton";
import { PageState } from "@/components/ui/PageState";
import { useAuth } from "@/contexts/AuthContext";
import { collectionsApi, type Collection } from "@/lib/api/collections";
import { documentsApi } from "@/lib/api/documents";
import { HttpError } from "@/lib/api/http";
import { savedSearchesApi } from "@/lib/api/savedSearches";
import { searchApi } from "@/lib/api/search";
import type { Project } from "@/types/document";

/**
 * The Librarian's plain chunk list (QA-2, decision #545): the ranked chunks for a
 * query, for finding a passage rather than asking a question. A query runs
 * POST /pedr/search; a saved search runs through its own execute call, which is
 * what counts the run. The list can be kept as a collection.
 */

export const CHUNK_LIST_SIZE = 20;

export type ChunkListRequest = { kind: "query"; query: string; projectId: string } | { kind: "saved"; savedId: string };

type Row = { chunkId: string; documentId: string | null; chunkIndex: number | null; content: string; score: number };
type Listing = { rows: Row[]; query: string; projectId: string; savedName: string | null };

async function loadListing(request: ChunkListRequest): Promise<Listing> {
  if (request.kind === "saved") {
    const result = await savedSearchesApi.execute(request.savedId);
    const project = result.saved_search.filters?.project_id;
    return {
      rows: result.semantic.results.map((chunk) => ({
        chunkId: chunk.chunk_id,
        documentId: chunk.document_id ?? null,
        chunkIndex: chunk.chunk_index ?? null,
        content: chunk.content,
        score: chunk.score,
      })),
      query: result.saved_search.query_text,
      projectId: typeof project === "string" ? project : "",
      savedName: result.saved_search.name,
    };
  }
  const result = await searchApi.pedrSearch({ query: request.query, top_k: CHUNK_LIST_SIZE, project_id: request.projectId || undefined });
  return {
    rows: result.results.map((chunk) => ({
      chunkId: chunk.chunk_id,
      documentId: chunk.document_id ?? null,
      chunkIndex: chunk.chunk_index ?? null,
      content: chunk.content,
      score: chunk.rrf_score,
    })),
    query: request.query,
    projectId: request.projectId,
    savedName: null,
  };
}

/** QA-1's chunk link: the document page opens its Chunks tab on this chunk. */
function chunkHref(row: Row) {
  const index = row.chunkIndex == null ? "" : `&index=${row.chunkIndex}`;
  return `/documents/${row.documentId}?chunk=${encodeURIComponent(row.chunkId)}${index}`;
}

function SaveAsCollection({ rows, defaultName }: { rows: Row[]; defaultName: string }) {
  const [name, setName] = useState(defaultName.slice(0, 255));
  const [collection, setCollection] = useState<Collection | null>(null);
  const [added, setAdded] = useState<Set<string>>(() => new Set());
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const remaining = rows.filter((row) => !added.has(row.chunkId)).length;

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !name.trim()) return;
    setBusy(true);
    setFailure(null);
    const saved = new Set(added);
    try {
      // A retry reuses the collection it already made and adds only what is missing.
      const target = collection ?? (await collectionsApi.create({ name: name.trim() }));
      setCollection(target);
      for (const row of rows) {
        if (saved.has(row.chunkId)) continue;
        await collectionsApi.addChunk(target.id, { chunk_id: row.chunkId });
        saved.add(row.chunkId);
      }
    } catch (error) {
      setFailure(error instanceof Error ? error.message : "The collection could not be saved.");
    } finally {
      setAdded(saved);
      setBusy(false);
    }
  }

  if (collection && remaining === 0) {
    return (
      <p role="status" className="text-sm text-secondary">
        Saved {rows.length === 1 ? "1 chunk" : `${rows.length} chunks`} to <Link href={`/collections/${collection.id}`} className="text-accent-text underline">{collection.name}</Link>.
      </p>
    );
  }
  return (
    <form onSubmit={(event) => void save(event)} className="flex flex-col gap-2 sm:flex-row sm:items-end">
      <div className="min-w-0 flex-1">
        <label htmlFor="chunk-list-collection" className="form-label">Collection name</label>
        <input
          id="chunk-list-collection"
          className="form-input"
          value={name}
          maxLength={255}
          disabled={busy || Boolean(collection)}
          onChange={(event) => setName(event.target.value)}
        />
      </div>
      <button type="submit" disabled={busy || !name.trim()} className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-on-accent hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-60">
        {busy ? "Saving…" : collection ? `Add the remaining ${remaining}` : `Save ${rows.length === 1 ? "1 chunk" : `${rows.length} chunks`} as a collection`}
      </button>
      {failure && (
        <p role="alert" className="break-words text-sm text-danger sm:basis-full">
          {collection ? (
            <>Created <Link href={`/collections/${collection.id}`} className="underline">{collection.name}</Link> with {rows.length - remaining} of {rows.length} chunks. {failure}</>
          ) : failure}
        </p>
      )}
    </form>
  );
}

export function ChunkList({ request, projects }: { request: ChunkListRequest; projects: Project[] }) {
  const { user } = useAuth();
  const [savedSearch, setSavedSearch] = useState(false);
  const requestKey = request.kind === "saved" ? `saved:${request.savedId}` : `query:${request.projectId}:${request.query}`;
  // Never refetched behind the user's back: a saved search's execute call counts a run.
  const listing = useSWR(["librarian-chunks", user?.user_id, requestKey], () => loadListing(request), {
    revalidateOnFocus: false,
    revalidateOnReconnect: false,
    revalidateIfStale: false,
    shouldRetryOnError: false,
  });
  const rows = listing.data?.rows ?? [];
  const documentIds = [...new Set(rows.flatMap((row) => (row.documentId ? [row.documentId] : [])))].sort();
  const documents = useSWR(documentIds.length ? ["librarian-chunk-documents", user?.user_id, ...documentIds] : null, async () => {
    const settled = await Promise.allSettled(documentIds.map((id) => documentsApi.getDocument(id)));
    return new Map(settled.flatMap((result) => (result.status === "fulfilled" ? [[result.value.id, result.value.name] as const] : [])));
  });
  const saved = useSWR(request.kind === "query" ? ["saved-searches", user?.user_id] : null, () => savedSearchesApi.list());

  const projectId = listing.data?.projectId ?? (request.kind === "query" ? request.projectId : "");
  const projectName = projects.find((project) => project.id === projectId)?.name;
  const scope = projectId ? `In ${projectName ?? "one project"}` : "Across all your projects";
  const notFound = listing.error instanceof HttpError && listing.error.status === 404;

  function documentLabel(row: Row) {
    const name = row.documentId ? documents.data?.get(row.documentId) ?? "Document" : "Chunk without a document";
    return row.chunkIndex == null ? name : `${name} #${row.chunkIndex}`;
  }

  let title = request.kind === "query" ? `Chunks matching “${request.query}”` : "Saved search";
  if (listing.data) {
    const count = rows.length === 1 ? "1 chunk matches" : `${rows.length} chunks match`;
    title = listing.data.savedName ? `Saved search “${listing.data.savedName}”: ${count}` : `${count} “${listing.data.query}”`;
  }

  return (
    <section className="panel min-w-0 space-y-4 p-5" aria-label="Matching chunks">
      <header className="space-y-1">
        <h2 className="break-words text-lg font-semibold text-foreground">{title}</h2>
        {listing.data && (
          <p className="text-sm text-secondary">
            {scope}, best match first{listing.data.savedName ? `, for “${listing.data.query}”` : ""}. Open a chunk to read it in its document.
          </p>
        )}
      </header>

      {listing.error ? (
        <PageState state="error" title={notFound ? "This saved search no longer exists" : "The chunks could not be listed"} onRetry={notFound ? undefined : () => void listing.mutate()}>
          {notFound ? "It may have been deleted. Search again from the box above." : "Try again when the search service is available."}
        </PageState>
      ) : !listing.data ? (
        <PageState state="loading" title="Searching the documents…" />
      ) : rows.length === 0 ? (
        <PageState state="empty" title="No chunks match">Try other words{projectId ? ", or another project" : ""}.</PageState>
      ) : (
        <>
          <ol className="space-y-3">
            {rows.map((row, index) => (
              <li key={row.chunkId} className="min-w-0 rounded-lg border border-line p-3">
                <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                  <p className="min-w-0 break-words text-sm font-semibold">
                    <span className="mr-2 font-mono text-muted">{index + 1}.</span>
                    {row.documentId ? (
                      <Link href={chunkHref(row)} className="text-accent-text underline">{documentLabel(row)}</Link>
                    ) : (
                      <span>{documentLabel(row)}</span>
                    )}
                  </p>
                  <span className="text-xs text-secondary">Score {row.score.toFixed(4)}</span>
                </div>
                <p className="mt-2 line-clamp-4 whitespace-pre-line break-words text-sm text-foreground">
                  {row.content || "This chunk's text is not in the search result; open it to read it."}
                </p>
                <AddToCollection chunkId={row.chunkId} variant="compact" className="mt-2" />
              </li>
            ))}
          </ol>
          <div className="space-y-3 border-t border-line pt-4">
            <SaveAsCollection rows={rows} defaultName={listing.data.savedName ?? listing.data.query} />
            {request.kind === "query" && saved.data && (
              <SaveSearchButton
                currentQuery={request.query}
                filters={{ projectId: request.projectId, documentType: "", startDate: "", endDate: "" }}
                topK={CHUNK_LIST_SIZE}
                savedSearchCount={saved.data.items.length}
                limitPerUser={saved.data.limit_per_user}
                onSaved={() => {
                  setSavedSearch(true);
                  void saved.mutate();
                }}
              />
            )}
            {savedSearch && (
              <p role="status" className="text-sm text-secondary">
                Search saved. Run it again from <Link href="/saved-searches" className="text-accent-text underline">Saved searches</Link>.
              </p>
            )}
          </div>
        </>
      )}
    </section>
  );
}
