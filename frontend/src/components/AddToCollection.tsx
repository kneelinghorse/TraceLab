/**
 * AddToCollection - Dropdown component for adding chunks to collections
 */

import { collectionsApi, type Collection } from "@/lib/api/collections";
import { useState, useEffect } from "react";
import useSWR from "swr";

type AddToCollectionProps = {
  chunkId: string;
  onAdded?: () => void;
  className?: string;
  variant?: "default" | "compact";
};

export function AddToCollection({
  chunkId,
  onAdded,
  className = "",
  variant = "default",
}: AddToCollectionProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [isAdding, setIsAdding] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);

  const { data: response, mutate } = useSWR(
    isOpen ? "collections-dropdown" : null,
    () => collectionsApi.list()
  );
  const collections = response?.data ?? [];

  // Clear feedback after 3 seconds
  useEffect(() => {
    if (feedback) {
      const timer = setTimeout(() => setFeedback(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [feedback]);

  const handleAddToCollection = async (collection: Collection) => {
    setIsAdding(true);
    setFeedback(null);
    try {
      await collectionsApi.addChunk(collection.id, { chunk_id: chunkId });
      setFeedback({ type: "success", message: `Added to "${collection.name}"` });
      setIsOpen(false);
      onAdded?.();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to add to collection";
      setFeedback({ type: "error", message });
    } finally {
      setIsAdding(false);
    }
  };

  const handleCreateAndAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;

    setIsAdding(true);
    setFeedback(null);
    try {
      const collection = await collectionsApi.create({ name: newName.trim() });
      await collectionsApi.addChunk(collection.id, { chunk_id: chunkId });
      setFeedback({ type: "success", message: `Created "${collection.name}" and added chunk` });
      setNewName("");
      setIsCreating(false);
      setIsOpen(false);
      mutate();
      onAdded?.();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to create collection";
      setFeedback({ type: "error", message });
    } finally {
      setIsAdding(false);
    }
  };

  const buttonClass = variant === "compact"
    ? "text-xs px-2 py-1 border border-gray-300 dark:border-gray-600 rounded text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700"
    : "px-3 py-1.5 text-sm border border-white/20 rounded-lg text-slate-200 hover:border-sky-300 hover:text-sky-200";

  return (
    <div className={`relative ${isOpen ? "z-50" : ""} ${className}`}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={buttonClass}
        disabled={isAdding}
      >
        {isAdding ? "Adding..." : "+ Collection"}
      </button>

      {/* Dropdown */}
      {isOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-40"
            onClick={() => {
              setIsOpen(false);
              setIsCreating(false);
            }}
          />

          {/* Menu */}
          <div className="absolute right-0 mt-1 w-64 z-50 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg">
            <div className="p-2">
              <p className="text-xs font-medium text-gray-500 dark:text-gray-400 px-2 py-1">
                Add to collection
              </p>

              {/* Existing collections */}
              <div className="max-h-48 overflow-y-auto">
                {collections.length === 0 ? (
                  <p className="px-2 py-2 text-sm text-gray-500 dark:text-gray-400">
                    No collections yet
                  </p>
                ) : (
                  collections.map((collection) => (
                    <button
                      key={collection.id}
                      onClick={() => handleAddToCollection(collection)}
                      disabled={isAdding}
                      className="w-full text-left px-2 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded disabled:opacity-50"
                    >
                      <span className="block truncate">{collection.name}</span>
                      <span className="text-xs text-gray-500 dark:text-gray-400">
                        {collection.item_count} {collection.item_count === 1 ? "chunk" : "chunks"}
                      </span>
                    </button>
                  ))
                )}
              </div>

              {/* Divider */}
              <div className="border-t border-gray-200 dark:border-gray-700 my-2" />

              {/* Create new */}
              {isCreating ? (
                <form onSubmit={handleCreateAndAdd} className="p-2">
                  <input
                    type="text"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    placeholder="Collection name..."
                    className="w-full px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    autoFocus
                  />
                  <div className="flex gap-2 mt-2">
                    <button
                      type="submit"
                      disabled={!newName.trim() || isAdding}
                      className="flex-1 px-2 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                    >
                      Create & Add
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setIsCreating(false);
                        setNewName("");
                      }}
                      className="px-2 py-1 text-xs text-gray-600 dark:text-gray-400"
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              ) : (
                <button
                  onClick={() => setIsCreating(true)}
                  className="w-full text-left px-2 py-2 text-sm text-blue-600 dark:text-blue-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
                >
                  + New Collection
                </button>
              )}
            </div>
          </div>
        </>
      )}

      {/* Feedback */}
      {feedback && (
        <div
          className={`absolute right-0 mt-1 px-3 py-1.5 text-xs rounded-lg whitespace-nowrap z-50 ${
            feedback.type === "success"
              ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
              : "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
          }`}
        >
          {feedback.message}
        </div>
      )}
    </div>
  );
}
