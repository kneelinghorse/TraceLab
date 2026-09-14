import { httpClient } from "@/lib/api/http";

export type NavigationEntityType = "project" | "document" | "mission" | "report" | "collection" | "evidence";
export type NavigationItem = { id: string; title: string; href: string };
export type NavigationGroup = { entity_type: NavigationEntityType; total: number; page: number; page_size: number; items: NavigationItem[] };
export type NavigationSearchResponse = { query: string; groups: NavigationGroup[] };

export const navigationApi = {
  search(query: string, entityType?: NavigationEntityType, page = 1) {
    return httpClient.get<NavigationSearchResponse>("/navigation/search", { params: { q: query, entity_type: entityType, page, page_size: 5 } });
  },
};
