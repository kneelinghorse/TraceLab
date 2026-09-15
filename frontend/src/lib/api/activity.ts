import { httpClient } from "@/lib/api/http";

export type ActivityType = "mission" | "report" | "evidence";
export interface ActivityItem {
  type: ActivityType;
  id: string;
  title: string;
  subtitle: string | null;
  status: string | null;
  occurred_at: string;
  href: string;
  new: boolean;
}
export interface ActivityPage {
  generated_at: string;
  refresh_seconds: number;
  page: number;
  page_size: number;
  total: number;
  new_total: number;
  items: ActivityItem[];
}
export interface ActivitySummary { generated_at: string; new_total: number; by_type: Record<string, number> }
export interface ViewedItem { type: ActivityType; id: string; occurred_at: string }

export const activityApi = {
  list: (params: { page?: number; page_size?: number } = {}) => httpClient.get<ActivityPage>("/activity", { params }),
  summary: () => httpClient.get<ActivitySummary>("/activity/summary"),
  markViewed: (items: ViewedItem[]) => httpClient.put<{ viewed: number; new_total: number }>("/activity/viewed", { items }),
};

export const ACTIVITY_SECTIONS: Record<ActivityType, { label: string; href: string }> = {
  mission: { label: "Missions", href: "/missions" },
  report: { label: "Reports", href: "/reports" },
  evidence: { label: "Evidence", href: "/evidence" },
};

export function newBadgeName(label: string, count: number) {
  return `${label}, ${count.toLocaleString()} new`;
}

/** The moment a mission last happened, matching the server's activity order. */
export function missionOccurredAt(mission: { status: string; completed_at?: string | null; started_at?: string | null; queued_at?: string | null; created_at?: string; updated_at: string }) {
  if (mission.status === "completed") return mission.completed_at ?? mission.updated_at;
  if (mission.status === "in_progress") return mission.started_at ?? mission.updated_at;
  if (mission.status === "queued") return mission.queued_at ?? mission.created_at ?? mission.updated_at;
  return mission.updated_at;
}
