import { httpClient } from "@/lib/api/http";
import type { PEDRSearchParams, PEDRSearchResponse } from "@/types/search";

const PEDR_PATH = "/pedr/search";

export const searchApi = {
  /**
   * PEDR unified search - 5-layer fusion search with RRF ranking.
   * Uses lexical, semantic, syntactic, pragmatic, and governance layers.
   */
  pedrSearch(params: PEDRSearchParams) {
    return httpClient.post<PEDRSearchResponse>(PEDR_PATH, params);
  },
};
