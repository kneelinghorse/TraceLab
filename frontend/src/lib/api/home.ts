import type { ActivityPage } from "@/lib/api/activity";
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
  missions: { total: number; by_status: Record<string, number> };
  activity: ActivityPage;
  active_runs: HomeSection<HomeMission>;
  recent_reports: HomeSection<HomeRecent>;
  recent_projects: HomeSection<HomeRecent>;
  favorites: HomeSection<HomeRecent>;
  evidence_activity: HomeSection<HomeEvidenceActivity>;
}
export const homeApi = {
  favorites: (params: { page?: number; page_size?: number; project_id?: string } = {}) => httpClient.get<HomeSection<HomeRecent>>("/home/favorites", { params }),
  pinProject: (id: string) => httpClient.put<void>(`/home/favorites/projects/${id}`),
  unpinProject: (id: string) => httpClient.delete<void>(`/home/favorites/projects/${id}`),
  get: () => httpClient.get<HomeSnapshot>("/home"),
};
