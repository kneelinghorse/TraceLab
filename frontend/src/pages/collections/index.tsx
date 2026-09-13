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
import useSWR from "swr";

export default function CollectionsPage() {
  const { askConfirmation, notify, feedback } = useFeedback();
  const [page, setPage] = useState(1);
  const [isCreating, setIsCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);

  const { data: response, mutate, isLoading, error } = useSWR(
    "collections",
    () => collectionsApi.list()
  );

  const allCollections = response?.data ?? [];
  const pages = Math.ceil(allCollections.length / 20);
  const currentPage = Math.min(page, Math.max(1, pages));
  const collections = allCollections.slice((currentPage - 1) * 20, currentPage * 20);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) {
      setCreateError("Name is required");
      return;
    }

    setCreateError(null);
    try {
      await collectionsApi.create({
        name: newName.trim(),
        description: newDescription.trim() || undefined,
      });
      setNewName("");
      setNewDescription("");
      setIsCreating(false);
      mutate();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to create collection";
      setCreateError(message);
    }
  };

  const handleDelete = async (collection: Collection) => {
    if (!await askConfirmation(`Delete collection "${collection.name}"? This will not delete the chunks themselves.`)) {
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
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-foreground">Collections</h1>
            <p className="mt-2 text-secondary">
              Organize chunks from searches and documents for later export or analysis
            </p>
          </div>

          {/* Create Collection */}
          <div className="mb-6">
            {!isCreating ? (
              <button
                onClick={() => setIsCreating(true)}
                className="px-6 py-2 bg-accent text-on-accent rounded-lg hover:bg-accent transition-colors"
              >
                New Collection
              </button>
            ) : (
              <form onSubmit={handleCreate} className="bg-surface rounded-lg border border-line p-6">
                <h2 className="text-lg font-semibold text-foreground mb-4">Create Collection</h2>
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-secondary mb-1">
                      Name *
                    </label>
                    <input
                      type="text"
                      aria-label="Collection name"
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      placeholder="e.g., Key Research Findings"
                      className="w-full px-4 py-2 border border-line-strong rounded-lg bg-surface text-foreground"
                      autoFocus
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-secondary mb-1">
                      Description
                    </label>
                    <textarea
                      aria-label="Collection description"
                      value={newDescription}
                      onChange={(e) => setNewDescription(e.target.value)}
                      placeholder="Optional description..."
                      rows={2}
                      className="w-full px-4 py-2 border border-line-strong rounded-lg bg-surface text-foreground"
                    />
                  </div>
                  {createError && (
                    <p className="text-sm text-danger">{createError}</p>
                  )}
                  <div className="flex gap-3">
                    <button
                      type="submit"
                      className="px-4 py-2 bg-accent text-on-accent rounded-lg hover:bg-accent transition-colors"
                    >
                      Create
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setIsCreating(false);
                        setNewName("");
                        setNewDescription("");
                        setCreateError(null);
                      }}
                      className="px-4 py-2 text-secondary hover:text-foreground transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              </form>
            )}
          </div>

          {/* Collections List */}
          {error ? <PageState state="error" title="Collections could not load." onRetry={() => void mutate()} /> : isLoading ? (
            <PageState state="loading" title="Loading collections…" />
          ) : collections.length === 0 ? (
            <div className="text-center py-12 bg-surface rounded-lg border border-line">
              <p className="text-muted mb-4">No collections yet</p>
              <p className="text-sm text-muted">
                Create a collection to start organizing chunks from your searches and documents.
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
                        className="text-lg font-semibold text-foreground hover:text-accent-text"
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
                          Created {formatDistanceToNow(new Date(collection.created_at), { addSuffix: true })}
                        </span>
                        {collection.updated_at !== collection.created_at && (
                          <span>
                            Updated {formatDistanceToNow(new Date(collection.updated_at), { addSuffix: true })}
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
          {!error && <PaginationBar page={currentPage} pages={pages} total={response?.total} onChange={setPage} />}
        </div>
      </div>
    </AuthGate>
  );
}
