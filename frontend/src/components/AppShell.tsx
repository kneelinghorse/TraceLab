import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { FormEvent, KeyboardEvent as ReactKeyboardEvent, ReactNode } from "react";

import { AuthGate } from "@/components/AuthGate";
import { Navigation, NavigationIcon, activeNavigationItem, navigationGroups } from "@/components/Navigation";
import { ThemeSelect } from "@/components/ThemeSelect";
import { useAuth } from "@/contexts/AuthContext";
import { useRole } from "@/contexts/RoleContext";
import { OPEN_COMMAND_PALETTE_EVENT } from "@/lib/command-palette";

function Brand() {
  return <Link href="/" className="flex items-center gap-3 font-semibold tracking-tight text-foreground"><span aria-hidden="true" className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-on-accent">T</span><span>TraceLab</span></Link>;
}

const subscribeHydration = () => () => {};
const clientSnapshot = () => true;
const serverSnapshot = () => false;

function keepDialogFocus(event: ReactKeyboardEvent<HTMLDialogElement>) {
  if (event.key !== "Tab") return;
  const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>("a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), [tabindex='0']"))
    .filter((element) => element.getClientRects().length > 0);
  const first = controls[0];
  const last = controls[controls.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last?.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first?.focus();
  }
}

export function AppShell({ children }: { children: ReactNode }) {
  const hydrated = useSyncExternalStore(subscribeHydration, clientSnapshot, serverSnapshot);
  const { isAuthenticated, user, logout } = useAuth();
  const { isAdmin } = useRole();
  const router = useRouter();
  const drawer = useRef<HTMLDialogElement>(null);
  const commands = useRef<HTMLDialogElement>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [query, setQuery] = useState("");
  const items = navigationGroups.filter((group) => !group.admin || isAdmin).flatMap((group) => group.items);
  const active = activeNavigationItem(router.pathname, items);
  const matching = items.filter((item) => item.label.toLowerCase().includes(query.trim().toLowerCase()));

  function openCommands() {
    setQuery("");
    if (!commands.current?.open) commands.current?.showModal();
    searchInput.current?.focus();
  }

  useEffect(() => {
    function requested() {
      if (!isAuthenticated) return;
      setQuery("");
      if (!commands.current?.open) commands.current?.showModal();
      searchInput.current?.focus();
    }
    function keyboard(event: KeyboardEvent) {
      if (isAuthenticated && (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        requested();
      }
    }
    window.addEventListener("keydown", keyboard);
    window.addEventListener(OPEN_COMMAND_PALETTE_EVENT, requested);
    return () => {
      window.removeEventListener("keydown", keyboard);
      window.removeEventListener(OPEN_COMMAND_PALETTE_EVENT, requested);
    };
  }, [isAuthenticated]);

  useEffect(() => {
    const media = window.matchMedia("(min-width: 900px)");
    const closeDrawer = () => { if (media.matches) drawer.current?.close(); };
    media.addEventListener("change", closeDrawer);
    return () => media.removeEventListener("change", closeDrawer);
  }, []);

  function go(href: string) {
    commands.current?.close();
    drawer.current?.close();
    void router.push(href);
  }

  function search(event: FormEvent) {
    event.preventDefault();
    if (query.trim()) go(`/search?q=${encodeURIComponent(query.trim())}`);
  }

  function userMenu() {
    return <div className="space-y-4 border-t border-line p-4">
      <ThemeSelect />
      <div className="flex items-center justify-between gap-2">
        <Link href="/settings" className="min-w-0 text-sm font-medium text-foreground" onClick={() => drawer.current?.close()}><span className="block truncate">{user?.display_name || user?.email || "Account"}</span><span className="text-xs font-normal text-muted">Settings</span></Link>
        <button type="button" onClick={logout} className="shrink-0 rounded-lg px-2 py-2 text-xs text-muted hover:bg-surface-alt">Sign out</button>
      </div>
    </div>;
  }

  // The session lives in browser storage. Keep the initial server and client
  // trees identical while the theme bootstrap already paints the right colors.
  if (!hydrated) return <main id="main-content" className="app-auth-main min-h-screen"><p role="status">Loading workspace…</p></main>;

  if (!isAuthenticated) {
    const isErrorPage = router.pathname === "/404" || router.pathname === "/_error";
    return <div className="app-auth-layout">
      <a href="#main-content" className="skip-link">Skip to content</a>
      <header className="flex flex-wrap items-center justify-between gap-4 px-6 py-5"><Brand /><ThemeSelect /></header>
      <main id="main-content" tabIndex={-1} className="app-auth-main">{isErrorPage ? children : <AuthGate>{children}</AuthGate>}</main>
    </div>;
  }

  return <>
    <a href="#main-content" className="skip-link">Skip to content</a>
    <aside className="app-sidebar" aria-label="Workspace">
      <div className="px-6 py-6"><Brand /></div>
      <div className="app-sidebar-scroll"><Navigation /></div>
      {userMenu()}
    </aside>
    <div className="app-workspace">
      <header className="app-toolbar">
        <button type="button" className="app-mobile-menu rounded-lg p-2 text-secondary hover:bg-surface-alt" aria-label="Open navigation" aria-expanded={drawerOpen} aria-controls="navigation-drawer" onClick={() => { drawer.current?.showModal(); setDrawerOpen(true); }}><NavigationIcon name="menu" /></button>
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-secondary">{active?.label || "Workspace"}</span>
        <button type="button" className="flex items-center gap-3 rounded-lg border border-line px-3 py-2 text-sm text-muted hover:border-line-strong" onClick={openCommands}><NavigationIcon name="search" /><span>Search</span><kbd className="hidden text-xs sm:inline">⌘ K</kbd></button>
      </header>
      <main id="main-content" tabIndex={-1} className="app-main context-detail" data-region="body">{children}</main>
    </div>
    <dialog id="navigation-drawer" ref={drawer} aria-label="Navigation" className="app-dialog app-drawer" onKeyDown={keepDialogFocus} onClose={() => setDrawerOpen(false)}>
      <div className="flex items-center justify-between px-5 py-5"><Brand /><button type="button" aria-label="Close navigation" className="rounded-lg p-2" onClick={() => drawer.current?.close()}><NavigationIcon name="close" /></button></div>
      <div className="app-sidebar-scroll"><Navigation onNavigate={() => drawer.current?.close()} /></div>
      {userMenu()}
    </dialog>
    <dialog ref={commands} className="app-dialog app-command-dialog" aria-labelledby="command-title" onKeyDown={keepDialogFocus}>
      <div className="flex items-center justify-between border-b border-line px-5 py-3"><h2 id="command-title" className="text-sm font-medium">Search and navigation</h2><button type="button" aria-label="Close search" className="rounded-lg p-2" onClick={() => commands.current?.close()}><NavigationIcon name="close" /></button></div>
      <form onSubmit={search} className="flex items-center gap-3 border-b border-line p-4"><NavigationIcon name="search" /><label htmlFor="command-query" className="sr-only">Search research or find a section</label><input ref={searchInput} id="command-query" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search research or find a section…" className="min-w-0 flex-1 bg-transparent py-2 text-foreground placeholder:text-muted" autoComplete="off" /><button type="submit" className="rounded-lg bg-accent px-3 py-2 text-sm text-on-accent" disabled={!query.trim()}>Search</button></form>
      <div className="max-h-[55vh] overflow-y-auto p-3"><p className="px-3 py-2 text-xs text-muted">Go to</p>{matching.map((item) => <button key={item.href} type="button" className="app-nav-link w-full text-left" onClick={() => go(item.href)}><NavigationIcon name={item.icon} />{item.label}</button>)}{matching.length === 0 && <p className="px-3 py-3 text-sm text-muted">Press Enter to search your research.</p>}</div>
    </dialog>
  </>;
}
