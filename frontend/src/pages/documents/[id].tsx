/**
 * Document detail page
 */

import { AuthGate } from "@/components/AuthGate";
import { documentsApi } from "@/lib/api/documents";
import type { Document } from "@/types/document";
import { formatDistanceToNow } from "date-fns";
import Link from "next/link";
import { useRouter } from "next/router";
import { useState } from "react";
import useSWR from "swr";

export default function DocumentDetailPage() {
  const router = useRouter();
  const { id } = router.query;
  const [processing, setProcessing] = useState(false);

  const { data: document, mutate } = useSWR<Document>(
    id ? `document-${id}` : null,
    () => documentsApi.getDocument(id as string)
  );

  const handleProcess = async () => {
    if (!id) return;

    setProcessing(true);
    try {
      await documentsApi.processDocument(id as string);
      // Poll for updated status
      setTimeout(() => mutate(), 2000);
    } catch (error) {
      alert("Failed to process document");
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
      alert("Failed to delete document");
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
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
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

