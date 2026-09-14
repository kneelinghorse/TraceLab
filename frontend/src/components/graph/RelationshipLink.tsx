import Link from "next/link";
import { graphHref } from "@/lib/api/graph";
import type { NavigationEntityType } from "@/lib/api/navigation";

export function RelationshipLink({ type, id }: { type: NavigationEntityType; id: string }) {
  return <Link href={graphHref(type, id)} className="inline-flex shrink-0 rounded-lg border border-line-strong px-3 py-2 text-sm text-accent-text hover:bg-surface-alt">View relationships</Link>;
}
