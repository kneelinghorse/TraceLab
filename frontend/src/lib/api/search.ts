import { httpClient } from "@/lib/api/http";
import type {
  PEDRSearchParams,
  PEDRSearchResponse,
  RagResponsePayload,
  SearchHistoryResponse,
  SearchFacetResponse,
  SearchQueryParams,
  SearchReplayResponse,
  SemanticSearchResponse,
} from "@/types/search";

const SEMANTIC_PATH = "/retrieval/search";
const RAG_PATH = "/search";
const HISTORY_PATH = "/search/history";
const PEDR_PATH = "/pedr/search";

export const searchApi = {
  facets(params: { project_id?: string } = {}) {
    return httpClient.post<SearchFacetResponse>("/facets", params);
  },

  semanticSearch(params: SearchQueryParams) {
    return httpClient.post<SemanticSearchResponse>(SEMANTIC_PATH, params);
  },

  ragQuery(params: SearchQueryParams) {
    return httpClient.post<RagResponsePayload>(RAG_PATH, params);
  },

  history(limit = 20) {
    return httpClient.get<SearchHistoryResponse>(HISTORY_PATH, { params: { limit } });
  },

  clearHistory() {
    return httpClient.delete<{ deleted: number }>(HISTORY_PATH);
  },

  replay(historyId: string) {
    return httpClient.post<SearchReplayResponse>(`/search/replay/${historyId}`);
  },

  /**
   * PEDR unified search - 5-layer fusion search with RRF ranking.
   * Uses lexical, semantic, syntactic, pragmatic, and governance layers.
   */
  pedrSearch(params: PEDRSearchParams) {
    return httpClient.post<PEDRSearchResponse>(PEDR_PATH, params);
  },
};
