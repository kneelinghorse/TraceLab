/**
 * Reports list page
 */

import { AuthGate } from "@/components/AuthGate";
import { reportsApi, type ReportListItem, type ReportStatus } from "@/lib/api/reports";
import { formatDistanceToNow } from "date-fns";
import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";

type StatusFilter = "all" | ReportStatus;

export default function ReportsPage() {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const { data: response, isLoading } = useSWR(
    ["reports", statusFilter, page],
    () =>
      reportsApi.list({
        status: statusFilter === "all" ? undefined : statusFilter,
        page,
        page_size: pageSize,
      })
  );

  const reports = response?.items ?? [];
  const total = response?.total ?? 0;
  const totalPages = Math.ceil(total / pageSize);

  const getStatusBadge = (status: ReportStatus) => {
    const baseClasses = "px-2 py-0.5 rounded-full text-xs font-medium";
    if (status === "final") {
      return (
        <span className={`${baseClasses} bg-success-surface dark:bg-success-surface text-success dark:text-success`}>
          Final
        </span>
      );
    }
    return (
      <span className={`${baseClasses} bg-warning-surface dark:bg-warning-surface text-warning dark:text-warning`}>
        Draft
      </span>
    );
  };

  return (
    <AuthGate>
      <div className="min-h-screen bg-background dark:bg-background">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-foreground dark:text-foreground">Reports</h1>
            <p className="mt-2 text-secondary dark:text-muted">
              View and manage synthesized reports from your collections
            </p>
          </div>

          {/* Filters */}
          <div className="mb-6 flex items-center gap-4">
            <span className="text-sm text-secondary dark:text-muted">Filter by status:</span>
            <div className="flex gap-2">
              {(["all", "draft", "final"] as const).map((status) => (
                <button
                  key={status}
                  onClick={() => {
                    setStatusFilter(status);
                    setPage(1);
                  }}
                  className={`px-3 py-1 rounded-md text-sm font-medium transition-colors ${
                    statusFilter === status
                      ? "bg-accent text-on-accent"
                      : "bg-surface dark:bg-surface text-secondary dark:text-muted border border-line-strong dark:border-line-strong hover:bg-background dark:hover:bg-surface-alt"
                  }`}
                >
                  {status.charAt(0).toUpperCase() + status.slice(1)}
                </button>
              ))}
            </div>
          </div>

          {/* Reports List */}
          {isLoading ? (
            <div className="text-center py-12">
              <p className="text-muted">Loading reports...</p>
            </div>
          ) : reports.length === 0 ? (
            <div className="text-center py-12 bg-surface dark:bg-surface rounded-lg border border-line dark:border-line">
              <p className="text-muted dark:text-muted mb-4">No reports yet</p>
              <p className="text-sm text-muted dark:text-muted">
                Create a report from a collection to synthesize content with AI.
              </p>
              <Link
                href="/collections"
                className="mt-4 inline-block px-4 py-2 bg-accent text-on-accent rounded-lg hover:bg-accent transition-colors"
              >
                Go to Collections
              </Link>
            </div>
          ) : (
            <>
              <div className="bg-surface dark:bg-surface rounded-lg border border-line dark:border-line overflow-hidden">
                <table className="min-w-full divide-y divide-line dark:divide-line">
                  <thead className="bg-background dark:bg-surface-alt">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-medium text-muted dark:text-muted uppercase tracking-wider">
                        Title
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-muted dark:text-muted uppercase tracking-wider">
                        Status
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-muted dark:text-muted uppercase tracking-wider">
                        Type
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-muted dark:text-muted uppercase tracking-wider">
                        Chunks
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-muted dark:text-muted uppercase tracking-wider">
                        Tokens
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-muted dark:text-muted uppercase tracking-wider">
                        Created
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-surface dark:bg-surface divide-y divide-line dark:divide-line">
                    {reports.map((report: ReportListItem) => (
                      <tr
                        key={report.id}
                        className="hover:bg-background dark:hover:bg-surface-alt cursor-pointer"
                        onClick={() => (window.location.href = `/reports/${report.id}`)}
                      >
                        <td className="px-6 py-4">
                          <Link
                            href={`/reports/${report.id}`}
                            className="text-foreground dark:text-foreground font-medium hover:text-accent-text dark:hover:text-accent-text"
                            onClick={(e) => e.stopPropagation()}
                          >
                            {report.title}
                          </Link>
                        </td>
                        <td className="px-6 py-4">{getStatusBadge(report.status)}</td>
                        <td className="px-6 py-4 text-sm text-secondary dark:text-muted">
                          {report.report_type}
                        </td>
                        <td className="px-6 py-4 text-sm text-secondary dark:text-muted">
                          {report.chunk_count}
                        </td>
                        <td className="px-6 py-4 text-sm text-secondary dark:text-muted">
                          {report.tokens_used.toLocaleString()}
                        </td>
                        <td className="px-6 py-4 text-sm text-muted dark:text-muted">
                          {formatDistanceToNow(new Date(report.created_at), { addSuffix: true })}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="mt-4 flex items-center justify-between">
                  <button
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page === 1}
                    className="px-4 py-2 text-sm border border-line-strong dark:border-line-strong rounded-lg disabled:opacity-50 disabled:cursor-not-allowed hover:bg-surface dark:hover:bg-surface-alt"
                  >
                    Previous
                  </button>
                  <span className="text-sm text-secondary dark:text-muted">
                    Page {page} of {totalPages} ({total} total)
                  </span>
                  <button
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page >= totalPages}
                    className="px-4 py-2 text-sm border border-line-strong dark:border-line-strong rounded-lg disabled:opacity-50 disabled:cursor-not-allowed hover:bg-surface dark:hover:bg-surface-alt"
                  >
                    Next
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </AuthGate>
  );
}
