import { httpClient } from "@/lib/api/http";

export interface DescriptionCitation {
  marker: number;
  available: boolean;
  chunk_id?: string;
  document_id?: string;
  excerpt?: string;
  href?: string;
}

export interface DescriptionProposal {
  project_id: string;
  proposal_token: string;
  description: string;
  current_description: string | null;
  prompt: string;
  basis: "corpus" | "planning_brief";
  model: string;
  citations: DescriptionCitation[];
  coverage: { readable_chunks: number; eligible_chunks: number; used_chunks: number; excluded_chunks: number; limited: boolean; chunk_limit: number; character_limit: number };
}

export interface DescriptionState {
  project_id: string;
  description: string | null;
  revision: number;
  can_restore: boolean;
  provenance: {
    proposal_id: string;
    current: boolean;
    origin: string;
    model: string;
    prompt: string;
    basis: string;
    accepted_by: string;
    accepted_at: string;
    previous_value: string | null;
    accepted_value: string;
    generated_value: string;
    edited: boolean;
    restored_at: string | null;
    citations: DescriptionCitation[];
  } | null;
}

export const descriptionApi = {
  state(projectId: string): Promise<DescriptionState> {
    return httpClient.get<DescriptionState>(`/librarian/descriptions/${projectId}`);
  },
  draft(projectId: string, prompt: string): Promise<DescriptionProposal> {
    return httpClient.post<DescriptionProposal>("/librarian/descriptions/draft", { project_id: projectId, prompt });
  },
  accept(projectId: string, proposalToken: string, description: string): Promise<DescriptionState> {
    return httpClient.post<DescriptionState>("/librarian/descriptions/accept", { project_id: projectId, proposal_token: proposalToken, description });
  },
  restore(projectId: string, proposalId: string): Promise<DescriptionState> {
    return httpClient.post<DescriptionState>("/librarian/descriptions/restore", { project_id: projectId, proposal_id: proposalId });
  },
};
