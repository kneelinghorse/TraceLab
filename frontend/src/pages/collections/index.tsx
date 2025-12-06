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
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Collections</h1>
            <p className="mt-2 text-gray-600 dark:text-gray-400">
              Organize chunks from searches and documents for later export or analysis
            </p>
          </div>

          {/* Create Collection */}
          <div className="mb-6">
            {!isCreating ? (
              <button
                onClick={() => setIsCreating(true)}
                className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                New Collection
              </button>
            ) : (
              <form onSubmit={handleCreate} className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Create Collection</h2>
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Name *
                    </label>
                    <input
                      type="text"
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      placeholder="e.g., Key Research Findings"
                      className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                      autoFocus
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Description
                    </label>
                    <textarea
                      value={newDescription}
                      onChange={(e) => setNewDescription(e.target.value)}
                      placeholder="Optional description..."
                      rows={2}
                      className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    />
                  </div>
                  {createError && (
                    <p className="text-sm text-red-600 dark:text-red-400">{createError}</p>
                  )}
                  <div className="flex gap-3">
                    <button
                      type="submit"
                      className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
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
                      className="px-4 py-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors"
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
              <p className="text-gray-500">Loading collections...</p>
            </div>
          ) : collections.length === 0 ? (
            <div className="text-center py-12 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
              <p className="text-gray-500 dark:text-gray-400 mb-4">No collections yet</p>
              <p className="text-sm text-gray-400 dark:text-gray-500">
                Create a collection to start organizing chunks from your searches and documents.
              </p>
            </div>
          ) : (
            <div className="grid gap-4">
              {collections.map((collection) => (
                <div
                  key={collection.id}
                  className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6 hover:shadow-lg transition-shadow"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <Link
                        href={`/collections/${collection.id}`}
                        className="text-lg font-semibold text-gray-900 dark:text-white hover:text-blue-600 dark:hover:text-blue-400"
                      >
                        {collection.name}
                      </Link>

                      {collection.description && (
                        <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
                          {collection.description}
                        </p>
                      )}

                      <div className="mt-3 flex flex-wrap gap-4 text-sm text-gray-600 dark:text-gray-400">
                        <span className="inline-flex items-center gap-1">
                          <span className="font-medium text-blue-600 dark:text-blue-400">
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
                        className="px-4 py-2 text-sm text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-gray-700 rounded"
                      >
                        View
                      </Link>
                      <button
                        onClick={() => handleDelete(collection)}
                        className="px-4 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-gray-700 rounded"
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
