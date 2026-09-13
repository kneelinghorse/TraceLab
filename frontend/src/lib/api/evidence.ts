import { httpClient } from "@/lib/api/http";

export interface LedgerEntry {
  id: string;
  project_id: string;
  mission_id: string | null;
  session_key: string;
  claim: string;
  summary: string | null;
  source_url: string;
  source_sighting_count: number;
  disposition: "supporting" | "contradicting" | "background" | "rejected";
  tags: string[];
  created_at: string;
}

export interface LedgerPage {
  entries: LedgerEntry[];
  entry_total: number;
  page: number;
  page_size: number;
}

export const evidenceApi = {
  list(projectId: string, page = 1, filters: { mission_id?: string; session_key?: string } = {}): Promise<LedgerPage> {
    return httpClient.get("/evidence", { params: { project_id: projectId, page, page_size: 20, ...filters } });
  },
};
