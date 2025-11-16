import { formatDistanceToNow } from "date-fns";

import type { SavedSearch } from "@/types/saved-searches";

type SavedSearchesListProps = {
  items: SavedSearch[];
  limitPerUser: number;
  isLoading?: boolean;
  onExecute: (entry: SavedSearch) => void | Promise<void>;
  onLoad?: (entry: SavedSearch) => void;
  onDelete?: (entry: SavedSearch) => void | Promise<void>;
  onSelect?: (entry: SavedSearch) => void;
};

export function SavedSearchesList({
  items,
  limitPerUser,
  isLoading = false,
  onExecute,
  onLoad,
  onDelete,
  onSelect,
}: SavedSearchesListProps) {
  if (isLoading) {
    return <p className="text-sm text-slate-400">Loading saved searches…</p>;
  }

  if (items.length === 0) {
    return <p className="text-sm text-slate-400">No saved searches yet. Capture a frequent query to build your quick access list.</p>;
  }

  return (
    <div className="space-y-3">
      {items.map((entry) => (
        <article
          key={entry.id}
          className="rounded-2xl border border-white/10 bg-black/25 p-4 text-sm text-slate-200 transition hover:border-sky-400/40"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <button
              type="button"
              onClick={() => onSelect?.(entry)}
              className="text-left text-base font-semibold text-white hover:text-sky-300"
            >
              {entry.name}
            </button>
            <span className="text-xs text-slate-400">
              {entry.last_used_at
                ? `Last run ${formatDistanceToNow(new Date(entry.last_used_at), { addSuffix: true })}`
                : "Never run"}
            </span>
          </div>
          {entry.description && <p className="mt-1 text-slate-400">{entry.description}</p>}
          <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-400">
            <span>Top K {entry.top_k}</span>
            <span>
              {entry.use_count} run{entry.use_count === 1 ? "" : "s"}
            </span>
            {getFilterValue(entry, "project_id") && <span>Project {getFilterValue(entry, "project_id")}</span>}
            {getFilterValue(entry, "source_type") && <span>Type {getFilterValue(entry, "source_type")}</span>}
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
            <button
              type="button"
              onClick={() => onExecute(entry)}
              className="rounded-full border border-white/20 px-3 py-1 text-white hover:border-sky-400/70"
            >
              Run now
            </button>
            {onLoad && (
              <button
                type="button"
                onClick={() => onLoad(entry)}
                className="rounded-full border border-transparent px-3 py-1 text-slate-300 hover:text-white"
              >
                Load filters
              </button>
            )}
            {onDelete && (
              <button
                type="button"
                onClick={() => onDelete(entry)}
                className="text-rose-300 hover:text-rose-200"
              >
                Delete
              </button>
            )}
          </div>
        </article>
      ))}
      <p className="text-xs text-slate-500">
        {items.length}/{limitPerUser} saved searches
      </p>
    </div>
  );
}

const getFilterValue = (entry: SavedSearch, key: string) => {
  const value = entry.filters?.[key];
  if (value === null || value === undefined) {
    return "";
  }
  if (Array.isArray(value)) {
    return value.join(", ");
  }
  return String(value);
};
