import { formatDistanceToNow, format } from "date-fns";

interface ExecutionTimelineProps {
  createdAt: string | null;
  queuedAt: string | null;
  startedAt: string | null;
  completedAt: string | null;
  executionMetadata: Record<string, unknown>;
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

function MetadataCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3">
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">{label}</p>
      <p className="font-medium text-gray-900 dark:text-white">{String(value)}</p>
    </div>
  );
}

export function ExecutionTimeline({
  createdAt,
  queuedAt,
  startedAt,
  completedAt,
  executionMetadata,
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

  const loops = executionMetadata.loops as number | undefined;
  const duration = executionMetadata.duration as string | undefined;
  const sources = executionMetadata.sources as number | undefined;
  const model = executionMetadata.model as string | undefined;
  const tokensUsed = executionMetadata.tokens_used as number | undefined;

  const hasMetadata = loops !== undefined || duration || sources !== undefined || model;

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
            {loops !== undefined && <MetadataCard label="Loops" value={loops} />}
            {duration && <MetadataCard label="Duration" value={duration} />}
            {sources !== undefined && <MetadataCard label="Sources" value={sources} />}
            {model && <MetadataCard label="Model" value={model} />}
            {tokensUsed !== undefined && <MetadataCard label="Tokens Used" value={tokensUsed.toLocaleString()} />}
          </div>
        </div>
      )}

      {events.length === 0 && !hasMetadata && (
        <p className="text-gray-500 dark:text-gray-400 text-sm">No execution data available yet.</p>
      )}
    </div>
  );
}
