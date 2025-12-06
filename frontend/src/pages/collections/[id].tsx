/**
 * Collection detail page
 */

import { AuthGate } from "@/components/AuthGate";
import { CreateReportModal } from "@/components/CreateReportModal";
import { collectionsApi, type CollectionDetail, type CollectionItem } from "@/lib/api/collections";
import { formatDistanceToNow } from "date-fns";
import Link from "next/link";
import { useRouter } from "next/router";
import { useState } from "react";
import useSWR from "swr";

export default function CollectionDetailPage() {
  const router = useRouter();
  const { id } = router.query;
  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editError, setEditError] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [isReportModalOpen, setIsReportModalOpen] = useState(false);

  const { data: collection, mutate, isLoading } = useSWR<CollectionDetail>(
    id ? `collection-${id}` : null,
    () => collectionsApi.get(id as string)
  );

  const handleStartEdit = () => {
    if (!collection) return;
    setEditName(collection.name);
    setEditDescription(collection.description || "");
    setIsEditing(true);
  };

  const handleSaveEdit = async () => {
    if (!collection || !editName.trim()) {
      setEditError("Name is required");
      return;
    }

    setEditError(null);
    try {
      await collectionsApi.update(collection.id, {
        name: editName.trim(),
        description: editDescription.trim() || undefined,
      });
      setIsEditing(false);
      mutate();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to update collection";
      setEditError(message);
    }
  };

  const handleDelete = async () => {
    if (!collection) return;
    if (!confirm(`Delete collection "${collection.name}"? This will not delete the chunks themselves.`)) {
      return;
    }

    try {
      await collectionsApi.delete(collection.id);
      router.push("/collections");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to delete collection";
      alert(message);
    }
  };

  const handleRemoveChunk = async (item: CollectionItem) => {
    if (!collection) return;
    if (!confirm("Remove this chunk from the collection?")) return;

    try {
      await collectionsApi.removeChunk(collection.id, item.chunk_id);
      mutate();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to remove chunk";
      alert(message);
    }
  };

  const handleExport = async () => {
    if (!collection) return;
    setIsExporting(true);
    try {
      await collectionsApi.exportMarkdown(collection.id);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to export collection";
      alert(message);
    } finally {
      setIsExporting(false);
    }
  };

  if (isLoading || !collection) {
    return (
      <AuthGate>
        <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
          <p className="text-gray-500">Loading collection...</p>
        </div>
      </AuthGate>
    );
  }

  return (
    <AuthGate>
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Back Link */}
          <Link
            href="/collections"
            className="text-blue-600 dark:text-blue-400 hover:underline mb-4 inline-block"
          >
            &larr; Back to Collections
          </Link>

          {/* Header */}
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6 mb-6">
            {isEditing ? (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Name *
                  </label>
                  <input
                    type="text"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    autoFocus
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Description
                  </label>
                  <textarea
                    value={editDescription}
                    onChange={(e) => setEditDescription(e.target.value)}
                    rows={2}
                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                  />
                </div>
                {editError && (
                  <p className="text-sm text-red-600 dark:text-red-400">{editError}</p>
                )}
                <div className="flex gap-3">
                  <button
                    onClick={handleSaveEdit}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                  >
                    Save
                  </button>
                  <button
                    onClick={() => {
                      setIsEditing(false);
                      setEditError(null);
                    }}
                    className="px-4 py-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div className="flex items-start justify-between">
                  <div>
                    <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
                      {collection.name}
                    </h1>
                    {collection.description && (
                      <p className="mt-2 text-gray-600 dark:text-gray-400">
                        {collection.description}
                      </p>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setIsReportModalOpen(true)}
                      disabled={collection.item_count === 0}
                      className="px-4 py-2 text-sm bg-purple-600 text-white hover:bg-purple-700 rounded disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      Create Report
                    </button>
                    <button
                      onClick={handleExport}
                      disabled={isExporting || collection.item_count === 0}
                      className="px-4 py-2 text-sm text-green-600 dark:text-green-400 hover:bg-green-50 dark:hover:bg-gray-700 rounded disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isExporting ? "Exporting..." : "Export"}
                    </button>
                    <button
                      onClick={handleStartEdit}
                      className="px-4 py-2 text-sm text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-gray-700 rounded"
                    >
                      Edit
                    </button>
                    <button
                      onClick={handleDelete}
                      className="px-4 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-gray-700 rounded"
                    >
                      Delete
                    </button>
                  </div>
                </div>

                <div className="mt-4 flex flex-wrap gap-4 text-sm text-gray-600 dark:text-gray-400">
                  <span className="inline-flex items-center gap-1">
                    <span className="font-medium text-blue-600 dark:text-blue-400">
                      {collection.item_count}
                    </span>
                    {collection.item_count === 1 ? "chunk" : "chunks"}
                  </span>
                  <span>
                    Created {formatDistanceToNow(new Date(collection.created_at), { addSuffix: true })}
                  </span>
                </div>
              </>
            )}
          </div>

          {/* Collection Items */}
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Chunks in Collection
            </h2>

            {collection.items.length === 0 ? (
              <div className="text-center py-8">
                <p className="text-gray-500 dark:text-gray-400 mb-2">No chunks in this collection yet</p>
                <p className="text-sm text-gray-400 dark:text-gray-500">
                  Add chunks from search results or document views using the &quot;Add to Collection&quot; button.
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                {collection.items.map((item) => (
                  <div
                    key={item.id}
                    className="border border-gray-200 dark:border-gray-600 rounded-lg p-4"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-2">
                          <code className="text-xs bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded text-gray-600 dark:text-gray-300">
                            {item.chunk_id.slice(0, 8)}...
                          </code>
                          {item.document_id && (
                            <Link
                              href={`/documents/${item.document_id}`}
                              className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                            >
                              View document
                            </Link>
                          )}
                        </div>

                        {item.chunk_content && (
                          <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
                            {item.chunk_content}
                            {item.chunk_content.length >= 200 && "..."}
                          </p>
                        )}

                        {item.notes && (
                          <p className="mt-2 text-sm text-gray-500 dark:text-gray-400 italic">
                            Note: {item.notes}
                          </p>
                        )}

                        <p className="mt-2 text-xs text-gray-400 dark:text-gray-500">
                          Added {formatDistanceToNow(new Date(item.added_at), { addSuffix: true })}
                        </p>
                      </div>

                      <button
                        onClick={() => handleRemoveChunk(item)}
                        className="px-3 py-1 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-gray-700 rounded flex-shrink-0"
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Create Report Modal */}
      <CreateReportModal
        collectionId={collection.id}
        collectionName={collection.name}
        isOpen={isReportModalOpen}
        onClose={() => setIsReportModalOpen(false)}
      />
    </AuthGate>
  );
}
