import useSWR, { mutate } from "swr";
import { useAuth } from "@/contexts/AuthContext";

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
  sort?: MissionListParams["sort"];
}

export function useApiMissions(options: UseApiMissionsOptions = {}) {
  const { user } = useAuth();
  const { page = 1, pageSize = 20, status, projectId, sort } = options;

  const params: MissionListParams = {
    page,
    page_size: pageSize,
    status,
    project_id: projectId,
    sort,
  };

  const key = [API_MISSIONS_KEY, user?.user_id, page, pageSize, status ?? "all", projectId ?? "all", sort ?? "created_desc"];

  const { data, error, isLoading, mutate: mutateList } = useSWR<PaginatedResponse<ApiMission>>(
    key,
    () => missionsApi.list(params),
    {
      revalidateOnFocus: true,
      refreshInterval: 15000,
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
  const { user } = useAuth();
  const key = missionId ? [`${API_MISSIONS_KEY}-detail`, user?.user_id, missionId] : null;

  const { data, error, isLoading, mutate: mutateMission } = useSWR<ApiMission>(
    key,
    () => missionsApi.get(missionId as string),
    {
      revalidateOnFocus: true,
      refreshInterval: mission => mission && ["queued", "in_progress"].includes(mission.status) ? 5000 : 0,
    },
  );

  return {
    mission: data,
    isLoading,
    error,
    refresh: () => mutateMission(),
  };
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
