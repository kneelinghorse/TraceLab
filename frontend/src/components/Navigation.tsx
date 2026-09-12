import Link from "next/link";
import { useRouter } from "next/router";

import { useRole } from "@/contexts/RoleContext";

export type NavigationItem = { label: string; href: string; icon: string };
export const navigationGroups: { label: string; admin?: boolean; items: NavigationItem[] }[] = [
  { label: "", items: [
    { label: "Home", href: "/", icon: "home" },
    { label: "Projects", href: "/projects", icon: "folder" },
  ] },
  { label: "Data", items: [
    { label: "Documents", href: "/documents", icon: "document" },
    { label: "Evidence", href: "/evidence", icon: "evidence" },
  ] },
  { label: "Context", items: [
    { label: "Collections", href: "/collections", icon: "collection" },
  ] },
  { label: "Jobs", items: [
    { label: "Missions", href: "/missions", icon: "mission" },
    { label: "Queue", href: "/missions/queue", icon: "queue" },
  ] },
  { label: "Synthesis", items: [
    { label: "Reports", href: "/reports", icon: "report" },
  ] },
  { label: "Discover", items: [
    { label: "Search", href: "/search", icon: "search" },
    { label: "Saved searches", href: "/saved-searches", icon: "bookmark" },
  ] },
  { label: "Admin", admin: true, items: [
    { label: "Users", href: "/admin/users", icon: "users" },
    { label: "Spaces", href: "/admin/spaces", icon: "spaces" },
    { label: "Observability", href: "/console", icon: "activity" },
  ] },
];

const iconPaths: Record<string, string> = {
  home: "M3 10 12 3l9 7M5 9v12h5v-7h4v7h5V9",
  folder: "M3 7V5h6l2 2h10v13H3V7Z",
  document: "M5 3h9l5 5v13H5V3Zm9 0v6h5M8 13h8M8 17h6",
  evidence: "m8 8 3-3a4 4 0 0 1 6 6l-3 3M16 16l-3 3a4 4 0 0 1-6-6l3-3M8 16l8-8",
  collection: "m3 7 9-4 9 4-9 4-9-4Zm0 5 9 4 9-4M3 17l9 4 9-4",
  mission: "M12 3a9 9 0 1 0 9 9M12 7a5 5 0 1 0 5 5M12 12l8-8M16 3h5v5",
  queue: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
  report: "M5 3h14v18H5V3Zm4 14v-4m3 4V8m3 9v-6",
  search: "M20 20l-5-5M10.5 17a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13Z",
  bookmark: "M6 3h12v18l-6-4-6 4V3Z",
  users: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm9-7a4 4 0 0 1 0 7m4 10v-2a4 4 0 0 0-3-4",
  spaces: "M3 3h7v7H3V3Zm11 0h7v7h-7V3ZM3 14h7v7H3v-7Zm11 0h7v7h-7v-7Z",
  activity: "M2 12h5l3-8 4 16 3-8h5",
  menu: "M4 6h16M4 12h16M4 18h16",
  close: "m6 6 12 12M6 18 18 6",
};

export function NavigationIcon({ name }: { name: string }) {
  return <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" className="shrink-0"><path d={iconPaths[name] || iconPaths.document} /></svg>;
}

export function activeNavigationItem(path: string, items: NavigationItem[]) {
  return [...items].sort((a, b) => b.href.length - a.href.length).find((item) => path === item.href || (item.href !== "/" && path.startsWith(`${item.href}/`)));
}

export function Navigation({ onNavigate }: { onNavigate?: () => void }) {
  const { pathname } = useRouter();
  const { isAdmin } = useRole();
  const groups = navigationGroups.filter((group) => !group.admin || isAdmin);
  const active = activeNavigationItem(pathname, groups.flatMap((group) => group.items));
  return (
    <nav aria-label="Main navigation">
      {groups.map((group) => (
        <div key={group.label || "home"}>
          {group.label && <p className="app-nav-group">{group.label}</p>}
          {group.items.map((item) => (
            <Link key={item.href} href={item.href} className="app-nav-link" aria-current={active?.href === item.href ? "page" : undefined} onClick={onNavigate}>
              <NavigationIcon name={item.icon} /><span>{item.label}</span>
            </Link>
          ))}
        </div>
      ))}
    </nav>
  );
}
