/**
 * CorrectionStatusCard - Displays correction queue statistics and recent items.
 */

import type { CorrectionStatusResponse, CorrectionItem, CorrectionStatus } from "@/types/console";

interface CorrectionStatusCardProps {
  status: CorrectionStatusResponse;
  onTriggerRetry?: () => void;
  onClearCompleted?: () => void;
  isLoading?: boolean;
}

const STATUS_COLORS: Record<CorrectionStatus, string> = {
  pending: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
  in_progress: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  completed: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  failed: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  skipped: "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200",
};

const ERROR_TYPE_LABELS: Record<string, string> = {
  no_embedding: "No Embedding",
  low_similarity: "Low Similarity",
  no_chunks: "No Chunks",
  timeout: "Timeout",
  validation_error: "Validation Error",
  empty_content: "Empty Content",
  database_error: "Database Error",
};

function StatBox({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className={`px-4 py-3 rounded-lg ${color}`}>
      <div className="text-2xl font-bold">{value}</div>
      <div className="text-sm opacity-80">{label}</div>
    </div>
  );
}

function CorrectionItemRow({ item }: { item: CorrectionItem }) {
  const timeSince = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const minutes = Math.floor(diff / 60000);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
  };

  return (
    <div className="flex items-center justify-between py-2 border-b border-gray-100 dark:border-gray-700 last:border-0">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className={`text-xs px-2 py-0.5 rounded-full ${STATUS_COLORS[item.status]}`}>
            {item.status}
          </span>
          <span className="text-sm font-medium text-gray-900 dark:text-white truncate">
            {item.evidence_id}
          </span>
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
          {ERROR_TYPE_LABELS[item.error_type] ?? item.error_type} • Retry {item.retry_count}/{item.max_retries}
          {item.best_similarity != null && ` • Best: ${Math.round(item.best_similarity * 100)}%`}
        </div>
      </div>
      <div className="text-xs text-gray-400 dark:text-gray-500 ml-4">
        {timeSince(item.updated_at)}
      </div>
    </div>
  );
}

export function CorrectionStatusCard({
  status,
  onTriggerRetry,
  onClearCompleted,
  isLoading,
}: CorrectionStatusCardProps) {
  const { stats, error_distribution, recent_items } = status;
  const successRate = stats.completed + stats.failed > 0
    ? Math.round((stats.completed / (stats.completed + stats.failed)) * 100)
    : 0;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
          Correction Queue
        </h3>
        <div className="flex gap-2">
          {onTriggerRetry && stats.pending > 0 && (
            <button
              onClick={onTriggerRetry}
              disabled={isLoading}
              className="text-sm px-3 py-1.5 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
            >
              Retry Pending
            </button>
          )}
          {onClearCompleted && stats.completed > 0 && (
            <button
              onClick={onClearCompleted}
              disabled={isLoading}
              className="text-sm px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
            >
              Clear Completed
            </button>
          )}
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
        <StatBox
          label="Pending"
          value={stats.pending}
          color="bg-yellow-50 text-yellow-900 dark:bg-yellow-900/30 dark:text-yellow-200"
        />
        <StatBox
          label="In Progress"
          value={stats.in_progress}
          color="bg-blue-50 text-blue-900 dark:bg-blue-900/30 dark:text-blue-200"
        />
        <StatBox
          label="Completed"
          value={stats.completed}
          color="bg-green-50 text-green-900 dark:bg-green-900/30 dark:text-green-200"
        />
        <StatBox
          label="Failed"
          value={stats.failed}
          color="bg-red-50 text-red-900 dark:bg-red-900/30 dark:text-red-200"
        />
        <StatBox
          label="Success Rate"
          value={successRate}
          color="bg-purple-50 text-purple-900 dark:bg-purple-900/30 dark:text-purple-200"
        />
      </div>

      {/* Error Distribution */}
      {Object.keys(error_distribution).length > 0 && (
        <div className="mb-6">
          <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
            Error Distribution
          </h4>
          <div className="flex flex-wrap gap-2">
            {Object.entries(error_distribution).map(([type, count]) => (
              <span
                key={type}
                className="text-xs px-2 py-1 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded"
              >
                {ERROR_TYPE_LABELS[type] ?? type}: {count}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Recent Items */}
      {recent_items.length > 0 && (
        <div>
          <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
            Recent Items
          </h4>
          <div className="max-h-64 overflow-y-auto">
            {recent_items.map((item) => (
              <CorrectionItemRow key={item.correction_id} item={item} />
            ))}
          </div>
        </div>
      )}

      {/* Empty State */}
      {stats.total === 0 && (
        <p className="text-center text-gray-500 dark:text-gray-400 py-4">
          No corrections in queue.
        </p>
      )}

      {/* Last Updated */}
      <div className="mt-4 pt-4 border-t border-gray-100 dark:border-gray-700 text-xs text-gray-400 dark:text-gray-500">
        Last updated: {new Date(status.last_updated).toLocaleString()}
      </div>
    </div>
  );
}
