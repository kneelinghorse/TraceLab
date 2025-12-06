/**
 * Modal for creating a new report from a collection
 */

import { reportsApi, type ReportFormat } from "@/lib/api/reports";
import { useRouter } from "next/router";
import { useState } from "react";

type CreateReportModalProps = {
  collectionId: string;
  collectionName: string;
  isOpen: boolean;
  onClose: () => void;
};

export function CreateReportModal({
  collectionId,
  collectionName,
  isOpen,
  onClose,
}: CreateReportModalProps) {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [format, setFormat] = useState<ReportFormat>("summary");
  const [prompt, setPrompt] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setError("Title is required");
      return;
    }

    setError(null);
    setIsCreating(true);

    try {
      const report = await reportsApi.create({
        title: title.trim(),
        collection_id: collectionId,
        format,
        prompt: prompt.trim() || undefined,
      });
      router.push(`/reports/${report.id}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to create report";
      setError(message);
      setIsCreating(false);
    }
  };

  const handleClose = () => {
    if (isCreating) return;
    setTitle("");
    setFormat("summary");
    setPrompt("");
    setError(null);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black bg-opacity-50 transition-opacity"
        onClick={handleClose}
      />

      {/* Modal */}
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="relative w-full max-w-lg bg-white dark:bg-gray-800 rounded-lg shadow-xl">
          {/* Header */}
          <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
              Create Report
            </h2>
            <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
              Synthesize content from &quot;{collectionName}&quot;
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit}>
            <div className="px-6 py-4 space-y-4">
              {/* Title */}
              <div>
                <label
                  htmlFor="report-title"
                  className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                >
                  Title *
                </label>
                <input
                  id="report-title"
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g., Research Summary - Q4 Findings"
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  disabled={isCreating}
                  autoFocus
                />
              </div>

              {/* Format */}
              <div>
                <label
                  htmlFor="report-format"
                  className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                >
                  Format
                </label>
                <select
                  id="report-format"
                  value={format}
                  onChange={(e) => setFormat(e.target.value as ReportFormat)}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  disabled={isCreating}
                >
                  <option value="summary">Summary - Concise overview</option>
                  <option value="report">Report - Detailed analysis</option>
                  <option value="bullets">Bullets - Key points list</option>
                  <option value="markdown">Markdown - Formatted document</option>
                </select>
              </div>

              {/* Custom Prompt */}
              <div>
                <label
                  htmlFor="report-prompt"
                  className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                >
                  Custom Prompt (optional)
                </label>
                <textarea
                  id="report-prompt"
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="e.g., Focus on technical implementation details..."
                  rows={3}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
                  disabled={isCreating}
                />
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  Add specific instructions for the AI synthesis
                </p>
              </div>

              {/* Error */}
              {error && (
                <div className="p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg">
                  <p className="text-sm text-red-700 dark:text-red-400">{error}</p>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="px-6 py-4 border-t border-gray-200 dark:border-gray-700 flex justify-end gap-3">
              <button
                type="button"
                onClick={handleClose}
                disabled={isCreating}
                className="px-4 py-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isCreating}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {isCreating ? (
                  <>
                    <svg
                      className="animate-spin h-4 w-4 text-white"
                      xmlns="http://www.w3.org/2000/svg"
                      fill="none"
                      viewBox="0 0 24 24"
                    >
                      <circle
                        className="opacity-25"
                        cx="12"
                        cy="12"
                        r="10"
                        stroke="currentColor"
                        strokeWidth="4"
                      />
                      <path
                        className="opacity-75"
                        fill="currentColor"
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                      />
                    </svg>
                    Creating...
                  </>
                ) : (
                  "Create Report"
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
