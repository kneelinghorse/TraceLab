import useSWR, { mutate } from "swr";

import { fetchMission, fetchMissions, fetchQualityReport } from "@/lib/api/missions";
import type { Mission, QualityGateReport } from "@/types/mission";

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
