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
    <div className="min-h-screen bg-background dark:bg-background py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-foreground dark:text-foreground">
            Mission Operations Center
          </h1>
          <p className="mt-2 text-secondary dark:text-muted">
            Real-time mission progress, PEDR search activity, and operations visibility
          </p>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="mb-6 p-4 bg-danger-surface dark:bg-danger-surface border border-danger-line dark:border-danger-line rounded-lg text-danger dark:text-danger">
            {error}
          </div>
        )}

        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <div className="text-muted dark:text-muted">Loading dashboard...</div>
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
                  className="flex-1 p-4 bg-surface dark:bg-surface rounded-lg border border-line dark:border-line hover:border-info-line dark:hover:border-info-line transition-colors"
                >
                  <h3 className="font-semibold text-foreground dark:text-foreground">
                    Mission List
                  </h3>
                  <p className="text-sm text-muted dark:text-muted mt-1">
                    Browse and filter all missions
                  </p>
                </Link>
                <Link
                  href="/console/corrections"
                  className="flex-1 p-4 bg-surface dark:bg-surface rounded-lg border border-line dark:border-line hover:border-info-line dark:hover:border-info-line transition-colors"
                >
                  <h3 className="font-semibold text-foreground dark:text-foreground">
                    Corrections Queue
                  </h3>
                  <p className="text-sm text-muted dark:text-muted mt-1">
                    View and manage pending corrections
                  </p>
                </Link>
              </div>
            </section>

            {/* Recent Missions */}
            <section className="mb-8">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-foreground dark:text-foreground">
                  Recent Missions
                </h2>
                <Link
                  href="/console/missions"
                  className="text-sm text-accent-text dark:text-accent-text underline underline-offset-4"
                >
                  View all
                </Link>
              </div>
              <div className="bg-surface dark:bg-surface rounded-lg border border-line dark:border-line divide-y divide-line dark:divide-line">
                {recentMissions.map((mission) => {
                  const hasError = !!mission.error_message;
                  return (
                    <Link
                      key={mission.id}
                      href={`/console/missions/${mission.id}`}
                      className="flex items-center justify-between p-4 hover:bg-background dark:hover:bg-surface-alt transition-colors"
                    >
                      <div className="flex-1 min-w-0">
                        <h3 className="font-medium text-foreground dark:text-foreground truncate">
                          {mission.title ?? mission.mission_id ?? "Untitled"}
                        </h3>
                        <p className="text-sm text-muted dark:text-muted">
                          {mission.objective?.slice(0, 80) ?? "No objective"}
                          {(mission.objective?.length ?? 0) > 80 ? "..." : ""}
                        </p>
                      </div>
                      <div className="flex items-center gap-3 ml-4">
                        <span
                          className={`text-xs px-2 py-1 rounded-full ${
                            mission.status === "completed"
                              ? "bg-success-surface text-success dark:bg-success-surface dark:text-success"
                              : mission.status === "in_progress"
                              ? "bg-warning-surface text-warning dark:bg-warning-surface dark:text-warning"
                              : mission.status === "queued"
                              ? "bg-info-surface text-info dark:bg-info-surface dark:text-info"
                              : mission.status === "blocked"
                              ? "bg-danger-surface text-danger dark:bg-danger-surface dark:text-danger"
                              : "bg-surface text-foreground dark:bg-surface-alt dark:text-secondary"
                          }`}
                        >
                          {mission.status ?? "draft"}
                        </span>
                        {hasError && (
                          <span className="text-xs px-2 py-1 rounded-full bg-danger-surface text-danger dark:bg-danger-surface dark:text-danger">
                            error
                          </span>
                        )}
                      </div>
                    </Link>
                  );
                })}
                {recentMissions.length === 0 && (
                  <p className="p-4 text-center text-muted dark:text-muted">
                    No missions found.
                  </p>
                )}
              </div>
            </section>

            {/* Corrections Status */}
            {data.corrections && (
              <section>
                <h2 className="text-lg font-semibold text-foreground dark:text-foreground mb-4">
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
    </div>
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
    topic_similar: "bg-accent",
    contains: "bg-accent",
    part_of: "bg-accent",
    co_occurs: "bg-success",
    belongs_to: "bg-success",
    references: "bg-warning",
    derived_from: "bg-warning",
  };

  return (
    <div className="bg-surface dark:bg-surface rounded-lg border border-line dark:border-line p-6">
      <h2 className="text-lg font-semibold text-foreground dark:text-foreground mb-4">Graph Layer</h2>

      {isLoading ? (
        <p className="text-sm text-muted dark:text-muted">Loading...</p>
      ) : !stats ? (
        <p className="text-sm text-muted dark:text-muted">Graph stats unavailable</p>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-4 mb-6">
            <div className="text-center">
              <p className="text-2xl font-bold text-foreground dark:text-foreground">
                {stats.total_edges?.toLocaleString() ?? "—"}
              </p>
              <p className="text-xs text-muted dark:text-muted mt-0.5">Total edges</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-foreground dark:text-foreground">
                {stats.document_count?.toLocaleString() ?? "—"}
              </p>
              <p className="text-xs text-muted dark:text-muted mt-0.5">Documents</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-foreground dark:text-foreground">
                {stats.chunk_count?.toLocaleString() ?? "—"}
              </p>
              <p className="text-xs text-muted dark:text-muted mt-0.5">Chunks</p>
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
                      <span className="text-secondary dark:text-muted">{type}</span>
                      <span className="font-medium text-foreground dark:text-foreground">{count.toLocaleString()}</span>
                    </div>
                    <div className="w-full bg-surface dark:bg-surface-alt rounded-full h-1.5">
                      <div
                        className={`h-1.5 rounded-full ${EDGE_COLORS[type] ?? "bg-surface-alt"}`}
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
