import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import { useState } from "react";
import useSWR, { useSWRConfig } from "swr";

import { AuthGate } from "@/components/AuthGate";
import { PageState } from "@/components/ui/PageState";
import { PaginationBar } from "@/components/ui/PaginationBar";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useAuth } from "@/contexts/AuthContext";
import { homeApi } from "@/lib/api/home";
import { INBOX_PAGE_SIZE, INBOX_SECTIONS, SECTION_LABELS, inboxApi, type InboxItem, type InboxSection } from "@/lib/api/inbox";
import { parseApiTimestamp } from "@/lib/api/timestamps";
import { useInboxSummary } from "@/lib/hooks/useInboxSummary";

const DESCRIPTIONS: Record<InboxSection, string> = {
  failures: "Validation failures and blocked runs, newest first.",
  completions: "Finished missions, including results DeepSearch wrote directly. Reviewing a result is explicit.",
  evidence: "Recent evidence writes grouped by project, mission, session and origin.",
};
const EMPTY: Record<InboxSection, string> = { failures: "No agent failures.", completions: "No completed missions.", evidence: "No new evidence." };

function when(value: string) {
  return parseApiTimestamp(value).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function Item({ item, reviewing, onReview }: { item: InboxItem; reviewing: string | null; onReview: (item: InboxItem) => void }) {
  const isEvidence = item.section === "evidence";
  return <li className="flex flex-wrap items-start justify-between gap-3 p-5">
    <div className="flex min-w-0 flex-1 items-start gap-3">
      <span aria-hidden="true" className={`mt-2 h-2 w-2 shrink-0 rounded-full ${item.unread ? "bg-accent" : "bg-transparent"}`} />
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          {item.unread && <span className="rounded-full bg-surface-alt px-2 py-0.5 font-medium text-accent-text">Unread</span>}
          {item.status && <StatusBadge status={item.status} />}
          {item.section === "completions" && item.reviewed && <span className="text-muted">Reviewed</span>}
          <span className="break-all text-muted">{isEvidence ? (item.origin === "deepsearch-worker" ? "DeepSearch" : "Research agent") : item.label}</span>
        </div>
        <Link href={item.href} className={`block break-words font-semibold hover:text-accent-text ${item.unread ? "text-foreground" : "text-secondary"}`}>{isEvidence ? `${(item.entry_count ?? 0).toLocaleString()} evidence entries` : item.title}</Link>
        {isEvidence && <p className="break-all text-xs text-muted">{item.session_key}</p>}
        <p className="text-xs text-muted"><time dateTime={item.occurred_at}>{when(item.occurred_at)}</time></p>
      </div>
    </div>
    {item.section === "completions" && !item.reviewed && <button type="button" disabled={reviewing !== null} onClick={() => onReview(item)} className="rounded-lg border border-line px-3 py-2 text-sm text-secondary hover:bg-surface-alt disabled:opacity-50">{reviewing === item.id ? "Saving review…" : "Mark reviewed"}</button>}
  </li>;
}

function Section({ section, userId, reviewing, onReview, unread }: { section: InboxSection; userId?: string; reviewing: string | null; onReview: (item: InboxItem) => void; unread?: number }) {
  const [page, setPage] = useState(1);
  const { data, error, isLoading, mutate } = useSWR(userId ? ["inbox", userId, section, page] : null, () => inboxApi.list(section, { page }));
  const title = SECTION_LABELS[section];
  const headingId = `inbox-${section}`;
  return <section aria-labelledby={headingId} className="panel min-w-0 overflow-hidden">
    <div className="border-b border-line px-5 py-4">
      <h2 id={headingId} className="flex flex-wrap items-center gap-2 text-base font-semibold">{title}{data && <span className="rounded-full bg-surface-alt px-2 py-0.5 text-xs font-medium text-secondary">{data.total.toLocaleString()}</span>}{unread !== undefined && unread > 0 && <span className="text-xs font-medium text-accent-text">{unread.toLocaleString()} unread</span>}</h2>
      <p className="mt-1 text-xs text-muted">{DESCRIPTIONS[section]}</p>
    </div>
    {error ? <PageState state="error" title={`${title} could not load.`} onRetry={() => void mutate()} /> : isLoading || !data ? <PageState state="loading" title={`Loading ${title.toLowerCase()}…`} /> : data.items.length === 0 ? <PageState state="empty" title={EMPTY[section]} /> : <ol className="divide-y divide-line">{data.items.map(item => <Item key={item.id} item={item} reviewing={reviewing} onReview={onReview} />)}</ol>}
    {data && <div className="px-5"><PaginationBar page={page} pages={Math.ceil(data.total / INBOX_PAGE_SIZE)} total={data.total} label={`${title} pages`} onChange={setPage} /></div>}
  </section>;
}

function InboxContent() {
  const router = useRouter();
  const { user } = useAuth();
  const { mutate: mutateAll } = useSWRConfig();
  const summary = useInboxSummary();
  const [marking, setMarking] = useState(false);
  const [reviewing, setReviewing] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const requested = router.query.section;
  const focused = typeof requested === "string" ? INBOX_SECTIONS.find(section => section === requested) : undefined;
  const unknownSection = router.isReady && typeof requested === "string" && !focused;
  const sections = focused ? [focused] : INBOX_SECTIONS;

  async function refresh() {
    await Promise.all([summary.mutate(), mutateAll(key => Array.isArray(key) && key[0] === "inbox")]);
  }
  async function markAllSeen() {
    if (!summary.data) return;
    setMarking(true);
    setNotice(null);
    try {
      // The server's generated_at string goes back verbatim (decision #395, learning #173).
      await inboxApi.markSeen(summary.data.generated_at);
      await refresh();
    } catch {
      setNotice("The inbox could not be marked as seen. Refresh and try again.");
    } finally {
      setMarking(false);
    }
  }
  async function review(item: InboxItem) {
    if (!item.updated_at) return;
    setReviewing(item.id);
    setNotice(null);
    try {
      await homeApi.review({ id: item.id, updated_at: item.updated_at });
      await refresh();
    } catch {
      setNotice("Review could not be saved. The result may have changed; refresh and try again.");
    } finally {
      setReviewing(null);
    }
  }

  return <div className="mx-auto max-w-5xl space-y-7 px-4 py-8 sm:px-6 lg:py-10">
    <Head><title>Inbox · TraceLab</title></Head>
    <header className="flex flex-wrap items-end justify-between gap-5">
      <div><p className="mb-2 text-xs font-semibold uppercase tracking-widest text-muted">Priority inbox</p><h1 className="text-3xl font-semibold tracking-tight">Inbox</h1><p className="mt-2 max-w-xl text-secondary">Agent failures first, then finished missions, then new evidence. Opening this page marks nothing; use the button once you have caught up.</p></div>
      <button type="button" onClick={() => void markAllSeen()} disabled={marking || !summary.data || summary.data.unread.total === 0} className="rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-on-accent disabled:opacity-50">{marking ? "Marking…" : "Mark all as seen"}</button>
    </header>
    {notice && <p role="alert" className="rounded-lg bg-danger-surface p-4 text-danger">{notice}</p>}
    {summary.error ? <PageState state="error" title="Unread counts could not load." onRetry={() => void summary.mutate()} /> : !summary.data ? <PageState state="loading" title="Loading your inbox…" /> : <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted">
      <p><span className="font-medium text-foreground">{summary.data.unread.total.toLocaleString()} unread</span> · seen through <time dateTime={summary.data.seen_through}>{when(summary.data.seen_through)}</time></p>
      <p>Updated <time dateTime={summary.data.generated_at}>{when(summary.data.generated_at)}</time> · refreshes every {summary.data.refresh_seconds}s</p>
    </div>}
    <nav aria-label="Inbox sections" className="flex flex-wrap gap-2">{INBOX_SECTIONS.map(section => <Link key={section} href={section === focused ? "/inbox" : `/inbox?section=${section}`} aria-current={section === focused ? "page" : undefined} className={`rounded-lg px-4 py-2 text-sm ${section === focused ? "bg-accent text-on-accent" : "border border-line text-foreground hover:bg-surface-alt"}`}>{SECTION_LABELS[section]}{summary.data && summary.data.unread[section] > 0 && <span className="ml-2 rounded-full bg-surface-alt px-2 py-0.5 text-xs text-secondary">{summary.data.unread[section].toLocaleString()}</span>}</Link>)}</nav>
    {!router.isReady ? <PageState state="loading" title="Loading inbox sections…" /> : unknownSection ? <PageState state="empty" title="Inbox section not found"><Link href="/inbox" className="text-accent-text underline underline-offset-4">Open the full inbox</Link></PageState> : sections.map(section => <Section key={section} section={section} userId={user?.user_id} reviewing={reviewing} onReview={item => void review(item)} unread={summary.data?.unread[section]} />)}
  </div>;
}

export default function InboxPage() {
  return <AuthGate><InboxContent /></AuthGate>;
}
