import { apiRequest } from "@/lib/api/http";
import type {
  Mission,
  MissionCreatePayload,
  MissionUpdatePayload,
  QualityGateReport,
} from "@/types/mission";

const MISSIONS_PATH = "/missions";

interface ListResponse<T> {
  data: T[];
}

export async function fetchMissions(): Promise<Mission[]> {
  const response = await apiRequest<ListResponse<Mission>>(`${MISSIONS_PATH}`);
  return response.data;
}

export async function fetchMission(missionId: string): Promise<Mission> {
  return apiRequest<Mission>(`${MISSIONS_PATH}/${missionId}`);
}

export async function createMission(payload: MissionCreatePayload): Promise<Mission> {
  return apiRequest<Mission>(`${MISSIONS_PATH}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateMission(missionId: string, payload: MissionUpdatePayload): Promise<Mission> {
  return apiRequest<Mission>(`${MISSIONS_PATH}/${missionId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function fetchQualityReport(missionId: string): Promise<QualityGateReport> {
  return apiRequest<QualityGateReport>(`/quality/missions/${missionId}/quality`);
}
