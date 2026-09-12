/**
 * MissionActivityFeed — real-time mission activity via SSE.
 *
 * Connects to GET /api/v1/missions/events/stream and displays
 * live mission progress: status changes, PEDR layer results, errors.
 * Falls back to polling /events/recent on SSE failure.
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { API_BASE_URL, API_PATH_PREFIX } from "@/lib/api/http";
import { getStoredAuth } from "@/lib/auth/storage";
import type { MissionEvent, MissionEventType } from "@/types/mission-events";
import { getEventCategory, getEventLabel } from "@/types/mission-events";

const MAX_EVENTS = 100;
const RECONNECT_DELAY_MS = 3000;

interface MissionActivityFeedProps {
  /** Max events to display */
  maxDisplay?: number;
}

/** Color dot for event category */
function EventDot({ type }: { type: MissionEventType }) {
  const category = getEventCategory(type);
  const colors: Record<string, string> = {
    mission: "bg-accent",
    pedr: "bg-accent",
    quality: "bg-success",
    system: "bg-surface-alt",
  };
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full ${colors[category] ?? "bg-surface-alt"}`}
    />
  );
}

/** Status indicator for SSE connection */
function ConnectionStatus({ connected }: { connected: boolean }) {
  return (
    <span className="flex items-center gap-1.5 text-xs">
      <span
        className={`w-1.5 h-1.5 rounded-full ${
          connected ? "bg-success animate-pulse" : "bg-danger"
        }`}
      />
      <span className={connected ? "text-success dark:text-success" : "text-danger dark:text-danger"}>
        {connected ? "Live" : "Disconnected"}
      </span>
    </span>
  );
}

/** Format ISO timestamp to relative time */
function formatRelativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 1000) return "just now";
  if (diff < 60_000) return `${Math.floor(diff / 1000)}s ago`;
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  return `${Math.floor(diff / 3_600_000)}h ago`;
}

export function MissionActivityFeed({ maxDisplay = 50 }: MissionActivityFeedProps) {
  const [events, setEvents] = useState<MissionEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const addEvent = useCallback((event: MissionEvent) => {
    if (event.event_type === "system.heartbeat") return; // Don't display heartbeats
    setEvents((prev) => {
      const next = [event, ...prev];
      return next.length > MAX_EVENTS ? next.slice(0, MAX_EVENTS) : next;
    });
  }, []);

  const connect = useCallback(() => {
    // Clean up existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const auth = getStoredAuth();
    const token = auth?.token ?? "";

    // EventSource doesn't support custom headers, so pass token as query param
    const url = `${API_BASE_URL}${API_PATH_PREFIX}/missions/events/stream?token=${encodeURIComponent(token)}`;

    const eventSource = new EventSource(url);
    eventSourceRef.current = eventSource;

    // Listen for all event types we care about
    const eventTypes: MissionEventType[] = [
      "mission.queued",
      "mission.started",
      "mission.completed",
      "mission.failed",
      "mission.status_changed",
      "pedr.search_started",
      "pedr.layer_started",
      "pedr.layer_completed",
      "pedr.layer_failed",
      "pedr.fusion_completed",
      "pedr.search_completed",
      "quality.gates_evaluated",
      "system.heartbeat",
    ];

    for (const eventType of eventTypes) {
      eventSource.addEventListener(eventType, (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data) as MissionEvent;
          if (data.event_type === "system.heartbeat") {
            // Just update connected state, don't display
            setConnected(true);
            return;
          }
          addEvent(data);
        } catch {
          // Ignore parse errors
        }
      });
    }

    eventSource.onopen = () => {
      setConnected(true);
    };

    eventSource.onerror = () => {
      setConnected(false);
      eventSource.close();
      // Auto-reconnect
      reconnectTimerRef.current = setTimeout(connect, RECONNECT_DELAY_MS);
    };
  }, [addEvent]);

  // Load initial events then start SSE
  useEffect(() => {
    const auth = getStoredAuth();
    const token = auth?.token ?? "";

    // Fetch recent events for initial state
    fetch(
      `${API_BASE_URL}${API_PATH_PREFIX}/missions/events/recent?limit=50`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      }
    )
      .then((res) => (res.ok ? res.json() : []))
      .then((data: MissionEvent[]) => {
        // Reverse so newest first, filter heartbeats
        const filtered = (data ?? [])
          .filter((e) => e.event_type !== "system.heartbeat")
          .reverse();
        setEvents(filtered);
      })
      .catch(() => {
        // Ignore — SSE will provide events
      });

    // Start SSE connection
    connect();

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
    };
  }, [connect]);

  const displayEvents = events.slice(0, maxDisplay);

  return (
    <div className="bg-surface dark:bg-surface rounded-lg border border-line dark:border-line">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-line dark:border-line">
        <h3 className="text-sm font-semibold text-foreground dark:text-foreground">
          Mission Activity
        </h3>
        <ConnectionStatus connected={connected} />
      </div>

      {/* Event list */}
      <div className="max-h-[400px] overflow-y-auto divide-y divide-line dark:divide-line">
        {displayEvents.length === 0 ? (
          <div className="px-4 py-8 text-center text-sm text-muted dark:text-muted">
            No activity yet. Events will appear here when missions run.
          </div>
        ) : (
          displayEvents.map((event, i) => {
            const isError =
              event.event_type === "mission.failed" ||
              event.event_type === "pedr.layer_failed";
            return (
              <div
                key={`${event.timestamp}-${i}`}
                className={`px-4 py-2 flex items-start gap-2.5 text-sm ${
                  isError
                    ? "bg-danger-surface dark:bg-danger-surface"
                    : "hover:bg-background dark:hover:bg-surface-alt"
                }`}
              >
                <span className="mt-1.5 flex-shrink-0">
                  <EventDot type={event.event_type} />
                </span>
                <div className="flex-1 min-w-0">
                  <p
                    className={`truncate ${
                      isError
                        ? "text-danger dark:text-danger"
                        : "text-foreground dark:text-secondary"
                    }`}
                  >
                    {getEventLabel(event)}
                  </p>
                </div>
                <span className="text-xs text-muted dark:text-muted whitespace-nowrap flex-shrink-0">
                  {formatRelativeTime(event.timestamp)}
                </span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
