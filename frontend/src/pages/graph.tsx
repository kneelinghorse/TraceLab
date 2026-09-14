import { useRouter } from "next/router";
import { useRef, useState, useSyncExternalStore } from "react";
import useSWR from "swr";
import { AuthGate } from "@/components/AuthGate";
import { NeighborhoodDiagram } from "@/components/graph/NeighborhoodDiagram";
import { NeighborhoodList } from "@/components/graph/NeighborhoodList";
import { PageState } from "@/components/ui/PageState";
import { useAuth } from "@/contexts/AuthContext";
import { graphApi, graphHref, parseGraphRoot, type GraphDepth, type GraphNode } from "@/lib/api/graph";
import { HttpError } from "@/lib/api/http";
import { navigationApi, type NavigationEntityType } from "@/lib/api/navigation";

const labels: Record<NavigationEntityType, string> = { project: "Projects", document: "Documents", collection: "Collections", mission: "Missions", report: "Reports", evidence: "Evidence" };
const subscribeWidth = (changed: () => void) => {
  const media = window.matchMedia("(min-width: 768px)");
  media.addEventListener("change", changed);
  return () => media.removeEventListener("change", changed);
};
const wideSnapshot = () => window.matchMedia("(min-width: 768px)").matches;
const serverSnapshot = () => false;

function RootPicker({ onSelect }: { onSelect: (type: NavigationEntityType, id: string) => void }) {
  const { user } = useAuth();
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const { data, error, isLoading, mutate } = useSWR(submitted ? ["graph-root-search", user?.user_id, submitted] : null, () => navigationApi.search(submitted));
  const groups = data?.groups.filter(group => group.total > 0) ?? [];
  return <section className="panel p-5" aria-label="Choose a root object">
    <form onSubmit={event => { event.preventDefault(); const term = query.trim(); if (term === submitted) void mutate(); else setSubmitted(term); }} className="flex flex-col gap-3 sm:flex-row sm:items-end">
      <label className="min-w-0 flex-1"><span className="form-label">Find an object</span><input value={query} onChange={event => setQuery(event.target.value)} maxLength={200} required className="form-input" placeholder="Search by title or name…" /></label>
      <button type="submit" disabled={!query.trim()} className="shrink-0 rounded-lg bg-accent px-4 py-3 text-sm text-on-accent disabled:opacity-50">Find objects</button>
    </form>
    <p className="mt-3 text-sm text-secondary">Choose a project, document, collection, mission, report or evidence entry.</p>
    {submitted && (isLoading ? <PageState state="loading" title="Finding objects…" /> : error ? <PageState state="error" title="Objects could not load" onRetry={() => void mutate()} /> : groups.length ? <div className="mt-5 grid gap-4 sm:grid-cols-2" aria-label="Root search results">{groups.map(group => <section key={group.entity_type} className="min-w-0">
      <h2 className="mb-2 text-sm font-semibold">{labels[group.entity_type]} ({group.total.toLocaleString()})</h2>
      <ul className="space-y-1">{group.items.map(item => <li key={item.id}><button type="button" aria-label={`Center on ${item.title}`} onClick={() => onSelect(group.entity_type, item.id)} className="block w-full break-words rounded-lg border border-line px-3 py-2 text-left text-sm text-accent-text hover:bg-surface-alt">{item.title}</button></li>)}</ul>
    </section>)}</div> : <PageState state="empty" title="No matching objects">Try another name or title.</PageState>)}
  </section>;
}

export default function GraphPage() {
  return <AuthGate><Relationships /></AuthGate>;
}

function Relationships() {
  const router = useRouter();
  const { user } = useAuth();
  const title = useRef<HTMLHeadingElement>(null);
  const wide = useSyncExternalStore(subscribeWidth, wideSnapshot, serverSnapshot);
  const root = parseGraphRoot(router.query.root);
  const depth: GraphDepth = router.query.depth === "2" ? 2 : 1;
  const { data, error, isLoading, mutate } = useSWR(router.isReady && root ? ["graph-neighborhood", user?.user_id, root.type, root.id, depth] : null,
    () => graphApi.neighborhood(root!.type, root!.id, depth), { dedupingInterval: 0, keepPreviousData: false });
  function center(type: NavigationEntityType, id: string, nextDepth = depth) {
    void router.push(graphHref(type, id, nextDepth), undefined, { shallow: true }).then(() => title.current?.focus());
  }
  const onCenter = (node: GraphNode) => center(node.type, node.id);
  return <div className="mx-auto max-w-7xl space-y-6 px-4 py-8 sm:px-6">
    <header><h1 ref={title} tabIndex={-1} className="text-3xl font-semibold tracking-tight">Relationships</h1><p className="mt-2 max-w-3xl text-secondary">Follow the recorded connections between your research objects. Choose a center, then explore its sources and outputs.</p></header>
    <RootPicker onSelect={center} />
    {root && <div role="group" aria-label="Relationship depth" className="flex flex-wrap items-center gap-3"><span className="text-sm font-medium">Explore</span>{([1, 2] as const).map(value => <button key={value} type="button" aria-pressed={depth === value} onClick={() => center(root.type, root.id, value)} className={`rounded-lg border px-4 py-2 text-sm ${depth === value ? "border-line-strong bg-accent text-on-accent" : "border-line bg-surface text-foreground hover:bg-surface-alt"}`}>Depth {value}</button>)}</div>}
    {!router.isReady ? <PageState state="loading" title="Loading relationships…" /> : router.query.root && !root ? <PageState state="error" title="Invalid relationship link">Find an object above to choose a valid root.</PageState> : !root ? <PageState state="empty" title="Choose an object to explore">Its relationships will appear here as a diagram and a complete list.</PageState> : error instanceof HttpError && error.status === 404 ? <PageState state="empty" title="Root object not found">This object is no longer available here. Choose another root above.</PageState> : error instanceof HttpError && error.status === 403 ? <PageState state="error" title="Access to this object is restricted">Choose an object you can access.</PageState> : error ? <PageState state="error" title="Relationships could not load" onRetry={() => void mutate()} /> : isLoading ? <PageState state="loading" title="Loading relationships…" /> : data && <div data-neighborhood-root={data.root.key} className="space-y-6">
      {data.truncated && <p className="rounded-lg border border-info-line bg-info-surface p-4 text-sm text-accent-text">More relationships are available. Each group shows its full accessible total. Center on an object to explore its connections.</p>}
      {!data.edges.length && <PageState state="empty" title="No accessible relationships are recorded">You can still open this root object or choose another center.</PageState>}
      <details open={wide} className="panel p-4 sm:p-5"><summary className="cursor-pointer font-medium md:hidden">Show relationship diagram</summary><div><h2 className="mt-3 text-lg font-semibold md:mt-0">Relationship diagram</h2><p className="mt-1 text-sm text-secondary">Direct connections on the inner ring; second-hop objects on the outer ring. Use the list for full titles and navigation.</p><NeighborhoodDiagram neighborhood={data} /></div></details>
      <NeighborhoodList neighborhood={data} onCenter={onCenter} />
    </div>}
  </div>;
}
