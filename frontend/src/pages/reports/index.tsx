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
        <span className={`${baseClasses} bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400`}>
          Final
        </span>
      );
    }
    return (
      <span className={`${baseClasses} bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400`}>
        Draft
      </span>
    );
  };

  return (
    <AuthGate>
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Reports</h1>
            <p className="mt-2 text-gray-600 dark:text-gray-400">
              View and manage synthesized reports from your collections
            </p>
          </div>

          {/* Filters */}
          <div className="mb-6 flex items-center gap-4">
            <span className="text-sm text-gray-600 dark:text-gray-400">Filter by status:</span>
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
                      ? "bg-blue-600 text-white"
                      : "bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700"
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
              <p className="text-gray-500">Loading reports...</p>
            </div>
          ) : reports.length === 0 ? (
            <div className="text-center py-12 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
              <p className="text-gray-500 dark:text-gray-400 mb-4">No reports yet</p>
              <p className="text-sm text-gray-400 dark:text-gray-500">
                Create a report from a collection to synthesize content with AI.
              </p>
              <Link
                href="/collections"
                className="mt-4 inline-block px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                Go to Collections
              </Link>
            </div>
          ) : (
            <>
              <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                  <thead className="bg-gray-50 dark:bg-gray-700">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        Title
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        Status
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        Type
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        Chunks
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        Tokens
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        Created
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                    {reports.map((report: ReportListItem) => (
                      <tr
                        key={report.id}
                        className="hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer"
                        onClick={() => (window.location.href = `/reports/${report.id}`)}
                      >
                        <td className="px-6 py-4">
                          <Link
                            href={`/reports/${report.id}`}
                            className="text-gray-900 dark:text-white font-medium hover:text-blue-600 dark:hover:text-blue-400"
                            onClick={(e) => e.stopPropagation()}
                          >
                            {report.title}
                          </Link>
                        </td>
                        <td className="px-6 py-4">{getStatusBadge(report.status)}</td>
                        <td className="px-6 py-4 text-sm text-gray-600 dark:text-gray-400">
                          {report.report_type}
                        </td>
                        <td className="px-6 py-4 text-sm text-gray-600 dark:text-gray-400">
                          {report.chunk_count}
                        </td>
                        <td className="px-6 py-4 text-sm text-gray-600 dark:text-gray-400">
                          {report.tokens_used.toLocaleString()}
                        </td>
                        <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400">
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
                    className="px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-100 dark:hover:bg-gray-700"
                  >
                    Previous
                  </button>
                  <span className="text-sm text-gray-600 dark:text-gray-400">
                    Page {page} of {totalPages} ({total} total)
                  </span>
                  <button
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page >= totalPages}
                    className="px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-100 dark:hover:bg-gray-700"
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
