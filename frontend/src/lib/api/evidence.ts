import { httpClient } from "@/lib/api/http";

export type Disposition = "supporting" | "contradicting" | "background" | "rejected";
export interface LedgerEntry {
  id: string;
  project_id: string;
  mission_id: string | null;
  session_key: string;
  origin: "mcp-agent" | "deepsearch-worker";
  claim: string;
  summary: string | null;
  snippet: string | null;
  query: string | null;
  source_url: string;
  source_id: string;
  source_sighting_count: number;
  disposition: Disposition;
  tags: string[];
  created_at: string;
  updated_at: string;
}
export interface LedgerNote {
  id: string; session_key: string; note_key: string; content: string; tags: string[]; updated_at: string;
}
export interface LedgerPage {
  entries: LedgerEntry[]; entry_total: number; notes: LedgerNote[]; note_total: number; page: number; page_size: number;
}
export interface EvidenceFilters {
  mission_id?: string; session_key?: string; disposition?: Disposition; tag?: string;
  created_from?: string; created_until?: string; source_id?: string; report_id?: string; document_id?: string;
}
export interface EvidenceDetail {
  entry: LedgerEntry;
  links: { kind: "mission" | "report"; id: string; title: string; href: string; relationship: string; mission_result?: boolean }[];
}
export interface PromotionResult { report_id: string; document_id: string | null; title: string; entry_count: number; note_count: number }
export const evidenceApi = {
  list(projectId: string, page = 1, filters: EvidenceFilters = {}): Promise<LedgerPage> {
    return httpClient.get("/evidence", { params: { project_id: projectId, page, page_size: 20, ...filters } });
  },
  async search(projectId: string, q: string, page = 1, filters: EvidenceFilters = {}): Promise<LedgerPage> {
    const result = await httpClient.get<{ entries: LedgerEntry[]; total: number; page: number; page_size: number }>("/evidence/search", { params: { project_id: projectId, q, page, page_size: 20, ...filters } });
    return { ...result, entry_total: result.total, notes: [], note_total: 0 };
  },
  get(id: string): Promise<EvidenceDetail> { return httpClient.get(`/evidence/${id}`); },
  promote(body: { project_id: string; session_key: string; target: "report" | "document"; title?: string }): Promise<PromotionResult> {
    return httpClient.post("/evidence/promote", body);
  },
};
export function evidenceHref(projectId: string, filters: EvidenceFilters = {}) {
  const query = new URLSearchParams({ project_id: projectId });
  Object.entries(filters).forEach(([key, value]) => { if (value) query.set(key, value); });
  return `/evidence?${query}`;
}
export function sourceDomain(url: string) { try { return new URL(url).hostname; } catch { return "Source"; } }
