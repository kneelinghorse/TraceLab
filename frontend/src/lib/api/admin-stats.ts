import { httpClient } from "./http";

export interface AdminStats {
  generated_at: string;
  refresh_seconds: number;
  scope: "system";
  missions: { total: number; by_status: Record<string, number> };
  projects: number;
  documents: number;
  chunks: number;
  reports: number;
  ingestion_jobs: { total: number; by_status: Record<string, number> };
  graph_edges: number;
  graph_edges_by_type: Record<string, number>;
  evidence_entries: number;
  evidence_sources: number;
  evidence_notes: number;
  recent_missions: { id: string; mission_id: string; title: string; status: string; updated_at: string }[];
  worker: {
    status: string;
    checked_at: string;
    uptime_seconds: number | null;
    missions_processed: number | null;
    missions_completed: number | null;
    missions_failed: number | null;
    current_mission_id: string | null;
    error: string | null;
  } | null;
  reconciler: { enabled?: boolean; last_run_at?: string | null; last_status?: string | null; runs?: number; last_counts?: Record<string, number> };
  corrections: Record<string, number> | null;
  corrections_error: string | null;
  process_scope: string;
}

export const adminStatsApi = { get: (): Promise<AdminStats> => httpClient.get("/admin/stats") };
