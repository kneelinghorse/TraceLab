import { httpClient } from "@/lib/api/http";
import type {
  ApiMission,
  ApiMissionCreate,
  ApiMissionUpdate,
  Mission,
  MissionCreatePayload,
  MissionListParams,
  MissionSubmitResponse,
  MissionUpdatePayload,
  QualityGateReport,
  ReportPromotionResponse,
} from "@/types/mission";
import type { PaginatedResponse } from "@/types/pagination";

const MISSIONS_PATH = "/missions";

// ============================================
// New API missions (B16.1+ schema)
// ============================================

export const missionsApi = {
  /**
   * List missions with optional filtering and pagination.
   */
  list(params: MissionListParams = {}): Promise<PaginatedResponse<ApiMission>> {
    return httpClient.get<PaginatedResponse<ApiMission>>(MISSIONS_PATH, {
      params: {
        page: params.page,
        page_size: params.page_size,
        status: params.status,
        project_id: params.project_id,
      },
    });
  },

  /**
   * Get a single mission by ID.
   */
  get(missionId: string): Promise<ApiMission> {
    return httpClient.get<ApiMission>(`${MISSIONS_PATH}/${missionId}`);
  },

  /**
   * Create a new mission.
   */
  create(data: ApiMissionCreate): Promise<ApiMission> {
    return httpClient.post<ApiMission>(MISSIONS_PATH, data);
  },

  /**
   * Update an existing mission (PATCH — partial update).
   */
  update(missionId: string, data: ApiMissionUpdate): Promise<ApiMission> {
    return httpClient.patch<ApiMission>(`${MISSIONS_PATH}/${missionId}`, data);
  },

  /**
   * Delete a mission.
   */
  delete(missionId: string): Promise<void> {
    return httpClient.delete<void>(`${MISSIONS_PATH}/${missionId}`);
  },

  /**
   * Submit a draft mission to DeepSearch (sets status to queued).
   */
  submitToDeepSearch(missionId: string): Promise<MissionSubmitResponse> {
    return httpClient.post<MissionSubmitResponse>(
      `${MISSIONS_PATH}/${missionId}/submit`
    );
  },

  /**
   * Promote a mission's report to a searchable document.
   * This creates a new document from the report's content and runs it
   * through the chunking/embedding pipeline for future searches.
   */
  promoteReport(missionId: string): Promise<ReportPromotionResponse> {
    return httpClient.post<ReportPromotionResponse>(
      `${MISSIONS_PATH}/${missionId}/promote-report`
    );
  },
};

// ============================================
// Legacy Mission Protocol API (for MissionProtocolForm)
// ============================================

interface ListResponse<T> {
  data: T[];
}

export async function fetchMissions(): Promise<Mission[]> {
  // Legacy endpoint returns different format
  const response = await httpClient.get<ListResponse<Mission>>("/mission-protocols");
  return response.data;
}

export async function fetchMission(missionId: string): Promise<Mission> {
  return httpClient.get<Mission>(`/mission-protocols/${missionId}`);
}

export async function createMission(payload: MissionCreatePayload): Promise<Mission> {
  return httpClient.post<Mission>("/mission-protocols", payload);
}

export async function updateMission(missionId: string, payload: MissionUpdatePayload): Promise<Mission> {
  return httpClient.put<Mission>(`/mission-protocols/${missionId}`, payload);
}

export async function fetchQualityReport(missionId: string): Promise<QualityGateReport> {
  return httpClient.get<QualityGateReport>(`/quality/missions/${missionId}/quality`);
}
