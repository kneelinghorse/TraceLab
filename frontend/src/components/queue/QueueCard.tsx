import Link from "next/link";
import { formatDistanceToNow } from "date-fns";

import type { ApiMission } from "@/types/mission";

import { ExecutionProgress } from "./ExecutionProgress";

interface RunningMissionCardProps {
  mission: ApiMission;
}

export function RunningMissionCard({ mission }: RunningMissionCardProps) {
  return (
    <div className="bg-white dark:bg-gray-800 border-2 border-blue-400 dark:border-blue-500 rounded-xl p-6 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className="relative flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-3 w-3 bg-blue-500" />
          </span>
          <span className="text-sm font-semibold text-blue-600 dark:text-blue-400 uppercase tracking-wide">
            Running
          </span>
        </div>
        <Link
          href={`/missions/${mission.id}`}
          className="text-sm text-gray-500 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
        >
          View Details
        </Link>
      </div>

      <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-1">
        {mission.title}
      </h2>
      <p className="text-sm font-mono text-gray-500 dark:text-gray-400 mb-4">
        {mission.mission_id}
      </p>

      <p className="text-gray-600 dark:text-gray-300 text-sm mb-6 line-clamp-2">
        {mission.objective}
      </p>

      <ExecutionProgress
        executionMetadata={mission.execution_metadata}
        startedAt={mission.started_at}
        status="in_progress"
      />

      {mission.started_at && (
        <p className="mt-4 text-xs text-gray-500 dark:text-gray-400">
          Started {formatDistanceToNow(new Date(mission.started_at), { addSuffix: true })}
        </p>
      )}
    </div>
  );
}

interface QueuedMissionCardProps {
  mission: ApiMission;
  position: number;
  estimatedWait?: string;
  onCancel?: (missionId: string) => void;
}

export function QueuedMissionCard({
  mission,
  position,
  estimatedWait,
  onCancel,
}: QueuedMissionCardProps) {
  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:border-amber-400 dark:hover:border-amber-500 transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex-shrink-0 w-10 h-10 rounded-full bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center">
            <span className="text-lg font-bold text-amber-600 dark:text-amber-400">
              {position}
            </span>
          </div>
          <div className="min-w-0">
            <Link
              href={`/missions/${mission.id}`}
              className="font-semibold text-gray-900 dark:text-white hover:text-blue-600 dark:hover:text-blue-400 transition-colors truncate block"
            >
              {mission.title}
            </Link>
            <p className="text-xs font-mono text-gray-500 dark:text-gray-400">
              {mission.mission_id}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {estimatedWait && (
            <span className="text-xs text-gray-500 dark:text-gray-400">
              ~{estimatedWait}
            </span>
          )}
          {onCancel && (
            <button
              onClick={() => onCancel(mission.id)}
              className="text-xs text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 transition-colors px-2 py-1 rounded hover:bg-red-50 dark:hover:bg-red-900/20"
            >
              Cancel
            </button>
          )}
        </div>
      </div>

      <p className="mt-2 text-sm text-gray-600 dark:text-gray-300 line-clamp-1 pl-13">
        {mission.objective}
      </p>

      {mission.queued_at && (
        <p className="mt-2 text-xs text-gray-500 dark:text-gray-400 pl-13">
          Queued {formatDistanceToNow(new Date(mission.queued_at), { addSuffix: true })}
        </p>
      )}
    </div>
  );
}

export function EmptyQueueState() {
  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-12 text-center">
      <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gray-100 dark:bg-gray-700 flex items-center justify-center">
        <svg
          className="w-8 h-8 text-gray-400"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"
          />
        </svg>
      </div>
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
        No Active Missions
      </h3>
      <p className="text-gray-500 dark:text-gray-400 max-w-sm mx-auto">
        There are no missions currently running or waiting in the queue.
        Create a new mission to get started.
      </p>
      <Link
        href="/missions/new"
        className="mt-6 inline-flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium text-sm"
      >
        Create Mission
      </Link>
    </div>
  );
}

interface RefreshIndicatorProps {
  lastRefresh: Date;
  isRefreshing: boolean;
}

export function RefreshIndicator({ lastRefresh, isRefreshing }: RefreshIndicatorProps) {
  return (
    <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
      {isRefreshing ? (
        <>
          <svg className="animate-spin h-3 w-3" fill="none" viewBox="0 0 24 24">
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
          <span>Refreshing...</span>
        </>
      ) : (
        <>
          <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
          <span>
            Last updated {formatDistanceToNow(lastRefresh, { addSuffix: true })}
          </span>
        </>
      )}
    </div>
  );
}
