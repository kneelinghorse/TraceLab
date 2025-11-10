"use client";

import { formatDistanceToNow } from "date-fns";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { SVGProps } from "react";
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

  const handleQuickAddEvidence = async (missionId: string, chunk: SearchResultChunk, note?: string) => {
    const mission = missions.find((item) => item.id === missionId);
    if (!mission) {
      throw new Error("Mission not found.");
    }

    const doc = chunk.document_id ? documentIndex.get(chunk.document_id) : undefined;
    const evidenceId = chunk.chunk_id ? `EV-${chunk.chunk_id}` : `EV-${Date.now()}`;
    const baseSummary = chunk.content.length > 280 ? `${chunk.content.slice(0, 277)}…` : chunk.content;
    const trimmedNote = note?.trim();
    const summary = trimmedNote ? `${baseSummary}\n\nResearcher note: ${trimmedNote}` : baseSummary;
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

  const filterChips = [
    filters.projectId && { label: "Project", value: filters.projectId },
    filters.documentType && { label: "Type", value: filters.documentType },
    filters.startDate && { label: "From", value: filters.startDate },
    filters.endDate && { label: "To", value: filters.endDate },
  ].filter(Boolean) as { label: string; value: string }[];

  const searchStats = [
    { label: "Projects", value: projects.length },
    { label: "Documents", value: documents.length },
    { label: "Queries this session", value: history.length },
  ];

  return (
    <main className="relative mx-auto max-w-7xl space-y-10 px-4 py-12 sm:px-6 lg:px-10" ref={resultsAnchorRef}>
      <header className="grid gap-6 lg:grid-cols-[2fr,1fr]">
        <div className="glass-card grid gap-6 rounded-3xl p-8 text-white">
          <div className="flex items-center gap-3 text-slate-200">
            <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-sky-500/20 text-sky-200">
              <SparklesIcon className="h-5 w-5" />
            </span>
            <div>
              <p className="text-xs uppercase tracking-[0.4em] text-slate-400">RAG control room</p>
              <p className="text-lg font-semibold text-white">Blend semantic search with evidence-ready answers</p>
            </div>
          </div>
          <div className="space-y-3">
            <h1 className="text-4xl font-semibold">Search TraceLab intelligence in one pass</h1>
            <p className="text-lg text-slate-300">
              Narrow the retrieval corpus with projects, document types, or time windows, then capture synthesized answers with
              traceable citations.
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            {searchStats.map((stat) => (
              <div key={stat.label} className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                <p className="text-xs uppercase tracking-[0.3em] text-slate-400">{stat.label}</p>
                <p className="text-2xl font-semibold text-white">{stat.value}</p>
              </div>
            ))}
          </div>
        </div>
        <div className="glass-card rounded-3xl p-6">
          <p className="text-xs uppercase tracking-[0.4em] text-slate-400">Session health</p>
          <div className="mt-4 space-y-4">
            <div className="flex items-baseline justify-between">
              <p className="text-4xl font-semibold text-white">{filteredResults.length.toString().padStart(2, "0")}</p>
              <p className="text-sm text-slate-400">semantic matches</p>
            </div>
            <div className="flex items-baseline justify-between">
              <p className="text-3xl font-semibold text-emerald-300">{ragPayload ? "Ready" : "Pending"}</p>
              <p className="text-sm text-slate-400">RAG synthesis</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-slate-900/40 p-4 text-sm text-slate-300">
              <p className="font-semibold text-white">Workflow</p>
              <p>1. Craft filters • 2. Inspect ranked chunks • 3. Log evidence / citations.</p>
            </div>
          </div>
        </div>
      </header>

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

      <section className="glass-card rounded-3xl p-6">
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Active filters</p>
          {filterChips.length === 0 && <span className="text-sm text-slate-500">Corpus wide</span>}
          <div className="flex flex-wrap gap-2">
            {filterChips.map((chip) => (
              <span key={`${chip.label}-${chip.value}`} className="rounded-full border border-white/15 bg-white/10 px-3 py-1 text-xs text-white/90">
                <strong className="mr-1 text-slate-400">{chip.label}:</strong> {chip.value}
              </span>
            ))}
          </div>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[7fr,5fr]">
        <section className="space-y-4">
          <div className="glass-card flex flex-wrap items-center justify-between gap-3 rounded-3xl p-5">
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Semantic results</p>
              <p className="text-xl font-semibold text-white">{filteredResults.length} supporting chunk{filteredResults.length === 1 ? "" : "s"}</p>
            </div>
            {searchError && <p className="text-sm text-rose-300">{searchError}</p>}
            {isSearching && !searchError && <p className="text-sm text-slate-400">Refreshing context…</p>}
          </div>

          {filteredResults.length === 0 && !isSearching ? (
            <div className="glass-card rounded-3xl p-8 text-center text-slate-300">
              <p className="text-lg font-semibold text-white">No semantic matches yet</p>
              <p className="mt-2 text-sm text-slate-400">Adjust filters or run a new query to populate this panel.</p>
            </div>
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

      <section className="grid gap-6 lg:grid-cols-2">
        <div className="glass-card rounded-3xl p-6">
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
            <p className="mt-4 text-sm text-slate-400">No previous queries stored.</p>
          ) : (
            <ul className="mt-4 space-y-3">
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
        </div>

        <div className="glass-card rounded-3xl p-6">
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Workflow tips</p>
          <ol className="mt-4 space-y-3 text-sm text-slate-300">
            <li className="rounded-2xl border border-white/10 bg-black/20 p-4">
              <strong className="text-white">Evidence-first:</strong> Promote the highest scoring chunk into a mission with Quick Add before editing summaries.
            </li>
            <li className="rounded-2xl border border-white/10 bg-black/20 p-4">
              <strong className="text-white">Compare wording:</strong> Click a citation to jump back to its chunk, validating tone + context alignment.
            </li>
            <li className="rounded-2xl border border-white/10 bg-black/20 p-4">
              <strong className="text-white">Session hygiene:</strong> Keep query history small; archive validated prompts into Mission Protocol notes.
            </li>
          </ol>
        </div>
      </section>
    </main>
  );
}
