import type { FormEvent } from "react";

import type { Project } from "@/types/document";

export type SearchFiltersState = {
  projectId: string;
  documentType: string;
  startDate: string;
  endDate: string;
};

const CHUNKS_PRESETS = [10, 15, 20, 25, 35] as const;

type SearchBarProps = {
  query: string;
  onQueryChange: (value: string) => void;
  filters: SearchFiltersState;
  onFiltersChange: (update: Partial<SearchFiltersState>) => void;
  onSubmit: () => void;
  isSearching: boolean;
  projects: Project[];
  documentTypes: string[];
  topK: number;
  onTopKChange: (value: number) => void;
  graphEnabled: boolean;
  onGraphEnabledChange: (value: boolean) => void;
};

export function SearchBar({
  query,
  onQueryChange,
  filters,
  onFiltersChange,
  onSubmit,
  isSearching,
  projects,
  topK,
  onTopKChange,
  graphEnabled,
  onGraphEnabledChange,
}: SearchBarProps) {
  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmit();
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      onSubmit();
    }
  };

  return (
    <form onSubmit={handleSubmit} className="w-full">
      <div className="glass-card rounded-2xl p-4 sm:p-6">
        {/* Search input row */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
          <div className="flex-1">
            <textarea
              id="query-input"
              value={query}
              onChange={(event) => onQueryChange(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Search TraceLab intelligence..."
              rows={2}
              className="w-full resize-none rounded-xl border border-white/15 bg-white/5 px-4 py-3 text-lg text-white placeholder:text-slate-500 focus:border-sky-400/60 focus:outline-none focus:ring-2 focus:ring-sky-400/30"
            />
          </div>
          <button
            type="submit"
            disabled={isSearching}
            className="inline-flex h-[52px] items-center justify-center gap-2 whitespace-nowrap rounded-xl bg-gradient-to-r from-sky-500 to-indigo-500 px-8 font-semibold text-white shadow-lg shadow-sky-500/25 transition hover:from-sky-400 hover:to-indigo-400 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {isSearching && (
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/70 border-t-transparent" />
            )}
            {isSearching ? "Searching..." : "Search"}
          </button>
        </div>

        {/* Filters row */}
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <label
              htmlFor="project-filter"
              className="text-sm text-slate-400"
            >
              Project
            </label>
            <select
              id="project-filter"
              value={filters.projectId}
              onChange={(event) =>
                onFiltersChange({ projectId: event.target.value })
              }
              className="rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-sm text-white focus:border-sky-400/60 focus:outline-none"
            >
              <option value="">All projects</option>
              {projects.map((project) => (
                <option
                  key={project.id}
                  value={project.id}
                  className="bg-slate-900 text-white"
                >
                  {project.name}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-2">
            <label htmlFor="chunks-filter" className="text-sm text-slate-400">
              Chunks
            </label>
            <select
              id="chunks-filter"
              value={topK}
              onChange={(event) => onTopKChange(Number(event.target.value))}
              className="rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-sm text-white focus:border-sky-400/60 focus:outline-none"
            >
              {CHUNKS_PRESETS.map((preset) => (
                <option
                  key={preset}
                  value={preset}
                  className="bg-slate-900 text-white"
                >
                  {preset}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-2">
            <label htmlFor="graph-toggle" className="text-sm text-slate-400">
              Graph expansion
            </label>
            <input
              id="graph-toggle"
              type="checkbox"
              checked={graphEnabled}
              onChange={(event) => onGraphEnabledChange(event.target.checked)}
              className="h-4 w-4 rounded border-white/20 bg-white/5 text-sky-400 focus:ring-2 focus:ring-sky-400/40"
            />
          </div>

          {(filters.projectId || topK !== 10) && (
            <button
              type="button"
              onClick={() => {
                onFiltersChange({ projectId: "" });
                onTopKChange(10);
              }}
              className="text-sm text-slate-400 hover:text-white"
            >
              Reset
            </button>
          )}
        </div>
      </div>
    </form>
  );
}
