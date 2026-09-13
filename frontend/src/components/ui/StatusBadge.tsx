const statusTokens: Record<string, string> = {
  draft: "bg-surface-alt text-secondary", queued: "bg-warning-surface text-warning", in_progress: "bg-info-surface text-info", completed: "bg-success-surface text-success", blocked: "bg-danger-surface text-danger", cancelled: "bg-surface-alt text-muted", validation_failed: "bg-warning-surface text-warning",
  final: "bg-success-surface text-success", active: "bg-success-surface text-success", inactive: "bg-surface-alt text-muted", pending: "bg-warning-surface text-warning", failed: "bg-danger-surface text-danger", skipped: "bg-surface-alt text-secondary",
};
export function StatusBadge({ status, label }: { status: string | boolean; label?: string }) {
  const key = typeof status === "boolean" ? (status ? "completed" : "inactive") : status;
  const words = key.replaceAll("_", " ");
  return <span className={`inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-medium ${statusTokens[key] ?? "bg-surface-alt text-secondary"}`}>{typeof status === "boolean" && <span aria-hidden="true">{status ? "✓" : "○"}</span>}{label ?? words.charAt(0).toUpperCase() + words.slice(1)}{typeof status === "boolean" && <span className="sr-only">{status ? " complete" : " pending"}</span>}</span>;
}
