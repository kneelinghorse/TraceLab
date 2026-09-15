import useSWR, { mutate } from "swr";

import { useAuth } from "@/contexts/AuthContext";
import { activityApi } from "@/lib/api/activity";
import type { ActivitySummary, ViewedItem } from "@/lib/api/activity";

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
