import { httpClient } from "@/lib/api/http";
import type { RagResponsePayload, SearchQueryParams, SemanticSearchResponse } from "@/types/search";

const SEMANTIC_PATH = "/retrieval/search";
const RAG_PATH = "/search";

export const searchApi = {
  semanticSearch(params: SearchQueryParams) {
    return httpClient.post<SemanticSearchResponse>(SEMANTIC_PATH, params);
  },

  ragQuery(params: SearchQueryParams) {
    return httpClient.post<RagResponsePayload>(RAG_PATH, params);
  },
};
