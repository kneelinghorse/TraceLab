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
    <main className="min-h-screen bg-gray-50 dark:bg-gray-900 py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Breadcrumb */}
        <nav className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          <Link href="/console" className="hover:text-gray-700 dark:hover:text-gray-200">
            Console
          </Link>
          {" / "}
          <span className="text-gray-900 dark:text-white">Corrections</span>
        </nav>

        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
              Correction Queue
            </h1>
            <p className="mt-2 text-gray-600 dark:text-gray-400">
              Manage auto-linking corrections and webhook delivery
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleProcessNow}
              disabled={isLoading || actionLoading}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              Process Now
            </button>
            <button
              onClick={loadData}
              disabled={isLoading}
              className="px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
            >
              Refresh
            </button>
          </div>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-800 dark:text-red-200">
            {error}
          </div>
        )}

        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <div className="text-gray-500 dark:text-gray-400">Loading corrections...</div>
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
            <div className="flex gap-4 mb-6 border-b border-gray-200 dark:border-gray-700">
              <button
                onClick={() => setActiveTab("queue")}
                className={`pb-3 px-1 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === "queue"
                    ? "border-blue-500 text-blue-600 dark:text-blue-400"
                    : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                }`}
              >
                Queue
              </button>
              <button
                onClick={() => setActiveTab("telemetry")}
                className={`pb-3 px-1 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === "telemetry"
                    ? "border-blue-500 text-blue-600 dark:text-blue-400"
                    : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                }`}
              >
                Telemetry
              </button>
              <button
                onClick={() => setActiveTab("deadletter")}
                className={`pb-3 px-1 text-sm font-medium border-b-2 transition-colors flex items-center gap-2 ${
                  activeTab === "deadletter"
                    ? "border-blue-500 text-blue-600 dark:text-blue-400"
                    : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                }`}
              >
                Dead Letter
                {deadLetter.length > 0 && (
                  <span className="px-1.5 py-0.5 text-xs bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200 rounded-full">
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
              <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                  Grafana-Ready Telemetry
                </h3>
                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Queue Counts
                    </h4>
                    <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4">
                      <pre className="text-sm text-gray-600 dark:text-gray-300 overflow-x-auto">
                        {JSON.stringify(telemetry.queue_counts, null, 2)}
                      </pre>
                    </div>
                  </div>
                  <div>
                    <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Webhook Stats
                    </h4>
                    <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4">
                      <pre className="text-sm text-gray-600 dark:text-gray-300 overflow-x-auto">
                        {JSON.stringify(telemetry.webhook_stats ?? { message: "No webhook data" }, null, 2)}
                      </pre>
                    </div>
                  </div>
                </div>
                <div className="mt-4 pt-4 border-t border-gray-100 dark:border-gray-700">
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    Success Rate: {Math.round(telemetry.success_rate * 100)}% |
                    Last Updated: {new Date(telemetry.last_updated).toLocaleString()}
                  </p>
                </div>
              </div>
            )}

            {/* Dead Letter Tab */}
            {activeTab === "deadletter" && (
              <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                    Dead Letter Queue ({deadLetter.length})
                  </h3>
                  {deadLetter.length > 0 && (
                    <button
                      onClick={async () => {
                        // Implement clear dead letter
                        setError("Clear dead letter not yet implemented");
                      }}
                      className="text-sm px-3 py-1.5 text-red-600 dark:text-red-400 border border-red-300 dark:border-red-700 rounded hover:bg-red-50 dark:hover:bg-red-900/20"
                    >
                      Clear All
                    </button>
                  )}
                </div>

                {deadLetter.length === 0 ? (
                  <p className="text-center text-gray-500 dark:text-gray-400 py-8">
                    No failed webhook deliveries.
                  </p>
                ) : (
                  <div className="space-y-4 max-h-96 overflow-y-auto">
                    {deadLetter.map((item, idx) => (
                      <div
                        key={idx}
                        className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg"
                      >
                        <div className="flex items-start justify-between mb-2">
                          <span className="font-medium text-gray-900 dark:text-white text-sm truncate max-w-[60%]">
                            {item.url}
                          </span>
                          <span className="text-xs text-gray-500 dark:text-gray-400">
                            {item.attempts} attempts
                          </span>
                        </div>
                        <p className="text-sm text-red-700 dark:text-red-300 mb-2">
                          {item.error}
                        </p>
                        <details className="text-xs">
                          <summary className="cursor-pointer text-gray-500 dark:text-gray-400">
                            View Payload
                          </summary>
                          <pre className="mt-2 p-2 bg-gray-100 dark:bg-gray-700 rounded overflow-x-auto text-gray-600 dark:text-gray-300">
                            {JSON.stringify(item.payload, null, 2)}
                          </pre>
                        </details>
                        <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">
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
    </main>
  );
}

export default function CorrectionsPage() {
  return (
    <AuthGate>
      <CorrectionsContent />
    </AuthGate>
  );
}
