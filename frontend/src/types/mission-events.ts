/**
 * Types for real-time mission event streaming (SSE).
 * Mirrors backend app/core/mission_events.py MissionEvent.
 */

export type MissionEventType =
  // Mission lifecycle
  | "mission.queued"
  | "mission.started"
  | "mission.completed"
  | "mission.failed"
  | "mission.status_changed"
  // PEDR search progress
  | "pedr.search_started"
  | "pedr.layer_started"
  | "pedr.layer_completed"
  | "pedr.layer_failed"
  | "pedr.fusion_completed"
  | "pedr.search_completed"
  // Quality & governance
  | "quality.gates_evaluated"
  // System
  | "system.heartbeat";

export interface MissionEvent {
  event_type: MissionEventType;
  timestamp: string;
  mission_id?: string;
  mission_title?: string;
  layer?: string;
  duration_ms?: number;
  result_count?: number;
  status?: string;
  previous_status?: string;
  error?: string;
  details?: Record<string, unknown>;
}

/** Categorize events for display purposes. */
export function getEventCategory(type: MissionEventType): "mission" | "pedr" | "quality" | "system" {
  if (type.startsWith("mission.")) return "mission";
  if (type.startsWith("pedr.")) return "pedr";
  if (type.startsWith("quality.")) return "quality";
  return "system";
}

/** Get a human-readable label for an event. */
export function getEventLabel(event: MissionEvent): string {
  switch (event.event_type) {
    case "mission.queued":
      return `Mission queued: ${event.mission_title ?? event.mission_id ?? "unknown"}`;
    case "mission.started":
      return `Mission started: ${event.mission_title ?? event.mission_id ?? "unknown"}`;
    case "mission.completed":
      return `Mission completed: ${event.mission_title ?? event.mission_id ?? "unknown"}`;
    case "mission.failed":
      return `Mission failed: ${event.mission_title ?? event.mission_id ?? "unknown"}`;
    case "mission.status_changed":
      return `Mission ${event.mission_id ?? ""}: ${event.previous_status ?? "?"} → ${event.status ?? "?"}`;
    case "pedr.layer_completed":
      return `${event.layer ?? "layer"}: ${event.result_count ?? 0} results (${(event.duration_ms ?? 0).toFixed(0)}ms)`;
    case "pedr.layer_failed":
      return `${event.layer ?? "layer"} failed: ${event.error ?? "unknown error"}`;
    case "pedr.search_completed":
      return `Search complete: ${event.result_count ?? 0} results (${(event.duration_ms ?? 0).toFixed(0)}ms)`;
    case "quality.gates_evaluated": {
      const d = event.details ?? {};
      return `Quality gates: ${d.gates_passed ?? "?"}/${d.total_gates ?? "?"} passed (score: ${d.score ?? "?"})`;
    }
    case "system.heartbeat":
      return "heartbeat";
    default:
      return event.event_type;
  }
}
