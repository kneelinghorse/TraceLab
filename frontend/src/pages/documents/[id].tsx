import { HttpError } from "@/lib/api/http";
import { PaginationBar } from "@/components/ui/PaginationBar";
import { PageState } from "@/components/ui/PageState";
import { Dialog } from "@/components/ui/Dialog";
import { EvidencePanel } from "@/components/evidence/EvidencePanel";
/**
 * Document detail page
 */

import { AddToCollection } from "@/components/AddToCollection";
import { AuthGate } from "@/components/AuthGate";
import { documentsApi } from "@/lib/api/documents";
import type { Document, DocumentChunk } from "@/types/document";
import type { PaginatedResponse } from "@/types/pagination";
import { formatDistanceToNow } from "date-fns";
import Link from "next/link";
import { useRouter } from "next/router";
import { useState } from "react";
import useSWR from "swr";

export default function DocumentDetailPage() {
  const router = useRouter();
  const { id } = router.query;
  const [actionError, setActionError] = useState<string | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [chunksPage, setChunksPage] = useState(1);
  const [expandedChunks, setExpandedChunks] = useState<Set<string>>(new Set());

  const { data: document, mutate, error: loadError, isLoading } = useSWR<Document>(
    id ? `document-${id}` : null,
    () => documentsApi.getDocument(id as string)
  );

  const { data: chunksResponse, isLoading: chunksLoading } = useSWR<PaginatedResponse<DocumentChunk>>(
    document?.chunked && id ? `chunks-${id}-${chunksPage}` : null,
    () => documentsApi.listChunks(id as string, { page: chunksPage, pageSize: 10 })
  );

  const toggleChunk = (chunkId: string) => {
    setExpandedChunks((prev) => {
      const next = new Set(prev);
      if (next.has(chunkId)) {
        next.delete(chunkId);
      } else {
        next.add(chunkId);
      }
      return next;
    });
  };

  const handleProcess = async () => {
    if (!id) return;

    setProcessing(true);
    try {
      await documentsApi.processDocument(id as string);
      // Poll for updated status
      setTimeout(() => mutate(), 2000);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to process document";
      setActionError(message);
    } finally {
      setProcessing(false);
    }
  };

  const handleDelete = async () => {
    if (!id) return;
    setDeleting(true);
    setActionError(null);

    try {
      await documentsApi.deleteDocument(id as string);
      router.push("/documents");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to delete document";
      setActionError(message);
    } finally {
      setDeleting(false);
    }
  };

  const handleDownload = async () => {
    if (!id || !document) return;

    setDownloading(true);
    try {
      const blob = await documentsApi.downloadDocument(id as string);
      const url = window.URL.createObjectURL(blob);
      const link = window.document.createElement("a");
      link.href = url;
      link.download = document.name;
      window.document.body.appendChild(link);
      link.click();
      window.document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to download document";
      setActionError(message);
    } finally {
      setDownloading(false);
    }
  };

  if (loadError instanceof HttpError && loadError.status === 404) return <AuthGate><PageState state="empty" title="Document not found." /></AuthGate>;
  if (loadError) return <AuthGate><PageState state="error" title="Document could not be loaded." onRetry={() => void mutate()} /></AuthGate>;
  if (!router.isReady || isLoading) return <AuthGate><PageState state="loading" title="Loading document…" /></AuthGate>;
  if (!document) return <AuthGate><PageState state="empty" title="Document not found." /></AuthGate>;

  return (
    <AuthGate>
      <div className="min-h-screen bg-background dark:bg-background">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {actionError && !deleteOpen && <p role="alert" className="mb-4 break-words rounded bg-danger-surface p-4 text-danger">{actionError}</p>}
          <Dialog open={deleteOpen} title="Delete document" onClose={() => { if (!deleting) setDeleteOpen(false); }}>
            <p className="mb-4">Delete this document? This cannot be undone.</p>
            {actionError && <p role="alert" className="mb-4 break-words text-danger">{actionError}</p>}
            <div className="flex gap-3"><button disabled={deleting} className="rounded border border-line px-3 py-2" onClick={() => setDeleteOpen(false)}>Cancel</button><button disabled={deleting} className="rounded bg-danger-surface px-3 py-2 text-danger" onClick={() => void handleDelete()}>{deleting ? "Deleting…" : "Delete document"}</button></div>
          </Dialog>
          {/* Back Link */}
          <Link
            href="/documents"
            className="text-accent-text dark:text-accent-text underline underline-offset-4 mb-4 inline-block"
          >
            ← Back to Documents
          </Link>

          <EvidencePanel projectId={document.project_id} filters={{ document_id: document.id }} />

          {/* Header */}
          <div className="bg-surface dark:bg-surface rounded-lg border border-line dark:border-line p-6 mb-6">
            <h1 className="text-2xl font-bold text-foreground dark:text-foreground mb-4">
              {document.name}
            </h1>

            {/* Document Stats - Prominently displayed */}
            {document.chunked && (document.chunk_count || document.word_count || document.total_tokens) && (
              <div className="mb-6 flex flex-wrap gap-4">
                {document.chunk_count !== undefined && document.chunk_count > 0 && (
                  <div className="bg-info-surface dark:bg-info-surface border border-info-line dark:border-info-line rounded-lg px-4 py-3">
                    <div className="text-2xl font-bold text-accent-text dark:text-accent-text">
                      {document.chunk_count}
                    </div>
                    <div className="text-sm text-accent-text dark:text-accent-text">Chunks</div>
                  </div>
                )}
                {document.word_count !== undefined && document.word_count > 0 && (
                  <div className="bg-success-surface dark:bg-success-surface border border-success-line dark:border-success-line rounded-lg px-4 py-3">
                    <div className="text-2xl font-bold text-success dark:text-success">
                      {document.word_count.toLocaleString()}
                    </div>
                    <div className="text-sm text-success dark:text-success">Words</div>
                  </div>
                )}
                {document.total_tokens !== undefined && document.total_tokens > 0 && (
                  <div className="bg-info-surface dark:bg-info-surface border border-info-line dark:border-info-line rounded-lg px-4 py-3">
                    <div className="text-2xl font-bold text-accent-text dark:text-accent-text">
                      {document.total_tokens.toLocaleString()}
                    </div>
                    <div className="text-sm text-accent-text dark:text-accent-text">Tokens</div>
                  </div>
                )}
              </div>
            )}

            {/* Content Preview */}
            {document.preview && (
              <div className="mb-6 bg-background dark:bg-surface-alt rounded-lg p-4">
                <h3 className="text-sm font-medium text-foreground dark:text-foreground mb-2">
                  Content Preview
                </h3>
                <p className="text-sm text-secondary dark:text-secondary whitespace-pre-wrap">
                  {document.preview}
                </p>
              </div>
            )}

            {/* Metadata */}
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-muted dark:text-muted">File Type:</span>
                <span className="ml-2 text-foreground dark:text-foreground">
                  {document.file_type || document.mime_type || "Unknown"}
                </span>
              </div>
              {document.file_size && (
                <div>
                  <span className="text-muted dark:text-muted">File Size:</span>
                  <span className="ml-2 text-foreground dark:text-foreground">
                    {(document.file_size / 1024).toFixed(2)} KB
                  </span>
                </div>
              )}
              {document.uploaded_at && (
                <div>
                  <span className="text-muted dark:text-muted">Uploaded:</span>
                  <span className="ml-2 text-foreground dark:text-foreground">
                    {formatDistanceToNow(new Date(document.uploaded_at), { addSuffix: true })}
                  </span>
                </div>
              )}
              {document.source_type && (
                <div>
                  <span className="text-muted dark:text-muted">Source:</span>
                  <span className="ml-2 text-foreground dark:text-foreground">
                    {document.source_type}
                  </span>
                </div>
              )}
            </div>

            {/* Processing Status */}
            <div className="mt-6">
              <h3 className="text-sm font-medium text-foreground dark:text-foreground mb-3">
                Processing Status
              </h3>
              <div className="space-y-2">
                <StatusRow label="Processed" status={document.processed} />
                <StatusRow label="Chunked" status={document.chunked} />
                <StatusRow label="Embedded" status={document.embedded} />
              </div>
              {document.validation_status && (
                <div className="mt-4">
                  <span className="text-sm text-muted dark:text-muted">Validation Status: </span>
                  <span className={`text-sm font-medium ${
                    document.validation_status === "completed" ? "text-success dark:text-success" : "text-warning dark:text-warning"
                  }`}>
                    {document.validation_status}
                  </span>
                </div>
              )}
            </div>

            {/* Actions */}
            <div className="mt-6 flex gap-4">
              <button
                onClick={handleDownload}
                disabled={downloading}
                className="px-4 py-2 bg-success-surface text-success rounded-lg hover:bg-success-surface disabled:bg-surface-alt disabled:cursor-not-allowed transition-colors"
              >
                {downloading ? "Downloading..." : "Download Original"}
              </button>
              {!document.processed && (
                <button
                  onClick={handleProcess}
                  disabled={processing}
                  className="px-4 py-2 bg-accent text-on-accent rounded-lg hover:bg-accent disabled:bg-surface-alt disabled:cursor-not-allowed transition-colors"
                >
                  {processing ? "Processing..." : "Process Document"}
                </button>
              )}
              <button
                onClick={() => { setActionError(null); setDeleteOpen(true); }}
                className="px-4 py-2 border border-danger-line text-danger dark:text-danger rounded-lg hover:bg-danger-surface dark:hover:bg-surface-alt transition-colors"
              >
                Delete Document
              </button>
            </div>
          </div>

          {/* Processing Events */}
          {document.processing_events && document.processing_events.length > 0 && (
            <div className="bg-surface dark:bg-surface rounded-lg border border-line dark:border-line p-6 mb-6">
              <h2 className="text-lg font-semibold text-foreground dark:text-foreground mb-4">
                Processing History
              </h2>
              <div className="space-y-3">
                {document.processing_events.map((event) => (
                  <div
                    key={event.id}
                    className="border-l-4 border-info-line pl-4 py-2"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-foreground dark:text-foreground">
                        {event.stage}
                      </span>
                      <span className={`text-sm ${
                        event.status === "succeeded" ? "text-success dark:text-success" :
                        event.status === "failed" ? "text-danger dark:text-danger" :
                        "text-warning dark:text-warning"
                      }`}>
                        {event.status}
                      </span>
                    </div>
                    {event.message && (
                      <p className="text-sm text-secondary dark:text-muted mt-1">
                        {event.message}
                      </p>
                    )}
                    <p className="text-xs text-muted dark:text-muted mt-1">
                      {formatDistanceToNow(new Date(event.created_at), { addSuffix: true })}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Document Chunks */}
          {document.chunked && (
            <div className="bg-surface dark:bg-surface rounded-lg border border-line dark:border-line p-6">
              <h2 className="text-lg font-semibold text-foreground dark:text-foreground mb-4">
                Document Chunks
                {chunksResponse && (
                  <span className="ml-2 text-sm font-normal text-muted dark:text-muted">
                    ({chunksResponse.pagination.total} total)
                  </span>
                )}
              </h2>

              {chunksLoading && (
                <p className="text-muted dark:text-muted">Loading chunks...</p>
              )}

              {chunksResponse && chunksResponse.data.length > 0 && (
                <>
                  <div className="space-y-3">
                    {chunksResponse.data.map((chunk) => (
                      <div
                        key={chunk.id}
                        className="border border-line dark:border-line-strong rounded-lg overflow-hidden"
                      >
                        <div className="px-4 py-3 flex items-center justify-between bg-background dark:bg-surface-alt">
                          <button
                            onClick={() => toggleChunk(chunk.id)}
                            className="flex items-center gap-4 hover:text-accent-text dark:hover:text-accent-text transition-colors"
                          >
                            <span className="font-mono text-sm text-accent-text dark:text-accent-text">
                              #{chunk.chunk_index}
                            </span>
                            {chunk.token_count && (
                              <span className="text-xs text-muted dark:text-muted bg-surface-alt dark:bg-surface-alt px-2 py-0.5 rounded">
                                {chunk.token_count} tokens
                              </span>
                            )}
                            <span className="text-muted">
                              {expandedChunks.has(chunk.id) ? "−" : "+"}
                            </span>
                          </button>
                          <AddToCollection chunkId={chunk.id} variant="compact" />
                        </div>
                        {expandedChunks.has(chunk.id) && (
                          <div className="px-4 py-3 bg-surface dark:bg-surface">
                            <pre className="text-sm text-secondary dark:text-secondary whitespace-pre-wrap font-mono overflow-x-auto">
                              {chunk.content}
                            </pre>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>

                  {/* Pagination */}
                  <PaginationBar page={chunksPage} pages={chunksResponse.pagination.pages} onChange={setChunksPage} label="Document chunk pages" />
                </>
              )}

              {chunksResponse && chunksResponse.data.length === 0 && (
                <p className="text-muted dark:text-muted">No chunks available.</p>
              )}
            </div>
          )}
        </div>
      </div>
    </AuthGate>
  );
}

function StatusRow({ label, status }: { label: string; status: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <div className={`w-4 h-4 rounded-full ${
        status ? "bg-success" : "bg-surface-alt dark:bg-surface-alt"
      }`} />
      <span className="text-sm text-foreground dark:text-foreground">{label}</span>
      <span className="text-sm text-muted dark:text-muted">
        {status ? "Complete" : "Pending"}
      </span>
    </div>
  );
}
