/**
 * Document detail page
 */

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
  const [processing, setProcessing] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [chunksPage, setChunksPage] = useState(1);
  const [expandedChunks, setExpandedChunks] = useState<Set<string>>(new Set());

  const { data: document, mutate } = useSWR<Document>(
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
      alert(message);
    } finally {
      setProcessing(false);
    }
  };

  const handleDelete = async () => {
    if (!id || !confirm("Are you sure you want to delete this document?")) return;

    try {
      await documentsApi.deleteDocument(id as string);
      router.push("/documents");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to delete document";
      alert(message);
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
      alert(message);
    } finally {
      setDownloading(false);
    }
  };

  if (!document) {
    return (
      <AuthGate>
        <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
          <p className="text-gray-500">Loading document...</p>
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
            href="/documents"
            className="text-blue-600 dark:text-blue-400 hover:underline mb-4 inline-block"
          >
            ← Back to Documents
          </Link>

          {/* Header */}
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6 mb-6">
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">
              {document.name}
            </h1>

            {/* Document Stats - Prominently displayed */}
            {document.chunked && (document.chunk_count || document.word_count || document.total_tokens) && (
              <div className="mb-6 flex flex-wrap gap-4">
                {document.chunk_count !== undefined && document.chunk_count > 0 && (
                  <div className="bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800 rounded-lg px-4 py-3">
                    <div className="text-2xl font-bold text-blue-700 dark:text-blue-300">
                      {document.chunk_count}
                    </div>
                    <div className="text-sm text-blue-600 dark:text-blue-400">Chunks</div>
                  </div>
                )}
                {document.word_count !== undefined && document.word_count > 0 && (
                  <div className="bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 rounded-lg px-4 py-3">
                    <div className="text-2xl font-bold text-green-700 dark:text-green-300">
                      {document.word_count.toLocaleString()}
                    </div>
                    <div className="text-sm text-green-600 dark:text-green-400">Words</div>
                  </div>
                )}
                {document.total_tokens !== undefined && document.total_tokens > 0 && (
                  <div className="bg-purple-50 dark:bg-purple-900/30 border border-purple-200 dark:border-purple-800 rounded-lg px-4 py-3">
                    <div className="text-2xl font-bold text-purple-700 dark:text-purple-300">
                      {document.total_tokens.toLocaleString()}
                    </div>
                    <div className="text-sm text-purple-600 dark:text-purple-400">Tokens</div>
                  </div>
                )}
              </div>
            )}

            {/* Content Preview */}
            {document.preview && (
              <div className="mb-6 bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
                <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-2">
                  Content Preview
                </h3>
                <p className="text-sm text-gray-600 dark:text-gray-300 whitespace-pre-wrap">
                  {document.preview}
                </p>
              </div>
            )}

            {/* Metadata */}
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-gray-500 dark:text-gray-400">File Type:</span>
                <span className="ml-2 text-gray-900 dark:text-white">
                  {document.file_type || document.mime_type || "Unknown"}
                </span>
              </div>
              {document.file_size && (
                <div>
                  <span className="text-gray-500 dark:text-gray-400">File Size:</span>
                  <span className="ml-2 text-gray-900 dark:text-white">
                    {(document.file_size / 1024).toFixed(2)} KB
                  </span>
                </div>
              )}
              {document.uploaded_at && (
                <div>
                  <span className="text-gray-500 dark:text-gray-400">Uploaded:</span>
                  <span className="ml-2 text-gray-900 dark:text-white">
                    {formatDistanceToNow(new Date(document.uploaded_at), { addSuffix: true })}
                  </span>
                </div>
              )}
              {document.source_type && (
                <div>
                  <span className="text-gray-500 dark:text-gray-400">Source:</span>
                  <span className="ml-2 text-gray-900 dark:text-white">
                    {document.source_type}
                  </span>
                </div>
              )}
            </div>

            {/* Processing Status */}
            <div className="mt-6">
              <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-3">
                Processing Status
              </h3>
              <div className="space-y-2">
                <StatusRow label="Processed" status={document.processed} />
                <StatusRow label="Chunked" status={document.chunked} />
                <StatusRow label="Embedded" status={document.embedded} />
              </div>
              {document.validation_status && (
                <div className="mt-4">
                  <span className="text-sm text-gray-500 dark:text-gray-400">Validation Status: </span>
                  <span className={`text-sm font-medium ${
                    document.validation_status === "completed" ? "text-green-600 dark:text-green-400" : "text-yellow-600 dark:text-yellow-400"
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
                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
              >
                {downloading ? "Downloading..." : "Download Original"}
              </button>
              {!document.processed && (
                <button
                  onClick={handleProcess}
                  disabled={processing}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
                >
                  {processing ? "Processing..." : "Process Document"}
                </button>
              )}
              <button
                onClick={handleDelete}
                className="px-4 py-2 border border-red-600 text-red-600 dark:text-red-400 rounded-lg hover:bg-red-50 dark:hover:bg-gray-700 transition-colors"
              >
                Delete Document
              </button>
            </div>
          </div>

          {/* Processing Events */}
          {document.processing_events && document.processing_events.length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6 mb-6">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                Processing History
              </h2>
              <div className="space-y-3">
                {document.processing_events.map((event) => (
                  <div
                    key={event.id}
                    className="border-l-4 border-blue-500 pl-4 py-2"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-gray-900 dark:text-white">
                        {event.stage}
                      </span>
                      <span className={`text-sm ${
                        event.status === "succeeded" ? "text-green-600 dark:text-green-400" :
                        event.status === "failed" ? "text-red-600 dark:text-red-400" :
                        "text-yellow-600 dark:text-yellow-400"
                      }`}>
                        {event.status}
                      </span>
                    </div>
                    {event.message && (
                      <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                        {event.message}
                      </p>
                    )}
                    <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                      {formatDistanceToNow(new Date(event.created_at), { addSuffix: true })}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Document Chunks */}
          {document.chunked && (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                Document Chunks
                {chunksResponse && (
                  <span className="ml-2 text-sm font-normal text-gray-500 dark:text-gray-400">
                    ({chunksResponse.pagination.total} total)
                  </span>
                )}
              </h2>

              {chunksLoading && (
                <p className="text-gray-500 dark:text-gray-400">Loading chunks...</p>
              )}

              {chunksResponse && chunksResponse.data.length > 0 && (
                <>
                  <div className="space-y-3">
                    {chunksResponse.data.map((chunk) => (
                      <div
                        key={chunk.id}
                        className="border border-gray-200 dark:border-gray-600 rounded-lg overflow-hidden"
                      >
                        <button
                          onClick={() => toggleChunk(chunk.id)}
                          className="w-full px-4 py-3 flex items-center justify-between bg-gray-50 dark:bg-gray-700 hover:bg-gray-100 dark:hover:bg-gray-600 transition-colors"
                        >
                          <div className="flex items-center gap-4">
                            <span className="font-mono text-sm text-blue-600 dark:text-blue-400">
                              #{chunk.chunk_index}
                            </span>
                            {chunk.token_count && (
                              <span className="text-xs text-gray-500 dark:text-gray-400 bg-gray-200 dark:bg-gray-600 px-2 py-0.5 rounded">
                                {chunk.token_count} tokens
                              </span>
                            )}
                          </div>
                          <span className="text-gray-400">
                            {expandedChunks.has(chunk.id) ? "−" : "+"}
                          </span>
                        </button>
                        {expandedChunks.has(chunk.id) && (
                          <div className="px-4 py-3 bg-white dark:bg-gray-800">
                            <pre className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap font-mono overflow-x-auto">
                              {chunk.content}
                            </pre>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>

                  {/* Pagination */}
                  {chunksResponse.pagination.pages > 1 && (
                    <div className="mt-4 flex items-center justify-between">
                      <button
                        onClick={() => setChunksPage((p) => Math.max(1, p - 1))}
                        disabled={chunksPage === 1}
                        className="px-3 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-100 dark:hover:bg-gray-700"
                      >
                        Previous
                      </button>
                      <span className="text-sm text-gray-600 dark:text-gray-400">
                        Page {chunksResponse.pagination.page} of {chunksResponse.pagination.pages}
                      </span>
                      <button
                        onClick={() => setChunksPage((p) => Math.min(chunksResponse.pagination.pages, p + 1))}
                        disabled={chunksPage >= chunksResponse.pagination.pages}
                        className="px-3 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-100 dark:hover:bg-gray-700"
                      >
                        Next
                      </button>
                    </div>
                  )}
                </>
              )}

              {chunksResponse && chunksResponse.data.length === 0 && (
                <p className="text-gray-500 dark:text-gray-400">No chunks available.</p>
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
        status ? "bg-green-500" : "bg-gray-300 dark:bg-gray-600"
      }`} />
      <span className="text-sm text-gray-900 dark:text-white">{label}</span>
      <span className="text-sm text-gray-500 dark:text-gray-400">
        {status ? "Complete" : "Pending"}
      </span>
    </div>
  );
}
