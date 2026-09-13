import { HttpError } from "@/lib/api/http";
import { PaginationBar } from "@/components/ui/PaginationBar";
import { PageState } from "@/components/ui/PageState";
import { Dialog } from "@/components/ui/Dialog";
import { EvidencePanel } from "@/components/evidence/EvidencePanel";
import { TabList } from "@/components/ui/TabList";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useAuth } from "@/contexts/AuthContext";
import { documentState } from "@/lib/document-state";
import { parseApiTimestamp } from "@/lib/api/timestamps";
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
  const { query } = useRouter();
  return <DocumentDetail key={typeof query.id === "string" ? query.id : "loading"} />;
}

function DocumentDetail() {
  const { user } = useAuth();
  const router = useRouter();
  const { id } = router.query;
  const [actionError, setActionError] = useState<string | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [chunksPage, setChunksPage] = useState(1);
  const [expandedChunks, setExpandedChunks] = useState<Set<string>>(new Set());
  const [tab, setTab] = useState<"Overview" | "Chunks" | "Evidence">("Overview");

  const { data: document, mutate, error: loadError, isLoading } = useSWR<Document>(
    id ? ["document", user?.user_id, id] : null,
    () => documentsApi.getDocument(id as string)
  );

  const { data: chunksResponse, isLoading: chunksLoading, error: chunksError, mutate: mutateChunks } = useSWR<PaginatedResponse<DocumentChunk>>(
    document && id ? ["chunks", user?.user_id, id, chunksPage] : null,
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
    setActionError(null);
    try {
      const result = await documentsApi.processDocument(id as string);
      const failed = Object.entries(result.stages ?? {}).filter(([, stage]) => stage.status === "failed").map(([name]) => name);
      if (result.status !== "completed" || failed.length) setActionError(`Processing needs attention: ${failed.join(", ") || result.status || "unknown"}.`);
      await Promise.all([mutate(), mutateChunks()]);
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
      <div className="min-h-screen bg-background">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {actionError && !deleteOpen && <p role="alert" className="mb-4 break-words rounded bg-danger-surface p-4 text-danger">{actionError}</p>}
          <Dialog open={deleteOpen} title="Delete document" onClose={() => { if (!deleting) setDeleteOpen(false); }}>
            <p className="mb-4">Remove this document from active lists? It is retained for recovery.</p>
            {actionError && <p role="alert" className="mb-4 break-words text-danger">{actionError}</p>}
            <div className="flex gap-3"><button disabled={deleting} className="rounded border border-line px-3 py-2" onClick={() => setDeleteOpen(false)}>Cancel</button><button disabled={deleting} className="rounded bg-danger-surface px-3 py-2 text-danger" onClick={() => void handleDelete()}>{deleting ? "Deleting…" : "Delete document"}</button></div>
          </Dialog>
          {/* Back Link */}
          <Link
            href="/documents"
            className="text-accent-text underline underline-offset-4 mb-4 inline-block"
          >
            ← Back to Documents
          </Link>

          {/* Header */}
          <div className="bg-surface rounded-lg border border-line p-6 mb-6">
            <h1 className="break-words text-2xl font-bold text-foreground mb-4">
              {document.name}
            </h1>
            <div className="mb-4 flex flex-wrap items-center gap-4"><StatusBadge {...documentState(document)} /><Link className="text-sm text-accent-text underline" href={`/projects/${document.project_id}`}>Open project</Link></div>
            <div className="mb-4"><AddToCollection documentId={document.id} /></div>

            {/* Document Stats - Prominently displayed */}
            {(document.chunk_count != null || document.word_count != null || document.total_tokens != null) && (
              <div className="mb-6 flex flex-wrap gap-4">
                {document.chunk_count != null && (
                  <div className="bg-info-surface border border-info-line rounded-lg px-4 py-3">
                    <div className="text-2xl font-bold text-accent-text">
                      {document.chunk_count}
                    </div>
                    <div className="text-sm text-accent-text">Chunks</div>
                  </div>
                )}
                {document.word_count != null && (
                  <div className="bg-success-surface border border-success-line rounded-lg px-4 py-3">
                    <div className="text-2xl font-bold text-success">
                      {document.word_count.toLocaleString()}
                    </div>
                    <div className="text-sm text-success">Words</div>
                  </div>
                )}
                {document.total_tokens != null && (
                  <div className="bg-info-surface border border-info-line rounded-lg px-4 py-3">
                    <div className="text-2xl font-bold text-accent-text">
                      {document.total_tokens.toLocaleString()}
                    </div>
                    <div className="text-sm text-accent-text">Tokens</div>
                  </div>
                )}
              </div>
            )}

            {/* Content Preview */}
            {document.preview && (
              <div className="mb-6 bg-background rounded-lg p-4">
                <h3 className="text-sm font-medium text-foreground mb-2">
                  Content Preview
                </h3>
                <p className="text-sm text-secondary whitespace-pre-wrap">
                  {document.preview}
                </p>
              </div>
            )}

            {/* Metadata */}
            <div className="grid gap-4 break-words text-sm sm:grid-cols-2">
              <div>
                <span className="text-muted">File Type:</span>
                <span className="ml-2 text-foreground">
                  {document.file_type || document.mime_type || "Unknown"}
                </span>
              </div>
              {document.file_size && (
                <div>
                  <span className="text-muted">File Size:</span>
                  <span className="ml-2 text-foreground">
                    {(document.file_size / 1024).toFixed(2)} KB
                  </span>
                </div>
              )}
              {document.uploaded_at && (
                <div>
                  <span className="text-muted">Uploaded:</span>
                  <span className="ml-2 text-foreground">
                  {formatDistanceToNow(parseApiTimestamp(document.uploaded_at), { addSuffix: true })}
                  </span>
                </div>
              )}
              {document.source_type && (
                <div>
                  <span className="text-muted">Source:</span>
                  <span className="ml-2 text-foreground">
                    {document.source_type}
                  </span>
                </div>
              )}
            </div>

            {/* Processing Status */}
            <div className="mt-6">
              <h3 className="text-sm font-medium text-foreground mb-3">
                Processing Status
              </h3>
              <div className="space-y-2">
                <StatusRow label="Processed" status={document.processed} />
                <StatusRow label="Chunked" status={document.chunked} />
                <StatusRow label="Embedded" status={document.embedded} />
              </div>
              {document.validation_status && (
                <div className="mt-4">
                  <span className="text-sm text-muted">Validation Status: </span>
                  <span className={`text-sm font-medium ${
                    document.validation_status === "completed" ? "text-success" : "text-warning"
                  }`}>
                    {document.validation_status}
                  </span>
                </div>
              )}
            </div>

            {/* Actions */}
            <div className="mt-6 flex flex-wrap gap-4">
              <button
                onClick={handleDownload}
                disabled={downloading}
                className="px-4 py-2 bg-success-surface text-success rounded-lg hover:bg-success-surface disabled:bg-surface-alt disabled:cursor-not-allowed transition-colors"
              >
                {downloading ? "Downloading..." : "Download Original"}
              </button>
              {document.processed !== true && (
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
                className="px-4 py-2 border border-danger-line text-danger rounded-lg hover:bg-danger-surface transition-colors"
              >
                Delete Document
              </button>
            </div>
          </div>

          <TabList id="document" label="Document sections" tabs={["Overview", "Chunks", "Evidence"] as const} value={tab} onChange={setTab} />
          <div id="document-panel" role="tabpanel" aria-labelledby={`document-${tab}`} className="mt-6">
          {tab === "Evidence" && <EvidencePanel projectId={document.project_id} filters={{ document_id: document.id }} />}
          {tab === "Overview" && !document.processing_events?.length && <p className="panel p-5 text-secondary">No processing history has been recorded.</p>}

          {/* Processing Events */}
          {tab === "Overview" && document.processing_events && document.processing_events.length > 0 && (
            <div className="bg-surface rounded-lg border border-line p-6 mb-6">
              <h2 className="text-lg font-semibold text-foreground mb-4">
                Processing History
              </h2>
              <div className="space-y-3">
                {document.processing_events.map((event) => (
                  <div
                    key={event.id}
                    className="border-l-4 border-info-line pl-4 py-2"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-foreground">
                        {event.stage}
                      </span>
                      <span className={`text-sm ${
                        event.status === "succeeded" ? "text-success" :
                        event.status === "failed" ? "text-danger" :
                        "text-warning"
                      }`}>
                        {event.status}
                      </span>
                    </div>
                    {event.message && (
                      <p className="text-sm text-secondary mt-1">
                        {event.message}
                      </p>
                    )}
                    <p className="text-xs text-muted mt-1">
                      {formatDistanceToNow(parseApiTimestamp(event.created_at), { addSuffix: true })}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Document Chunks */}
          {tab === "Chunks" && (
            <div className="bg-surface rounded-lg border border-line p-6">
              <h2 className="text-lg font-semibold text-foreground mb-4">
                Document Chunks
                {chunksResponse && (
                  <span className="ml-2 text-sm font-normal text-muted">
                    ({chunksResponse.pagination.total} total)
                  </span>
                )}
              </h2>

              {chunksLoading && (
                <p role="status" className="text-muted">Loading chunks...</p>
              )}
              {chunksError && <PageState state="error" title="Chunks could not load." onRetry={() => void mutateChunks()} />}

              {chunksResponse && chunksResponse.data.length > 0 && (
                <>
                  <div className="space-y-3">
                    {chunksResponse.data.map((chunk) => (
                      <div
                        key={chunk.id}
                        className="border border-line rounded-lg overflow-hidden"
                      >
                        <div className="px-4 py-3 flex items-center justify-between bg-background">
                          <button
                            onClick={() => toggleChunk(chunk.id)}
                            aria-expanded={expandedChunks.has(chunk.id)}
                            aria-controls={`chunk-${chunk.id}`}
                            className="flex flex-wrap items-center gap-4 hover:text-accent-text transition-colors"
                          >
                            <span className="font-mono text-sm text-accent-text">
                              #{chunk.chunk_index}
                            </span>
                            {chunk.token_count && (
                              <span className="text-xs text-muted bg-surface-alt px-2 py-0.5 rounded">
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
                          <div id={`chunk-${chunk.id}`} className="px-4 py-3 bg-surface">
                            {(chunk.start_char != null || chunk.end_char != null) && <p className="mb-2 text-xs text-muted">Source characters: {chunk.start_char ?? "unknown"}–{chunk.end_char ?? "unknown"}</p>}
                            <pre className="whitespace-pre-wrap text-sm text-secondary [overflow-wrap:anywhere]">
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
                <p className="text-muted">No chunks available.</p>
              )}
            </div>
          )}
          </div>
        </div>
      </div>
    </AuthGate>
  );
}

function StatusRow({ label, status }: { label: string; status: boolean | null | undefined }) {
  return (
    <div className="flex items-center gap-3">
      <div className={`w-4 h-4 rounded-full ${
        status ? "bg-success" : "bg-surface-alt"
      }`} />
      <span className="text-sm text-foreground">{label}</span>
      <span className="text-sm text-muted">
        {status === true ? "Complete" : status === false ? "Pending" : "Unknown"}
      </span>
    </div>
  );
}
