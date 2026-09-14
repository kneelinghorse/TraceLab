"use client";

import { formatDistanceToNow } from "date-fns";
import { useRouter } from "next/router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { SVGProps } from "react";
import useSWR from "swr";

import { useAuth } from "@/contexts/AuthContext";
import { PageState } from "@/components/ui/PageState";
import { HttpError } from "@/lib/api/http";
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
import { parseApiTimestamp } from "@/lib/api/timestamps";
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

function SparklesIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M12 2l1.8 4.8L18 8.5l-4.2 2.2L12 16l-1.8-5.3L6 8.5l4.2-1.7z" />
      <path d="M5 19l.7 1.6L8 21.4l-1.8.9L5 24l-.8-1.7L2 21.4l2.3-.8z" />
      <path d="M19 14l.9 2.2 2.1.9-2.1.9L19 20l-.9-2.2-2.1-.9 2.1-.9z" />
    </svg>
  );
}

export function SearchPage() {
  const { user } = useAuth();
  return (
    <AuthGate>
      <div className="min-w-0 bg-background">
        <SearchExperience key={user?.user_id ?? "anonymous"} />
      </div>
    </AuthGate>
  );
}

function SearchExperience() {
  const { user } = useAuth();
  const userId = user?.user_id;
  const router = useRouter();
  const lastRouteCommand = useRef<string | null>(null);
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
  const [hasSearched, setHasSearched] = useState(false);
  const [notFound, setNotFound] = useState(false);
  const [resultQuery, setResultQuery] = useState("");
  const [semanticFallback, setSemanticFallback] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const requestVersion = useRef(0);
  const retrySearch = useRef<(() => void) | null>(null);
  useEffect(() => () => { requestVersion.current += 1; }, []);
  const [graphEnabled, setGraphEnabled] = useState(true);

  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const resultsAnchorRef = useRef<HTMLDivElement | null>(null);

  const { data: projectResponse, error: projectError } = useSWR<Project[]>(
    userId ? ["search-projects", userId] : null,
    () => projectsApi.listAllProjects()
  );
  const projects = useMemo(() => projectResponse ?? [], [projectResponse]);
  const { data: documentResponse, error: documentError } = useSWR<PaginatedResponse<Document>>(
    userId ? ["search-documents", userId, filters.projectId || "all"] : null,
    () =>
      documentsApi.listDocuments({
        projectId: filters.projectId || undefined,
        pageSize: 100,
      }),
  );
  const documents = useMemo(() => documentResponse?.data ?? [], [documentResponse]);

  const facets = useSWR(userId ? ["search-facets", userId, filters.projectId] : null,
    () => searchApi.facets({ project_id: filters.projectId || undefined }));
  const { data: historyResponse, error: historyError, mutate: mutateHistory } = useSWR(userId ? ["search-history", userId] : null, () => searchApi.history());
  const historyEntries = historyResponse?.entries ?? [];
  const { data: savedSearchResponse, error: savedSearchError, mutate: mutateSavedSearches } = useSWR(userId ? ["saved-searches", userId] : null, () =>
    savedSearchesApi.list(),
  );
  const savedSearches = savedSearchResponse?.items ?? [];
  const savedSearchLimit = savedSearchResponse?.limit_per_user ?? 50;
  const savedSearchCount = savedSearches.length;
  const [savePreset, setSavePreset] = useState<SaveSearchPreset | null>(null);

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

  const documentTypes = useMemo(() => facets.data?.source_types?.map(type => type.value) ?? [], [facets.data]);

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
    if (pedrResults.length > 0) {
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
  }, [pedrResults, semanticResults]);

  const handleFiltersChange = (update: Partial<SearchFiltersState>) => {
    setFilters((current) => {
      const next = { ...current, ...update };
      if (update.projectId !== undefined && update.projectId !== current.projectId) {
        next.documentType = "";
      }
      return next;
    });
  };

  const beginSearch = useCallback(() => {
    const version = ++requestVersion.current;
    setIsSearching(true);
    setHasSearched(true);
    setSearchError(null);
    setNotFound(false);
    setRagError(null);
    setHighlightedChunkId(null);
    setPedrResults([]);
    setPedrMetadata(null);
    setSemanticResults([]);
    setRagPayload(null);
    setSemanticFallback(false);
    setResultQuery("");
    return version;
  }, []);

  const executeSearch = useCallback(
    async (override?: Partial<SearchFiltersState & { query: string; topK: number }>) => {
      const queryText = (override?.query ?? query).trim();
      const version = beginSearch();
      const current = () => version === requestVersion.current;
      if (!queryText) { setSearchError("Enter a query to run search."); setIsSearching(false); return; }
      const selected = { ...filters, ...override };
      if (selected.startDate && selected.endDate && selected.startDate > selected.endDate) {
        setSearchError("Collected from must not follow Collected until."); setIsSearching(false); return;
      }
      const payload = {
        query: queryText, top_k: override?.topK ?? topK,
        project_id: selected.projectId || undefined, source_type: selected.documentType || undefined,
        date_from: selected.startDate || undefined, date_to: selected.endDate || undefined,
      };
      setResultQuery(queryText);
      retrySearch.current = () => { void executeSearch({ ...selected, query: queryText, topK: payload.top_k }); };
      try {
        try {
          const response = await searchApi.pedrSearch({ ...payload, enable_graph: graphEnabled });
          if (!current()) return;
          setPedrResults(response.results);
          setPedrMetadata(response.metadata);
        } catch {
          if (!current()) return;
          setSemanticFallback(true);
          const response = await searchApi.semanticSearch(payload);
          if (!current()) return;
          setSemanticResults(response.results);
        }
        try {
          const response = await searchApi.ragQuery(payload);
          if (current()) setRagPayload(response);
        } catch {
          if (current()) setRagError("Synthesis is unavailable. The search results are still available above.");
        }
      } catch {
        if (current()) setSearchError("Try this search again when the service is available.");
      } finally {
        if (current()) { setIsSearching(false); void mutateHistory(); }
      }
    },
    [beginSearch, filters, graphEnabled, mutateHistory, query, topK],
  );

  const executeStored = useCallback(async (kind: "saved" | "history", id: string) => {
    const version = beginSearch();
    const current = () => version === requestVersion.current;
    retrySearch.current = () => { void executeStored(kind, id); };
    try {
      const payload = kind === "saved" ? await savedSearchesApi.execute(id) : await searchApi.replay(id);
      if (!current()) return;
      const entry = "saved_search" in payload ? payload.saved_search : payload.entry;
      setQuery(entry.query_text);
      setResultQuery(entry.query_text);
      setTopK(entry.top_k);
      setFilters(normalizeFilters(entry.filters));
      setSemanticResults(payload.semantic.results ?? []);
      setRagPayload(payload.rag);
    } catch (error) {
      if (current()) {
        setNotFound(error instanceof HttpError && error.status === 404);
        setSearchError("This saved or recent search could not be opened.");
      }
    } finally {
      if (current()) { setIsSearching(false); void mutateHistory(); void mutateSavedSearches(); }
    }
  }, [beginSearch, mutateHistory, mutateSavedSearches, normalizeFilters]);

  // A command runs once per URL change, including commands issued while this
  // page is already mounted. Input/filter edits never replay the URL command.
  useEffect(() => {
    if (!router.isReady) return;
    const commands = (["q", "saved", "history"] as const).flatMap(kind => {
      const value = router.query[kind];
      return typeof value === "string" && value.trim() ? [{ kind, value: value.trim() }] : [];
    });
    if (commands.length !== 1) { lastRouteCommand.current = null; return; }
    const command = commands[0];
    const key = `${command.kind}:${command.value}`;
    if (lastRouteCommand.current === key) return;
    lastRouteCommand.current = key;
    if (command.kind === "q") { setQuery(command.value); void executeSearch({ query: command.value }); }
    else void executeStored(command.kind, command.value);
  }, [router.isReady, router.query, executeSearch, executeStored]);

  const clearHistory = async () => {
    setActionError(null);
    try { await searchApi.clearHistory(); await mutateHistory(); }
    catch { setActionError("Unable to clear history. Try again."); }
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
      setActionError(message);
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
    <div className="relative mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-10" ref={resultsAnchorRef}>
      {/* Search bar at top - prominent and full width */}
      <div className="mb-8">
        <div className="mb-4 flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-info-surface text-accent-text">
            <SparklesIcon className="h-5 w-5" />
          </span>
          <div>
            <h1 className="text-2xl font-semibold text-foreground">Search TraceLab</h1>
            <p className="text-sm text-secondary">Semantic search with RAG synthesis</p>
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
          graphEnabled={graphEnabled}
          onGraphEnabledChange={setGraphEnabled}
        />
        {facets.error && <PageState state="error" title="Could not load source filters" onRetry={() => void facets.mutate()} />}
      </div>

      {/* Main content with sidebar */}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
        {/* Main content area */}
        <div className="space-y-6">
          {/* Results section */}
          <section aria-label="Search results" className="min-w-0 space-y-4">
            <div className="panel flex flex-wrap items-center justify-between gap-3 rounded-2xl p-4">
              <div>
                <div className="flex items-center gap-2">
                  <p className="text-xs uppercase tracking-[0.2em] text-secondary">Results</p>
                  {pedrMetadata && (
                    <span className="rounded-full border border-success-line bg-success-surface px-2 py-0.5 text-xs text-success">
                      PEDR
                    </span>
                  )}
                </div>
                <p className="text-lg font-semibold text-foreground">
                  {hasSearched ? `${normalizedResults.length} results` : "Not searched"}
                </p>
              </div>
              {resultQuery && <p className="max-w-full break-words text-sm text-secondary">Results for “{resultQuery}”</p>}
              {isSearching && !searchError && (
                <p className="text-sm text-secondary">Searching…</p>
              )}
            </div>

            {/* PEDR metadata panel */}
            <PEDRMetadataPanel metadata={pedrMetadata} />

            {semanticFallback && !searchError && <p role="status" className="text-sm text-secondary">Showing semantic results while PEDR is unavailable.</p>}
            {searchError ? <PageState state="error" title={notFound ? "Search not found" : "Search unavailable"} onRetry={notFound ? undefined : () => retrySearch.current?.()}>{searchError}</PageState>
              : isSearching && normalizedResults.length === 0 ? <PageState state="loading" title="Searching your research…" />
              : normalizedResults.length === 0 ? <PageState state="empty" title={hasSearched ? "No matching results" : "Start with a question"}>{hasSearched ? "Try different terms or adjust the filters." : "Enter a question or open a saved or recent search."}</PageState> : (
              <div className="grid gap-4">
                {normalizedResults.map((result) => (
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
          {actionError && <PageState state="error" title="Action failed">{actionError}</PageState>}
          <section className="grid min-w-0 gap-6 lg:grid-cols-2">
            <div className="panel rounded-2xl p-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs uppercase tracking-[0.2em] text-secondary">History</p>
                  <h3 className="text-lg font-semibold text-foreground">Recent searches</h3>
                </div>
                {historyEntries.length > 0 && (
                  <button
                    onClick={() => void clearHistory()}
                    className="text-sm text-secondary hover:text-foreground"
                  >
                    Clear
                  </button>
                )}
              </div>
              {historyError ? <PageState state="error" title="Could not load recent searches" onRetry={() => void mutateHistory()} /> : !historyResponse ? <PageState state="loading" title="Loading recent searches…" /> : historyEntries.length === 0 ? (
                <p className="mt-4 text-sm text-secondary">No previous queries.</p>
              ) : (
                <ul className="mt-4 space-y-2">
                  {historyEntries.slice(0, 5).map((entry) => {
                    const entryFilters = extractHistoryFilters(entry);
                    return (
                      <li
                        key={entry.id}
                        className="rounded-xl border border-line bg-surface-alt p-3"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm text-foreground">{entry.query_text}</p>
                            <p className="text-xs text-secondary">
                              {formatDistanceToNow(parseApiTimestamp(entry.created_at), {
                                addSuffix: true,
                              })}
                            </p>
                          </div>
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => void executeStored("history", entry.id)}
                              className="rounded-lg border border-line px-2 py-1 text-xs text-secondary hover:border-info-line"
                            >
                              Run
                            </button>
                            <button
                              onClick={() => handleSaveFromHistory(entry)}
                              className="px-2 py-1 text-xs text-secondary hover:text-foreground"
                            >
                              Save
                            </button>
                          </div>
                        </div>
                        {(entryFilters.projectId || entry.top_k !== 10) && (
                          <div className="mt-1 flex flex-wrap gap-1 text-xs text-secondary">
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

            <div className="panel rounded-2xl p-5">
              <div>
                <p className="text-xs uppercase tracking-[0.2em] text-secondary">Saved</p>
                <h3 className="text-lg font-semibold text-foreground">Quick access</h3>
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
                {savedSearchError ? <PageState state="error" title="Could not load saved searches" onRetry={() => void mutateSavedSearches()} /> : <SavedSearchesList
                  items={savedSearches}
                  limitPerUser={savedSearchLimit}
                  isLoading={!savedSearchResponse}
                  onExecute={(entry) => void executeStored("saved", entry.id)}
                  onLoad={(entry) => handleLoadSavedSearch(entry)}
                  onDelete={(entry) => void handleDeleteSavedSearch(entry)}
                  onSelect={(entry) => handleLoadSavedSearch(entry)}
                />}
              </div>
            </div>
          </section>
        </div>

        {/* Right sidebar - Stats */}
        <aside className="space-y-4 lg:sticky lg:top-8 lg:self-start">
          <div className="panel rounded-2xl p-5">
            <p className="text-xs uppercase tracking-[0.2em] text-secondary">Corpus Stats</p>
            <div className="mt-4 space-y-4">
              <div>
                <p className="text-3xl font-semibold text-foreground">
                  {projectResponse ? projects.length : "—"}
                </p>
                <p className="text-sm text-secondary">Projects</p>
                {projectError && (
                  <p className="text-xs text-danger mt-1">Failed to load</p>
                )}
              </div>
              <div>
                <p className="text-3xl font-semibold text-foreground">
                  {documentResponse?.pagination?.total ?? "—"}
                </p>
                <p className="text-sm text-secondary">Documents</p>
                {documentError && (
                  <p className="text-xs text-danger mt-1">Failed to load</p>
                )}
              </div>
              <div>
                <p className="text-3xl font-semibold text-foreground">{historyResponse ? historyEntries.length : "—"}</p>
                <p className="text-sm text-secondary">Recent searches loaded</p>
              </div>
            </div>
          </div>

          <div className="panel rounded-2xl p-5">
            <p className="text-xs uppercase tracking-[0.2em] text-secondary">Current search</p>
            <div className="mt-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-secondary">Matches</span>
                <span className="text-lg font-semibold text-foreground">{normalizedResults.length}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-secondary">RAG</span>
                <span className={`text-sm font-medium ${ragPayload ? "text-success" : "text-secondary"}`}>
                  {ragPayload ? "Ready" : ragError ? "Unavailable" : isSearching ? "Working" : "Not requested"}
                </span>
              </div>
              {filters.projectId && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-secondary">Filter</span>
                  <span className="text-sm text-accent-text">Project active</span>
                </div>
              )}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
