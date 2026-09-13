/**
 * Console Corrections Queue - View and manage pending corrections.
 */

import { useState } from "react";
import useSWR from "swr";
import Head from "next/head";
import { RequireAdmin } from "@/components/RequireAdmin";
import { useAuth } from "@/contexts/AuthContext";
import Link from "next/link";

import { AuthGate } from "@/components/AuthGate";
import { CorrectionStatusCard } from "@/components/console/CorrectionStatusCard";
import { StatCard, StatGrid } from "@/components/console/StatCard";
import {
  getCorrectionStatus,
  getCorrectionTelemetry,
  triggerCorrections,
  clearCompletedCorrections,
  processCorrections,
  getDeadLetterQueue,
} from "@/lib/api/console";

export function CorrectionsContent() {
  const { user } = useAuth();
  const { data, error: readError, isLoading, isValidating, mutate } = useSWR(["admin-corrections", user?.user_id], async () => {
    const [status, telemetry, deadLetter] = await Promise.all([getCorrectionStatus(50), getCorrectionTelemetry(), getDeadLetterQueue()]);
    return { status, telemetry, deadLetter };
  }, { refreshInterval: 30000 });
  const status = data?.status;
  const telemetry = data?.telemetry;
  const deadLetter = data?.deadLetter.items ?? [];
  const deadLetterCount = data?.deadLetter.count ?? 0;
  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const error = actionError || (readError ? (data ? "Refresh failed. Showing the last successful snapshot." : "Corrections could not load. Try Refresh to retry.") : null);
  const [activeTab, setActiveTab] = useState<"queue" | "telemetry" | "deadletter">("queue");
  const loadData = () => mutate();

  const handleTriggerRetry = async () => {
    try {
      setActionLoading(true);
      setError(null);
      setNotice(null);
      const result = await triggerCorrections();
      setNotice(result.message);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to trigger retries");
    } finally {
      setActionLoading(false);
    }
  };

  const handleClearCompleted = async () => {
    try {
      setActionLoading(true);
      setError(null);
      setNotice(null);
      const result = await clearCompletedCorrections();
      setNotice(result.message);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to clear completed");
    } finally {
      setActionLoading(false);
    }
  };

  const handleProcessNow = async () => {
    try {
      setActionLoading(true);
      setError(null);
      setNotice(null);
      const result = await processCorrections();
      setNotice(result.message);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to process corrections");
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background dark:bg-background py-8">
      <Head><title>Corrections · TraceLab</title></Head>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Breadcrumb */}
        <nav className="text-sm text-muted dark:text-muted mb-4">
          <Link href="/admin/observability" className="hover:text-secondary dark:hover:text-secondary">
            Observability
          </Link>
          {" / "}
          <span className="text-foreground dark:text-foreground">Corrections</span>
        </nav>

        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-4 mb-8">
          <div>
            <h1 className="text-3xl font-bold text-foreground dark:text-foreground">
              Correction Queue
            </h1>
            <p className="mt-2 text-secondary dark:text-muted">
              Manage auto-linking corrections and webhook delivery. This queue belongs to the current API process and resets on restart.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={handleProcessNow}
              disabled={isLoading || actionLoading || !status}
              className="px-4 py-2 bg-accent text-on-accent rounded-lg hover:bg-accent disabled:opacity-50"
            >
              Process Now
            </button>
            <button
              onClick={loadData}
              disabled={isValidating}
              className="px-4 py-2 border border-line-strong dark:border-line-strong text-secondary dark:text-secondary rounded-lg hover:bg-background dark:hover:bg-surface-alt disabled:opacity-50"
            >
              {isValidating ? "Refreshing…" : "Refresh"}
            </button>
          </div>
        </div>

        {/* Error Alert */}
        {error && (
          <div role="alert" className="mb-6 p-4 bg-danger-surface dark:bg-danger-surface border border-danger-line dark:border-danger-line rounded-lg text-danger dark:text-danger">
            {error}
          </div>
        )}

        {notice && <p role="status" className="mb-4 rounded-lg bg-success-surface p-4 text-success">{notice}</p>}
        <p className="mb-4 text-sm text-muted">Refreshes every 30s{status ? ` · Updated ${new Date(status.last_updated).toLocaleString()}` : ""}</p>
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <div className="text-muted dark:text-muted">Loading corrections...</div>
          </div>
        ) : data ? (
          <>
            {/* Summary Stats */}
            {status && (
              <section className="mb-8">
                <StatGrid columns={5}>
                  <StatCard
                    label="Pending"
                    value={status.stats.pending}
                    color="yellow"
                  />
                  <StatCard
                    label="In Progress"
                    value={status.stats.in_progress}
                    color="blue"
                  />
                  <StatCard
                    label="Completed"
                    value={status.stats.completed}
                    color="green"
                  />
                  <StatCard
                    label="Failed"
                    value={status.stats.failed}
                    color="red"
                  />
                  <StatCard
                    label="Success Rate"
                    value={status.stats.completed + status.stats.failed ? `${Math.round((telemetry?.success_rate ?? 0) * 100)}%` : "No attempts"}
                    color="purple"
                  />
                </StatGrid>
              </section>
            )}

            {/* Tabs */}
            <div className="flex flex-wrap gap-4 mb-6 border-b border-line dark:border-line" aria-label="Correction views">
              <button
                aria-pressed={activeTab === "queue"}
                onClick={() => setActiveTab("queue")}
                className={`pb-3 px-1 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === "queue"
                    ? "border-info-line text-accent-text dark:text-accent-text"
                    : "border-transparent text-muted dark:text-muted hover:text-secondary dark:hover:text-secondary"
                }`}
              >
                Queue
              </button>
              <button
                aria-pressed={activeTab === "telemetry"}
                onClick={() => setActiveTab("telemetry")}
                className={`pb-3 px-1 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === "telemetry"
                    ? "border-info-line text-accent-text dark:text-accent-text"
                    : "border-transparent text-muted dark:text-muted hover:text-secondary dark:hover:text-secondary"
                }`}
              >
                Telemetry
              </button>
              <button
                aria-pressed={activeTab === "deadletter"}
                onClick={() => setActiveTab("deadletter")}
                className={`pb-3 px-1 text-sm font-medium border-b-2 transition-colors flex items-center gap-2 ${
                  activeTab === "deadletter"
                    ? "border-info-line text-accent-text dark:text-accent-text"
                    : "border-transparent text-muted dark:text-muted hover:text-secondary dark:hover:text-secondary"
                }`}
              >
                Dead Letter
                {deadLetterCount > 0 && (
                  <span className="px-1.5 py-0.5 text-xs bg-danger-surface text-danger dark:bg-danger-surface dark:text-danger rounded-full">
                    {deadLetterCount}
                  </span>
                )}
              </button>
            </div>

            {/* Queue Tab */}
            {activeTab === "queue" && status && (
              <CorrectionStatusCard
                status={status}
                onTriggerRetry={handleTriggerRetry}
                onClearCompleted={handleClearCompleted}
                isLoading={actionLoading}
              />
            )}

            {/* Telemetry Tab */}
            {activeTab === "telemetry" && telemetry && (
              <div className="bg-surface dark:bg-surface rounded-lg border border-line dark:border-line p-6">
                <h3 className="text-lg font-semibold text-foreground dark:text-foreground mb-4">
                  Grafana-Ready Telemetry
                </h3>
                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <h4 className="text-sm font-medium text-secondary dark:text-secondary mb-2">
                      Queue Counts
                    </h4>
                    <div className="bg-background dark:bg-surface-alt rounded-lg p-4">
                      <pre className="text-sm text-secondary dark:text-secondary overflow-x-auto">
                        {JSON.stringify(telemetry.queue_counts, null, 2)}
                      </pre>
                    </div>
                  </div>
                  <div>
                    <h4 className="text-sm font-medium text-secondary dark:text-secondary mb-2">
                      Webhook Stats
                    </h4>
                    <div className="bg-background dark:bg-surface-alt rounded-lg p-4">
                      <pre className="text-sm text-secondary dark:text-secondary overflow-x-auto">
                        {JSON.stringify(telemetry.webhook_stats ?? { message: "No webhook data" }, null, 2)}
                      </pre>
                    </div>
                  </div>
                </div>
                <div className="mt-4 pt-4 border-t border-line dark:border-line">
                  <p className="text-sm text-muted dark:text-muted">
                    Success Rate: {Math.round(telemetry.success_rate * 100)}% |
                    Last Updated: {new Date(telemetry.last_updated).toLocaleString()}
                  </p>
                </div>
              </div>
            )}

            {/* Dead Letter Tab */}
            {activeTab === "deadletter" && (
              <div className="bg-surface dark:bg-surface rounded-lg border border-line dark:border-line p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-foreground dark:text-foreground">
                    Dead Letter Queue ({deadLetterCount})
                  </h3>

                </div>

                {deadLetterCount > deadLetter.length && <p className="mb-4 text-sm text-muted">Showing {deadLetter.length} of {deadLetterCount} failed deliveries.</p>}
                {deadLetter.length === 0 ? (
                  <p className="text-center text-muted dark:text-muted py-8">
                    No failed webhook deliveries.
                  </p>
                ) : (
                  <div className="space-y-4 max-h-96 overflow-y-auto">
                    {deadLetter.map((item, idx) => (
                      <div
                        key={idx}
                        className="p-4 bg-danger-surface dark:bg-danger-surface border border-danger-line dark:border-danger-line rounded-lg"
                      >
                        <div className="flex items-start justify-between mb-2">
                          <span className="font-medium text-foreground dark:text-foreground text-sm truncate max-w-[60%]">
                            {item.url}
                          </span>
                          <span className="text-xs text-muted dark:text-muted">
                            {item.attempts} attempts
                          </span>
                        </div>
                        <p className="text-sm text-danger dark:text-danger mb-2 break-words">
                          {item.error}
                        </p>
                        <details className="text-xs">
                          <summary className="cursor-pointer text-muted dark:text-muted">
                            View Payload
                          </summary>
                          <pre className="mt-2 p-2 bg-surface dark:bg-surface-alt rounded overflow-x-auto text-secondary dark:text-secondary">
                            {JSON.stringify(item.payload, null, 2)}
                          </pre>
                        </details>
                        <p className="text-xs text-muted dark:text-muted mt-2">
                          Last attempt: {new Date(item.last_attempt).toLocaleString()}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </>
        ) : null}
      </div>
    </div>
  );
}

export default function CorrectionsPage() {
  return (
    <AuthGate>
      <RequireAdmin><CorrectionsContent /></RequireAdmin>
    </AuthGate>
  );
}
