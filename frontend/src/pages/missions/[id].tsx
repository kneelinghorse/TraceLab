import Link from "next/link";
import { useRouter } from "next/router";
import { formatDistanceToNow } from "date-fns";

import { AuthGate } from "@/components/AuthGate";
import { useApiMission } from "@/lib/hooks/useMissions";
import type { MissionStatus } from "@/types/mission";

const STATUS_COLORS: Record<MissionStatus, { bg: string; text: string; dot: string }> = {
  draft: { bg: "bg-gray-100 dark:bg-gray-700", text: "text-gray-700 dark:text-gray-300", dot: "bg-gray-400" },
  queued: { bg: "bg-amber-100 dark:bg-amber-900/30", text: "text-amber-700 dark:text-amber-300", dot: "bg-amber-400" },
  in_progress: { bg: "bg-blue-100 dark:bg-blue-900/30", text: "text-blue-700 dark:text-blue-300", dot: "bg-blue-400" },
  completed: { bg: "bg-emerald-100 dark:bg-emerald-900/30", text: "text-emerald-700 dark:text-emerald-300", dot: "bg-emerald-400" },
  blocked: { bg: "bg-red-100 dark:bg-red-900/30", text: "text-red-700 dark:text-red-300", dot: "bg-red-400" },
  cancelled: { bg: "bg-gray-100 dark:bg-gray-700", text: "text-gray-500 dark:text-gray-400", dot: "bg-gray-300" },
};

function StatusBadge({ status }: { status: MissionStatus }) {
  const colors = STATUS_COLORS[status] ?? STATUS_COLORS.draft;
  const label = status.replace("_", " ");

  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium ${colors.bg} ${colors.text}`}>
      <span className={`w-2 h-2 rounded-full ${colors.dot}`} />
      {label.charAt(0).toUpperCase() + label.slice(1)}
    </span>
  );
}

function MissionDetailContent() {
  const router = useRouter();
  const missionId = typeof router.query.id === "string" ? router.query.id : undefined;

  const { mission, isLoading, error, refresh } = useApiMission(missionId);

  if (!missionId) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 py-8">
        <div className="max-w-4xl mx-auto px-4">
          <p className="text-gray-600 dark:text-gray-400">Select a mission to view details.</p>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 py-8">
        <div className="max-w-4xl mx-auto px-4">
          <p className="text-gray-600 dark:text-gray-400">Loading mission...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 py-8">
        <div className="max-w-4xl mx-auto px-4">
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-6">
            <p className="text-red-600 dark:text-red-400">
              Failed to load mission: {error.message}
            </p>
            <button
              onClick={refresh}
              className="mt-2 text-sm font-medium text-red-700 dark:text-red-300 underline"
            >
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!mission) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 py-8">
        <div className="max-w-4xl mx-auto px-4">
          <p className="text-gray-600 dark:text-gray-400">Mission not found.</p>
        </div>
      </div>
    );
  }

  const createdAt = mission.created_at
    ? formatDistanceToNow(new Date(mission.created_at), { addSuffix: true })
    : null;
  const updatedAt = mission.updated_at
    ? formatDistanceToNow(new Date(mission.updated_at), { addSuffix: true })
    : null;
  const startedAt = mission.started_at
    ? formatDistanceToNow(new Date(mission.started_at), { addSuffix: true })
    : null;
  const completedAt = mission.completed_at
    ? formatDistanceToNow(new Date(mission.completed_at), { addSuffix: true })
    : null;

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 py-8">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="mb-6">
          <Link
            href="/missions"
            className="inline-flex items-center text-sm text-blue-600 dark:text-blue-400 hover:text-blue-700"
          >
            &larr; Back to missions
          </Link>
        </div>

        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
          <div className="p-6 border-b border-gray-200 dark:border-gray-700">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-3 mb-2">
                  <StatusBadge status={mission.status} />
                  <span className="text-sm font-mono text-gray-500 dark:text-gray-400">
                    {mission.mission_id}
                  </span>
                </div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
                  {mission.title}
                </h1>
                <p className="mt-2 text-gray-600 dark:text-gray-300">
                  {mission.objective}
                </p>
              </div>
              <button
                onClick={refresh}
                className="px-3 py-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white border border-gray-300 dark:border-gray-600 rounded-lg"
              >
                Refresh
              </button>
            </div>

            {mission.tags.length > 0 && (
              <div className="mt-4 flex flex-wrap gap-2">
                {mission.tags.map((tag) => (
                  <span
                    key={tag}
                    className="px-2 py-1 text-xs bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 rounded"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            )}

            <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
              {createdAt && (
                <div>
                  <p className="text-gray-500 dark:text-gray-400">Created</p>
                  <p className="text-gray-900 dark:text-white">{createdAt}</p>
                </div>
              )}
              {startedAt && (
                <div>
                  <p className="text-gray-500 dark:text-gray-400">Started</p>
                  <p className="text-gray-900 dark:text-white">{startedAt}</p>
                </div>
              )}
              {completedAt && (
                <div>
                  <p className="text-gray-500 dark:text-gray-400">Completed</p>
                  <p className="text-gray-900 dark:text-white">{completedAt}</p>
                </div>
              )}
              {updatedAt && (
                <div>
                  <p className="text-gray-500 dark:text-gray-400">Updated</p>
                  <p className="text-gray-900 dark:text-white">{updatedAt}</p>
                </div>
              )}
            </div>
          </div>

          {mission.success_criteria.length > 0 && (
            <div className="p-6 border-b border-gray-200 dark:border-gray-700">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
                Success Criteria
              </h2>
              <ul className="space-y-2">
                {mission.success_criteria.map((criterion, index) => (
                  <li key={index} className="flex items-start gap-2">
                    <span className="mt-1 w-1.5 h-1.5 rounded-full bg-gray-400 flex-shrink-0" />
                    <span className="text-gray-600 dark:text-gray-300">{criterion}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {mission.deliverables.length > 0 && (
            <div className="p-6 border-b border-gray-200 dark:border-gray-700">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
                Deliverables
              </h2>
              <ul className="space-y-2">
                {mission.deliverables.map((deliverable, index) => (
                  <li key={index} className="flex items-start gap-2">
                    <span className="mt-1 w-1.5 h-1.5 rounded-full bg-blue-400 flex-shrink-0" />
                    <span className="text-gray-600 dark:text-gray-300">{deliverable}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {mission.error_message && (
            <div className="p-6 border-b border-gray-200 dark:border-gray-700">
              <h2 className="text-lg font-semibold text-red-600 dark:text-red-400 mb-3">
                Error
              </h2>
              <p className="text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 p-4 rounded-lg">
                {mission.error_message}
              </p>
            </div>
          )}

          {mission.result_markdown && (
            <div className="p-6 border-b border-gray-200 dark:border-gray-700">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
                Results
              </h2>
              <div className="prose prose-sm dark:prose-invert max-w-none bg-gray-50 dark:bg-gray-900 p-4 rounded-lg">
                <pre className="whitespace-pre-wrap text-sm text-gray-700 dark:text-gray-300 font-mono">
                  {mission.result_markdown}
                </pre>
              </div>
            </div>
          )}

          {mission.result_report_id && (
            <div className="p-6 border-b border-gray-200 dark:border-gray-700">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
                Generated Report
              </h2>
              <Link
                href={`/reports/${mission.result_report_id}`}
                className="inline-flex items-center text-blue-600 dark:text-blue-400 hover:text-blue-700 font-medium"
              >
                View Report &rarr;
              </Link>
            </div>
          )}

          {mission.deepsearch_job_id && (
            <div className="p-6">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
                Execution Details
              </h2>
              <div className="grid gap-4 sm:grid-cols-2 text-sm">
                <div>
                  <p className="text-gray-500 dark:text-gray-400">DeepSearch Job ID</p>
                  <p className="font-mono text-gray-900 dark:text-white">{mission.deepsearch_job_id}</p>
                </div>
                {mission.created_by && (
                  <div>
                    <p className="text-gray-500 dark:text-gray-400">Created By</p>
                    <p className="text-gray-900 dark:text-white">{mission.created_by}</p>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function MissionDetailPage() {
  return (
    <AuthGate>
      <MissionDetailContent />
    </AuthGate>
  );
}
