import type { FormEvent } from "react";

import type { Project } from "@/types/document";

export type SearchFiltersState = {
  projectId: string;
  documentType: string;
  startDate: string;
  endDate: string;
};

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
};

export function SearchBar({
  query,
  onQueryChange,
  filters,
  onFiltersChange,
  onSubmit,
  isSearching,
  projects,
  documentTypes,
  topK,
  onTopKChange,
}: SearchBarProps) {
  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmit();
  };

  const resetFilters = () => {
    onFiltersChange({ projectId: "", documentType: "", startDate: "", endDate: "" });
  };

  return (
    <form onSubmit={handleSubmit} className="glass-card grid gap-8 rounded-3xl p-8">
      <div className="grid gap-3">
        <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Semantic search</p>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <h2 className="text-3xl font-semibold text-white">Tune retrieval, then capture citations in a single pane</h2>
          <span className="rounded-full border border-white/15 bg-white/5 px-4 py-1 text-sm text-slate-300">
            {isSearching ? "Running query…" : "Idle"}
          </span>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[2fr,1fr]">
        <div className="space-y-2">
          <label className="text-xs uppercase tracking-[0.3em] text-slate-400" htmlFor="query-input">
            Query
          </label>
          <textarea
            id="query-input"
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="How does the research support our onboarding strategy?"
            className="min-h-[96px] w-full rounded-2xl border border-white/15 bg-white/5 px-4 py-3 text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-sky-400/60"
          />
          <p className="text-xs text-slate-400">Include intent + success metric so retrieval ranks relevant context.</p>
        </div>
        <div className="grid gap-4 rounded-2xl border border-white/10 bg-black/30 p-5 text-sm text-slate-300">
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Playbook</p>
          <p>• Use project filter for curated corpora.</p>
          <p>• Document type narrows to interviews, memos, etc.</p>
          <p>• Date window trims noise from legacy uploads.</p>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <label className="text-xs uppercase tracking-[0.3em] text-slate-400" htmlFor="project-filter">
            Project
          </label>
          <select
            id="project-filter"
            value={filters.projectId}
            onChange={(event) => onFiltersChange({ projectId: event.target.value })}
            className="w-full rounded-2xl border border-white/15 bg-white/5 px-4 py-3 text-white focus:outline-none"
          >
            <option value="">All projects</option>
            {projects.map((project) => (
              <option key={project.id} value={project.id} className="bg-slate-900 text-white">
                {project.name}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-2">
          <label className="text-xs uppercase tracking-[0.3em] text-slate-400" htmlFor="type-filter">
            Document type
          </label>
          <select
            id="type-filter"
            value={filters.documentType}
            onChange={(event) => onFiltersChange({ documentType: event.target.value })}
            className="w-full rounded-2xl border border-white/15 bg-white/5 px-4 py-3 text-white focus:outline-none"
          >
            <option value="">All types</option>
            {documentTypes.map((type) => (
              <option key={type} value={type} className="bg-slate-900 text-white">
                {type}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <label className="text-xs uppercase tracking-[0.3em] text-slate-400" htmlFor="start-date">
            From date
          </label>
          <input
            id="start-date"
            type="date"
            value={filters.startDate}
            onChange={(event) => onFiltersChange({ startDate: event.target.value })}
            className="w-full rounded-2xl border border-white/15 bg-white/5 px-4 py-3 text-white focus:outline-none"
          />
        </div>
        <div className="space-y-2">
          <label className="text-xs uppercase tracking-[0.3em] text-slate-400" htmlFor="end-date">
            To date
          </label>
          <input
            id="end-date"
            type="date"
            value={filters.endDate}
            onChange={(event) => onFiltersChange({ endDate: event.target.value })}
            className="w-full rounded-2xl border border-white/15 bg-white/5 px-4 py-3 text-white focus:outline-none"
          />
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-[2fr,1fr]">
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs uppercase tracking-[0.3em] text-slate-400">
            <span>Top K</span>
            <span className="text-slate-300">{topK} chunks</span>
          </div>
          <input
            type="range"
            min={3}
            max={15}
            step={1}
            value={topK}
            onChange={(event) => onTopKChange(Number(event.target.value))}
            className="w-full accent-sky-400"
          />
        </div>
        <div className="rounded-2xl border border-white/15 bg-white/5 px-4 py-3 text-sm text-slate-300">
          <p>Increase Top K if the first answer lacks coverage; lower it for faster iterations.</p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="submit"
          disabled={isSearching}
          className="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-sky-500 to-indigo-500 px-6 py-3 font-semibold text-white shadow-lg shadow-sky-500/25 transition hover:from-sky-400 hover:to-indigo-400 disabled:cursor-not-allowed disabled:opacity-70"
        >
          {isSearching && <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/70 border-t-transparent" />}
          Run search
        </button>
        <button
          type="button"
          onClick={resetFilters}
          className="rounded-full border border-white/20 px-4 py-2 text-sm text-slate-200 hover:border-sky-400/60"
        >
          Reset filters
        </button>
      </div>
    </form>
  );
}
