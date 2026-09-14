import Link from "next/link";
import type { GraphNeighborhood, GraphNode } from "@/lib/api/graph";
import { parseApiTimestamp } from "@/lib/api/timestamps";

function label(value: string) { return value.replaceAll("_", " ").replace(/^./, first => first.toUpperCase()); }

function NodeRow({ node, hop, relation, onCenter, edgeKey }: { node: GraphNode; hop: number; relation: string; onCenter: (node: GraphNode) => void; edgeKey?: string }) {
  const { updated_at, status, disposition, chunk_count } = node.attributes;
  return <li data-list-node-key={node.key} data-edge-key={edgeKey} className="flex min-w-0 flex-col gap-3 rounded-lg border border-line bg-surface p-4 sm:flex-row sm:items-start sm:justify-between">
    <div className="min-w-0 flex-1 space-y-2">
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-secondary"><span>{label(relation)}</span><span>{label(node.type)}</span><span>Hop {hop}</span></div>
      <Link href={node.href} className="block break-words font-medium text-accent-text underline underline-offset-4">{node.title}</Link>
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-secondary">
        {(status || disposition) && <span>{label(status || disposition!)}</span>}
        {chunk_count !== undefined && <span>{chunk_count.toLocaleString()} chunks</span>}
        {updated_at && <span>Updated <time dateTime={updated_at}>{parseApiTimestamp(updated_at).toLocaleString()}</time></span>}
      </div>
    </div>
    <button type="button" aria-label={`Center here: ${node.title}`} onClick={() => onCenter(node)} className="shrink-0 self-start rounded-lg border border-line-strong px-3 py-2 text-sm text-foreground hover:bg-surface-alt">Center here</button>
  </li>;
}

export function NeighborhoodList({ neighborhood, onCenter }: { neighborhood: GraphNeighborhood; onCenter: (node: GraphNode) => void }) {
  const { root, nodes, edges, groups } = neighborhood;
  const byKey = new Map(nodes.map(node => [node.key, node]));
  const direct = new Set(edges.filter(edge => edge.from === root.key).map(edge => edge.to));
  const represented = new Set([root.key, ...edges.map(edge => edge.to)]);
  const unlinked = nodes.filter(node => !represented.has(node.key));
  const hop = (key: string) => key === root.key ? 0 : direct.has(key) ? 1 : 2;
  return <section aria-label="Relationship list" className="min-w-0 space-y-5">
    <div><h2 className="text-xl font-semibold">Relationship list</h2><p className="mt-1 text-sm text-secondary">Every shown object and connection. Open an object or make it the new center.</p></div>
    <section aria-label="Root object"><h3 className="mb-2 font-semibold">Root object</h3><ul><NodeRow node={root} hop={0} relation="root" onCenter={onCenter} /></ul></section>
    {groups.map(group => {
      const from = byKey.get(group.from_key)!;
      return <section key={`${group.from_key}:${group.relation}`} data-relation-group={`${group.from_key}:${group.relation}`} className="min-w-0 space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0"><h3 className="font-semibold">{label(group.relation)}</h3><p className="break-words text-sm text-secondary">From {from.title}</p></div>
          <p className="shrink-0 text-sm text-secondary" data-group-total={group.total} data-group-shown={group.shown}>{group.shown.toLocaleString()} of {group.total.toLocaleString()} shown</p>
        </div>
        {group.shown === 0 ? <p className="text-sm text-muted">{group.total === 0 ? "No accessible objects in this relationship." : "This relationship is outside the displayed limit. Center on its source to explore it."}</p> : <ul className="space-y-2">{edges.filter(edge => edge.from === group.from_key && edge.relation === group.relation).map(edge => {
          const key = `${edge.from}>${edge.relation}>${edge.to}`;
          return <NodeRow key={key} edgeKey={key} node={byKey.get(edge.to)!} hop={hop(edge.to)} relation={edge.relation} onCenter={onCenter} />;
        })}</ul>}
      </section>;
    })}
    {unlinked.length > 0 && <section aria-label="Other shown objects"><h3 className="mb-2 font-semibold">Other shown objects</h3><ul className="space-y-2">{unlinked.map(node => <NodeRow key={node.key} node={node} hop={hop(node.key)} relation="shown object" onCenter={onCenter} />)}</ul></section>}
  </section>;
}
