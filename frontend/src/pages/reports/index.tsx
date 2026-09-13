import { useRouter } from "next/router";
import { PaginationBar } from "@/components/ui/PaginationBar";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { PageState } from "@/components/ui/PageState";
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
  const router = useRouter();
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const { data: response, isLoading, error, mutate } = useSWR(
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



  return (
    <AuthGate>
      <div className="min-h-screen bg-background">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-foreground">Reports</h1>
            <p className="mt-2 text-secondary">
              View and manage synthesized reports from your collections
            </p>
          </div>

          {/* Filters */}
          <div className="mb-6 flex flex-wrap items-center gap-4">
            <span className="text-sm text-secondary">Filter by status:</span>
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
                      : "bg-surface text-secondary border border-line-strong hover:bg-background"
                  }`}
                >
                  {status.charAt(0).toUpperCase() + status.slice(1)}
                </button>
              ))}
            </div>
          </div>

          {/* Reports List */}
          {error ? <PageState state="error" title="Reports could not load." onRetry={() => void mutate()} /> : isLoading ? (
            <PageState state="loading" title="Loading reports…" />
          ) : reports.length === 0 ? (
            <div className="text-center py-12 bg-surface rounded-lg border border-line">
              <p className="text-muted mb-4">No reports yet</p>
              <p className="text-sm text-muted">
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
              <div className="bg-surface rounded-lg border border-line overflow-x-auto">
                <table className="min-w-full divide-y divide-line">
                  <thead className="bg-background">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                        Title
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                        Status
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                        Type
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                        Chunks
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                        Tokens
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                        Created
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-surface divide-y divide-line">
                    {reports.map((report: ReportListItem) => (
                      <tr
                        key={report.id}
                        className="hover:bg-background cursor-pointer"
                        onClick={() => void router.push(`/reports/${report.id}`)}
                      >
                        <td className="px-6 py-4">
                          <Link
                            href={`/reports/${report.id}`}
                            className="text-foreground font-medium hover:text-accent-text"
                            onClick={(e) => e.stopPropagation()}
                          >
                            {report.title}
                          </Link>
                        </td>
                        <td className="px-6 py-4"><StatusBadge status={report.status} /></td>
                        <td className="px-6 py-4 text-sm text-secondary">
                          {report.report_type}
                        </td>
                        <td className="px-6 py-4 text-sm text-secondary">
                          {report.chunk_count}
                        </td>
                        <td className="px-6 py-4 text-sm text-secondary">
                          {report.tokens_used.toLocaleString()}
                        </td>
                        <td className="px-6 py-4 text-sm text-muted">
                          {formatDistanceToNow(new Date(report.created_at), { addSuffix: true })}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              <PaginationBar page={page} pages={totalPages} total={total} onChange={setPage} />
            </>
          )}
        </div>
      </div>
    </AuthGate>
  );
}
