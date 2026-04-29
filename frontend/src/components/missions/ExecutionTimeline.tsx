import { formatDistanceToNow, format } from "date-fns";

import type { MissionReportMetadata } from "@/types/mission";

interface ExecutionTimelineProps {
  createdAt: string | null;
  queuedAt: string | null;
  startedAt: string | null;
  completedAt: string | null;
  /**
   * `result_protocol.report_metadata` from a completed mission. T42.3
   * (sprint-42) swapped this surface from the lying `execution_metadata`
   * blob — `sources_count`, `loops_executed`, `coverage`,
   * `quality_gates_passed` kept emitting after DS's S64 entry-point flip
   * but no longer reflected the run. The truthful values live here, in
   * the writer.py-emitted block. Per DS message 27395546 the contract is
   * live: no fall-back to legacy fields, just an empty Execution Details
   * panel for missions that haven't finished yet.
   */
  reportMetadata: MissionReportMetadata | null | undefined;
}

interface TimelineEvent {
  label: string;
  timestamp: string;
  icon: "create" | "queue" | "start" | "complete";
}

const ICON_CLASSES: Record<TimelineEvent["icon"], { bg: string; icon: string }> = {
  create: { bg: "bg-gray-400", icon: "+" },
  queue: { bg: "bg-amber-400", icon: "Q" },
  start: { bg: "bg-blue-400", icon: "S" },
  complete: { bg: "bg-emerald-400", icon: "C" },
};

function TimelineItem({ event, isLast }: { event: TimelineEvent; isLast: boolean }) {
  const styles = ICON_CLASSES[event.icon];
  const date = new Date(event.timestamp);
  const relative = formatDistanceToNow(date, { addSuffix: true });
  const absolute = format(date, "MMM d, yyyy 'at' h:mm a");

  return (
    <div className="flex gap-3">
      <div className="flex flex-col items-center">
        <div className={`w-8 h-8 rounded-full ${styles.bg} flex items-center justify-center text-white text-xs font-bold`}>
          {styles.icon}
        </div>
        {!isLast && <div className="w-0.5 h-full bg-gray-200 dark:bg-gray-700 min-h-[24px]" />}
      </div>
      <div className="pb-4">
        <p className="font-medium text-gray-900 dark:text-white">{event.label}</p>
        <p className="text-sm text-gray-500 dark:text-gray-400" title={absolute}>
          {relative}
        </p>
      </div>
    </div>
  );
}

function MetadataCard({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3">
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">{label}</p>
      <p className="font-medium text-gray-900 dark:text-white">{String(value)}</p>
      {hint && <p className="mt-1 text-[11px] text-gray-400 dark:text-gray-500">{hint}</p>}
    </div>
  );
}

function formatRuntime(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const remSec = Math.round(seconds % 60);
  if (minutes < 60) return `${minutes}m ${remSec}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

export function ExecutionTimeline({
  createdAt,
  queuedAt,
  startedAt,
  completedAt,
  reportMetadata,
}: ExecutionTimelineProps) {
  const events: TimelineEvent[] = [];

  if (createdAt) {
    events.push({ label: "Mission Created", timestamp: createdAt, icon: "create" });
  }
  if (queuedAt) {
    events.push({ label: "Queued for Execution", timestamp: queuedAt, icon: "queue" });
  }
  if (startedAt) {
    events.push({ label: "Execution Started", timestamp: startedAt, icon: "start" });
  }
  if (completedAt) {
    events.push({ label: "Execution Completed", timestamp: completedAt, icon: "complete" });
  }

  const sources = reportMetadata?.sources_collected;
  const references = reportMetadata?.references;
  const stepsUsed = reportMetadata?.agent_steps_used;
  const stepsMax = reportMetadata?.agent_steps_max;
  const runtimeSeconds = reportMetadata?.runtime_seconds;
  const forensic = reportMetadata?.forensic;
  const buildHash = forensic?.build_hash;
  const schemaVersion = forensic?.schema_version;
  const distinctDomains = forensic?.distinct_domains;
  const distinctUrls = forensic?.distinct_urls_cited;

  const hasMetadata =
    sources != null ||
    references != null ||
    stepsUsed != null ||
    runtimeSeconds != null ||
    buildHash != null ||
    schemaVersion != null ||
    distinctDomains != null ||
    distinctUrls != null;

  return (
    <div className="space-y-6">
      {events.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide mb-4">
            Timeline
          </h3>
          <div className="space-y-0">
            {events.map((event, index) => (
              <TimelineItem key={event.label} event={event} isLast={index === events.length - 1} />
            ))}
          </div>
        </div>
      )}

      {hasMetadata && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide mb-4">
            Execution Details
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {sources != null && (
              <MetadataCard label="Sources collected" value={sources} />
            )}
            {references != null && (
              <MetadataCard label="References" value={references} />
            )}
            {stepsUsed != null && (
              <MetadataCard
                label="Agent steps"
                value={stepsMax != null ? `${stepsUsed} / ${stepsMax}` : stepsUsed}
              />
            )}
            {runtimeSeconds != null && (
              <MetadataCard label="Runtime" value={formatRuntime(runtimeSeconds)} />
            )}
            {distinctDomains != null && (
              <MetadataCard label="Distinct domains" value={distinctDomains} />
            )}
            {distinctUrls != null && (
              <MetadataCard label="URLs cited" value={distinctUrls} />
            )}
            {buildHash && (
              <MetadataCard
                label="Build"
                value={buildHash.slice(0, 12)}
                hint={schemaVersion ? `schema ${schemaVersion}` : undefined}
              />
            )}
          </div>
        </div>
      )}

      {events.length === 0 && !hasMetadata && (
        <p className="text-gray-500 dark:text-gray-400 text-sm">No execution data available yet.</p>
      )}
    </div>
  );
}
