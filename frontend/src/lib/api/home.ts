import { httpClient } from "@/lib/api/http";

export interface HomeSection<T> { total: number; items: T[] }
export interface HomeMission {
  id: string;
  mission_id: string;
  title: string;
  status: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
  reason: "validation_failed" | "blocked" | "stalled" | "unreviewed" | null;
  progress: { phase: string | null; percent: number | null; current_step: number | null; total_steps: number | null };
  report_id: string | null;
  evidence_count: number;
  evidence_href: string | null;
}
export interface HomeRecent { id: string; title: string; updated_at: string | null; href: string }
export interface HomeEvidenceActivity {
  project_id: string;
  mission_id: string | null;
  session_key: string;
  origin: string;
  entry_count: number;
  last_created_at: string;
  href: string;
}
export interface HomeSnapshot {
  generated_at: string;
  refresh_seconds: number;
  stalled_after_seconds: number;
  missions: { total: number; by_status: Record<string, number> };
  attention: HomeSection<HomeMission>;
  active_runs: HomeSection<HomeMission>;
  recent_reports: HomeSection<HomeRecent>;
  recent_projects: HomeSection<HomeRecent>;
  evidence_activity: HomeSection<HomeEvidenceActivity>;
}
export const homeApi = {
  get: () => httpClient.get<HomeSnapshot>("/home"),
  review: (mission: Pick<HomeMission, "id" | "updated_at">) => httpClient.put<void>(`/home/missions/${mission.id}/review`, { updated_at: mission.updated_at }),
};
