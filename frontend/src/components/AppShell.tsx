import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { ReactNode } from "react";

import { AuthGate } from "@/components/AuthGate";
import { CommandPalette } from "@/components/CommandPalette";
import { InboxAnnouncer, UnreadBadge } from "@/components/InboxBadge";
import { Navigation, NavigationIcon, activeNavigationItem, navigationGroups } from "@/components/Navigation";
import { ThemeSelect } from "@/components/ThemeSelect";
import { useAuth } from "@/contexts/AuthContext";
import { useRole } from "@/contexts/RoleContext";
import { inboxBadgeName } from "@/lib/api/inbox";
import { keepDialogFocus } from "@/lib/dialog-focus";
import { openCommandPalette } from "@/lib/command-palette";
import { useInboxSummary } from "@/lib/hooks/useInboxSummary";

function Brand() {
  return <Link href="/" className="flex items-center gap-3 font-semibold tracking-tight text-foreground"><span aria-hidden="true" className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-on-accent">T</span><span>TraceLab</span></Link>;
}

const subscribeHydration = () => () => {};
const clientSnapshot = () => true;
const serverSnapshot = () => false;


export function AppShell({ children }: { children: ReactNode }) {
  const hydrated = useSyncExternalStore(subscribeHydration, clientSnapshot, serverSnapshot);
  const { isAuthenticated, user, logout } = useAuth();
  const { isAdmin } = useRole();
  const { data: inbox } = useInboxSummary();
  const unread = inbox?.unread?.total ?? 0;
  const router = useRouter();
  const drawer = useRef<HTMLDialogElement>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const items = navigationGroups.filter((group) => !group.admin || isAdmin).flatMap((group) => group.items);
  const active = activeNavigationItem(router.pathname, items);

  useEffect(() => {
    const media = window.matchMedia("(min-width: 900px)");
    const closeDrawer = () => { if (media.matches) drawer.current?.close(); };
    media.addEventListener("change", closeDrawer);
    return () => media.removeEventListener("change", closeDrawer);
  }, []);

  function userMenu() {
    return <div className="border-t border-line px-4 py-3">
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
        <Link href="/inbox" aria-label={unread > 0 ? inboxBadgeName(unread) : "Inbox"} className="flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-sm text-muted hover:border-line-strong"><NavigationIcon name="inbox" /><span className="hidden sm:inline">Inbox</span><UnreadBadge total={unread} /></Link>
        <button type="button" className="flex items-center gap-3 rounded-lg border border-line px-3 py-2 text-sm text-muted hover:border-line-strong" onClick={openCommandPalette}><NavigationIcon name="search" /><span>Search</span><kbd className="hidden text-xs sm:inline">⌘ K</kbd></button>
      </header>
      <InboxAnnouncer total={inbox?.unread?.total} />
      <main id="main-content" tabIndex={-1} className="app-main context-detail" data-region="body">{children}</main>
    </div>
    <dialog id="navigation-drawer" ref={drawer} aria-label="Navigation" className="app-dialog app-drawer" onKeyDown={keepDialogFocus} onClose={() => setDrawerOpen(false)}>
      <div className="flex items-center justify-between px-5 py-5"><Brand /><button type="button" aria-label="Close navigation" className="rounded-lg p-2" onClick={() => drawer.current?.close()}><NavigationIcon name="close" /></button></div>
      <div className="app-sidebar-scroll"><Navigation onNavigate={() => drawer.current?.close()} /></div>
      {userMenu()}
    </dialog>
    <CommandPalette key={user?.user_id ?? "anonymous"} />
  </>;
}
