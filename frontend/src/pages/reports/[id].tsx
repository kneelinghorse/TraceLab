import { Dialog } from "@/components/ui/Dialog";
import { EvidencePanel } from "@/components/evidence/EvidencePanel";
/**
 * Report detail page
 */

import { AuthGate } from "@/components/AuthGate";
import { MarkdownRenderer } from "@/components/MarkdownRenderer";
import { reportsApi, type ReportDetail, type ReportStatus } from "@/lib/api/reports";
import { formatDistanceToNow } from "date-fns";
import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useRef, useState } from "react";
import useSWR from "swr";

export default function ReportDetailPage() {
  const router = useRouter();
  const { id } = router.query;
  const [actionError, setActionError] = useState<string | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editError, setEditError] = useState<string | null>(null);
  const [isCopied, setIsCopied] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [showExportMenu, setShowExportMenu] = useState(false);
  const exportRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (exportRef.current && !exportRef.current.contains(e.target as Node)) {
        setShowExportMenu(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const { data: report, mutate, isLoading, error: loadError } = useSWR<ReportDetail>(
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
      setActionError(message);
    }
  };

  const handleDelete = async () => {
    if (!report) return;
    setDeleting(true);
    setActionError(null);

    try {
      await reportsApi.delete(report.id);
      router.push("/reports");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to delete report";
      setActionError(message);
    } finally {
      setDeleting(false);
    }
  };

  const handleCopy = async () => {
    if (!report) return;
    try {
      await navigator.clipboard.writeText(report.content);
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), 2000);
    } catch {
      setActionError("Failed to copy to clipboard");
    }
  };

  const handleExport = async (format: "md" | "json" | "txt") => {
    if (!report) return;
    setIsExporting(true);
    try {
      const blob = await reportsApi.exportReport(report.id, format);
      const safeTitle = report.title.replace(/\s+/g, "-").replace(/\//g, "-").slice(0, 80);
      const ext = format;
      const url = window.URL.createObjectURL(blob);
      const link = window.document.createElement("a");
      link.href = url;
      link.download = `${safeTitle}.${ext}`;
      window.document.body.appendChild(link);
      link.click();
      window.document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Export failed";
      setActionError(message);
    } finally {
      setIsExporting(false);
    }
  };

  const getStatusBadge = (status: ReportStatus) => {
    const baseClasses = "px-3 py-1 rounded-full text-sm font-medium cursor-pointer transition-colors";
    if (status === "final") {
      return (
        <button
          onClick={handleToggleStatus}
          className={`${baseClasses} bg-success-surface dark:bg-success-surface text-success dark:text-success hover:bg-success-surface dark:hover:bg-success-surface`}
          title="Click to change to draft"
        >
          Final
        </button>
      );
    }
    return (
      <button
        onClick={handleToggleStatus}
        className={`${baseClasses} bg-warning-surface dark:bg-warning-surface text-warning dark:text-warning hover:bg-warning-surface dark:hover:bg-warning-surface`}
        title="Click to finalize"
      >
        Draft
      </button>
    );
  };

  if (loadError) return <AuthGate><div role="alert" className="p-6">Report could not be loaded. <button className="underline" onClick={() => void mutate()}>Retry</button></div></AuthGate>;

  if (isLoading || !report) {
    return (
      <AuthGate>
        <div className="min-h-screen bg-background dark:bg-background flex items-center justify-center">
          <p className="text-muted">Loading report...</p>
        </div>
      </AuthGate>
    );
  }

  return (
    <AuthGate>
      <div className="min-h-screen bg-background dark:bg-background">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {actionError && !deleteOpen && <p role="alert" className="mb-4 break-words rounded bg-danger-surface p-4 text-danger">{actionError}</p>}
          <Dialog open={deleteOpen} title="Delete report" onClose={() => { if (!deleting) setDeleteOpen(false); }}>
            <p className="mb-4">Delete this report? This cannot be undone.</p>
            {actionError && <p role="alert" className="mb-4 break-words text-danger">{actionError}</p>}
            <div className="flex gap-3"><button disabled={deleting} className="rounded border border-line px-3 py-2" onClick={() => setDeleteOpen(false)}>Cancel</button><button disabled={deleting} className="rounded bg-danger-surface px-3 py-2 text-danger" onClick={() => void handleDelete()}>{deleting ? "Deleting…" : "Delete report"}</button></div>
          </Dialog>
          {/* Back Link */}
          <Link
            href="/reports"
            className="text-accent-text dark:text-accent-text underline underline-offset-4 mb-4 inline-block"
          >
            &larr; Back to Reports
          </Link>

          {/* Header */}
          <div className="bg-surface dark:bg-surface rounded-lg border border-line dark:border-line p-6 mb-6">
            {isEditing ? (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-secondary dark:text-secondary mb-1">
                    Title *
                  </label>
                  <input
                    type="text"
                    aria-label="Report title"
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    className="w-full px-4 py-2 border border-line-strong dark:border-line-strong rounded-lg bg-surface dark:bg-surface-alt text-foreground dark:text-foreground"
                    autoFocus
                  />
                </div>
                {editError && (
                  <p className="text-sm text-danger dark:text-danger">{editError}</p>
                )}
                <div className="flex gap-3">
                  <button
                    onClick={handleSaveEdit}
                    className="px-4 py-2 bg-accent text-on-accent rounded-lg hover:bg-accent transition-colors"
                  >
                    Save
                  </button>
                  <button
                    onClick={() => {
                      setIsEditing(false);
                      setEditError(null);
                    }}
                    className="px-4 py-2 text-secondary dark:text-muted hover:text-foreground dark:hover:text-foreground transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                  <div className="flex items-center gap-3">
                    <h1 className="text-2xl font-bold text-foreground dark:text-foreground">
                      {report.title}
                    </h1>
                    {getStatusBadge(report.status)}
                  </div>
                  <div className="flex max-w-full flex-wrap gap-2">
                    <div className="relative" ref={exportRef}>
                      <button
                        onClick={() => setShowExportMenu((v) => !v)}
                        disabled={isExporting}
                        className="px-4 py-2 text-sm text-accent-text dark:text-accent-text hover:bg-info-surface dark:hover:bg-surface-alt rounded disabled:opacity-50"
                      >
                        {isExporting ? "Exporting..." : "Export ▾"}
                      </button>
                      {showExportMenu && (
                        <div className="absolute right-0 top-full mt-1 bg-surface dark:bg-surface border border-line dark:border-line-strong rounded-lg shadow-lg z-10 min-w-[140px]">
                          <button
                            onClick={() => { handleExport("md"); setShowExportMenu(false); }}
                            className="block w-full text-left px-4 py-2 text-sm text-secondary dark:text-secondary hover:bg-surface dark:hover:bg-surface-alt rounded-t-lg"
                          >
                            Markdown (.md)
                          </button>
                          <button
                            onClick={() => { handleExport("json"); setShowExportMenu(false); }}
                            className="block w-full text-left px-4 py-2 text-sm text-secondary dark:text-secondary hover:bg-surface dark:hover:bg-surface-alt"
                          >
                            JSON (.json)
                          </button>
                          <button
                            onClick={() => { handleExport("txt"); setShowExportMenu(false); }}
                            className="block w-full text-left px-4 py-2 text-sm text-secondary dark:text-secondary hover:bg-surface dark:hover:bg-surface-alt rounded-b-lg"
                          >
                            Plain text (.txt)
                          </button>
                        </div>
                      )}
                    </div>
                    <button
                      onClick={handleCopy}
                      className="px-4 py-2 text-sm text-success dark:text-success hover:bg-success-surface dark:hover:bg-surface-alt rounded"
                    >
                      {isCopied ? "Copied!" : "Copy"}
                    </button>
                    <button
                      onClick={handleStartEdit}
                      className="px-4 py-2 text-sm text-accent-text dark:text-accent-text hover:bg-info-surface dark:hover:bg-surface-alt rounded"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => { setActionError(null); setDeleteOpen(true); }}
                      className="px-4 py-2 text-sm text-danger dark:text-danger hover:bg-danger-surface dark:hover:bg-surface-alt rounded"
                    >
                      Delete
                    </button>
                  </div>
                </div>

                {/* Metadata */}
                <div className="mt-4 flex flex-wrap gap-4 text-sm text-secondary dark:text-muted">
                  <span>
                    Type: <span className="font-medium">{report.report_type}</span>
                  </span>
                  <span>
                    Chunks: <span className="font-medium text-accent-text dark:text-accent-text">{report.chunk_count}</span>
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
                  <div className="mt-4 p-3 bg-background dark:bg-surface-alt rounded-lg">
                    <span className="text-xs text-muted dark:text-muted uppercase tracking-wider">
                      Custom Prompt
                    </span>
                    <p className="mt-1 text-sm text-secondary dark:text-secondary italic">
                      {report.prompt}
                    </p>
                  </div>
                )}
              </>
            )}
          </div>

          <EvidencePanel projectId={report.project_id} filters={{ report_id: report.id }} />

          {/* Report Content */}
          <div className="bg-surface dark:bg-surface rounded-lg border border-line dark:border-line p-6 mb-6">
            <h2 className="text-lg font-semibold text-foreground dark:text-foreground mb-4">
              Content
            </h2>
            <MarkdownRenderer content={report.content} />
          </div>

          {/* Citations */}
          {report.citations && report.citations.length > 0 && (
            <div className="bg-surface dark:bg-surface rounded-lg border border-line dark:border-line p-6 mb-6">
              <h2 className="text-lg font-semibold text-foreground dark:text-foreground mb-4">
                Citations ({report.citations.length})
              </h2>
              <div className="space-y-3">
                {report.citations.map((citation, index) => (
                  <div
                    key={`${citation.chunk_id}-${index}`}
                    className="border border-line dark:border-line-strong rounded-lg p-4"
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <code className="text-xs bg-surface dark:bg-surface-alt px-2 py-0.5 rounded text-secondary dark:text-secondary">
                        {citation.chunk_id.slice(0, 8)}...
                      </code>
                      {citation.document_id && report.project_id && <Link className="text-xs text-accent-text underline" href={`/evidence?project_id=${report.project_id}&document_id=${citation.document_id}`}>Find evidence</Link>}
                      {citation.document_id && (
                        <Link
                          href={`/documents/${citation.document_id}`}
                          className="text-xs text-accent-text dark:text-accent-text underline underline-offset-4"
                        >
                          View document
                        </Link>
                      )}
                    </div>
                    {citation.excerpt && (
                      <p className="text-sm text-secondary dark:text-muted italic">
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
            <div className="bg-surface dark:bg-surface rounded-lg border border-line dark:border-line p-6">
              <h2 className="text-lg font-semibold text-foreground dark:text-foreground mb-4">
                Sources ({report.sources.length})
              </h2>
              <div className="space-y-2">
                {report.sources.map((source) => (
                  <div
                    key={source.id}
                    className="flex items-center justify-between py-2 border-b border-line dark:border-line last:border-0"
                  >
                    <div className="flex items-center gap-3">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                        source.source_type === "collection"
                          ? "bg-info-surface dark:bg-info-surface text-accent-text dark:text-accent-text"
                          : "bg-info-surface dark:bg-info-surface text-accent-text dark:text-accent-text"
                      }`}>
                        {source.source_type}
                      </span>
                      {source.source_type === "ledger_entry" && <Link className="text-sm text-accent-text underline" href={`/evidence/${source.source_id}`}>Open evidence</Link>}
                      <code className="text-sm text-secondary dark:text-muted">
                        {source.source_id.slice(0, 8)}...
                      </code>
                    </div>
                    <span className="text-xs text-muted dark:text-muted">
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
