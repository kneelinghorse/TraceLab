import useSWR from "swr";
import { useAuth } from "@/contexts/AuthContext";
import { inboxApi, type InboxSummary } from "@/lib/api/inbox";

/** One shared poll for the shell badge and the inbox page: hidden tabs pause, focus revalidates. */
export const INBOX_SWR_OPTIONS = {
  refreshInterval: (summary?: InboxSummary) => (summary?.refresh_seconds ?? 30) * 1000,
  refreshWhenHidden: false,
  revalidateOnFocus: true,
};
export function inboxSummaryKey(userId: string | undefined) { return userId ? ["inbox-summary", userId] : null; }
export function useInboxSummary() {
  const { user } = useAuth();
  return useSWR(inboxSummaryKey(user?.user_id), () => inboxApi.summary(), INBOX_SWR_OPTIONS);
}
