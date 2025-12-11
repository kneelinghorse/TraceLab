/**
 * WorkerHealthCard - Displays DeepSearch worker health status.
 */

import { useEffect, useState, useCallback } from "react";

import { getWorkerHealth } from "@/lib/api/console";
import type { WorkerHealthResponse } from "@/types/console";

interface WorkerHealthCardProps {
  refreshInterval?: number; // Auto-refresh interval in ms (default: 30000)
}

function formatUptime(seconds: number | null | undefined): string {
  if (seconds == null) return "N/A";

  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);

  if (hours > 24) {
    const days = Math.floor(hours / 24);
    const remainingHours = hours % 24;
    return `${days}d ${remainingHours}h`;
  }

  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }

  return `${minutes}m`;
}

function StatusBadge({ status }: { status: string }) {
  const colorClasses: Record<string, string> = {
    healthy: "bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-200",
    degraded: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-200",
    offline: "bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-200",
  };

  const colorClass = colorClasses[status] ?? colorClasses.offline;

  return (
    <span className={`text-sm font-medium px-3 py-1 rounded-full ${colorClass}`}>
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}

function StatItem({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex flex-col">
      <span className="text-xs text-gray-500 dark:text-gray-400">{label}</span>
      <span className="text-lg font-semibold text-gray-900 dark:text-white">{value}</span>
    </div>
  );
}

export function WorkerHealthCard({ refreshInterval = 30000 }: WorkerHealthCardProps) {
  const [health, setHealth] = useState<WorkerHealthResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastFetched, setLastFetched] = useState<Date | null>(null);

  const fetchHealth = useCallback(async () => {
    try {
      const data = await getWorkerHealth();
      setHealth(data);
      setError(null);
      setLastFetched(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch worker health");
      setHealth({ status: "offline", missions_processed: 0, missions_completed: 0, missions_failed: 0, error: "API request failed" });
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Initial fetch
  useEffect(() => {
    fetchHealth();
  }, [fetchHealth]);

  // Auto-refresh
  useEffect(() => {
    if (refreshInterval <= 0) return;

    const timer = setInterval(fetchHealth, refreshInterval);
    return () => clearInterval(timer);
  }, [fetchHealth, refreshInterval]);

  const isOffline = health?.status === "offline";

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
          DeepSearch Worker
        </h3>
        <div className="flex items-center gap-3">
          {health && <StatusBadge status={health.status} />}
          <button
            onClick={fetchHealth}
            disabled={isLoading}
            className="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 disabled:opacity-50"
            title="Refresh"
          >
            <svg
              className={`w-5 h-5 ${isLoading ? "animate-spin" : ""}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
          </button>
        </div>
      </div>

      {/* Error message */}
      {error && (
        <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded text-sm text-red-800 dark:text-red-200">
          {error}
        </div>
      )}

      {/* Loading state */}
      {isLoading && !health && (
        <div className="flex items-center justify-center py-8">
          <div className="text-gray-500 dark:text-gray-400">Loading worker status...</div>
        </div>
      )}

      {/* Health content */}
      {health && (
        <>
          {/* Offline message */}
          {isOffline && health.error && (
            <div className="mb-4 p-3 bg-gray-50 dark:bg-gray-700/50 rounded text-sm text-gray-600 dark:text-gray-300">
              {health.error}
            </div>
          )}

          {/* Stats grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <StatItem
              label="Uptime"
              value={formatUptime(health.uptime_seconds)}
            />
            <StatItem
              label="Processed"
              value={health.missions_processed}
            />
            <StatItem
              label="Completed"
              value={health.missions_completed}
            />
            <StatItem
              label="Failed"
              value={health.missions_failed}
            />
          </div>

          {/* Additional info */}
          <div className="flex flex-wrap gap-4 text-sm text-gray-600 dark:text-gray-400">
            {health.current_mission_id && (
              <div>
                <span className="font-medium">Current:</span>{" "}
                <span className="text-blue-600 dark:text-blue-400">
                  {health.current_mission_id}
                </span>
              </div>
            )}
            {health.poll_interval != null && (
              <div>
                <span className="font-medium">Poll interval:</span> {health.poll_interval}s
              </div>
            )}
          </div>
        </>
      )}

      {/* Last updated */}
      {lastFetched && (
        <div className="mt-4 pt-4 border-t border-gray-100 dark:border-gray-700 text-xs text-gray-400 dark:text-gray-500">
          Last checked: {lastFetched.toLocaleString()}
        </div>
      )}
    </div>
  );
}
