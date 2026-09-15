import { useRouter } from "next/router";
import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import useSWR from "swr";

import { NavigationIcon, navigationGroups } from "@/components/Navigation";
import { PageState } from "@/components/ui/PageState";
import { PaginationBar } from "@/components/ui/PaginationBar";
import { useAuth } from "@/contexts/AuthContext";
import { useRole } from "@/contexts/RoleContext";
import { navigationApi, type NavigationEntityType, type NavigationGroup } from "@/lib/api/navigation";
import { missionViewsApi, missionViewHref } from "@/lib/api/missionViews";
import { savedSearchesApi } from "@/lib/api/savedSearches";
import { searchApi } from "@/lib/api/search";
import { OPEN_COMMAND_PALETTE_EVENT } from "@/lib/command-palette";
import { keepDialogFocus } from "@/lib/dialog-focus";

const labels: Record<NavigationEntityType, string> = { project: "Projects", document: "Documents", mission: "Missions", report: "Reports", collection: "Collections", evidence: "Evidence" };
const commandClass = "block w-full min-w-0 rounded-lg px-3 py-2 text-left text-sm text-foreground hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus";

function EntityGroup({ initial, query, userId, go }: { initial: NavigationGroup; query: string; userId: string; go: (href: string) => void }) {
  const [page, setPage] = useState(1);
  const { data, error, isLoading, mutate } = useSWR(page > 1 ? ["palette-page", userId, query, initial.entity_type, page] : null,
    () => navigationApi.search(query, initial.entity_type, page));
  const group = page === 1 ? initial : data?.groups[0];
  const total = group?.total ?? initial.total;
  const title = `${labels[initial.entity_type]} (${total.toLocaleString()})`;
  return <section aria-label={title} className="border-b border-line px-2 py-3 last:border-0">
    <h3 className="px-3 pb-2 text-xs font-medium text-muted">{title}</h3>
    {error ? <PageState state="error" title="Could not load this page" onRetry={() => void mutate()} /> : isLoading ? <PageState state="loading" title="Loading objects…" /> : group?.items.map(item =>
      <button key={item.id} type="button" data-command-item className={commandClass} onClick={() => go(item.href)}><span className="line-clamp-2 break-words">{item.title}</span></button>)}
    <PaginationBar page={page} pages={Math.ceil(total / initial.page_size)} total={total} label={`${labels[initial.entity_type]} pages`} onChange={setPage} />
  </section>;
}

/** Extends the shell's existing native dialog and global opening event. */
export function CommandPalette() {
  const { user } = useAuth();
  const userId = user?.user_id ?? "";
  const { isAdmin } = useRole();
  const router = useRouter();
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const results = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const term = query.trim();

  const requestOpen = useCallback(() => {
    setQuery("");
    setOpen(true);
    if (!dialog.current?.open) dialog.current?.showModal();
    input.current?.focus();
  }, []);
  useEffect(() => {
    const keyboard = (event: globalThis.KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); requestOpen(); }
    };
    window.addEventListener("keydown", keyboard);
    window.addEventListener(OPEN_COMMAND_PALETTE_EVENT, requestOpen);
    return () => { window.removeEventListener("keydown", keyboard); window.removeEventListener(OPEN_COMMAND_PALETTE_EVENT, requestOpen); };
  }, [requestOpen]);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(term), 200);
    return () => window.clearTimeout(timer);
  }, [term]);

  const { data, error, isLoading, mutate } = useSWR(open && userId && term && term === debounced ? ["palette-names", userId, term] : null, () => navigationApi.search(term));
  const history = useSWR(open && userId ? ["palette-history", userId] : null, () => searchApi.history(5));
  const saved = useSWR(open && userId ? ["palette-saved", userId] : null, () => savedSearchesApi.list());
  const views = useSWR(open && userId ? ["mission-views", userId] : null, () => missionViewsApi.list());
  const viewItems = views.data?.items?.filter(entry => entry.name.toLowerCase().includes(term.toLowerCase())) ?? [];
  const groups = data?.groups?.filter(group => group.total > 0) ?? [];
  const items = navigationGroups.filter(group => !group.admin || isAdmin).flatMap(group => group.items).filter(item => item.label.toLowerCase().includes(term.toLowerCase()));
  const recent = history.data?.entries?.filter(entry => entry.query_text.toLowerCase().includes(term.toLowerCase())) ?? [];
  const savedItems = saved.data?.items?.filter(entry => entry.name.toLowerCase().includes(term.toLowerCase())) ?? [];

  function close() { setOpen(false); dialog.current?.close(); }
  function go(href: string) { close(); void router.push(href); }
  function keyboard(event: KeyboardEvent<HTMLDialogElement>) {
    keepDialogFocus(event);
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    const buttons = Array.from(results.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)") ?? []);
    const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
    if (["Home", "End"].includes(event.key) && index < 0) return; // Preserve text editing in the query.
    if (!buttons.length) return;
    event.preventDefault();
    const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : event.key === "ArrowDown" ? (index + 1) % buttons.length : index <= 0 ? buttons.length - 1 : index - 1;
    buttons[next].focus();
  }

  return <dialog ref={dialog} className="app-dialog app-command-dialog" aria-labelledby="command-title" onKeyDown={keyboard} onClose={() => {
    // Native close events are queued; a quick Cmd-K can reopen before delivery.
    if (!dialog.current?.open) setOpen(false);
  }}>
    <div className="flex items-center justify-between border-b border-line px-5 py-3"><h2 id="command-title" className="text-sm font-medium">Search and navigation</h2><button type="button" aria-label="Close search" className="rounded-lg p-2" onClick={close}><NavigationIcon name="close" /></button></div>
    <form onSubmit={event => { event.preventDefault(); if (term) go(`/search?q=${encodeURIComponent(term)}`); }} className="flex items-center gap-3 border-b border-line p-4"><NavigationIcon name="search" /><label htmlFor="command-query" className="sr-only">Search research or find a section</label><input ref={input} id="command-query" value={query} maxLength={200} onChange={event => setQuery(event.target.value)} placeholder="Find an object or search research…" className="min-w-0 flex-1 bg-transparent py-2 text-foreground placeholder:text-muted" autoComplete="off" /><button type="submit" className="rounded-lg bg-accent px-3 py-2 text-sm text-on-accent" disabled={!term}>Search</button></form>
    <div ref={results} className="max-h-[55vh] overflow-y-auto p-3">
      {term && (term !== debounced || isLoading ? <PageState state="loading" title="Finding objects…" /> : error ? <PageState state="error" title="Could not find objects" onRetry={() => void mutate()} /> : groups.length ? groups.map(group => <EntityGroup key={`${term}-${group.entity_type}`} initial={group} query={term} userId={userId} go={go} />) : <PageState state="empty" title="No matching objects">Press Enter to search your research.</PageState>)}
      {history.error ? <PageState state="error" title="Could not load recent searches" onRetry={() => void history.mutate()} /> : recent.length > 0 && <section aria-label="Recent searches" className="py-2"><h3 className="px-3 py-2 text-xs text-muted">Recent searches</h3>{recent.map(entry => <button key={entry.id} type="button" data-command-item className={commandClass} onClick={() => go(`/search?history=${encodeURIComponent(entry.id)}`)}><span className="line-clamp-2 break-words">{entry.query_text}</span></button>)}</section>}
      {saved.error ? <PageState state="error" title="Could not load saved searches" onRetry={() => void saved.mutate()} /> : savedItems.length > 0 && <section aria-label="Saved searches" className="py-2"><h3 className="px-3 py-2 text-xs text-muted">Saved searches</h3>{savedItems.map(entry => <button key={entry.id} type="button" data-command-item className={commandClass} onClick={() => go(`/search?saved=${encodeURIComponent(entry.id)}`)}><span className="line-clamp-2 break-words">{entry.name}</span></button>)}</section>}
      {views.error ? <PageState state="error" title="Could not load saved mission views" onRetry={() => void views.mutate()} /> : views.isLoading ? <PageState state="loading" title="Loading saved mission views…" /> : viewItems.length > 0 && <section aria-label="Saved mission views" className="py-2"><h3 className="px-3 py-2 text-xs text-muted">Saved mission views</h3>{viewItems.map(entry => <button key={entry.id} type="button" data-command-item className={commandClass} onClick={() => go(missionViewHref(entry.filters))}><span className="line-clamp-2 break-words">{entry.name} ({entry.total})</span></button>)}</section>}
      {!term && <section aria-label="Actions" className="py-2"><h3 className="px-3 py-2 text-xs text-muted">Actions</h3><button type="button" data-command-item className={commandClass} onClick={() => go("/missions/new")}>New mission</button><button type="button" data-command-item className={commandClass} onClick={() => go("/projects/new")}>New project</button><button type="button" data-command-item className={commandClass} onClick={() => go("/collections/new")}>New collection</button><button type="button" data-command-item className={commandClass} onClick={() => go("/documents/upload")}>Upload documents</button></section>}
      {items.length > 0 && <section aria-label="Go to" className="py-2"><h3 className="px-3 py-2 text-xs text-muted">Go to</h3>{items.map(item => <button key={item.href} type="button" data-command-item className="app-nav-link w-full text-left" onClick={() => go(item.href)}><NavigationIcon name={item.icon} />{item.label}</button>)}</section>}
    </div>
    <details className="border-t border-line px-5 py-3 text-xs text-secondary"><summary tabIndex={0} className="cursor-pointer font-medium">Keyboard help</summary><p className="mt-2">Cmd-K or Ctrl-K opens search. Type a name, then use Up/Down to focus objects and actions. Home/End moves to the first/last result when a result is focused. Enter opens the focused item; Enter in the query searches research. Tab reaches every control. Escape closes this dialog and restores focus to its opener.</p></details>
  </dialog>;
}
