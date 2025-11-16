import { useState } from "react";
import type { FormEvent } from "react";
import useSWR from "swr";

import { AuthGate } from "@/components/AuthGate";
import { SavedSearchesList } from "@/components/SavedSearchesList";
import { savedSearchesApi } from "@/lib/api/savedSearches";
import type { SavedSearch } from "@/types/saved-searches";

export default function SavedSearchesPage() {
  return (
    <AuthGate>
      <SavedSearchesManager />
    </AuthGate>
  );
}

function SavedSearchesManager() {
  const { data, mutate } = useSWR(["saved-searches"], () => savedSearchesApi.list());
  const savedSearches = data?.items ?? [];
  const limit = data?.limit_per_user ?? 50;

  const [selected, setSelected] = useState<SavedSearch | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [topK, setTopK] = useState(5);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const handleSelect = (entry: SavedSearch) => {
    setSelected(entry);
    setName(entry.name);
    setDescription(entry.description ?? "");
    setTopK(entry.top_k);
    setMessage(null);
    setError(null);
  };

  const handleExecute = async (entry: SavedSearch) => {
    setMessage(null);
    setError(null);
    try {
      await savedSearchesApi.execute(entry.id);
      setMessage(`Executed "${entry.name}". View results on the main search page.`);
    } catch (err) {
      const detail = err instanceof Error ? err.message : "Unable to execute saved search.";
      setError(detail);
    } finally {
      void mutate();
    }
  };

  const handleDelete = async (entry: SavedSearch) => {
    setMessage(null);
    setError(null);
    try {
      await savedSearchesApi.remove(entry.id);
      if (selected?.id === entry.id) {
        setSelected(null);
      }
      void mutate();
    } catch (err) {
      const detail = err instanceof Error ? err.message : "Unable to delete saved search.";
      setError(detail);
    }
  };

  const handleUpdate = async (event: FormEvent) => {
    event.preventDefault();
    if (!selected) {
      setError("Select a saved search to edit.");
      return;
    }
    setIsSaving(true);
    setError(null);
    setMessage(null);
    try {
      await savedSearchesApi.update(selected.id, {
        name: name.trim(),
        description: description.trim() || undefined,
        top_k: topK,
      });
      setMessage(`Updated "${name.trim() || selected.name}".`);
      void mutate();
    } catch (err) {
      const detail = err instanceof Error ? err.message : "Unable to update saved search.";
      setError(detail);
    } finally {
      setIsSaving(false);
    }
  };

  const clearSelection = () => {
    setSelected(null);
    setName("");
    setDescription("");
    setTopK(5);
  };

  return (
    <div className="min-h-screen bg-[hsl(var(--background))]">
      <main className="mx-auto max-w-5xl space-y-8 px-4 py-12 sm:px-6 lg:px-8">
        <header className="glass-card rounded-3xl p-8 text-white">
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Saved searches</p>
          <h1 className="mt-2 text-3xl font-semibold">Organize high-signal queries</h1>
          <p className="mt-3 text-slate-300">
            Bookmark the prompts you trust, edit their metadata, and prune the list when you hit the {limit} search limit.
          </p>
        </header>

        <section className="glass-card rounded-3xl p-6">
          <div className="flex items-center justify-between">
            <h2 className="text-2xl font-semibold text-white">Your saved searches</h2>
            <span className="text-sm text-slate-400">
              {savedSearches.length}/{limit} used
            </span>
          </div>
          <div className="mt-4">
            <SavedSearchesList
              items={savedSearches}
              limitPerUser={limit}
              isLoading={!data}
              onExecute={(entry) => void handleExecute(entry)}
              onDelete={(entry) => void handleDelete(entry)}
              onSelect={(entry) => handleSelect(entry)}
            />
          </div>
        </section>

        <section className="glass-card rounded-3xl p-6 text-white">
          <h2 className="text-2xl font-semibold">Edit metadata</h2>
          <p className="mt-2 text-sm text-slate-300">Select an entry above to rename it, tweak the description, or adjust Top K.</p>
          <form onSubmit={handleUpdate} className="mt-4 space-y-4">
            <div>
              <label className="text-xs uppercase tracking-[0.3em] text-slate-400" htmlFor="saved-name">
                Name
              </label>
              <input
                id="saved-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                className="mt-1 w-full rounded-2xl border border-white/15 bg-white/5 px-4 py-3 text-white focus:outline-none focus:ring-2 focus:ring-sky-400/60"
                placeholder="Daily checkout briefing"
              />
            </div>
            <div>
              <label className="text-xs uppercase tracking-[0.3em] text-slate-400" htmlFor="saved-description">
                Description
              </label>
              <textarea
                id="saved-description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                className="mt-1 w-full rounded-2xl border border-white/15 bg-white/5 px-4 py-3 text-white focus:outline-none focus:ring-2 focus:ring-sky-400/60"
                placeholder="Summarize incidents for the go-to-market team."
              />
            </div>
            <div>
              <label className="text-xs uppercase tracking-[0.3em] text-slate-400" htmlFor="saved-topk">
                Top K
              </label>
              <input
                id="saved-topk"
                type="number"
                min={1}
                max={50}
                value={topK}
                onChange={(event) => setTopK(Number(event.target.value))}
                className="mt-1 w-32 rounded-2xl border border-white/15 bg-white/5 px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-sky-400/60"
              />
            </div>
            {error && <p className="text-sm text-rose-300">{error}</p>}
            {message && <p className="text-sm text-emerald-300">{message}</p>}
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="submit"
                disabled={!selected || isSaving}
                className="rounded-full bg-gradient-to-r from-sky-500 to-indigo-500 px-6 py-2 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isSaving ? "Saving…" : "Save changes"}
              </button>
              <button type="button" onClick={clearSelection} className="text-sm text-slate-400 hover:text-white">
                Clear selection
              </button>
            </div>
          </form>
        </section>
      </main>
    </div>
  );
}
