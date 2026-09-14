import { RelationshipLink } from "@/components/graph/RelationshipLink";
import { HttpError } from "@/lib/api/http";
import { PageState } from "@/components/ui/PageState";
import { useFeedback } from "@/components/ui/useFeedback";
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
import { useAuth } from "@/contexts/AuthContext";
import { parseApiTimestamp } from "@/lib/api/timestamps";
import { CollectionDocuments } from "@/components/collections/CollectionDocuments";
import useSWR from "swr";

export default function CollectionDetailPage() {
  const { user } = useAuth();
  const [editInstructions, setEditInstructions] = useState("");
  const [saving, setSaving] = useState(false);
  const { askConfirmation, notify, feedback } = useFeedback();
  const router = useRouter();
  const { id } = router.query;
  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editError, setEditError] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [isReportModalOpen, setIsReportModalOpen] = useState(false);

  const { data: collection, mutate, isLoading, error } = useSWR<CollectionDetail>(
    id ? ["collection", user?.user_id, id] : null,
    () => collectionsApi.get(id as string)
  );

  const handleStartEdit = () => {
    if (!collection) return;
    setEditName(collection.name);
    setEditDescription(collection.description || "");
    setEditInstructions(collection.instructions || "");
    setIsEditing(true);
  };

  const handleSaveEdit = async () => {
    if (!collection || !editName.trim()) {
      setEditError("Name is required");
      return;
    }

    setEditError(null);
    setSaving(true);
    try {
      await collectionsApi.update(collection.id, {
        name: editName.trim(),
        description: editDescription.trim() || null,
        instructions: editInstructions.trim() || null,
      });
      setIsEditing(false);
      mutate();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to update collection";
      setEditError(message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!collection) return;
    if (!await askConfirmation(`Delete collection "${collection.name}"? The documents and excerpts will remain available.`)) {
      return;
    }

    try {
      await collectionsApi.delete(collection.id);
      router.push("/collections");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to delete collection";
      notify(message);
    }
  };

  const handleRemoveChunk = async (item: CollectionItem) => {
    if (!collection) return;
    if (!await askConfirmation("Remove this chunk from the collection?")) return;

    try {
      await collectionsApi.removeChunk(collection.id, item.chunk_id);
      mutate();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to remove chunk";
      notify(message);
    }
  };

  const handleExport = async () => {
    if (!collection) return;
    setIsExporting(true);
    try {
      await collectionsApi.exportMarkdown(collection.id);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to export collection";
      notify(message);
    } finally {
      setIsExporting(false);
    }
  };

  if (error instanceof HttpError && error.status === 404) return <AuthGate><PageState state="empty" title="Collection not found." /></AuthGate>;
  if (error) return <AuthGate><PageState state="error" title="Collection could not load." onRetry={() => void mutate()} /></AuthGate>;
  if (!router.isReady || isLoading) return <AuthGate><PageState state="loading" title="Loading collection…" /></AuthGate>;
  if (!collection) return <AuthGate><PageState state="empty" title="Collection not found." /></AuthGate>;

  return (
    <AuthGate>
      {feedback}
      <div className="min-h-screen bg-background">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Back Link */}
          <Link
            href="/collections"
            className="text-accent-text underline underline-offset-4 mb-4 inline-block"
          >
            &larr; Back to Collections
          </Link>

          {/* Header */}
          <div className="bg-surface rounded-lg border border-line p-6 mb-6">
            {isEditing ? (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-secondary mb-1">
                    Name *
                  </label>
                  <input
                    type="text"
                    aria-label="Collection name"
                      value={editName}
                    onChange={(e) => setEditName(e.target.value)}
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
                      value={editDescription}
                    onChange={(e) => setEditDescription(e.target.value)}
                    rows={2}
                    className="w-full px-4 py-2 border border-line-strong rounded-lg bg-surface text-foreground"
                  />
                </div>
                <label className="block text-sm font-medium text-secondary">Instructions<textarea value={editInstructions} onChange={event => setEditInstructions(event.target.value)} maxLength={20000} rows={5} className="mt-1 w-full rounded-lg border border-line-strong bg-surface px-4 py-2 text-foreground" /></label>
                {editError && (
                  <p className="text-sm text-danger">{editError}</p>
                )}
                <div className="flex gap-3">
                  <button
                    disabled={saving}
                    onClick={handleSaveEdit}
                    className="px-4 py-2 bg-accent text-on-accent rounded-lg hover:bg-accent transition-colors"
                  >
                    {saving ? "Saving…" : "Save"}
                  </button>
                  <button
                    disabled={saving}
                    onClick={() => {
                      setIsEditing(false);
                      setEditError(null);
                    }}
                    className="px-4 py-2 text-secondary hover:text-foreground transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                  <div>
                    <h1 className="break-words text-2xl font-bold text-foreground">
                      {collection.name}
                    </h1>
                    {collection.description && (
                      <p className="mt-2 text-secondary">
                        {collection.description}
                      </p>
                    )}
                  </div>
                  <div className="flex max-w-full flex-wrap gap-2">
                    <RelationshipLink type="collection" id={collection.id} />
                    <Link href={`/missions/new?collection=${collection.id}`} className="rounded bg-accent px-4 py-2 text-sm text-on-accent">Seed mission</Link>
                    <button
                      onClick={() => setIsReportModalOpen(true)}
                      disabled={collection.item_count === 0}
                      className="px-4 py-2 text-sm bg-accent text-on-accent hover:bg-accent rounded disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      Create Report
                    </button>
                    <button
                      onClick={handleExport}
                      disabled={isExporting || collection.item_count === 0}
                      className="px-4 py-2 text-sm text-success hover:bg-success-surface rounded disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isExporting ? "Exporting..." : "Export"}
                    </button>
                    <button
                      onClick={handleStartEdit}
                      className="px-4 py-2 text-sm text-accent-text hover:bg-info-surface rounded"
                    >
                      Edit
                    </button>
                    <button
                      onClick={handleDelete}
                      className="px-4 py-2 text-sm text-danger hover:bg-danger-surface rounded"
                    >
                      Delete
                    </button>
                  </div>
                </div>

                <section className="mt-5 space-y-2" aria-label="Collection instructions"><h2 className="font-semibold">Instructions</h2><p className="whitespace-pre-wrap break-words text-sm text-secondary">{collection.instructions || "Add instructions to guide missions seeded from this collection."}</p></section>
                <div className="mt-4 flex flex-wrap gap-4 text-sm text-secondary">
                  <span className="inline-flex items-center gap-1">
                    <span className="font-medium text-accent-text">
                      {collection.item_count}
                    </span>
                    {collection.item_count === 1 ? "chunk" : "chunks"}
                  </span>
                  <span>
                    Created {formatDistanceToNow(parseApiTimestamp(collection.created_at), { addSuffix: true })}
                  </span>
                </div>
              </>
            )}
          </div>

          <CollectionDocuments collectionId={collection.id} onChange={() => mutate()} />
          {/* Collection Items */}
          <div className="bg-surface rounded-lg border border-line p-6">
            <h2 className="text-lg font-semibold text-foreground mb-4">
              Chunks in Collection
            </h2>

            {collection.items.length === 0 ? (
              <div className="text-center py-8">
                <p className="text-muted mb-2">No chunks in this collection yet</p>
                <p className="text-sm text-muted">
                  Add chunks from search results or document views using the &quot;Add to Collection&quot; button.
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                {collection.items.map((item) => (
                  <div
                    key={item.id}
                    className="border border-line rounded-lg p-4"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-2">
                          <code className="text-xs bg-surface px-2 py-0.5 rounded text-secondary">
                            {item.chunk_id.slice(0, 8)}...
                          </code>
                          {item.document_id && (
                            <Link
                              href={`/documents/${item.document_id}`}
                              className="text-xs text-accent-text underline underline-offset-4"
                            >
                              View document
                            </Link>
                          )}
                        </div>

                        {item.chunk_content && (
                          <p className="text-sm text-secondary whitespace-pre-wrap">
                            {item.chunk_content}
                            {item.chunk_content.length >= 200 && "..."}
                          </p>
                        )}

                        {item.notes && (
                          <p className="mt-2 text-sm text-muted italic">
                            Note: {item.notes}
                          </p>
                        )}

                        <p className="mt-2 text-xs text-muted">
                          Added {formatDistanceToNow(parseApiTimestamp(item.added_at), { addSuffix: true })}
                        </p>
                      </div>

                      <button
                        onClick={() => handleRemoveChunk(item)}
                        className="px-3 py-1 text-sm text-danger hover:bg-danger-surface rounded flex-shrink-0"
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
