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
  const [isCreating, setIsCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);

  const { data: response, mutate, isLoading } = useSWR(
    "collections",
    () => collectionsApi.list()
  );

  const collections = response?.data ?? [];

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
    if (!confirm(`Delete collection "${collection.name}"? This will not delete the chunks themselves.`)) {
      return;
    }

    try {
      await collectionsApi.delete(collection.id);
      mutate();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to delete collection";
      alert(message);
    }
  };

  return (
    <AuthGate>
      <div className="min-h-screen bg-background dark:bg-background">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-foreground dark:text-foreground">Collections</h1>
            <p className="mt-2 text-secondary dark:text-muted">
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
              <form onSubmit={handleCreate} className="bg-surface dark:bg-surface rounded-lg border border-line dark:border-line p-6">
                <h2 className="text-lg font-semibold text-foreground dark:text-foreground mb-4">Create Collection</h2>
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-secondary dark:text-secondary mb-1">
                      Name *
                    </label>
                    <input
                      type="text"
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      placeholder="e.g., Key Research Findings"
                      className="w-full px-4 py-2 border border-line-strong dark:border-line-strong rounded-lg bg-surface dark:bg-surface-alt text-foreground dark:text-foreground"
                      autoFocus
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-secondary dark:text-secondary mb-1">
                      Description
                    </label>
                    <textarea
                      value={newDescription}
                      onChange={(e) => setNewDescription(e.target.value)}
                      placeholder="Optional description..."
                      rows={2}
                      className="w-full px-4 py-2 border border-line-strong dark:border-line-strong rounded-lg bg-surface dark:bg-surface-alt text-foreground dark:text-foreground"
                    />
                  </div>
                  {createError && (
                    <p className="text-sm text-danger dark:text-danger">{createError}</p>
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
                      className="px-4 py-2 text-secondary dark:text-muted hover:text-foreground dark:hover:text-foreground transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              </form>
            )}
          </div>

          {/* Collections List */}
          {isLoading ? (
            <div className="text-center py-12">
              <p className="text-muted">Loading collections...</p>
            </div>
          ) : collections.length === 0 ? (
            <div className="text-center py-12 bg-surface dark:bg-surface rounded-lg border border-line dark:border-line">
              <p className="text-muted dark:text-muted mb-4">No collections yet</p>
              <p className="text-sm text-muted dark:text-muted">
                Create a collection to start organizing chunks from your searches and documents.
              </p>
            </div>
          ) : (
            <div className="grid gap-4">
              {collections.map((collection) => (
                <div
                  key={collection.id}
                  className="bg-surface dark:bg-surface rounded-lg border border-line dark:border-line p-6 hover:shadow-lg transition-shadow"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <Link
                        href={`/collections/${collection.id}`}
                        className="text-lg font-semibold text-foreground dark:text-foreground hover:text-accent-text dark:hover:text-accent-text"
                      >
                        {collection.name}
                      </Link>

                      {collection.description && (
                        <p className="mt-1 text-sm text-secondary dark:text-muted">
                          {collection.description}
                        </p>
                      )}

                      <div className="mt-3 flex flex-wrap gap-4 text-sm text-secondary dark:text-muted">
                        <span className="inline-flex items-center gap-1">
                          <span className="font-medium text-accent-text dark:text-accent-text">
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

                    <div className="ml-4 flex gap-2">
                      <Link
                        href={`/collections/${collection.id}`}
                        className="px-4 py-2 text-sm text-accent-text dark:text-accent-text hover:bg-info-surface dark:hover:bg-surface-alt rounded"
                      >
                        View
                      </Link>
                      <button
                        onClick={() => handleDelete(collection)}
                        className="px-4 py-2 text-sm text-danger dark:text-danger hover:bg-danger-surface dark:hover:bg-surface-alt rounded"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </AuthGate>
  );
}
