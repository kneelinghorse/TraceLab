/**
 * Report detail page
 */

import { AuthGate } from "@/components/AuthGate";
import { reportsApi, type ReportDetail, type ReportStatus } from "@/lib/api/reports";
import { formatDistanceToNow } from "date-fns";
import Link from "next/link";
import { useRouter } from "next/router";
import { useState } from "react";
import useSWR from "swr";

export default function ReportDetailPage() {
  const router = useRouter();
  const { id } = router.query;
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editError, setEditError] = useState<string | null>(null);
  const [isCopied, setIsCopied] = useState(false);

  const { data: report, mutate, isLoading } = useSWR<ReportDetail>(
    id ? `report-${id}` : null,
    () => reportsApi.get(id as string)
  );

  const handleStartEdit = () => {
    if (!report) return;
    setEditTitle(report.title);
    setIsEditing(true);
  };

  const handleSaveEdit = async () => {
    if (!report || !editTitle.trim()) {
      setEditError("Title is required");
      return;
    }

    setEditError(null);
    try {
      await reportsApi.update(report.id, { title: editTitle.trim() });
      setIsEditing(false);
      mutate();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to update report";
      setEditError(message);
    }
  };

  const handleToggleStatus = async () => {
    if (!report) return;
    const newStatus: ReportStatus = report.status === "draft" ? "final" : "draft";
    try {
      await reportsApi.update(report.id, { status: newStatus });
      mutate();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to update status";
      alert(message);
    }
  };

  const handleDelete = async () => {
    if (!report) return;
    if (!confirm(`Delete report "${report.title}"? This cannot be undone.`)) {
      return;
    }

    try {
      await reportsApi.delete(report.id);
      router.push("/reports");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to delete report";
      alert(message);
    }
  };

  const handleCopy = async () => {
    if (!report) return;
    try {
      await navigator.clipboard.writeText(report.content);
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), 2000);
    } catch (error) {
      alert("Failed to copy to clipboard");
    }
  };

  const getStatusBadge = (status: ReportStatus) => {
    const baseClasses = "px-3 py-1 rounded-full text-sm font-medium cursor-pointer transition-colors";
    if (status === "final") {
      return (
        <button
          onClick={handleToggleStatus}
          className={`${baseClasses} bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 hover:bg-green-200 dark:hover:bg-green-900/50`}
          title="Click to change to draft"
        >
          Final
        </button>
      );
    }
    return (
      <button
        onClick={handleToggleStatus}
        className={`${baseClasses} bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400 hover:bg-yellow-200 dark:hover:bg-yellow-900/50`}
        title="Click to finalize"
      >
        Draft
      </button>
    );
  };

  if (isLoading || !report) {
    return (
      <AuthGate>
        <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
          <p className="text-gray-500">Loading report...</p>
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
            href="/reports"
            className="text-blue-600 dark:text-blue-400 hover:underline mb-4 inline-block"
          >
            &larr; Back to Reports
          </Link>

          {/* Header */}
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6 mb-6">
            {isEditing ? (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Title *
                  </label>
                  <input
                    type="text"
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    autoFocus
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
                  <div className="flex items-center gap-3">
                    <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
                      {report.title}
                    </h1>
                    {getStatusBadge(report.status)}
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={handleCopy}
                      className="px-4 py-2 text-sm text-green-600 dark:text-green-400 hover:bg-green-50 dark:hover:bg-gray-700 rounded"
                    >
                      {isCopied ? "Copied!" : "Copy"}
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

                {/* Metadata */}
                <div className="mt-4 flex flex-wrap gap-4 text-sm text-gray-600 dark:text-gray-400">
                  <span>
                    Type: <span className="font-medium">{report.report_type}</span>
                  </span>
                  <span>
                    Chunks: <span className="font-medium text-blue-600 dark:text-blue-400">{report.chunk_count}</span>
                  </span>
                  <span>
                    Tokens: <span className="font-medium">{report.tokens_used.toLocaleString()}</span>
                  </span>
                  <span>
                    Created {formatDistanceToNow(new Date(report.created_at), { addSuffix: true })}
                  </span>
                  {report.updated_at !== report.created_at && (
                    <span>
                      Updated {formatDistanceToNow(new Date(report.updated_at), { addSuffix: true })}
                    </span>
                  )}
                </div>

                {report.prompt && (
                  <div className="mt-4 p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                    <span className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                      Custom Prompt
                    </span>
                    <p className="mt-1 text-sm text-gray-700 dark:text-gray-300 italic">
                      {report.prompt}
                    </p>
                  </div>
                )}
              </>
            )}
          </div>

          {/* Report Content */}
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6 mb-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Content
            </h2>
            <div className="prose prose-gray dark:prose-invert max-w-none">
              <div className="text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
                {report.content}
              </div>
            </div>
          </div>

          {/* Citations */}
          {report.citations && report.citations.length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6 mb-6">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                Citations ({report.citations.length})
              </h2>
              <div className="space-y-3">
                {report.citations.map((citation, index) => (
                  <div
                    key={`${citation.chunk_id}-${index}`}
                    className="border border-gray-200 dark:border-gray-600 rounded-lg p-4"
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <code className="text-xs bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded text-gray-600 dark:text-gray-300">
                        {citation.chunk_id.slice(0, 8)}...
                      </code>
                      {citation.document_id && (
                        <Link
                          href={`/documents/${citation.document_id}`}
                          className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                        >
                          View document
                        </Link>
                      )}
                    </div>
                    {citation.excerpt && (
                      <p className="text-sm text-gray-600 dark:text-gray-400 italic">
                        &quot;{citation.excerpt}&quot;
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Sources */}
          {report.sources && report.sources.length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                Sources ({report.sources.length})
              </h2>
              <div className="space-y-2">
                {report.sources.map((source) => (
                  <div
                    key={source.id}
                    className="flex items-center justify-between py-2 border-b border-gray-100 dark:border-gray-700 last:border-0"
                  >
                    <div className="flex items-center gap-3">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                        source.source_type === "collection"
                          ? "bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-400"
                          : "bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400"
                      }`}>
                        {source.source_type}
                      </span>
                      <code className="text-sm text-gray-600 dark:text-gray-400">
                        {source.source_id.slice(0, 8)}...
                      </code>
                    </div>
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      {formatDistanceToNow(new Date(source.added_at), { addSuffix: true })}
                    </span>
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
