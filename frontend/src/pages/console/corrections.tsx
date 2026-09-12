/**
 * Console Corrections Queue - View and manage pending corrections.
 */

import { useEffect, useState, useCallback } from "react";
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
import type { CorrectionStatusResponse, CorrectionTelemetry } from "@/types/console";
import type { DeadLetterItem } from "@/lib/api/console";

function CorrectionsContent() {
  const [status, setStatus] = useState<CorrectionStatusResponse | null>(null);
  const [telemetry, setTelemetry] = useState<CorrectionTelemetry | null>(null);
  const [deadLetter, setDeadLetter] = useState<DeadLetterItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"queue" | "telemetry" | "deadletter">("queue");

  const loadData = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);

      const [statusData, telemetryData, dlqData] = await Promise.all([
        getCorrectionStatus(50),
        getCorrectionTelemetry(),
        getDeadLetterQueue(),
      ]);

      setStatus(statusData);
      setTelemetry(telemetryData);
      setDeadLetter(dlqData.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load corrections data");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleTriggerRetry = async () => {
    try {
      setActionLoading(true);
      await triggerCorrections();
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
      await clearCompletedCorrections();
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
      await processCorrections();
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to process corrections");
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background dark:bg-background py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Breadcrumb */}
        <nav className="text-sm text-muted dark:text-muted mb-4">
          <Link href="/console" className="hover:text-secondary dark:hover:text-secondary">
            Console
          </Link>
          {" / "}
          <span className="text-foreground dark:text-foreground">Corrections</span>
        </nav>

        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-foreground dark:text-foreground">
              Correction Queue
            </h1>
            <p className="mt-2 text-secondary dark:text-muted">
              Manage auto-linking corrections and webhook delivery
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleProcessNow}
              disabled={isLoading || actionLoading}
              className="px-4 py-2 bg-accent text-on-accent rounded-lg hover:bg-accent disabled:opacity-50"
            >
              Process Now
            </button>
            <button
              onClick={loadData}
              disabled={isLoading}
              className="px-4 py-2 border border-line-strong dark:border-line-strong text-secondary dark:text-secondary rounded-lg hover:bg-background dark:hover:bg-surface-alt disabled:opacity-50"
            >
              Refresh
            </button>
          </div>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="mb-6 p-4 bg-danger-surface dark:bg-danger-surface border border-danger-line dark:border-danger-line rounded-lg text-danger dark:text-danger">
            {error}
          </div>
        )}

        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <div className="text-muted dark:text-muted">Loading corrections...</div>
          </div>
        ) : (
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
                    value={`${telemetry?.success_rate ? Math.round(telemetry.success_rate * 100) : 0}%`}
                    color="purple"
                  />
                </StatGrid>
              </section>
            )}

            {/* Tabs */}
            <div className="flex gap-4 mb-6 border-b border-line dark:border-line">
              <button
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
                onClick={() => setActiveTab("deadletter")}
                className={`pb-3 px-1 text-sm font-medium border-b-2 transition-colors flex items-center gap-2 ${
                  activeTab === "deadletter"
                    ? "border-info-line text-accent-text dark:text-accent-text"
                    : "border-transparent text-muted dark:text-muted hover:text-secondary dark:hover:text-secondary"
                }`}
              >
                Dead Letter
                {deadLetter.length > 0 && (
                  <span className="px-1.5 py-0.5 text-xs bg-danger-surface text-danger dark:bg-danger-surface dark:text-danger rounded-full">
                    {deadLetter.length}
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
                    Dead Letter Queue ({deadLetter.length})
                  </h3>
                  {deadLetter.length > 0 && (
                    <button
                      onClick={async () => {
                        // Implement clear dead letter
                        setError("Clear dead letter not yet implemented");
                      }}
                      className="text-sm px-3 py-1.5 text-danger dark:text-danger border border-danger-line dark:border-danger-line rounded hover:bg-danger-surface dark:hover:bg-danger-surface"
                    >
                      Clear All
                    </button>
                  )}
                </div>

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
                        <p className="text-sm text-danger dark:text-danger mb-2">
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
        )}
      </div>
    </div>
  );
}

export default function CorrectionsPage() {
  return (
    <AuthGate>
      <CorrectionsContent />
    </AuthGate>
  );
}
