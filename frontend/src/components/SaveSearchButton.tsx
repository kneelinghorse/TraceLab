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
    const defaultName = query.slice(0, 80) || "Saved search";
    setName(source?.suggestedName ?? defaultName);
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
        <p className="text-sm text-secondary">
          Saved searches: {savedSearchCount}/{limitPerUser}
        </p>
        <button
          type="button"
          onClick={() => openPanel()}
          disabled={!canCreate}
          className="rounded-full border border-line px-4 py-1 text-sm text-foreground hover:border-info-line disabled:cursor-not-allowed disabled:opacity-50"
        >
          Save current search
        </button>
      </div>
      {isOpen && draft && (
        <div className="rounded-2xl border border-line bg-surface-alt p-4 text-sm text-secondary">
          <p className="text-xs uppercase tracking-[0.3em] text-secondary">Save search</p>
          <div className="mt-3 space-y-3">
            <div>
              <label className="text-xs uppercase tracking-[0.3em] text-secondary" htmlFor="saved-search-name">
                Name
              </label>
              <input
                id="saved-search-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                className="mt-1 w-full rounded-xl border border-line bg-background px-3 py-2 text-foreground focus:outline-none focus:ring-2 focus:ring-focus"
                placeholder="Weekly risk briefing"
              />
            </div>
            <div>
              <label className="text-xs uppercase tracking-[0.3em] text-secondary" htmlFor="saved-search-description">
                Description
              </label>
              <textarea
                id="saved-search-description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                className="mt-1 w-full rounded-xl border border-line bg-background px-3 py-2 text-foreground focus:outline-none focus:ring-2 focus:ring-focus"
                placeholder="Highlights checkout incidents in Sprint 09."
              />
            </div>
            <div className="rounded-xl border border-line bg-background p-3 text-xs text-secondary">
              <p className="font-semibold text-foreground">Query</p>
              <p>{draft.query}</p>
              {filtersSummary.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-2">
                  {filtersSummary.map((chip) => (
                    <span key={chip} className="rounded-full border border-line px-2 py-0.5 text-[11px] text-foreground">
                      {chip}
                    </span>
                  ))}
                </div>
              )}
              <p className="mt-1 text-secondary">Top K: {draft.topK}</p>
            </div>
            {error && <p className="text-sm text-danger">{error}</p>}
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => void handleSave()}
                disabled={isSaving}
                className="rounded-full bg-accent px-4 py-2 font-semibold text-on-accent shadow-sm disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isSaving ? "Saving…" : "Save search"}
              </button>
              <button type="button" onClick={closePanel} className="text-sm text-secondary hover:text-foreground">
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
      {!canCreate && <p className="text-xs text-warning">Limit reached. Remove an entry to add another.</p>}
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
