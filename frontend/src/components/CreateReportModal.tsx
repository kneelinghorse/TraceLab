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
        className="fixed inset-0 bg-backdrop bg-opacity-50 transition-opacity"
        onClick={handleClose}
      />

      {/* Modal */}
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="relative w-full max-w-lg bg-surface dark:bg-surface rounded-lg shadow-xl">
          {/* Header */}
          <div className="px-6 py-4 border-b border-line dark:border-line">
            <h2 className="text-xl font-semibold text-foreground dark:text-foreground">
              Create Report
            </h2>
            <p className="mt-1 text-sm text-secondary dark:text-muted">
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
                  className="block text-sm font-medium text-secondary dark:text-secondary mb-1"
                >
                  Title *
                </label>
                <input
                  id="report-title"
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g., Research Summary - Q4 Findings"
                  className="w-full px-4 py-2 border border-line-strong dark:border-line-strong rounded-lg bg-surface dark:bg-surface-alt text-foreground dark:text-foreground focus:ring-2 focus:ring-focus focus:border-transparent"
                  disabled={isCreating}
                  autoFocus
                />
              </div>

              {/* Format */}
              <div>
                <label
                  htmlFor="report-format"
                  className="block text-sm font-medium text-secondary dark:text-secondary mb-1"
                >
                  Format
                </label>
                <select
                  id="report-format"
                  value={format}
                  onChange={(e) => setFormat(e.target.value as ReportFormat)}
                  className="w-full px-4 py-2 border border-line-strong dark:border-line-strong rounded-lg bg-surface dark:bg-surface-alt text-foreground dark:text-foreground focus:ring-2 focus:ring-focus focus:border-transparent"
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
                  className="block text-sm font-medium text-secondary dark:text-secondary mb-1"
                >
                  Custom Prompt (optional)
                </label>
                <textarea
                  id="report-prompt"
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="e.g., Focus on technical implementation details..."
                  rows={3}
                  className="w-full px-4 py-2 border border-line-strong dark:border-line-strong rounded-lg bg-surface dark:bg-surface-alt text-foreground dark:text-foreground focus:ring-2 focus:ring-focus focus:border-transparent resize-none"
                  disabled={isCreating}
                />
                <p className="mt-1 text-xs text-muted dark:text-muted">
                  Add specific instructions for the AI synthesis
                </p>
              </div>

              {/* Error */}
              {error && (
                <div className="p-3 bg-danger-surface dark:bg-danger-surface border border-danger-line dark:border-danger-line rounded-lg">
                  <p className="text-sm text-danger dark:text-danger">{error}</p>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="px-6 py-4 border-t border-line dark:border-line flex justify-end gap-3">
              <button
                type="button"
                onClick={handleClose}
                disabled={isCreating}
                className="px-4 py-2 text-secondary dark:text-muted hover:text-foreground dark:hover:text-foreground transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isCreating}
                className="px-4 py-2 bg-accent text-on-accent rounded-lg hover:bg-accent transition-colors disabled:bg-surface-alt disabled:cursor-not-allowed flex items-center gap-2"
              >
                {isCreating ? (
                  <>
                    <svg
                      className="animate-spin h-4 w-4 text-foreground"
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
