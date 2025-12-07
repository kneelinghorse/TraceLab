import { useState, useCallback, useMemo } from "react";
import Link from "next/link";

import { AuthGate } from "@/components/AuthGate";
import {
  RunningMissionCard,
  QueuedMissionCard,
  EmptyQueueState,
  RefreshIndicator,
} from "@/components/queue";
import { useApiMissions, calculateQueuePosition } from "@/lib/hooks/useMissions";
import { useInterval } from "@/lib/hooks/useInterval";
import { missionsApi } from "@/lib/api/missions";
import type { ApiMission } from "@/types/mission";

const REFRESH_INTERVAL = 30000; // 30 seconds

function MissionQueueContent() {
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Fetch all missions that are in_progress or queued
  const {
    missions: inProgressMissions,
    isLoading: loadingInProgress,
    refresh: refreshInProgress,
  } = useApiMissions({ status: "in_progress", pageSize: 100 });

  const {
    missions: queuedMissions,
    isLoading: loadingQueued,
    refresh: refreshQueued,
  } = useApiMissions({ status: "queued", pageSize: 100 });

  const isLoading = loadingInProgress || loadingQueued;

  // Sort queued missions by queue position
  const sortedQueuedMissions = useMemo(() => {
    return [...queuedMissions].sort((a, b) => {
      const aTime = a.queued_at ? new Date(a.queued_at).getTime() : 0;
      const bTime = b.queued_at ? new Date(b.queued_at).getTime() : 0;
      return aTime - bTime;
    });
  }, [queuedMissions]);

  // Combined refresh function
  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true);
    await Promise.all([refreshInProgress(), refreshQueued()]);
    setLastRefresh(new Date());
    setIsRefreshing(false);
  }, [refreshInProgress, refreshQueued]);

  // Auto-refresh every 30 seconds
  useInterval(handleRefresh, REFRESH_INTERVAL);

  // Cancel mission handler
  const handleCancelMission = async (missionId: string) => {
    if (!confirm("Are you sure you want to cancel this mission?")) return;

    try {
      await missionsApi.update(missionId, { status: "cancelled" });
      handleRefresh();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to cancel mission");
    }
  };

  // Estimate wait time based on queue position (rough estimate)
  const estimateWaitTime = (position: number): string => {
    // Assume ~5 minutes per mission ahead in queue (rough estimate)
    const minutes = position * 5;
    if (minutes >= 60) {
      return `${Math.round(minutes / 60)}h`;
    }
    return `${minutes}m`;
  };

  const hasActiveMissions = inProgressMissions.length > 0 || sortedQueuedMissions.length > 0;

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-8">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <Link
                href="/missions"
                className="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 transition-colors"
              >
                Missions
              </Link>
              <span className="text-gray-300 dark:text-gray-600">/</span>
              <span className="text-sm font-medium text-gray-900 dark:text-white">
                Queue
              </span>
            </div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
              Mission Queue
            </h1>
            <p className="mt-1 text-gray-600 dark:text-gray-400">
              {hasActiveMissions
                ? `${inProgressMissions.length} running, ${sortedQueuedMissions.length} waiting`
                : "No active missions"}
            </p>
          </div>
          <div className="flex items-center gap-4">
            <RefreshIndicator lastRefresh={lastRefresh} isRefreshing={isRefreshing} />
            <button
              onClick={handleRefresh}
              disabled={isRefreshing}
              className="px-3 py-1.5 text-sm font-medium text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors disabled:opacity-50"
            >
              Refresh
            </button>
          </div>
        </header>

        {isLoading && !hasActiveMissions ? (
          <div className="py-12 text-center">
            <p className="text-gray-500 dark:text-gray-400">Loading queue...</p>
          </div>
        ) : !hasActiveMissions ? (
          <EmptyQueueState />
        ) : (
          <div className="space-y-8">
            {/* Running Missions Section */}
            {inProgressMissions.length > 0 && (
              <section>
                <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide mb-4">
                  Currently Running
                </h2>
                <div className="space-y-4">
                  {inProgressMissions.map((mission) => (
                    <RunningMissionCard key={mission.id} mission={mission} />
                  ))}
                </div>
              </section>
            )}

            {/* Queued Missions Section */}
            {sortedQueuedMissions.length > 0 && (
              <section>
                <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide mb-4">
                  Waiting in Queue ({sortedQueuedMissions.length})
                </h2>
                <div className="space-y-3">
                  {sortedQueuedMissions.map((mission, index) => {
                    const position = index + 1;
                    return (
                      <QueuedMissionCard
                        key={mission.id}
                        mission={mission}
                        position={position}
                        estimatedWait={estimateWaitTime(position)}
                        onCancel={handleCancelMission}
                      />
                    );
                  })}
                </div>
              </section>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function MissionQueuePage() {
  return (
    <AuthGate>
      <MissionQueueContent />
    </AuthGate>
  );
}
