import useSWR, { mutate } from "swr";

import { fetchMission, fetchMissions, fetchQualityReport, missionsApi } from "@/lib/api/missions";
import type { ApiMission, Mission, MissionListParams, MissionStatus, QualityGateReport } from "@/types/mission";
import type { PaginatedResponse } from "@/types/pagination";

// ============================================
// New API hooks (B16.1+ schema)
// ============================================

const API_MISSIONS_KEY = "api-missions";

interface UseApiMissionsOptions {
  page?: number;
  pageSize?: number;
  status?: MissionStatus;
  projectId?: string;
}

export function useApiMissions(options: UseApiMissionsOptions = {}) {
  const { page = 1, pageSize = 20, status, projectId } = options;

  const params: MissionListParams = {
    page,
    page_size: pageSize,
    status,
    project_id: projectId,
  };

  const key = [API_MISSIONS_KEY, page, pageSize, status ?? "all", projectId ?? "all"];

  const { data, error, isLoading, mutate: mutateList } = useSWR<PaginatedResponse<ApiMission>>(
    key,
    () => missionsApi.list(params),
    {
      revalidateOnFocus: false,
    },
  );

  return {
    missions: data?.data ?? [],
    pagination: data?.pagination,
    isLoading,
    error,
    refresh: () => mutateList(),
  };
}

export function useApiMission(missionId?: string) {
  const key = missionId ? [`${API_MISSIONS_KEY}-detail`, missionId] : null;

  const { data, error, isLoading, mutate: mutateMission } = useSWR<ApiMission>(
    key,
    () => missionsApi.get(missionId as string),
    {
      revalidateOnFocus: false,
    },
  );

  return {
    mission: data,
    isLoading,
    error,
    refresh: () => mutateMission(),
  };
}

/**
 * Calculate queue position for a mission.
 * Returns the position (1-indexed) if the mission is queued, or null otherwise.
 */
export function calculateQueuePosition(mission: ApiMission, allMissions: ApiMission[]): number | null {
  if (mission.status !== "queued") {
    return null;
  }

  // Filter to only queued missions and sort by queued_at
  const queuedMissions = allMissions
    .filter((m) => m.status === "queued")
    .sort((a, b) => {
      const aTime = a.queued_at ? new Date(a.queued_at).getTime() : 0;
      const bTime = b.queued_at ? new Date(b.queued_at).getTime() : 0;
      return aTime - bTime;
    });

  const index = queuedMissions.findIndex((m) => m.id === mission.id);
  return index >= 0 ? index + 1 : null;
}

// ============================================
// Legacy Mission Protocol hooks
// ============================================

const MISSIONS_KEY = "missions";

export function useMissionList() {
  const { data, error, isLoading } = useSWR<Mission[]>(MISSIONS_KEY, fetchMissions, {
    revalidateOnFocus: false,
  });

  return {
    missions: data ?? [],
    isLoading,
    error,
    refresh: () => mutate(MISSIONS_KEY),
  };
}

export function useMissionDetail(missionId?: string) {
  const key = missionId ? `${MISSIONS_KEY}-${missionId}` : null;
  const { data, error, isLoading, mutate: mutateDetail } = useSWR<Mission>(
    key,
    () => fetchMission(missionId as string),
    {
      revalidateOnFocus: false,
    },
  );

  return {
    mission: data,
    isLoading,
    error,
    refresh: () => mutateDetail(),
  };
}

export function useQualityReport(missionId?: string) {
  const key = missionId ? `${MISSIONS_KEY}-${missionId}-quality` : null;
  const { data, error, isLoading, mutate: mutateQuality } = useSWR<QualityGateReport>(
    key,
    () => fetchQualityReport(missionId as string),
    {
      refreshInterval: 15000,
    },
  );

  return {
    report: data,
    isLoading,
    error,
    refresh: () => mutateQuality(),
  };
}
