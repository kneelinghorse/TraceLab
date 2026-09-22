import useSWR, { mutate } from "swr";

import { useAuth } from "@/contexts/AuthContext";
import { activityApi } from "@/lib/api/activity";
import type { ActivitySummary, EvidenceGroupScope, ViewedItem } from "@/lib/api/activity";

export const ACTIVITY_SUMMARY_KEY = "activity-summary";

export function useActivitySummary() {
  const { user } = useAuth();
  return useSWR<ActivitySummary>(user ? [ACTIVITY_SUMMARY_KEY, user.user_id] : null, activityApi.summary, {
    refreshInterval: 30000, revalidateOnFocus: true, shouldRetryOnError: false,
  });
}

/** Record that the user opened an item; badges and Home refresh from the server. Never blocks navigation. */
export async function markViewed(items: ViewedItem[]) {
  if (!items.length) return;
  try {
    await activityApi.markViewed(items);
  } catch {
    return;
  }
  void mutate((key) => Array.isArray(key) && (key[0] === ACTIVITY_SUMMARY_KEY || key[0] === "home"), undefined, { revalidate: true });
}

/**
 * Record that the user opened a group of evidence (a project's, or one run's): the
 * whole group stops being new at once (BADGE-1, decision #528). Never blocks the page.
 */
export async function markEvidenceSeen(scope: EvidenceGroupScope) {
  try {
    await activityApi.markEvidenceViewed(scope);
  } catch {
    return;
  }
  void mutate((key) => Array.isArray(key) && (key[0] === ACTIVITY_SUMMARY_KEY || key[0] === "home"), undefined, { revalidate: true });
}
