import { httpClient } from "@/lib/api/http";
import type { DescriptionCitation } from "@/lib/api/librarian-descriptions";

export type ReportFormat = "summary" | "report" | "bullets" | "markdown";
export type ReportInputs = {
  project_id: string; collection_id: string | null; collection_name: string | null; source_token: string;
  members: { marker: number; chunk_id: string; document_name: string; text: string; characters: number; href: string }[];
  coverage: { readable_chunks: number; eligible_chunks: number; excluded_chunks: number; other_project_chunks: number; listed_chunks: number; limited: boolean; candidate_limit: number; chunk_limit: number; character_limit: number };
};
export type ReportPreview = {
  project_id: string; report_id: string; title: string; prompt: string; format: ReportFormat; content: string;
  proposal_token: string; model: string; generated_at: string; citations: DescriptionCitation[]; input_chunk_ids: string[]; input_characters: number;
};
export type SavedReport = { report_id: string; title: string; href: string };
export type ReportDraftInput = { project_id: string; source_token: string; chunk_ids: string[]; reviewed_sources: true; title: string; prompt: string; format: ReportFormat };

export const librarianReportsApi = {
  sources(projectId: string, collectionId?: string): Promise<ReportInputs> {
    return httpClient.get("/librarian/reports/sources", { params: { project_id: projectId, collection_id: collectionId } });
  },
  draft(input: ReportDraftInput): Promise<ReportPreview> {
    return httpClient.post("/librarian/reports/draft", input);
  },
  accept(projectId: string, proposalToken: string): Promise<SavedReport> {
    return httpClient.post("/librarian/reports/accept", { project_id: projectId, proposal_token: proposalToken });
  },
};
