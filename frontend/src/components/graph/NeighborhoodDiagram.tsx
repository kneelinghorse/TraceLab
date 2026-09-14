import { useId } from "react";
import type { GraphNeighborhood } from "@/lib/api/graph";

const clamp = (title: string, limit: number) => title.length > limit ? title.slice(0, limit - 1) + "…" : title;

export function NeighborhoodDiagram({ neighborhood }: { neighborhood: GraphNeighborhood }) {
  const titleId = useId();
  const descriptionId = useId();
  const { root, nodes, edges, groups } = neighborhood;
  const positions = new Map<string, { x: number; y: number; outer: boolean }>([[root.key, { x: 600, y: 600, outer: false }]]);
  const sectors = groups.filter(group => group.from_key === root.key && group.shown > 0);
  const place = (key: string, angle: number, radius: number, outer: boolean) => positions.set(key, { x: 600 + Math.cos(angle) * radius, y: 600 + Math.sin(angle) * radius, outer });
  sectors.forEach((group, sector) => {
    const members = [...new Set(edges.filter(edge => edge.from === root.key && edge.relation === group.relation).map(edge => edge.to))].filter(key => !positions.has(key));
    members.forEach((key, index) => place(key, -Math.PI / 2 + (sector + (index + 0.5) / members.length) * 2 * Math.PI / sectors.length, 200, false));
  });
  const outer = nodes.filter(node => !positions.has(node.key));
  outer.forEach((node, index) => place(node.key, -Math.PI / 2 + (index + 0.5) * 2 * Math.PI / outer.length, 380, true));
  return <svg role="img" aria-labelledby={titleId} aria-describedby={descriptionId} viewBox={outer.length ? "0 0 1200 1200" : "200 200 800 800"} className="block h-auto max-h-[42rem] w-full" focusable="false">
    <title id={titleId}>Relationship diagram for {root.title}</title>
    <desc id={descriptionId}>The root is at the center. Direct relationships occupy inner sectors; second-hop objects occupy the outer ring. Full titles, connection names and all navigation controls are in the relationship list.</desc>
    <circle cx="600" cy="600" r="200" fill="none" stroke="var(--theme-border-subtle)" strokeDasharray="4 8" />
    {outer.length > 0 && <circle cx="600" cy="600" r="380" fill="none" stroke="var(--theme-border-subtle)" strokeDasharray="4 8" />}
    {edges.map(edge => {
      const from = positions.get(edge.from)!;
      const to = positions.get(edge.to)!;
      return <path key={`${edge.from}:${edge.relation}:${edge.to}`} d={edge.from === edge.to ? `M ${from.x} ${from.y} c 50 -55 50 55 0 0` : `M ${from.x} ${from.y} L ${to.x} ${to.y}`} fill="none" stroke="var(--theme-border-strong)" strokeWidth="1.5" strokeDasharray={edge.from === root.key ? undefined : "5 5"} />;
    })}
    {nodes.map(node => {
      const point = positions.get(node.key)!;
      const isRoot = node.key === root.key;
      const left = point.x < 600;
      const angle = Math.atan2(point.y - 600, point.x - 600) * 180 / Math.PI + (left ? 180 : 0);
      return <g key={node.key} data-graph-node-key={node.key}>
        <circle cx={point.x} cy={point.y} r={isRoot ? 14 : 8} fill={isRoot ? "var(--theme-text-accent)" : "var(--theme-surface-raised)"} stroke="var(--theme-text-accent)" strokeWidth="2.5" />
        <text x={isRoot ? point.x : point.x + (left ? -16 : 16)} y={isRoot ? point.y + 42 : point.y + 7} transform={isRoot ? undefined : `rotate(${angle} ${point.x} ${point.y})`} textAnchor={isRoot ? "middle" : left ? "end" : "start"} fill="var(--theme-text-primary)" fontSize={isRoot ? 26 : 22} fontWeight={isRoot ? 600 : 400}>{clamp(node.title, isRoot ? 24 : point.outer ? 14 : 11)}</text>
      </g>;
    })}
  </svg>;
}
