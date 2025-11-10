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
    <form onSubmit={handleSubmit} className="glass-card p-6 space-y-6">
      <div>
        <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Semantic Search</p>
        <h1 className="text-3xl font-semibold text-white">Query documents + synthesize answers</h1>
      </div>

      <div className="space-y-4">
        <label className="text-sm text-slate-300" htmlFor="query-input">
          Query
        </label>
        <input
          id="query-input"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="How does the research support our onboarding strategy?"
          className="w-full rounded-2xl border border-white/15 bg-white/5 px-4 py-3 text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-sky-400/60"
        />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <label className="text-sm text-slate-300" htmlFor="project-filter">
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
          <label className="text-sm text-slate-300" htmlFor="type-filter">
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
          <label className="text-sm text-slate-300" htmlFor="start-date">
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
          <label className="text-sm text-slate-300" htmlFor="end-date">
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

      <div className="space-y-2">
        <div className="flex items-center justify-between text-sm text-slate-300">
          <span>Top K</span>
          <span>{topK} chunks</span>
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

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="submit"
          disabled={isSearching}
          className="inline-flex items-center gap-2 rounded-full bg-sky-500 px-6 py-3 font-semibold text-white shadow-lg shadow-sky-500/25 transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-70"
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
