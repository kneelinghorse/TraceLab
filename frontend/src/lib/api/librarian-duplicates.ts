import { httpClient } from "@/lib/api/http";

export interface DuplicateDocument { id: string; name: string; href: string }
export interface DuplicatePair {
  candidate_id: string;
  kind: "exact_text" | "probable_overlap";
  score: number;
  documents: DuplicateDocument[];
  basis: string;
  evidence: { left_excerpt: string; right_excerpt: string }[];
  recommendation: string;
}
export interface DuplicateScan {
  project_id: string;
  scanned_at: string;
  method: string;
  candidates: DuplicatePair[];
  coverage: {
    readable_documents: number; scanned_documents: number; examined_documents: number;
    empty_documents: number; overlong_documents: number; exact_only_documents: number;
    limited: boolean; document_limit: number; character_limit: number;
    candidate_count: number; candidates_limited: boolean; pair_limit: number;
  };
}
export interface DuplicateComparison { candidate: DuplicatePair; documents: (DuplicateDocument & { content: string })[] }

export const duplicateApi = {
  scan(projectId: string): Promise<DuplicateScan> {
    return httpClient.post<DuplicateScan>("/librarian/duplicates/scan", { project_id: projectId });
  },
  compare(projectId: string, pair: DuplicatePair): Promise<DuplicateComparison> {
    return httpClient.post<DuplicateComparison>("/librarian/duplicates/compare", {
      project_id: projectId, document_ids: pair.documents.map(doc => doc.id), candidate_id: pair.candidate_id,
    });
  },
};
