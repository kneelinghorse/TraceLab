import { StatusBadge } from "@/components/ui/StatusBadge";
/**
 * CorrectionStatusCard - Displays correction queue statistics and recent items.
 */

import type { CorrectionStatusResponse, CorrectionItem } from "@/types/console";

interface CorrectionStatusCardProps {
  status: CorrectionStatusResponse;
  onTriggerRetry?: () => void;
  onClearCompleted?: () => void;
  isLoading?: boolean;
}

const ERROR_TYPE_LABELS: Record<string, string> = {
  no_embedding: "No Embedding",
  low_similarity: "Low Similarity",
  no_chunks: "No Chunks",
  timeout: "Timeout",
  validation_error: "Validation Error",
  empty_content: "Empty Content",
  database_error: "Database Error",
};

function StatBox({ label, value, color }: { label: string; value: number | string; color: string }) {
  return (
    <div className={`px-4 py-3 rounded-lg ${color}`}>
      <div className="text-2xl font-bold">{value}</div>
      <div className="text-sm">{label}</div>
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
    <div className="flex items-center justify-between py-2 border-b border-line dark:border-line last:border-0">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <StatusBadge status={item.status} />
          <span className="text-sm font-medium text-foreground dark:text-foreground truncate">
            {item.evidence_id}
          </span>
        </div>
        <div className="text-xs text-muted dark:text-muted mt-1">
          {ERROR_TYPE_LABELS[item.error_type] ?? item.error_type} • Retry {item.retry_count}/{item.max_retries}
          {item.best_similarity != null && ` • Best: ${Math.round(item.best_similarity * 100)}%`}
        </div>
      </div>
      <div className="text-xs text-muted dark:text-muted ml-4">
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
    : null;

  return (
    <div className="bg-surface dark:bg-surface rounded-lg border border-line dark:border-line p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <h3 className="text-lg font-semibold text-foreground dark:text-foreground">
          Correction Queue
        </h3>
        <div className="flex flex-wrap gap-2">
          {onTriggerRetry && stats.pending > 0 && (
            <button
              onClick={onTriggerRetry}
              disabled={isLoading}
              className="text-sm px-3 py-1.5 bg-accent text-on-accent rounded hover:bg-accent disabled:opacity-50"
            >
              Retry Pending
            </button>
          )}
          {onClearCompleted && stats.completed > 0 && (
            <button
              onClick={onClearCompleted}
              disabled={isLoading}
              className="text-sm px-3 py-1.5 border border-line-strong dark:border-line-strong text-secondary dark:text-secondary rounded hover:bg-background dark:hover:bg-surface-alt disabled:opacity-50"
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
          color="bg-warning-surface text-warning dark:bg-warning-surface dark:text-warning"
        />
        <StatBox
          label="In Progress"
          value={stats.in_progress}
          color="bg-info-surface text-info dark:bg-info-surface dark:text-accent-text"
        />
        <StatBox
          label="Completed"
          value={stats.completed}
          color="bg-success-surface text-success dark:bg-success-surface dark:text-success"
        />
        <StatBox
          label="Failed"
          value={stats.failed}
          color="bg-danger-surface text-danger dark:bg-danger-surface dark:text-danger"
        />
        <StatBox
          label="Success Rate"
          value={successRate == null ? "No attempts" : `${successRate}%`}
          color="bg-info-surface text-info dark:bg-info-surface dark:text-accent-text"
        />
      </div>

      {/* Error Distribution */}
      {Object.keys(error_distribution).length > 0 && (
        <div className="mb-6">
          <h4 className="text-sm font-medium text-secondary dark:text-secondary mb-3">
            Error Distribution
          </h4>
          <div className="flex flex-wrap gap-2">
            {Object.entries(error_distribution).map(([type, count]) => (
              <span
                key={type}
                className="text-xs px-2 py-1 bg-surface dark:bg-surface-alt text-secondary dark:text-secondary rounded"
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
          <h4 className="text-sm font-medium text-secondary dark:text-secondary mb-3">
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
        <p className="text-center text-muted dark:text-muted py-4">
          No corrections in queue.
        </p>
      )}

      {/* Last Updated */}
      <div className="mt-4 pt-4 border-t border-line dark:border-line text-xs text-muted dark:text-muted">
        Last updated: {new Date(status.last_updated).toLocaleString()}
      </div>
    </div>
  );
}
