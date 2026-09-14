import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { Dialog } from "@/components/ui/Dialog";
import { PageState } from "@/components/ui/PageState";
import { useAuth } from "@/contexts/AuthContext";
import { homeApi } from "@/lib/api/home";
import { HttpError } from "@/lib/api/http";
import { BUILTIN_DASHBOARDS, missionViewHref, missionViewsApi, type MissionViewFilters, type SavedMissionView } from "@/lib/api/missionViews";
import { parseApiTimestamp } from "@/lib/api/timestamps";

type Editing = { action: "save" } | { action: "rename" | "delete"; view: SavedMissionView };

export function MissionDashboards({ filters }: { filters: MissionViewFilters }) {
  const { user } = useAuth();
  const attention = useSWR(["mission-attention", user?.user_id], () => homeApi.attention(), { refreshInterval: 15000 });
  const saved = useSWR(["mission-views", user?.user_id], () => missionViewsApi.list(), { refreshInterval: 15000 });
  const [editing, setEditing] = useState<Editing | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  function open(value: Editing) { setEditing(value); setName(value.action === "save" ? "" : value.view.name); setError(""); }
  function close() { if (!busy) setEditing(null); }
  async function submit() {
    if (!editing) return;
    setBusy(true); setError("");
    try {
      if (editing.action === "save") await missionViewsApi.create(name.trim(), filters);
      else if (editing.action === "rename") await missionViewsApi.rename(editing.view.id, name.trim());
      else await missionViewsApi.delete(editing.view.id);
      await saved.mutate();
      setEditing(null);
    } catch (cause) {
      setError(cause instanceof HttpError && cause.status === 404 ? "Saved view not found. It may have been removed in another session." : cause instanceof Error ? cause.message : "Could not save this change. Try again.");
    } finally { setBusy(false); }
  }
  const title = editing?.action === "delete" ? "Delete saved view" : editing?.action === "rename" ? "Rename saved view" : "Save view";
  return <section className="panel p-5" aria-label="Mission dashboards">
    <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-lg font-semibold">Dashboards</h2><button type="button" className="rounded-lg border border-line px-4 py-2 text-sm" onClick={() => open({ action: "save" })}>Save view</button></div>
    {attention.error ? <PageState state="error" title="Dashboard totals unavailable." onRetry={() => void attention.mutate()} /> : !attention.data ? <PageState state="loading" title="Loading dashboards…" /> : <>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">{BUILTIN_DASHBOARDS.map(dashboard => <Link key={dashboard.key} href={missionViewHref(dashboard.filters)} className="min-w-0 rounded-lg border border-line p-4 hover:bg-surface-alt"><span className="block break-words text-sm text-secondary">{dashboard.label}</span><span className="mt-1 block text-2xl font-semibold">{attention.data?.dashboards.find(item => item.key === dashboard.key)?.total ?? 0}</span></Link>)}</div>
      <p className="mt-3 text-xs text-muted">Live workspace counts · updated <time dateTime={attention.data.generated_at}>{parseApiTimestamp(attention.data.generated_at).toLocaleString()}</time></p>
    </>}
    <h3 className="mt-5 text-sm font-medium">Your saved views</h3>
    {saved.error ? <PageState state="error" title="Saved views could not load." onRetry={() => void saved.mutate()} /> : !saved.data ? <PageState state="loading" title="Loading saved views…" /> : !saved.data.items.length ? <PageState state="empty" title="No saved views yet.">Save the current filters to return to this work.</PageState> : <ul className="mt-2 divide-y divide-line">{saved.data.items.map(view => <li key={view.id} className="flex flex-wrap items-center gap-2 py-3">
      <Link href={missionViewHref(view.filters)} className="min-w-0 flex-1 break-words text-sm font-medium text-accent-text underline underline-offset-4">{view.name} <span className="whitespace-nowrap text-secondary">({view.total})</span></Link>
      <button type="button" aria-label={`Rename ${view.name}`} className="rounded-lg border border-line px-3 py-2 text-xs" onClick={() => open({ action: "rename", view })}>Rename</button>
      <button type="button" aria-label={`Delete ${view.name}`} className="rounded-lg border border-line px-3 py-2 text-xs" onClick={() => open({ action: "delete", view })}>Delete</button>
    </li>)}</ul>}
    <Dialog open={editing !== null} title={title} onClose={close}>
      <form onSubmit={event => { event.preventDefault(); void submit(); }}>
        {editing?.action === "delete" ? <p className="break-words text-sm text-secondary">Delete “{editing.view.name}” from your saved views? The missions will remain available.</p> : <><label htmlFor="mission-view-name" className="form-label">View name</label><input autoFocus id="mission-view-name" className="form-input w-full" value={name} onChange={event => setName(event.target.value)} required maxLength={120} /><p className="mt-3 text-sm text-secondary">{editing?.action === "save" ? "Saves the current view, reason, status and project filters for your account." : "Choose a name for these saved filters."}</p></>}
        {error && <PageState state="error" title={error} />}
        <div className="mt-5 flex justify-end gap-3"><button type="button" disabled={busy} onClick={close} className="rounded-lg border border-line px-4 py-2 text-sm disabled:opacity-50">Cancel</button><button type="submit" disabled={busy || (editing?.action !== "delete" && !name.trim())} className="rounded-lg bg-accent px-4 py-2 text-sm text-on-accent disabled:opacity-50">{busy ? "Saving…" : editing?.action === "delete" ? "Delete view" : "Save"}</button></div>
      </form>
    </Dialog>
  </section>;
}
