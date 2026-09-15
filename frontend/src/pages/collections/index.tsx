import { PageState } from "@/components/ui/PageState";
import { PaginationBar } from "@/components/ui/PaginationBar";
import { useFeedback } from "@/components/ui/useFeedback";
/**
 * Collections list page
 */

import { AuthGate } from "@/components/AuthGate";
import { collectionsApi, type Collection } from "@/lib/api/collections";
import { formatDistanceToNow } from "date-fns";
import Link from "next/link";
import { useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { parseApiTimestamp } from "@/lib/api/timestamps";
import useSWR from "swr";

export default function CollectionsPage() {
  const { user } = useAuth();
  const { askConfirmation, notify, feedback } = useFeedback();
  const [page, setPage] = useState(1);

  const { data: response, mutate, isLoading, error } = useSWR(
    ["collections", user?.user_id, page],
    () => collectionsApi.list({ page, page_size: 20 })
  );

  const collections = response?.data ?? [];
  const pages = Math.ceil((response?.total ?? 0) / 20);

  const handleDelete = async (collection: Collection) => {
    if (!await askConfirmation(`Delete collection "${collection.name}"? The documents and excerpts will remain available.`)) {
      return;
    }

    try {
      await collectionsApi.delete(collection.id);
      mutate();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to delete collection";
      notify(message);
    }
  };

  return (
    <AuthGate>
      {feedback}
      <div className="min-h-screen bg-background">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Header */}
          <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
            <div>
              <h1 className="text-3xl font-bold text-foreground">Collections</h1>
              <p className="mt-2 text-secondary">
                Keep instructions, documents and excerpts together to guide your next mission
              </p>
            </div>
            <Link href="/collections/new" className="px-6 py-2 bg-accent text-on-accent rounded-lg hover:bg-accent transition-colors">New collection</Link>
          </div>

          {response && !error && <p className="mb-4 text-sm text-secondary">{response.total.toLocaleString()} collections</p>}
          {/* Collections List */}
          {error ? <PageState state="error" title="Collections could not load." onRetry={() => void mutate()} /> : isLoading ? (
            <PageState state="loading" title="Loading collections…" />
          ) : collections.length === 0 ? (
            <div className="text-center py-12 bg-surface rounded-lg border border-line">
              <p className="text-muted mb-4">No collections yet</p>
              <p className="text-sm text-muted">
                Create a collection, then add documents or excerpts from their detail pages.
              </p>
            </div>
          ) : (
            <div className="grid gap-4">
              {collections.map((collection) => (
                <div
                  key={collection.id}
                  className="bg-surface rounded-lg border border-line p-6 hover:shadow-lg transition-shadow"
                >
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0 flex-1">
                      <Link
                        href={`/collections/${collection.id}`}
                        className="break-words text-lg font-semibold text-foreground hover:text-accent-text"
                      >
                        {collection.name}
                      </Link>

                      {collection.description && (
                        <p className="mt-1 line-clamp-3 text-sm text-secondary">
                          {collection.description}
                        </p>
                      )}

                      <div className="mt-3 flex flex-wrap gap-4 text-sm text-secondary">
                        <span className="inline-flex items-center gap-1">
                          <span className="font-medium text-accent-text">
                            {collection.item_count}
                          </span>
                          {collection.item_count === 1 ? "chunk" : "chunks"}
                        </span>
                        <span>
                          Created {formatDistanceToNow(parseApiTimestamp(collection.created_at), { addSuffix: true })}
                        </span>
                        {collection.updated_at !== collection.created_at && (
                          <span>
                            Updated {formatDistanceToNow(parseApiTimestamp(collection.updated_at), { addSuffix: true })}
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="flex shrink-0 gap-2">
                      <Link
                        href={`/collections/${collection.id}`}
                        className="px-4 py-2 text-sm text-accent-text hover:bg-info-surface rounded"
                      >
                        View
                      </Link>
                      <button
                        onClick={() => handleDelete(collection)}
                        className="px-4 py-2 text-sm text-danger hover:bg-danger-surface rounded"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
          {!error && <PaginationBar page={page} pages={pages} total={response?.total} onChange={setPage} />}
        </div>
      </div>
    </AuthGate>
  );
}
