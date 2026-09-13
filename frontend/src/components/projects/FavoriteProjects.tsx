import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { useAuth } from "@/contexts/AuthContext";
import { PaginationBar } from "@/components/ui/PaginationBar";
import { homeApi, type HomeRecent, type HomeSection } from "@/lib/api/home";

export function FavoriteProjects({ initial }: { initial: HomeSection<HomeRecent> }) {
  const { user } = useAuth();
  const [page, setPage] = useState(1);
  const activePage = Math.min(page, Math.max(1, Math.ceil(initial.total / 6)));
  const response = useSWR(activePage > 1 ? ["favorites", user?.user_id, activePage] : null, () => homeApi.favorites({ page: activePage }));
  const data = activePage === 1 ? initial : response.data;
  return <section className="panel space-y-4 p-5" aria-label="Favorite projects">
    <h2 className="text-lg font-semibold">Favorite projects <span className="text-sm text-secondary">({initial.total.toLocaleString()})</span></h2>
    {response.isLoading && <p role="status">Loading favorites…</p>}
    {response.error && <p role="alert">Favorites could not load. <button className="underline" onClick={() => void response.mutate()}>Retry favorites</button></p>}
    {data && <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{data.items.map(item => <li key={item.id}><Link href={item.href} className="block break-words rounded-lg border border-line px-4 py-3 font-medium hover:text-accent-text">{item.title}</Link></li>)}</ul>}
    {data?.total === 0 && <p className="text-sm text-secondary">Favorite a project from its hub to keep it here.</p>}
    {initial.total > 6 && <PaginationBar label="Favorite project pages" page={activePage} pages={Math.ceil(initial.total / 6)} onChange={setPage} />}
  </section>;
}
