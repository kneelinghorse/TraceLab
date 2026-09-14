import { httpClient } from "@/lib/api/http";
import type { MissionListParams } from "@/types/mission";

export const ATTENTION_REASONS = ["validation_failed", "blocked", "stalled", "unreviewed"] as const;
export type AttentionReason = typeof ATTENTION_REASONS[number];
export const REASON_LABELS: Record<AttentionReason, string> = { validation_failed: "Validation failed", blocked: "Blocked", stalled: "Stalled queue", unreviewed: "Unreviewed completion" };
export type MissionViewFilters = Pick<MissionListParams, "view" | "reason" | "status" | "project_id">;
export interface SavedMissionView {
  id: string; name: string; entity_type: "missions"; filters: MissionViewFilters;
  created_at: string; updated_at: string; total: number;
}
export const BUILTIN_DASHBOARDS: { key: "at_risk" | "unreviewed"; label: string; filters: MissionViewFilters }[] = [
  { key: "at_risk", label: "At risk missions", filters: { view: "attention", reason: ["validation_failed", "blocked", "stalled"] } },
  { key: "unreviewed", label: "Unreviewed completions", filters: { view: "attention", reason: ["unreviewed"] } },
];
export function missionViewHref(filters: MissionViewFilters) {
  const params = new URLSearchParams();
  if (filters.view) params.set("view", filters.view);
  filters.reason?.forEach(reason => params.append("reason", reason));
  if (filters.status) params.set("status", filters.status);
  if (filters.project_id) params.set("project_id", filters.project_id);
  return `/missions${params.size ? `?${params}` : ""}`;
}
export const missionViewsApi = {
  list: () => httpClient.get<{ items: SavedMissionView[] }>("/mission-views"),
  create: (name: string, filters: MissionViewFilters) => httpClient.post<SavedMissionView>("/mission-views", { name, filters }),
  rename: (id: string, name: string) => httpClient.put<SavedMissionView>(`/mission-views/${id}`, { name }),
  delete: (id: string) => httpClient.delete<void>(`/mission-views/${id}`),
};
