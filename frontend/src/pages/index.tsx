import Head from "next/head";
import Link from "next/link";
import { useState } from "react";
import type { ReactNode } from "react";
import useSWR from "swr";

import { AuthGate } from "@/components/AuthGate";
import { FavoriteProjects } from "@/components/projects/FavoriteProjects";
import { NavigationIcon } from "@/components/Navigation";
import { useAuth } from "@/contexts/AuthContext";
import { homeApi } from "@/lib/api/home";
import type { HomeMission, HomeRecent, HomeSection } from "@/lib/api/home";
import { openCommandPalette } from "@/lib/command-palette";

const REASONS = {
  validation_failed: { label: "Validation failed", color: "text-danger bg-danger-surface" },
  blocked: { label: "Blocked", color: "text-danger bg-danger-surface" },
  stalled: { label: "Waiting in queue", color: "text-warning bg-warning-surface" },
  unreviewed: { label: "Ready for review", color: "text-success bg-success-surface" },
};

function updated(value: string) {
  // API timestamps are UTC, including older offset-free SQL timestamps.
  return new Date(/(?:Z|[+-]\d\d:\d\d)$/.test(value) ? value : `${value}Z`).toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}

function Section({ title, count, children, link }: { title: string; count: number; children: ReactNode; link?: { href: string; label: string } }) {
  return <section className="panel min-w-0 overflow-hidden" aria-label={title}>
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
      <h2 className="flex items-center gap-2 text-base font-semibold">{title}<span className="rounded-full bg-surface-alt px-2 py-0.5 text-xs font-medium text-secondary">{count.toLocaleString()}</span></h2>
      {link && <Link className="text-sm text-accent-text underline-offset-4 hover:underline" href={link.href}>{link.label}</Link>}
    </div>
    {children}
  </section>;
}

function ResultLinks({ mission }: { mission: HomeMission }) {
  return <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
    {mission.report_id ? <Link href={`/reports/${mission.report_id}`} className="text-accent-text underline underline-offset-4">Open report</Link> : <span className="text-muted">No accessible report</span>}
    {mission.evidence_href ? <Link href={mission.evidence_href} className="text-accent-text underline underline-offset-4">Evidence ({mission.evidence_count.toLocaleString()})</Link> : <span className="text-muted">No accessible evidence</span>}
  </div>;
}

function Recents({ title, data, href }: { title: string; data: HomeSection<HomeRecent>; href: string }) {
  return <Section title={title} count={data.total} link={{ href, label: "View all" }}>
    <ul className="divide-y divide-line">{data.items.map((item) => <li key={item.id} className="px-5 py-4">
      <Link href={item.href} className="block break-words font-medium text-foreground hover:text-accent-text">{item.title}</Link>
      {item.updated_at && <p className="mt-1 text-xs text-muted">Updated <time dateTime={item.updated_at}>{updated(item.updated_at)}</time></p>}
    </li>)}</ul>
    {data.total === 0 && <p className="p-5 text-sm text-secondary">Nothing here yet.</p>}
  </Section>;
}

function HomeContent() {
  const { user } = useAuth();
  const { data, error, isLoading, isValidating, mutate } = useSWR(["home", user?.user_id], homeApi.get, {
    refreshInterval: (snapshot) => (snapshot?.refresh_seconds ?? 30) * 1000,
  });
  const [reviewing, setReviewing] = useState<string | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);

  async function review(mission: HomeMission) {
    setReviewing(mission.id);
    setReviewError(null);
    try {
      await homeApi.review(mission);
      await mutate();
    } catch {
      setReviewError("Review could not be saved. Refresh Home to check for a changed result, then try again.");
    } finally {
      setReviewing(null);
    }
  }

  return <div className="mx-auto max-w-7xl space-y-7 px-4 py-8 sm:px-6 lg:py-10">
    <Head><title>Home · TraceLab</title></Head>
    <header className="flex flex-wrap items-end justify-between gap-5">
      <div><p className="mb-2 text-xs font-semibold uppercase tracking-widest text-muted">Research workspace</p><h1 className="text-3xl font-semibold tracking-tight">Home</h1><p className="mt-2 max-w-xl text-secondary">What needs your attention, and what changed while you were away.</p></div>
      <Link href="/missions/new" className="inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-on-accent"><NavigationIcon name="mission" />New mission</Link>
    </header>
    <button type="button" onClick={openCommandPalette} className="panel flex w-full items-center gap-3 px-5 py-4 text-left text-secondary hover:border-line-strong">
      <NavigationIcon name="search" /><span className="min-w-0 flex-1">Search research or jump to a section</span><kbd className="hidden rounded border border-line px-2 py-1 text-xs sm:inline">⌘ K</kbd>
    </button>
    {isLoading && <div role="status" className="panel p-8 text-secondary">Loading your workspace…</div>}
    {error && <div role="alert" className="rounded-lg border border-line bg-danger-surface p-5 text-danger"><p>{data ? "Home could not refresh. The last successful snapshot is shown below." : "Home could not load. Try again to retrieve your workspace."}</p><button type="button" onClick={() => void mutate()} className="mt-3 rounded border border-current px-3 py-2 text-sm">Try again</button></div>}
    {reviewError && <p role="alert" className="rounded-lg bg-danger-surface p-4 text-danger">{reviewError}</p>}
    {data && <>
      {data.favorites && <FavoriteProjects key={user?.user_id} initial={data.favorites} />}
      <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted">
        <p><Link href="/missions" className="font-medium text-accent-text underline underline-offset-4">{data.missions.total.toLocaleString()} missions</Link> in your workspace · {data.missions.by_status.completed.toLocaleString()} completed</p>
        <div className="flex flex-wrap items-center gap-3"><p>Updated <time dateTime={data.generated_at}>{updated(data.generated_at)}</time> · refreshes every {data.refresh_seconds}s</p><button type="button" onClick={() => void mutate()} disabled={isValidating} className="rounded border border-line px-3 py-1.5 text-secondary disabled:opacity-50">{isValidating ? "Refreshing…" : "Refresh"}</button></div>
      </div>
      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <Section title="Needs attention" count={data.attention.total} link={{ href: "/missions", label: "All missions" }}>
          <p className="border-b border-line px-5 py-3 text-xs text-muted">Validation failures first, then blocked runs, queues over {data.stalled_after_seconds / 3600} hour, and completions to review.</p>
          <ol className="divide-y divide-line">{data.attention.items.map((mission) => {
            const reason = REASONS[mission.reason!];
            return <li key={mission.id} className="space-y-3 p-5">
              <div className="flex flex-wrap items-center gap-2"><span className={`rounded-full px-2.5 py-1 text-xs font-medium ${reason.color}`}>{reason.label}</span><span className="break-all text-xs text-muted">{mission.mission_id}</span></div>
              <Link href={`/missions/${mission.id}`} className="block break-words font-semibold hover:text-accent-text">{mission.title}</Link>
              {(mission.status === "completed" || mission.status === "validation_failed") && <ResultLinks mission={mission} />}
              {mission.reason === "unreviewed" && <button type="button" disabled={reviewing !== null} onClick={() => void review(mission)} className="rounded-lg border border-line px-3 py-2 text-sm text-secondary hover:bg-surface-alt disabled:opacity-50">{reviewing === mission.id ? "Saving review…" : "Mark reviewed"}</button>}
            </li>;
          })}</ol>
          {data.attention.total === 0 && <div className="p-6"><p className="font-medium">You’re up to date.</p><p className="mt-1 text-sm text-secondary">No missions need your attention right now.</p></div>}
          {data.attention.total > data.attention.items.length && <p className="border-t border-line px-5 py-3 text-xs text-muted">Showing the first {data.attention.items.length} of {data.attention.total.toLocaleString()} items. Reviewed completions leave this queue.</p>}
        </Section>
        <Section title="Active missions" count={data.active_runs.total} link={{ href: "/missions?view=queue", label: "Open queue" }}>
          <ul className="divide-y divide-line">{data.active_runs.items.map((mission) => <li key={mission.id} className="space-y-3 p-5">
            <Link href={`/missions/${mission.id}`} className="block break-words font-semibold hover:text-accent-text">{mission.title}</Link>
            <p className="text-sm text-secondary">{mission.progress.phase ? mission.progress.phase.replaceAll("_", " ") : "Phase not reported"}</p>
            {mission.progress.percent !== null ? <div className="flex items-center gap-3"><div role="progressbar" aria-label={`${mission.title} progress`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={mission.progress.percent} className="h-2 min-w-0 flex-1 overflow-hidden rounded-full bg-surface-alt"><div className="h-full rounded-full bg-accent" style={{ width: `${mission.progress.percent}%` }} /></div><span className="text-xs text-secondary">{mission.progress.percent}%</span></div> : <p className="text-xs text-muted">Progress not reported yet.</p>}
            {mission.progress.current_step !== null && <p className="text-xs text-secondary">Step {mission.progress.current_step} of {mission.progress.total_steps}</p>}
            <p className="text-xs text-muted">{mission.started_at ? <>Started <time dateTime={mission.started_at}>{updated(mission.started_at)}</time></> : "Start time not reported"}</p>
            <Link href={`/missions/${mission.id}`} className="inline-block text-sm text-accent-text underline underline-offset-4">Inspect run</Link>
          </li>)}</ul>
          {data.active_runs.total === 0 && <p className="p-5 text-sm text-secondary">No missions are running. You can start a new mission and return here to follow it.</p>}
          {data.active_runs.total > data.active_runs.items.length && <p className="border-t border-line p-4 text-xs text-muted">Showing {data.active_runs.items.length} of {data.active_runs.total} active missions.</p>}
        </Section>
      </div>
      <div className="grid items-start gap-6 lg:grid-cols-2">
        <Recents title="Recent reports" data={data.recent_reports} href="/reports" />
        <Recents title="Recent projects" data={data.recent_projects} href="/projects" />
      </div>
      <Section title="Agent & evidence activity" count={data.evidence_activity.total} link={{ href: "/evidence", label: "Browse evidence" }}>
        <p className="border-b border-line px-5 py-3 text-xs text-muted">Recent evidence writes grouped by project, mission, session and origin.</p>
        <ul className="divide-y divide-line">{data.evidence_activity.items.map((activity) => <li key={`${activity.project_id}:${activity.mission_id}:${activity.session_key}:${activity.origin}`} className="flex flex-wrap items-center justify-between gap-3 p-5">
          <div className="min-w-0 flex-1"><Link href={activity.href} className="break-words font-medium text-foreground hover:text-accent-text">{activity.entry_count.toLocaleString()} evidence entries · {activity.origin === "deepsearch-worker" ? "DeepSearch" : "Research agent"}</Link><p className="mt-1 break-all text-xs text-muted">{activity.session_key}</p></div>
          <time className="text-xs text-muted" dateTime={activity.last_created_at}>{updated(activity.last_created_at)}</time>
        </li>)}</ul>
        {data.evidence_activity.total === 0 && <p className="p-5 text-sm text-secondary">Evidence activity will appear as agents capture sourced findings.</p>}
      </Section>
    </>}
  </div>;
}

export default function HomePage() {
  return <AuthGate><HomeContent /></AuthGate>;
}
