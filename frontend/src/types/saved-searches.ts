import type { RagResponsePayload, SemanticSearchResponse } from "@/types/search";
import type { SearchFiltersState } from "@/components/SearchBar";

export interface SavedSearch {
  id: string;
  name: string;
  description?: string | null;
  query_text: string;
  search_mode: string;
  filters: Record<string, unknown>;
  top_k: number;
  owner: string;
  use_count: number;
  last_used_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface SavedSearchListResponse {
  items: SavedSearch[];
  limit_per_user: number;
}

export interface SavedSearchExecuteResponse {
  saved_search: SavedSearch;
  rag: RagResponsePayload;
  semantic: SemanticSearchResponse;
}

export interface SaveSearchRequestPayload {
  name: string;
  description?: string | null;
  query_text: string;
  search_mode?: string;
  filters: Record<string, unknown>;
  top_k: number;
}

export type UpdateSavedSearchPayload = Partial<SaveSearchRequestPayload>;

export type SaveSearchPreset = {
  query: string;
  filters: SearchFiltersState;
  topK: number;
  suggestedName?: string;
};
