"use client";

import { formatDistanceToNow } from "date-fns";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { SVGProps } from "react";
import useSWR from "swr";

import { AuthGate } from "@/components/AuthGate";
import { PEDRMetadataPanel } from "@/components/PEDRMetadataPanel";
import { RagSynthesis } from "@/components/RagSynthesis";
import { ResultCard } from "@/components/ResultCard";
import { SaveSearchButton } from "@/components/SaveSearchButton";
import { SavedSearchesList } from "@/components/SavedSearchesList";
import { SearchBar, type SearchFiltersState } from "@/components/SearchBar";
import { documentsApi } from "@/lib/api/documents";
import { projectsApi } from "@/lib/api/projects";
import type { PaginatedResponse } from "@/types/pagination";
import { searchApi } from "@/lib/api/search";
import { savedSearchesApi } from "@/lib/api/savedSearches";
import type { Document, Project } from "@/types/document";
import type {
  PEDRSearchMetadata,
  PEDRSearchResult,
  RagCitation,
  RagResponsePayload,
  SearchHistoryEntryPayload,
  SearchResultChunk,
} from "@/types/search";
import type { SavedSearch, SaveSearchPreset } from "@/types/saved-searches";

type SearchPageProps = {
  initialSection?: "search" | "results";
};

function SparklesIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M12 2l1.8 4.8L18 8.5l-4.2 2.2L12 16l-1.8-5.3L6 8.5l4.2-1.7z" />
      <path d="M5 19l.7 1.6L8 21.4l-1.8.9L5 24l-.8-1.7L2 21.4l2.3-.8z" />
      <path d="M19 14l.9 2.2 2.1.9-2.1.9L19 20l-.9-2.2-2.1-.9 2.1-.9z" />
    </svg>
  );
}

export function SearchPage({ initialSection = "search" }: SearchPageProps) {
  return (
    <AuthGate>
      <div className="relative min-h-screen overflow-hidden bg-[hsl(var(--background))]">
        <div className="pointer-events-none absolute inset-0 opacity-40">
          <div className="h-[40rem] w-[40rem] rounded-full bg-sky-500/40 blur-[180px]" />
          <div className="absolute right-10 top-10 h-72 w-72 rounded-full bg-indigo-500/40 blur-3xl" />
        </div>
        <SearchExperience initialSection={initialSection} />
      </div>
    </AuthGate>
  );
}

function SearchExperience({ initialSection }: SearchPageProps) {
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(10);
  const [filters, setFilters] = useState<SearchFiltersState>({ projectId: "", documentType: "", startDate: "", endDate: "" });
  const [semanticResults, setSemanticResults] = useState<SearchResultChunk[]>([]);
  const [pedrResults, setPedrResults] = useState<PEDRSearchResult[]>([]);
  const [pedrMetadata, setPedrMetadata] = useState<PEDRSearchMetadata | null>(null);
  const [ragPayload, setRagPayload] = useState<RagResponsePayload | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [ragError, setRagError] = useState<string | null>(null);
  const [highlightedChunkId, setHighlightedChunkId] = useState<string | null>(null);
  const [usePedr, setUsePedr] = useState(true); // Default to PEDR for main search

  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const resultsAnchorRef = useRef<HTMLDivElement | null>(null);

  const { data: projectResponse, error: projectError } = useSWR<PaginatedResponse<Project>>(
    ["search-projects"],
    () => projectsApi.listProjects({ pageSize: 100 })
  );
  const projects = projectResponse?.data ?? [];
  const { data: documentResponse, error: documentError } = useSWR<PaginatedResponse<Document>>(
    ["search-documents", filters.projectId || "all"],
    () =>
      documentsApi.listDocuments({
        projectId: filters.projectId || undefined,
        pageSize: 100,
      }),
  );
  const documents = documentResponse?.data ?? [];

  // Debug logging for API errors
  useEffect(() => {
    if (projectError) {
      console.error("[SearchExperience] Failed to load projects:", projectError);
    }
    if (documentError) {
      console.error("[SearchExperience] Failed to load documents:", documentError);
    }
  }, [projectError, documentError]);
  const { data: historyResponse, mutate: mutateHistory } = useSWR(["search-history"], () => searchApi.history());
  const historyEntries = historyResponse?.entries ?? [];
  const { data: savedSearchResponse, mutate: mutateSavedSearches } = useSWR(["saved-searches"], () =>
    savedSearchesApi.list(),
  );
  const savedSearches = savedSearchResponse?.items ?? [];
  const savedSearchLimit = savedSearchResponse?.limit_per_user ?? 50;
  const savedSearchCount = savedSearches.length;
  const [savePreset, setSavePreset] = useState<SaveSearchPreset | null>(null);

  useEffect(() => {
    if (initialSection === "results") {
      const timer = window.setTimeout(() => {
        resultsAnchorRef.current?.scrollIntoView({ behavior: "smooth" });
      }, 250);
      return () => window.clearTimeout(timer);
    }
  }, [initialSection]);

  const documentIndex = useMemo(() => {
    const map = new Map<string, Document>();
    for (const doc of documents) {
      map.set(doc.id, doc);
    }
    return map;
  }, [documents]);

  const projectIndex = useMemo(() => {
    const map = new Map<string, Project>();
    for (const proj of projects) {
      map.set(proj.id, proj);
    }
    return map;
  }, [projects]);

  const documentTypes = useMemo(() => {
    const unique = new Set<string>();
    documents.forEach((doc) => {
      if (doc.source_type) {
        unique.add(doc.source_type);
      }
    });
    return Array.from(unique).sort((a, b) => a.localeCompare(b));
  }, [documents]);

  const normalizeFilters = useCallback((source?: Record<string, unknown>): SearchFiltersState => {
    const payload = source ?? {};
    const pick = (key: string): string => {
      const value = payload[key];
      if (typeof value === "string") {
        return value;
      }
      return "";
    };
    return {
      projectId: pick("project_id"),
      documentType: pick("source_type"),
      startDate: pick("date_from"),
      endDate: pick("date_to"),
    };
  }, []);

  const extractHistoryFilters = useCallback(
    (entry: SearchHistoryEntryPayload): SearchFiltersState => normalizeFilters(entry.filters ?? {}),
    [normalizeFilters],
  );

  const savedSearchFilters = useCallback(
    (entry: SavedSearch | { filters?: Record<string, unknown> }) => normalizeFilters(entry.filters),
    [normalizeFilters],
  );

  // Convert PEDR results to SearchResultChunk format for compatibility
  const normalizedResults: SearchResultChunk[] = useMemo(() => {
    if (usePedr && pedrResults.length > 0) {
      return pedrResults.map((r) => ({
        chunk_id: r.chunk_id,
        content: r.content,
        document_id: r.document_id,
        project_id: r.project_id,
        chunk_index: r.chunk_index,
        source_type: r.source_type,
        score: r.rrf_score,
        // Keep PEDR-specific fields for extended display
        element_type: r.element_type,
        quality_score: r.quality_score,
        contributing_layers: r.contributing_layers,
      })) as SearchResultChunk[];
    }
    return semanticResults;
  }, [usePedr, pedrResults, semanticResults]);

  const filteredResults = useMemo(() => {
    return normalizedResults.filter((result) => {
      const doc = result.document_id ? documentIndex.get(result.document_id) : undefined;

      if (filters.documentType) {
        const type = result.source_type ?? doc?.source_type ?? "";
        if (type !== filters.documentType) {
          return false;
        }
      }

      if (filters.startDate && doc?.uploaded_at) {
        if (new Date(doc.uploaded_at) < new Date(filters.startDate)) {
          return false;
        }
      }

      if (filters.endDate && doc?.uploaded_at) {
        if (new Date(doc.uploaded_at) > new Date(filters.endDate)) {
          return false;
        }
      }

      return true;
    });
  }, [normalizedResults, documentIndex, filters.documentType, filters.startDate, filters.endDate]);

  const handleFiltersChange = (update: Partial<SearchFiltersState>) => {
    setFilters((current) => {
      const next = { ...current, ...update };
      if (update.projectId !== undefined && update.projectId !== current.projectId) {
        next.documentType = "";
      }
      return next;
    });
  };

  const executeSearch = useCallback(
    async (override?: Partial<SearchFiltersState & { query: string; topK: number }>) => {
      const queryText = (override?.query ?? query).trim();
      if (!queryText) {
        setSearchError("Enter a query to run search.");
        return;
      }

      const projectId = override?.projectId ?? filters.projectId;
      const documentType = override?.documentType ?? filters.documentType;
      const limit = override?.topK ?? topK;

      setIsSearching(true);
      setSearchError(null);
      setRagError(null);
      setHighlightedChunkId(null);

      // Try PEDR first, fall back to semantic search if it fails
      if (usePedr) {
        try {
          const pedrResponse = await searchApi.pedrSearch({
            query: queryText,
            top_k: limit,
            project_id: projectId || undefined,
            source_type: documentType || undefined,
          });

          setPedrResults(pedrResponse.results);
          setPedrMetadata(pedrResponse.metadata);
          setSemanticResults([]); // Clear semantic results when using PEDR

          // Still run RAG query with PEDR results as context
          try {
            const ragResponse = await searchApi.ragQuery({
              query: queryText,
              top_k: limit,
              project_id: projectId || undefined,
              source_type: documentType || undefined,
            });
            setRagPayload(ragResponse);
          } catch (ragErr) {
            const reason = ragErr instanceof Error ? ragErr.message : "RAG query failed.";
            setRagError(reason);
            setRagPayload(null);
          }

          void mutateHistory();
          setIsSearching(false);
          return;
        } catch (pedrError) {
          // PEDR failed, fall back to semantic search
          console.warn("PEDR search failed, falling back to semantic:", pedrError);
          setPedrResults([]);
          setPedrMetadata(null);
        }
      }

      // Fallback to semantic search
      const payload = {
        query: queryText,
        top_k: limit,
        project_id: projectId || undefined,
        source_type: documentType || undefined,
      };

      try {
        const [semantic, rag] = await Promise.allSettled([
          searchApi.semanticSearch(payload),
          searchApi.ragQuery(payload),
        ]);

        if (semantic.status === "fulfilled") {
          setSemanticResults(semantic.value.results ?? []);
        } else {
          const reason = semantic.reason instanceof Error ? semantic.reason.message : "Semantic search failed.";
          setSearchError(reason);
          setSemanticResults([]);
        }

        if (rag.status === "fulfilled") {
          setRagPayload(rag.value);
        } else {
          const reason = rag.reason instanceof Error ? rag.reason.message : "RAG query failed.";
          setRagError(reason);
          setRagPayload(null);
        }

        void mutateHistory();
      } finally {
        setIsSearching(false);
      }
    },
    [filters.documentType, filters.projectId, mutateHistory, query, topK, usePedr],
  );

  const handleHistoryRun = async (entry: SearchHistoryEntryPayload) => {
    const nextFilters = extractHistoryFilters(entry);
    setQuery(entry.query_text);
    setTopK(entry.top_k);
    setFilters(nextFilters);
    setIsSearching(true);
    setSearchError(null);
    setRagError(null);
    setHighlightedChunkId(null);

    try {
      const payload = await searchApi.replay(entry.id);
      setSemanticResults(payload.semantic.results ?? []);
      setRagPayload(payload.rag);
      setRagError(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Replay failed.";
      setSearchError(message);
      setSemanticResults([]);
      setRagPayload(null);
    } finally {
      setIsSearching(false);
      void mutateHistory();
    }
  };

  const clearHistory = async () => {
    try {
      await searchApi.clearHistory();
      await mutateHistory();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to clear history.";
      setSearchError(message);
    }
  };

  const handleSavedSearchExecute = async (entry: SavedSearch) => {
    setIsSearching(true);
    setSearchError(null);
    setRagError(null);
    setHighlightedChunkId(null);
    try {
      const payload = await savedSearchesApi.execute(entry.id);
      setQuery(payload.saved_search.query_text);
      setTopK(payload.saved_search.top_k);
      setFilters(savedSearchFilters(payload.saved_search));
      setSemanticResults(payload.semantic.results ?? []);
      setRagPayload(payload.rag);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Saved search execution failed.";
      setSearchError(message);
      setSemanticResults([]);
      setRagPayload(null);
    } finally {
      setIsSearching(false);
      void mutateHistory();
      void mutateSavedSearches();
    }
  };

  const handleLoadSavedSearch = (entry: SavedSearch) => {
    setQuery(entry.query_text);
    setTopK(entry.top_k);
    setFilters(savedSearchFilters(entry));
  };

  const handleDeleteSavedSearch = async (entry: SavedSearch) => {
    try {
      await savedSearchesApi.remove(entry.id);
      await mutateSavedSearches();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to delete saved search.";
      setSearchError(message);
    }
  };

  const handleSaveFromHistory = (entry: SearchHistoryEntryPayload) => {
    const historyFilters = extractHistoryFilters(entry);
    setSavePreset({
      query: entry.query_text,
      filters: historyFilters,
      topK: entry.top_k,
      suggestedName: entry.query_text.slice(0, 80),
    });
  };

  const registerCardRef = (chunkId: string | null | undefined) => (element: HTMLDivElement | null) => {
    if (!chunkId) return;
    if (element) {
      cardRefs.current[chunkId] = element;
    } else {
      delete cardRefs.current[chunkId];
    }
  };

  const handleCitationClick = (citation: RagCitation) => {
    if (!citation.chunk_id) return;
    setHighlightedChunkId(citation.chunk_id);
    const target = cardRefs.current[citation.chunk_id];
    target?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  return (
    <main className="relative mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-10" ref={resultsAnchorRef}>
      {/* Search bar at top - prominent and full width */}
      <div className="mb-8">
        <div className="mb-4 flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-sky-500/20 text-sky-200">
            <SparklesIcon className="h-5 w-5" />
          </span>
          <div>
            <h1 className="text-2xl font-semibold text-white">Search TraceLab</h1>
            <p className="text-sm text-slate-400">Semantic search with RAG synthesis</p>
          </div>
        </div>
        <SearchBar
          query={query}
          onQueryChange={setQuery}
          filters={filters}
          onFiltersChange={handleFiltersChange}
          onSubmit={() => executeSearch()}
          isSearching={isSearching}
          projects={projects}
          documentTypes={documentTypes}
          topK={topK}
          onTopKChange={setTopK}
        />
      </div>

      {/* Main content with sidebar */}
      <div className="grid gap-6 lg:grid-cols-[1fr,280px]">
        {/* Main content area */}
        <div className="space-y-6">
          {/* Results section */}
          <section className="space-y-4">
            <div className="glass-card flex flex-wrap items-center justify-between gap-3 rounded-2xl p-4">
              <div>
                <div className="flex items-center gap-2">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Results</p>
                  {pedrMetadata && (
                    <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-xs text-emerald-300">
                      PEDR
                    </span>
                  )}
                </div>
                <p className="text-lg font-semibold text-white">
                  {filteredResults.length} chunk{filteredResults.length === 1 ? "" : "s"}
                </p>
              </div>
              {searchError && <p className="text-sm text-rose-300">{searchError}</p>}
              {isSearching && !searchError && (
                <p className="text-sm text-slate-400">Searching…</p>
              )}
            </div>

            {/* PEDR metadata panel */}
            <PEDRMetadataPanel metadata={pedrMetadata} />

            {filteredResults.length === 0 && !isSearching ? (
              <div className="glass-card rounded-2xl p-8 text-slate-300">
                <div className="text-center">
                  <p className="text-lg font-semibold text-white">No results yet</p>
                  <p className="mt-2 text-sm text-slate-400">
                    Enter a query and search to find relevant content.
                  </p>
                </div>
                {!query && historyEntries.length > 0 && (
                  <div className="mt-6 border-t border-white/10 pt-6">
                    <p className="text-sm font-medium text-slate-400 mb-3">Recent searches</p>
                    <div className="flex flex-wrap gap-2">
                      {historyEntries.slice(0, 5).map((entry) => (
                        <button
                          key={entry.id}
                          onClick={() => void handleHistoryRun(entry)}
                          className="group flex items-center gap-2 rounded-full border border-white/15 bg-black/20 px-3 py-1.5 text-sm text-slate-200 hover:border-sky-400 hover:bg-sky-500/10 transition-colors"
                        >
                          <span className="truncate max-w-[200px]">{entry.query_text}</span>
                          <span className="text-xs text-slate-500 group-hover:text-sky-400">
                            {entry.result_count} results
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="grid gap-4">
                {filteredResults.map((result) => (
                  <ResultCard
                    key={result.chunk_id}
                    ref={registerCardRef(result.chunk_id)}
                    result={result}
                    document={result.document_id ? documentIndex.get(result.document_id) : undefined}
                    project={result.project_id ? projectIndex.get(result.project_id) : undefined}
                    isHighlighted={highlightedChunkId === result.chunk_id}
                  />
                ))}
              </div>
            )}
          </section>

          {/* RAG Synthesis */}
          <RagSynthesis
            payload={ragPayload}
            isLoading={isSearching && !ragPayload}
            error={ragError}
            onCitationClick={handleCitationClick}
          />

          {/* History and Saved Searches */}
          <section className="grid gap-6 lg:grid-cols-2">
            <div className="glass-card rounded-2xl p-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-400">History</p>
                  <h3 className="text-lg font-semibold text-white">Recent searches</h3>
                </div>
                {historyEntries.length > 0 && (
                  <button
                    onClick={() => void clearHistory()}
                    className="text-sm text-slate-400 hover:text-white"
                  >
                    Clear
                  </button>
                )}
              </div>
              {historyEntries.length === 0 ? (
                <p className="mt-4 text-sm text-slate-400">No previous queries.</p>
              ) : (
                <ul className="mt-4 space-y-2">
                  {historyEntries.slice(0, 5).map((entry) => {
                    const entryFilters = extractHistoryFilters(entry);
                    return (
                      <li
                        key={entry.id}
                        className="rounded-xl border border-white/10 bg-black/20 p-3"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm text-white">{entry.query_text}</p>
                            <p className="text-xs text-slate-400">
                              {formatDistanceToNow(new Date(entry.created_at), {
                                addSuffix: true,
                              })}
                            </p>
                          </div>
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => void handleHistoryRun(entry)}
                              className="rounded-lg border border-white/20 px-2 py-1 text-xs text-slate-200 hover:border-sky-300"
                            >
                              Run
                            </button>
                            <button
                              onClick={() => handleSaveFromHistory(entry)}
                              className="px-2 py-1 text-xs text-slate-400 hover:text-white"
                            >
                              Save
                            </button>
                          </div>
                        </div>
                        {(entryFilters.projectId || entry.top_k !== 10) && (
                          <div className="mt-1 flex flex-wrap gap-1 text-xs text-slate-500">
                            {entryFilters.projectId && (
                              <span>Project: {projectIndex.get(entryFilters.projectId)?.name ?? entryFilters.projectId}</span>
                            )}
                            <span>Chunks: {entry.top_k}</span>
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>

            <div className="glass-card rounded-2xl p-5">
              <div>
                <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Saved</p>
                <h3 className="text-lg font-semibold text-white">Quick access</h3>
              </div>
              <div className="mt-4">
                <SaveSearchButton
                  currentQuery={query}
                  filters={filters}
                  topK={topK}
                  savedSearchCount={savedSearchCount}
                  limitPerUser={savedSearchLimit}
                  preset={savePreset}
                  onPresetConsumed={() => setSavePreset(null)}
                  onSaved={() => {
                    void mutateSavedSearches();
                  }}
                />
              </div>
              <div className="mt-4">
                <SavedSearchesList
                  items={savedSearches}
                  limitPerUser={savedSearchLimit}
                  isLoading={!savedSearchResponse}
                  onExecute={(entry) => void handleSavedSearchExecute(entry)}
                  onLoad={(entry) => handleLoadSavedSearch(entry)}
                  onDelete={(entry) => void handleDeleteSavedSearch(entry)}
                  onSelect={(entry) => handleLoadSavedSearch(entry)}
                />
              </div>
            </div>
          </section>
        </div>

        {/* Right sidebar - Stats */}
        <aside className="space-y-4 lg:sticky lg:top-8 lg:self-start">
          <div className="glass-card rounded-2xl p-5">
            <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Corpus Stats</p>
            <div className="mt-4 space-y-4">
              <div>
                <p className="text-3xl font-semibold text-white">
                  {projectResponse?.pagination?.total ?? projects.length}
                </p>
                <p className="text-sm text-slate-400">Projects</p>
                {projectError && (
                  <p className="text-xs text-rose-400 mt-1">Failed to load</p>
                )}
              </div>
              <div>
                <p className="text-3xl font-semibold text-white">
                  {documentResponse?.pagination?.total ?? documents.length}
                </p>
                <p className="text-sm text-slate-400">Documents</p>
                {documentError && (
                  <p className="text-xs text-rose-400 mt-1">Failed to load</p>
                )}
              </div>
              <div>
                <p className="text-3xl font-semibold text-white">{historyEntries.length}</p>
                <p className="text-sm text-slate-400">Queries this session</p>
              </div>
            </div>
          </div>

          <div className="glass-card rounded-2xl p-5">
            <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Session Status</p>
            <div className="mt-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-400">Matches</span>
                <span className="text-lg font-semibold text-white">{filteredResults.length}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-400">RAG</span>
                <span className={`text-sm font-medium ${ragPayload ? "text-emerald-400" : "text-slate-500"}`}>
                  {ragPayload ? "Ready" : "Pending"}
                </span>
              </div>
              {filters.projectId && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-400">Filter</span>
                  <span className="text-sm text-sky-400">Project active</span>
                </div>
              )}
            </div>
          </div>
        </aside>
      </div>
    </main>
  );
}
