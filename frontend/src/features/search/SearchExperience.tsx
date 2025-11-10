import { formatDistanceToNow } from "date-fns";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";

import { AuthGate } from "@/components/AuthGate";
import { RagSynthesis } from "@/components/RagSynthesis";
import { ResultCard } from "@/components/ResultCard";
import { SearchBar, type SearchFiltersState } from "@/components/SearchBar";
import { documentsApi } from "@/lib/api/documents";
import { searchApi } from "@/lib/api/search";
import { updateMission } from "@/lib/api/missions";
import { useMissionList } from "@/lib/hooks/useMissions";
import type { Document, Project } from "@/types/document";
import type { Mission } from "@/types/mission";
import type { RagCitation, RagResponsePayload, SearchResultChunk } from "@/types/search";

const HISTORY_KEY = "tracelab.search.history";

type SearchHistoryEntry = SearchFiltersState & {
  id: string;
  query: string;
  timestamp: string;
  topK: number;
};

type SearchPageProps = {
  initialSection?: "search" | "results";
};

export function SearchPage({ initialSection = "search" }: SearchPageProps) {
  return (
    <AuthGate>
      <SearchExperience initialSection={initialSection} />
    </AuthGate>
  );
}

function SearchExperience({ initialSection }: SearchPageProps) {
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(6);
  const [filters, setFilters] = useState<SearchFiltersState>({ projectId: "", documentType: "", startDate: "", endDate: "" });
  const [semanticResults, setSemanticResults] = useState<SearchResultChunk[]>([]);
  const [ragPayload, setRagPayload] = useState<RagResponsePayload | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [ragError, setRagError] = useState<string | null>(null);
  const [history, setHistory] = useState<SearchHistoryEntry[]>([]);
  const [highlightedChunkId, setHighlightedChunkId] = useState<string | null>(null);

  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const resultsAnchorRef = useRef<HTMLDivElement | null>(null);

  const { missions, refresh: refreshMissions } = useMissionList();
  const { data: projects = [] } = useSWR<Project[]>("search-projects", () => documentsApi.listProjects());
  const { data: documents = [] } = useSWR<Document[]>(
    ["search-documents", filters.projectId || "all"],
    () => documentsApi.listDocuments(filters.projectId || undefined),
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const stored = window.localStorage.getItem(HISTORY_KEY);
      if (stored) {
        const parsed: SearchHistoryEntry[] = JSON.parse(stored);
        setHistory(parsed);
      }
    } catch {
      // ignore history parse issues
    }
  }, []);

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

  const documentTypes = useMemo(() => {
    const unique = new Set<string>();
    documents.forEach((doc) => {
      if (doc.source_type) {
        unique.add(doc.source_type);
      }
    });
    return Array.from(unique).sort((a, b) => a.localeCompare(b));
  }, [documents]);

  const filteredResults = useMemo(() => {
    return semanticResults.filter((result) => {
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
  }, [semanticResults, documentIndex, filters.documentType, filters.startDate, filters.endDate]);

  const persistHistoryEntry = useCallback((entry: Omit<SearchHistoryEntry, "id">) => {
    setHistory((previous) => {
      const identifier = typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
      const resolved = { ...entry, id: identifier } satisfies SearchHistoryEntry;
      const filtered = previous.filter((item) => !(item.query === entry.query && item.projectId === entry.projectId && item.documentType === entry.documentType && item.startDate === entry.startDate && item.endDate === entry.endDate));
      const next = [resolved, ...filtered].slice(0, 10);
      if (typeof window !== "undefined") {
        window.localStorage.setItem(HISTORY_KEY, JSON.stringify(next));
      }
      return next;
    });
  }, []);

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
    async (override?: Partial<SearchHistoryEntry>) => {
      const queryText = (override?.query ?? query).trim();
      if (!queryText) {
        setSearchError("Enter a query to run search.");
        return;
      }

      const projectId = override?.projectId ?? filters.projectId;
      const documentType = override?.documentType ?? filters.documentType;
      const fromDate = override?.startDate ?? filters.startDate;
      const toDate = override?.endDate ?? filters.endDate;
      const limit = override?.topK ?? topK;

      setIsSearching(true);
      setSearchError(null);
      setRagError(null);
      setHighlightedChunkId(null);

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

        persistHistoryEntry({
          query: queryText,
          projectId,
          documentType,
          startDate: fromDate,
          endDate: toDate,
          timestamp: new Date().toISOString(),
          topK: limit,
        });
      } finally {
        setIsSearching(false);
      }
    },
    [filters.documentType, filters.endDate, filters.projectId, filters.startDate, persistHistoryEntry, query, topK],
  );

  const handleHistoryRun = (entry: SearchHistoryEntry) => {
    setQuery(entry.query);
    setTopK(entry.topK);
    setFilters({
      projectId: entry.projectId,
      documentType: entry.documentType,
      startDate: entry.startDate,
      endDate: entry.endDate,
    });
    executeSearch(entry);
  };

  const clearHistory = () => {
    setHistory([]);
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(HISTORY_KEY);
    }
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

  const handleQuickAddEvidence = async (missionId: string, chunk: SearchResultChunk) => {
    const mission = missions.find((item) => item.id === missionId);
    if (!mission) {
      throw new Error("Mission not found.");
    }

    const doc = chunk.document_id ? documentIndex.get(chunk.document_id) : undefined;
    const evidenceId = chunk.chunk_id ? `EV-${chunk.chunk_id}` : `EV-${Date.now()}`;
    const summary = chunk.content.length > 280 ? `${chunk.content.slice(0, 277)}…` : chunk.content;
    const evidence = {
      evidence_id: evidenceId,
      source: doc?.name ?? "Semantic Search Result",
      summary: summary || "Semantic search chunk",
      chunk_id: chunk.chunk_id ?? "",
      insight_id: undefined,
      source_type: chunk.source_type ?? doc?.source_type ?? "semantic-search",
      relevance_score: Number(chunk.score.toFixed(4)),
      tags: ["search-ui"],
    } satisfies Mission["mission_data"]["evidence"][number];

    const nextEvidence = [...(mission.mission_data.evidence ?? []), evidence];
    await updateMission(mission.id, {
      mission_data: {
        ...mission.mission_data,
        evidence: nextEvidence,
      },
    });
    refreshMissions();
  };

  return (
    <main className="px-6 py-10 md:px-10 space-y-10">
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

      <section className="space-y-3">
        <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Active filters</p>
        <div className="flex flex-wrap gap-2 text-xs">
          {filters.projectId && <span className="rounded-full bg-white/10 px-3 py-1 text-slate-200">Project {filters.projectId}</span>}
          {filters.documentType && <span className="rounded-full bg-white/10 px-3 py-1 text-slate-200">Type {filters.documentType}</span>}
          {filters.startDate && <span className="rounded-full bg-white/10 px-3 py-1 text-slate-200">From {filters.startDate}</span>}
          {filters.endDate && <span className="rounded-full bg-white/10 px-3 py-1 text-slate-200">To {filters.endDate}</span>}
          {!filters.projectId && !filters.documentType && !filters.startDate && !filters.endDate && (
            <span className="text-slate-500">No additional filters applied.</span>
          )}
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-[2fr,1fr]" ref={resultsAnchorRef}>
        <section className="space-y-4">
          <div className="glass-card flex items-center justify-between rounded-2xl p-4">
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Semantic results</p>
              <p className="text-xl font-semibold text-white">{filteredResults.length} chunk(s)</p>
            </div>
            {searchError && <p className="text-sm text-rose-300">{searchError}</p>}
          </div>

          {filteredResults.length === 0 && !isSearching ? (
            <p className="rounded-2xl border border-dashed border-white/20 p-6 text-sm text-slate-300">
              {searchError ? "Search failed. Adjust filters or retry." : "Run a query to see retrieval results."}
            </p>
          ) : (
            <div className="grid gap-4">
              {filteredResults.map((result) => (
                <ResultCard
                  key={result.chunk_id}
                  ref={registerCardRef(result.chunk_id)}
                  result={result}
                  document={result.document_id ? documentIndex.get(result.document_id) : undefined}
                  missions={missions}
                  onQuickAddEvidence={handleQuickAddEvidence}
                  isHighlighted={highlightedChunkId === result.chunk_id}
                />
              ))}
            </div>
          )}
        </section>

        <RagSynthesis payload={ragPayload} isLoading={isSearching && !ragPayload} error={ragError} onCitationClick={handleCitationClick} />
      </div>

      <section className="glass-card p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Query history</p>
            <h3 className="text-2xl font-semibold text-white">Local session</h3>
          </div>
          {history.length > 0 && (
            <button onClick={clearHistory} className="text-sm text-slate-300 hover:text-white">
              Clear history
            </button>
          )}
        </div>
        {history.length === 0 ? (
          <p className="text-sm text-slate-400">No previous queries stored.</p>
        ) : (
          <ul className="space-y-3">
            {history.map((entry) => (
              <li key={entry.id} className="rounded-2xl border border-white/10 bg-black/20 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-sm text-white">{entry.query}</p>
                    <p className="text-xs text-slate-400">
                      {formatDistanceToNow(new Date(entry.timestamp), { addSuffix: true })}
                    </p>
                  </div>
                  <button
                    onClick={() => handleHistoryRun(entry)}
                    className="rounded-full border border-white/20 px-3 py-1 text-xs text-slate-200 hover:border-sky-300"
                  >
                    Run again
                  </button>
                </div>
                <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-400">
                  {entry.projectId && <span>Project {entry.projectId}</span>}
                  {entry.documentType && <span>Type {entry.documentType}</span>}
                  {entry.startDate && <span>From {entry.startDate}</span>}
                  {entry.endDate && <span>To {entry.endDate}</span>}
                  <span>Top K {entry.topK}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
