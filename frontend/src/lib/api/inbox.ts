import { httpClient } from "@/lib/api/http";

export const INBOX_SECTIONS = ["failures", "completions", "evidence"] as const;
export type InboxSection = typeof INBOX_SECTIONS[number];
export const SECTION_LABELS: Record<InboxSection, string> = { failures: "Agent failures", completions: "Mission completions", evidence: "New evidence" };
export const INBOX_PAGE_SIZE = 20;
export interface InboxCounts { failures: number; completions: number; evidence: number; total: number }
export interface InboxSummary { generated_at: string; refresh_seconds: number; seen_through: string; default_lookback_seconds: number; unread: InboxCounts }
export interface InboxItem {
  section: InboxSection; id: string; title: string; label: string; status: string | null; occurred_at: string; updated_at: string | null;
  unread: boolean; href: string; reviewed: boolean | null; entry_count: number | null; project_id: string | null; mission_id: string | null;
  session_key: string | null; origin: string | null;
}
export interface InboxPage { section: InboxSection; generated_at: string; seen_through: string; total: number; items: InboxItem[] }
export const inboxApi = {
  summary: () => httpClient.get<InboxSummary>("/inbox/summary"),
  list: (section: InboxSection, params: { page?: number; page_size?: number; unread_only?: boolean } = {}) => httpClient.get<InboxPage>("/inbox", { params: { section, page_size: INBOX_PAGE_SIZE, ...params } }),
  /** Send the server's generated_at string back verbatim; re-serializing a local Date shifts the watermark by the UTC offset. */
  markSeen: (seenThrough: string) => httpClient.put<{ seen_through: string }>("/inbox/seen", { seen_through: seenThrough }),
};
export function unreadBadge(total: number) { return total > 99 ? "99+" : String(total); }
export function inboxBadgeName(total: number) { return `Inbox, ${total} unread`; }
