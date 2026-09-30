import { httpClient } from "@/lib/api/http";
import type { DescriptionCitation } from "@/lib/api/librarian-descriptions";

export type CollectionDestination = { owner_id: string; workspace_id: string | null; space_name: string };
export type SuggestedMember = DescriptionCitation & { chunk_id: string; document_name: string; excerpt: string };
export type SuggestedGroup = { group_id: string; proposal_token: string; name: string; description: string; rationale: string; members: SuggestedMember[] };
export type CollectionSuggestions = {
  project_id: string; prompt: string; model: string; destination: CollectionDestination; groups: SuggestedGroup[];
  coverage: { readable_documents: number; documents_with_eligible_chunks: number; used_documents: number; readable_chunks: number; eligible_chunks: number; used_chunks: number; excluded_chunks: number; limited: boolean; chunk_limit: number; character_limit: number };
};
export type AcceptedCollection = {
  collection_id: string; name: string; href: string; state: "saved" | "partial" | "changed";
  completed_member_ids: string[]; missing_member_ids: string[]; destination: CollectionDestination; error?: string;
};
export type CollectionProvenanceState = { provenance: null | {
  origin: string; model: string; accepted_by: string; accepted_at: string; completed_at: string | null;
  destination: CollectionDestination; prompt?: string; project_id?: string; members?: DescriptionCitation[];
} };

export const organisationApi = {
  draft(projectId: string, prompt: string): Promise<CollectionSuggestions> {
    return httpClient.post("/librarian/collections/draft", { project_id: projectId, prompt });
  },
  accept(projectId: string, proposalToken: string, name: string, description: string, memberIds: string[]): Promise<AcceptedCollection> {
    return httpClient.post("/librarian/collections/accept", { project_id: projectId, proposal_token: proposalToken, name, description, member_ids: memberIds });
  },
  provenance(collectionId: string): Promise<CollectionProvenanceState> {
    return httpClient.get(`/librarian/collections/${collectionId}`);
  },
};
