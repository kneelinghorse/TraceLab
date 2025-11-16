import { httpClient } from "@/lib/api/http";
import type {
  SaveSearchRequestPayload,
  SavedSearch,
  SavedSearchExecuteResponse,
  SavedSearchListResponse,
  UpdateSavedSearchPayload,
} from "@/types/saved-searches";

const BASE_PATH = "/saved-searches";

export const savedSearchesApi = {
  list() {
    return httpClient.get<SavedSearchListResponse>(BASE_PATH);
  },

  create(payload: SaveSearchRequestPayload) {
    return httpClient.post<SavedSearch>(BASE_PATH, payload);
  },

  update(id: string, payload: UpdateSavedSearchPayload) {
    return httpClient.put<SavedSearch>(`${BASE_PATH}/${id}`, payload);
  },

  remove(id: string) {
    return httpClient.delete<void>(`${BASE_PATH}/${id}`);
  },

  execute(id: string) {
    return httpClient.post<SavedSearchExecuteResponse>(`${BASE_PATH}/${id}/execute`);
  },
};
