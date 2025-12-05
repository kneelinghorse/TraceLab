/**
 * Console Dashboard - Main operator console page.
 * Displays mission counts, quality distribution, and correction status.
 */

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";

import { AuthGate } from "@/components/AuthGate";
import { StatCard, StatGrid } from "@/components/console/StatCard";
import { CorrectionStatusCard } from "@/components/console/CorrectionStatusCard";
import {
  getConsoleMissions,
  getCorrectionStatus,
  computeDashboardStats,
  triggerCorrections,
  clearCompletedCorrections,
} from "@/lib/api/console";
import type { Mission } from "@/types/mission";
import type { CorrectionStatusResponse } from "@/types/console";

interface DashboardData {
  missions: Mission[];
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
            Operator Console
          </h1>
          <p className="mt-2 text-gray-600 dark:text-gray-400">
            Mission Protocol visibility and correction management
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
            {/* Mission Stats */}
            <section className="mb-8">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                Mission Overview
              </h2>
              <StatGrid columns={5}>
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
                  label="Draft"
                  value={data.stats?.missionsByStatus?.draft ?? 0}
                  color="default"
                />
                <StatCard
                  label="In Review"
                  value={data.stats?.missionsByStatus?.review ?? 0}
                  color="purple"
                />
              </StatGrid>
            </section>

            {/* Quality Distribution */}
            <section className="mb-8">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                Quality Distribution
              </h2>
              <StatGrid columns={4}>
                <StatCard
                  label="Excellent (80-100%)"
                  value={data.stats?.qualityDistribution.excellent ?? 0}
                  sublabel="missions"
                  color="green"
                />
                <StatCard
                  label="Good (60-79%)"
                  value={data.stats?.qualityDistribution.good ?? 0}
                  sublabel="missions"
                  color="blue"
                />
                <StatCard
                  label="Fair (40-59%)"
                  value={data.stats?.qualityDistribution.fair ?? 0}
                  sublabel="missions"
                  color="yellow"
                />
                <StatCard
                  label="Poor (0-39%)"
                  value={data.stats?.qualityDistribution.poor ?? 0}
                  sublabel="missions"
                  color="red"
                />
              </StatGrid>
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
                  const gates = mission.mission_data?.quality_checkpoints ?? [];
                  const failingGates = gates.filter((g) => g.status === "fail").length;
                  return (
                    <Link
                      key={mission.id}
                      href={`/console/missions/${mission.id}`}
                      className="flex items-center justify-between p-4 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                    >
                      <div className="flex-1 min-w-0">
                        <h3 className="font-medium text-gray-900 dark:text-white truncate">
                          {mission.mission_data?.title ?? mission.mission_data?.mission_id ?? "Untitled"}
                        </h3>
                        <p className="text-sm text-gray-500 dark:text-gray-400">
                          {mission.completion_percentage ?? 0}% complete
                        </p>
                      </div>
                      <div className="flex items-center gap-3 ml-4">
                        <span
                          className={`text-xs px-2 py-1 rounded-full ${
                            mission.mission_data?.status === "complete"
                              ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
                              : mission.mission_data?.status === "in_progress"
                              ? "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200"
                              : "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200"
                          }`}
                        >
                          {mission.mission_data?.status ?? "draft"}
                        </span>
                        {failingGates > 0 && (
                          <span className="text-xs px-2 py-1 rounded-full bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200">
                            {failingGates} failing
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

export default function ConsolePage() {
  return (
    <AuthGate>
      <ConsoleDashboard />
    </AuthGate>
  );
}
