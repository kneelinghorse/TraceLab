import { useEffect, useMemo, useState } from "react";

import { savedSearchesApi } from "@/lib/api/savedSearches";
import type { SearchFiltersState } from "@/components/SearchBar";
import type { SaveSearchPreset } from "@/types/saved-searches";

type SaveSearchButtonProps = {
  currentQuery: string;
  filters: SearchFiltersState;
  topK: number;
  savedSearchCount: number;
  limitPerUser: number;
  preset?: SaveSearchPreset | null;
  onPresetConsumed?: () => void;
  onSaved?: () => void;
};

const INITIAL_FILTERS: SearchFiltersState = {
  projectId: "",
  documentType: "",
  startDate: "",
  endDate: "",
};

export function SaveSearchButton({
  currentQuery,
  filters,
  topK,
  savedSearchCount,
  limitPerUser,
  preset,
  onPresetConsumed,
  onSaved,
}: SaveSearchButtonProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [draft, setDraft] = useState<SaveSearchPreset | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const canCreate = savedSearchCount < limitPerUser;
  const filtersSummary = useMemo(() => summarizeFilters(draft?.filters ?? filters), [draft?.filters, filters]);

  const openPanel = (source?: SaveSearchPreset) => {
    if (!canCreate) {
      setError("Saved search limit reached. Delete one to create another.");
      return;
    }
    const query = source?.query ?? currentQuery;
    if (!query.trim()) {
      setError("Run a query before saving it.");
      return;
    }
    const activeFilters = source?.filters ?? filters;
    const topKValue = source?.topK ?? topK;
    setDraft({
      query,
      filters: activeFilters,
      topK: topKValue,
      suggestedName: source?.suggestedName,
    });
    setName(source?.suggestedName ?? query.slice(0, 80) || "Saved search");
    setDescription("");
    setError(null);
    setIsOpen(true);
  };

  const closePanel = () => {
    setIsOpen(false);
    setDraft(null);
    setError(null);
  };

  const handleSave = async () => {
    if (!draft) {
      setError("Nothing to save yet.");
      return;
    }
    if (!name.trim()) {
      setError("Name is required.");
      return;
    }

    setIsSaving(true);
    try {
      await savedSearchesApi.create({
        name: name.trim(),
        description: description.trim() || undefined,
        query_text: draft.query,
        search_mode: "semantic",
        top_k: draft.topK,
        filters: buildFilterPayload(draft.filters),
      });
      closePanel();
      setName("");
      setDescription("");
      if (onSaved) {
        onSaved();
      }
    } catch (err) {
      const detail = err instanceof Error ? err.message : "Unable to save search.";
      setError(detail);
    } finally {
      setIsSaving(false);
    }
  };

  useEffect(() => {
    if (preset) {
      openPanel(preset);
      onPresetConsumed?.();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preset]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-slate-400">
          Saved searches: {savedSearchCount}/{limitPerUser}
        </p>
        <button
          type="button"
          onClick={() => openPanel()}
          disabled={!canCreate}
          className="rounded-full border border-white/20 px-4 py-1 text-sm text-white hover:border-sky-300 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Save current search
        </button>
      </div>
      {isOpen && draft && (
        <div className="rounded-2xl border border-white/10 bg-black/30 p-4 text-sm text-slate-200">
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Save search</p>
          <div className="mt-3 space-y-3">
            <div>
              <label className="text-xs uppercase tracking-[0.3em] text-slate-400" htmlFor="saved-search-name">
                Name
              </label>
              <input
                id="saved-search-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                className="mt-1 w-full rounded-xl border border-white/15 bg-slate-900/60 px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-sky-500/60"
                placeholder="Weekly risk briefing"
              />
            </div>
            <div>
              <label className="text-xs uppercase tracking-[0.3em] text-slate-400" htmlFor="saved-search-description">
                Description
              </label>
              <textarea
                id="saved-search-description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                className="mt-1 w-full rounded-xl border border-white/15 bg-slate-900/60 px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-sky-500/60"
                placeholder="Highlights checkout incidents in Sprint 09."
              />
            </div>
            <div className="rounded-xl border border-white/10 bg-slate-900/40 p-3 text-xs text-slate-300">
              <p className="font-semibold text-white">Query</p>
              <p>{draft.query}</p>
              {filtersSummary.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-2">
                  {filtersSummary.map((chip) => (
                    <span key={chip} className="rounded-full border border-white/15 px-2 py-0.5 text-[11px] text-white/80">
                      {chip}
                    </span>
                  ))}
                </div>
              )}
              <p className="mt-1 text-slate-400">Top K: {draft.topK}</p>
            </div>
            {error && <p className="text-sm text-rose-300">{error}</p>}
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => void handleSave()}
                disabled={isSaving}
                className="rounded-full bg-gradient-to-r from-sky-500 to-indigo-500 px-4 py-2 font-semibold text-white shadow-lg shadow-sky-500/30 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isSaving ? "Saving…" : "Save search"}
              </button>
              <button type="button" onClick={closePanel} className="text-sm text-slate-400 hover:text-white">
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
      {!canCreate && <p className="text-xs text-amber-300">Limit reached. Remove an entry to add another.</p>}
    </div>
  );
}

const buildFilterPayload = (state: SearchFiltersState) => {
  const payload: Record<string, string> = {};
  const source = state ?? INITIAL_FILTERS;
  if (source.projectId) payload.project_id = source.projectId;
  if (source.documentType) payload.source_type = source.documentType;
  if (source.startDate) payload.date_from = source.startDate;
  if (source.endDate) payload.date_to = source.endDate;
  return payload;
};

const summarizeFilters = (state: SearchFiltersState) => {
  const summary: string[] = [];
  if (state.projectId) summary.push(`Project ${state.projectId}`);
  if (state.documentType) summary.push(`Type ${state.documentType}`);
  if (state.startDate) summary.push(`From ${state.startDate}`);
  if (state.endDate) summary.push(`To ${state.endDate}`);
  return summary;
};
