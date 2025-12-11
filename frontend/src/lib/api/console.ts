/**
 * API client for Operator Console endpoints.
 * Handles relationships, corrections, and console-specific data fetching.
 */

import { httpClient } from "@/lib/api/http";
import type {
  CorrectionStatusResponse,
  CorrectionTelemetry,
  RelationshipContextResponse,
  WorkerHealthResponse,
} from "@/types/console";
import type { ApiMission } from "@/types/mission";
import type { PaginatedResponse } from "@/types/pagination";

// ==================== Relationships API ====================

export interface GetRelationshipContextParams {
  depth?: 1 | 2;
  entityTypes?: string[];
  minRelevance?: number;
}

export async function getRelationshipContext(
  missionId: string,
  params: GetRelationshipContextParams = {}
): Promise<RelationshipContextResponse> {
  const queryParams: Record<string, string | number | undefined> = {
    depth: params.depth,
    min_relevance: params.minRelevance,
  };

  // Handle array parameter for entity_types
  if (params.entityTypes?.length) {
    queryParams.entity_types = params.entityTypes.join(",");
  }

  return httpClient.get<RelationshipContextResponse>(
    `/missions/${missionId}/related`,
    { params: queryParams }
  );
}

// ==================== Corrections API ====================

export async function getCorrectionStatus(
  limit: number = 20
): Promise<CorrectionStatusResponse> {
  return httpClient.get<CorrectionStatusResponse>("/deepsearch/corrections", {
    params: { limit },
  });
}

export async function getCorrectionTelemetry(): Promise<CorrectionTelemetry> {
  return httpClient.get<CorrectionTelemetry>("/deepsearch/corrections/telemetry");
}

// ==================== Worker Health API ====================

export async function getWorkerHealth(): Promise<WorkerHealthResponse> {
  return httpClient.get<WorkerHealthResponse>("/deepsearch/worker/health");
}

export interface TriggerCorrectionParams {
  missionUuid?: string;
  evidenceIds?: string[];
  forceRetry?: boolean;
  callbackUrl?: string;
}

export interface TriggerCorrectionResponse {
  triggered: number;
  skipped: number;
  correction_ids: string[];
  message: string;
}

export async function triggerCorrections(
  params: TriggerCorrectionParams = {}
): Promise<TriggerCorrectionResponse> {
  return httpClient.post<TriggerCorrectionResponse>("/deepsearch/corrections", {
    mission_uuid: params.missionUuid,
    evidence_ids: params.evidenceIds,
    force_retry: params.forceRetry,
    callback_url: params.callbackUrl,
  });
}

export async function processCorrections(
  limit: number = 50
): Promise<{ processed: number; message: string; stats: Record<string, number> }> {
  return httpClient.post("/deepsearch/corrections/process", undefined, {
    params: { limit },
  });
}

export async function clearCompletedCorrections(): Promise<{
  cleared: number;
  message: string;
  stats: Record<string, number>;
}> {
  return httpClient.delete("/deepsearch/corrections/completed");
}

export interface DeadLetterItem {
  url: string;
  payload: Record<string, unknown>;
  error: string;
  attempts: number;
  last_attempt: string;
}

export async function getDeadLetterQueue(
  limit: number = 50
): Promise<{ count: number; items: DeadLetterItem[] }> {
  return httpClient.get("/deepsearch/corrections/dead-letter", {
    params: { limit },
  });
}

// ==================== Console Dashboard API ====================

/**
 * Fetch missions with computed console metrics.
 * Uses existing mission API (paginated response).
 */
export async function getConsoleMissions(): Promise<ApiMission[]> {
  const response = await httpClient.get<PaginatedResponse<ApiMission>>("/missions", {
    params: { page_size: 100 },
  });
  return response.data;
}

/**
 * Compute dashboard stats from missions and corrections data.
 * Uses ApiMission schema where status is directly on the mission object.
 */
export function computeDashboardStats(
  missions: ApiMission[],
  corrections: CorrectionStatusResponse
): {
  missionsByStatus: Record<string, number>;
  qualityDistribution: { excellent: number; good: number; fair: number; poor: number };
  totalMissions: number;
} {
  const missionsByStatus: Record<string, number> = {};
  const qualityDistribution = { excellent: 0, good: 0, fair: 0, poor: 0 };

  for (const mission of missions) {
    // Count by status - status is directly on ApiMission
    const status = mission.status ?? "draft";
    missionsByStatus[status] = (missionsByStatus[status] ?? 0) + 1;

    // Quality distribution based on success criteria completion
    // Since we don't have completion_percentage, use whether mission is completed
    if (mission.status === "completed") {
      qualityDistribution.excellent++;
    } else if (mission.status === "in_progress") {
      qualityDistribution.good++;
    } else if (mission.status === "queued") {
      qualityDistribution.fair++;
    } else {
      qualityDistribution.poor++;
    }
  }

  return {
    missionsByStatus,
    qualityDistribution,
    totalMissions: missions.length,
  };
}

// ==================== Export Utilities ====================

/**
 * Generate export content for a mission in JSON format.
 */
export function exportMissionAsJson(
  mission: ApiMission,
  relationships?: RelationshipContextResponse
): string {
  const exportData = {
    mission: {
      id: mission.id,
      mission_id: mission.mission_id,
      title: mission.title,
      objective: mission.objective,
      status: mission.status,
      success_criteria: mission.success_criteria,
      deliverables: mission.deliverables,
      tags: mission.tags,
      created_at: mission.created_at,
      updated_at: mission.updated_at,
    },
    relationships: relationships
      ? {
          totals: relationships.totals,
          documents: relationships.documents,
          insights: relationships.insights,
          chunks: relationships.chunks,
          related_missions: relationships.related_missions,
        }
      : null,
    exported_at: new Date().toISOString(),
  };

  return JSON.stringify(exportData, null, 2);
}

/**
 * Generate export content for a mission in YAML format.
 */
export function exportMissionAsYaml(
  mission: ApiMission,
  relationships?: RelationshipContextResponse
): string {
  // Simple YAML generation without external dependencies
  const lines: string[] = [];

  lines.push("# Mission Export");
  lines.push(`# Exported: ${new Date().toISOString()}`);
  lines.push("");
  lines.push("mission:");
  lines.push(`  id: "${mission.id}"`);
  lines.push(`  mission_id: "${mission.mission_id ?? ""}"`);
  lines.push(`  title: "${mission.title ?? "Untitled"}"`);
  lines.push(`  status: "${mission.status ?? "draft"}"`);
  lines.push(`  created_at: "${mission.created_at}"`);
  lines.push(`  updated_at: "${mission.updated_at}"`);

  if (mission.objective) {
    lines.push("");
    lines.push("  objective: |");
    lines.push(`    ${mission.objective.replace(/\n/g, "\n    ")}`);
  }

  if (mission.success_criteria?.length) {
    lines.push("");
    lines.push("  success_criteria:");
    for (const criterion of mission.success_criteria) {
      lines.push(`    - "${criterion.replace(/"/g, '\\"')}"`);
    }
  }

  if (mission.deliverables?.length) {
    lines.push("");
    lines.push("  deliverables:");
    for (const deliverable of mission.deliverables) {
      lines.push(`    - "${deliverable.replace(/"/g, '\\"')}"`);
    }
  }

  if (relationships) {
    lines.push("");
    lines.push("relationships:");
    lines.push("  totals:");
    lines.push(`    documents: ${relationships.totals.documents}`);
    lines.push(`    insights: ${relationships.totals.insights}`);
    lines.push(`    chunks: ${relationships.totals.chunks}`);
    lines.push(`    missions: ${relationships.totals.missions}`);

    if (relationships.documents.length) {
      lines.push("");
      lines.push("  documents:");
      for (const doc of relationships.documents) {
        lines.push(`    - id: "${doc.id}"`);
        lines.push(`      name: "${doc.name}"`);
        lines.push(`      evidence_chunks: ${doc.evidence_chunks}`);
      }
    }
  }

  return lines.join("\n");
}

/**
 * Trigger file download in the browser.
 */
export function downloadFile(content: string, filename: string, mimeType: string): void {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
