import { httpClient } from "@/lib/api/http";
import type { NavigationEntityType } from "@/lib/api/navigation";

export type GraphDepth = 1 | 2;
export interface GraphNode {
  key: string; type: NavigationEntityType; id: string; title: string; href: string;
  attributes: { updated_at?: string; status?: string; disposition?: string; chunk_count?: number; processed?: boolean; project_id?: string };
}
export interface GraphEdge { from: string; to: string; relation: string; basis: string }
export interface GraphGroup { from_key: string; relation: string; target_type: NavigationEntityType; total: number; shown: number }
export interface GraphNeighborhood { root: GraphNode; nodes: GraphNode[]; edges: GraphEdge[]; groups: GraphGroup[]; truncated: boolean }

export const graphApi = {
  neighborhood(rootType: NavigationEntityType, rootId: string, depth: GraphDepth = 1): Promise<GraphNeighborhood> {
    return httpClient.get("/graph/neighborhood", { params: { root_type: rootType, root_id: rootId, depth, per_relation_limit: 12, max_nodes: 60 } });
  },
};
export function graphHref(type: NavigationEntityType, id: string, depth?: GraphDepth) {
  return `/graph?root=${type}:${id}${depth ? `&depth=${depth}` : ""}`;
}
export function parseGraphRoot(value: string | string[] | undefined): { type: NavigationEntityType; id: string } | null {
  const match = typeof value === "string" && /^(project|document|collection|mission|report|evidence):([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i.exec(value);
  return match ? { type: match[1].toLowerCase() as NavigationEntityType, id: match[2] } : null;
}
