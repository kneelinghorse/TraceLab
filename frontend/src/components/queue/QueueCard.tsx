import Link from "next/link";
import { formatDistanceToNow } from "date-fns";

import type { ApiMission } from "@/types/mission";

import { ExecutionProgress } from "./ExecutionProgress";

interface RunningMissionCardProps {
  mission: ApiMission;
}

export function RunningMissionCard({ mission }: RunningMissionCardProps) {
  return (
    <div className="bg-surface border-2 border-info-line rounded-xl p-6 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className="relative flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-75" />
            <span className="relative inline-flex rounded-full h-3 w-3 bg-accent" />
          </span>
          <span className="text-sm font-semibold text-accent-text uppercase tracking-wide">
            Running
          </span>
        </div>
        <Link
          href={`/missions/${mission.id}`}
          className="text-sm text-muted hover:text-accent-text transition-colors"
        >
          View Details
        </Link>
      </div>

      <h2 className="text-xl font-bold text-foreground mb-1">
        {mission.title}
      </h2>
      <p className="text-sm font-mono text-muted mb-4">
        {mission.mission_id}
      </p>

      <p className="text-secondary text-sm mb-6 line-clamp-2">
        {mission.objective}
      </p>

      <ExecutionProgress
        executionMetadata={mission.execution_metadata}
        startedAt={mission.started_at}
        status="in_progress"
      />

      {mission.started_at && (
        <p className="mt-4 text-xs text-muted">
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
    <div className="bg-surface border border-line rounded-lg p-4 hover:border-warning-line transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex-shrink-0 w-10 h-10 rounded-full bg-warning-surface flex items-center justify-center">
            <span className="text-lg font-bold text-warning">
              {position}
            </span>
          </div>
          <div className="min-w-0">
            <Link
              href={`/missions/${mission.id}`}
              className="font-semibold text-foreground hover:text-accent-text transition-colors truncate block"
            >
              {mission.title}
            </Link>
            <p className="text-xs font-mono text-muted">
              {mission.mission_id}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {estimatedWait && (
            <span className="text-xs text-muted">
              ~{estimatedWait}
            </span>
          )}
          {onCancel && (
            <button
              onClick={() => onCancel(mission.id)}
              className="text-xs text-danger hover:text-danger transition-colors px-2 py-1 rounded hover:bg-danger-surface"
            >
              Cancel
            </button>
          )}
        </div>
      </div>

      <p className="mt-2 text-sm text-secondary line-clamp-1 pl-13">
        {mission.objective}
      </p>

      {mission.queued_at && (
        <p className="mt-2 text-xs text-muted pl-13">
          Queued {formatDistanceToNow(new Date(mission.queued_at), { addSuffix: true })}
        </p>
      )}
    </div>
  );
}

export function EmptyQueueState() {
  return (
    <div className="bg-surface border border-line rounded-xl p-12 text-center">
      <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-surface flex items-center justify-center">
        <svg
          className="w-8 h-8 text-muted"
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
      <h3 className="text-lg font-semibold text-foreground mb-2">
        No Active Missions
      </h3>
      <p className="text-muted max-w-sm mx-auto">
        There are no missions currently running or waiting in the queue.
        Create a new mission to get started.
      </p>
      <Link
        href="/missions/new"
        className="mt-6 inline-flex items-center px-4 py-2 bg-accent text-on-accent rounded-lg hover:bg-accent transition-colors font-medium text-sm"
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
    <div className="flex items-center gap-2 text-xs text-muted">
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
          <span className="w-1.5 h-1.5 rounded-full bg-success" />
          <span>
            Last updated {formatDistanceToNow(lastRefresh, { addSuffix: true })}
          </span>
        </>
      )}
    </div>
  );
}
