import type {
  Mission,
  MissionCreatePayload,
  MissionUpdatePayload,
  QualityGateReport,
} from "@/types/mission";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const MISSIONS_PATH = "/api/v1/missions";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
    },
    ...options,
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request to ${path} failed with ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export async function fetchMissions(): Promise<Mission[]> {
  return request<Mission[]>(`${MISSIONS_PATH}`);
}

export async function fetchMission(missionId: string): Promise<Mission> {
  return request<Mission>(`${MISSIONS_PATH}/${missionId}`);
}

export async function createMission(payload: MissionCreatePayload): Promise<Mission> {
  return request<Mission>(`${MISSIONS_PATH}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateMission(missionId: string, payload: MissionUpdatePayload): Promise<Mission> {
  return request<Mission>(`${MISSIONS_PATH}/${missionId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function fetchQualityReport(missionId: string): Promise<QualityGateReport> {
  return request<QualityGateReport>(`/api/v1/quality/missions/${missionId}/quality`);
}
