interface ExecutionProgressProps {
  executionMetadata: Record<string, unknown>;
  startedAt: string | null;
  status: "in_progress" | "queued";
}

function formatDuration(startedAt: string): string {
  const start = new Date(startedAt).getTime();
  const now = Date.now();
  const diffMs = now - start;

  const seconds = Math.floor(diffMs / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);

  if (hours > 0) {
    return `${hours}h ${minutes % 60}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${seconds % 60}s`;
  }
  return `${seconds}s`;
}

export function ExecutionProgress({
  executionMetadata,
  startedAt,
  status,
}: ExecutionProgressProps) {
  const currentLoop = executionMetadata.current_loop as number | undefined;
  const totalLoops = executionMetadata.total_loops as number | undefined;
  const currentPhase = executionMetadata.current_phase as string | undefined;
  const sources = executionMetadata.sources as number | undefined;
  const model = executionMetadata.model as string | undefined;

  // Calculate progress percentage
  let progressPercent = 0;
  if (status === "in_progress") {
    if (currentLoop !== undefined && totalLoops !== undefined && totalLoops > 0) {
      progressPercent = Math.round((currentLoop / totalLoops) * 100);
    } else if (currentLoop !== undefined) {
      // No total, show indeterminate progress based on current loop
      progressPercent = Math.min(currentLoop * 10, 90);
    } else {
      // Running but no loop info - show small progress
      progressPercent = 10;
    }
  }

  const elapsedTime = startedAt ? formatDuration(startedAt) : null;

  return (
    <div className="space-y-3">
      {/* Progress bar */}
      <div className="h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
        {status === "in_progress" ? (
          <div
            className="h-full bg-blue-500 rounded-full transition-all duration-500"
            style={{ width: `${progressPercent}%` }}
          />
        ) : (
          <div className="h-full bg-amber-400 w-0" />
        )}
      </div>

      {/* Progress details */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
        {status === "in_progress" && (
          <>
            {currentLoop !== undefined && (
              <span className="text-gray-600 dark:text-gray-300">
                Loop{" "}
                <span className="font-medium text-gray-900 dark:text-white">
                  {currentLoop}
                  {totalLoops !== undefined && ` / ${totalLoops}`}
                </span>
              </span>
            )}
            {currentPhase && (
              <span className="text-gray-600 dark:text-gray-300">
                Phase{" "}
                <span className="font-medium text-gray-900 dark:text-white capitalize">
                  {currentPhase.replace(/_/g, " ")}
                </span>
              </span>
            )}
            {elapsedTime && (
              <span className="text-gray-600 dark:text-gray-300">
                Elapsed{" "}
                <span className="font-medium text-gray-900 dark:text-white">
                  {elapsedTime}
                </span>
              </span>
            )}
            {sources !== undefined && (
              <span className="text-gray-600 dark:text-gray-300">
                Sources{" "}
                <span className="font-medium text-gray-900 dark:text-white">
                  {sources}
                </span>
              </span>
            )}
            {model && (
              <span className="text-gray-500 dark:text-gray-400 text-xs">
                {model}
              </span>
            )}
          </>
        )}
        {status === "queued" && (
          <span className="text-amber-600 dark:text-amber-400 text-sm">
            Waiting in queue...
          </span>
        )}
      </div>
    </div>
  );
}
