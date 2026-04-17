/**
 * Console Dashboard - Main operator console page.
 * Displays mission counts, quality distribution, and correction status.
 */

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";

import { AuthGate } from "@/components/AuthGate";
import { StatCard, StatGrid } from "@/components/console/StatCard";
import { CorrectionStatusCard } from "@/components/console/CorrectionStatusCard";
import { WorkerHealthCard } from "@/components/console/WorkerHealthCard";
import {
  getConsoleMissions,
  getCorrectionStatus,
  computeDashboardStats,
  triggerCorrections,
  clearCompletedCorrections,
} from "@/lib/api/console";
import type { ApiMission } from "@/types/mission";
import type { CorrectionStatusResponse } from "@/types/console";

interface DashboardData {
  missions: ApiMission[];
  corrections: CorrectionStatusResponse | null;
  stats: {
    missionsByStatus: Record<string, number>;
    qualityDistribution: { excellent: number; good: number; fair: number; poor: number };
    totalMissions: number;
  } | null;
}

function ConsoleDashboard() {
  const [data, setData] = useState<DashboardData>({
    missions: [],
    corrections: null,
    stats: null,
  });
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  const loadData = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);

      const [missions, corrections] = await Promise.all([
        getConsoleMissions(),
        getCorrectionStatus(),
      ]);

      const stats = computeDashboardStats(missions, corrections);

      setData({ missions, corrections, stats });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard data");
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

  const recentMissions = data.missions
    .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
    .slice(0, 5);

  return (
    <main className="min-h-screen bg-gray-50 dark:bg-gray-900 py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
            Mission Operations Center
          </h1>
          <p className="mt-2 text-gray-600 dark:text-gray-400">
            Real-time mission progress, PEDR search activity, and operations visibility
          </p>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-800 dark:text-red-200">
            {error}
          </div>
        )}

        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <div className="text-gray-500 dark:text-gray-400">Loading dashboard...</div>
          </div>
        ) : (
          <>
            {/* Compact Mission Stats */}
            <section className="mb-8">
              <StatGrid columns={4}>
                <StatCard
                  label="Total Missions"
                  value={data.stats?.totalMissions ?? 0}
                  color="blue"
                />
                <StatCard
                  label="In Progress"
                  value={data.stats?.missionsByStatus?.in_progress ?? 0}
                  color="yellow"
                />
                <StatCard
                  label="Complete"
                  value={data.stats?.missionsByStatus?.complete ?? 0}
                  color="green"
                />
                <StatCard
                  label="Queued"
                  value={data.stats?.missionsByStatus?.queued ?? 0}
                  color="purple"
                />
              </StatGrid>
            </section>

            {/* System health */}
            <section className="mb-8 grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2">
                <GraphHealthPanel />
              </div>
              <div>
                <WorkerHealthCard refreshInterval={30000} />
              </div>
            </section>

            {/* Quick Links */}
            <section className="mb-8">
              <div className="flex gap-4">
                <Link
                  href="/console/missions"
                  className="flex-1 p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 hover:border-blue-500 dark:hover:border-blue-400 transition-colors"
                >
                  <h3 className="font-semibold text-gray-900 dark:text-white">
                    Mission List
                  </h3>
                  <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                    Browse and filter all missions
                  </p>
                </Link>
                <Link
                  href="/console/corrections"
                  className="flex-1 p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 hover:border-blue-500 dark:hover:border-blue-400 transition-colors"
                >
                  <h3 className="font-semibold text-gray-900 dark:text-white">
                    Corrections Queue
                  </h3>
                  <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                    View and manage pending corrections
                  </p>
                </Link>
              </div>
            </section>

            {/* Recent Missions */}
            <section className="mb-8">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                  Recent Missions
                </h2>
                <Link
                  href="/console/missions"
                  className="text-sm text-blue-600 dark:text-blue-400 hover:underline"
                >
                  View all
                </Link>
              </div>
              <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 divide-y divide-gray-100 dark:divide-gray-700">
                {recentMissions.map((mission) => {
                  const hasError = !!mission.error_message;
                  return (
                    <Link
                      key={mission.id}
                      href={`/console/missions/${mission.id}`}
                      className="flex items-center justify-between p-4 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                    >
                      <div className="flex-1 min-w-0">
                        <h3 className="font-medium text-gray-900 dark:text-white truncate">
                          {mission.title ?? mission.mission_id ?? "Untitled"}
                        </h3>
                        <p className="text-sm text-gray-500 dark:text-gray-400">
                          {mission.objective?.slice(0, 80) ?? "No objective"}
                          {(mission.objective?.length ?? 0) > 80 ? "..." : ""}
                        </p>
                      </div>
                      <div className="flex items-center gap-3 ml-4">
                        <span
                          className={`text-xs px-2 py-1 rounded-full ${
                            mission.status === "completed"
                              ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
                              : mission.status === "in_progress"
                              ? "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200"
                              : mission.status === "queued"
                              ? "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200"
                              : mission.status === "blocked"
                              ? "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
                              : "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200"
                          }`}
                        >
                          {mission.status ?? "draft"}
                        </span>
                        {hasError && (
                          <span className="text-xs px-2 py-1 rounded-full bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200">
                            error
                          </span>
                        )}
                      </div>
                    </Link>
                  );
                })}
                {recentMissions.length === 0 && (
                  <p className="p-4 text-center text-gray-500 dark:text-gray-400">
                    No missions found.
                  </p>
                )}
              </div>
            </section>

            {/* Corrections Status */}
            {data.corrections && (
              <section>
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                  Corrections Overview
                </h2>
                <CorrectionStatusCard
                  status={data.corrections}
                  onTriggerRetry={handleTriggerRetry}
                  onClearCompleted={handleClearCompleted}
                  isLoading={actionLoading}
                />
              </section>
            )}
          </>
        )}
      </div>
    </main>
  );
}

// ---------------------------------------------------------------------------
// Graph health panel — corpus + graph layer stats
// ---------------------------------------------------------------------------

type GraphStats = {
  edge_counts: Record<string, number>;
  total_edges: number;
  document_count: number;
  chunk_count: number;
};

function GraphHealthPanel() {
  const [stats, setStats] = useState<GraphStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
    const token = typeof window !== "undefined"
      ? JSON.parse(localStorage.getItem("tracelab_auth") ?? "{}").token ?? ""
      : "";

    Promise.all([
      fetch(`${apiBase}/api/v1/graph/stats`, { headers: { Authorization: `Bearer ${token}` } })
        .then((r) => r.ok ? r.json() : null)
        .catch(() => null),
    ]).then(([graphData]) => {
      setStats(graphData);
      setIsLoading(false);
    });
  }, []);

  const EDGE_COLORS: Record<string, string> = {
    topic_similar: "bg-violet-500",
    contains: "bg-blue-500",
    part_of: "bg-sky-500",
    co_occurs: "bg-teal-500",
    belongs_to: "bg-green-500",
    references: "bg-yellow-500",
    derived_from: "bg-orange-500",
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Graph Layer</h2>

      {isLoading ? (
        <p className="text-sm text-gray-400 dark:text-gray-500">Loading...</p>
      ) : !stats ? (
        <p className="text-sm text-gray-400 dark:text-gray-500">Graph stats unavailable</p>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-4 mb-6">
            <div className="text-center">
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {stats.total_edges?.toLocaleString() ?? "—"}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">Total edges</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {stats.document_count?.toLocaleString() ?? "—"}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">Documents</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {stats.chunk_count?.toLocaleString() ?? "—"}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">Chunks</p>
            </div>
          </div>

          <div className="space-y-2">
            {Object.entries(stats.edge_counts ?? {})
              .sort(([, a], [, b]) => b - a)
              .map(([type, count]) => {
                const pct = stats.total_edges > 0 ? (count / stats.total_edges) * 100 : 0;
                return (
                  <div key={type}>
                    <div className="flex items-center justify-between text-xs mb-1">
                      <span className="text-gray-600 dark:text-gray-400">{type}</span>
                      <span className="font-medium text-gray-900 dark:text-white">{count.toLocaleString()}</span>
                    </div>
                    <div className="w-full bg-gray-100 dark:bg-gray-700 rounded-full h-1.5">
                      <div
                        className={`h-1.5 rounded-full ${EDGE_COLORS[type] ?? "bg-gray-400"}`}
                        style={{ width: `${Math.max(pct, 0.5)}%` }}
                      />
                    </div>
                  </div>
                );
              })}
          </div>
        </>
      )}
    </div>
  );
}

export default function ConsolePage() {
  return (
    <AuthGate>
      <ConsoleDashboard />
    </AuthGate>
  );
}
