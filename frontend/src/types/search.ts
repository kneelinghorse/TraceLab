/**
 * Types supporting the semantic search + RAG experience.
 */

export interface SearchResultChunk {
  chunk_id: string;
  content: string;
  document_id?: string;
  project_id?: string;
  chunk_index?: number;
  source_type?: string;
  score: number;
}

export interface SemanticSearchResponse {
  results: SearchResultChunk[];
}

export interface RagCitation {
  document_id?: string;
  chunk_id?: string;
  chunk_index?: number;
  source_type?: string;
  score?: number;
  snippet?: string;
}

export interface CompressionStats {
  original_chunks: number;
  filtered_chunks: number;
  original_tokens: number;
  filtered_tokens: number;
  reduction_ratio: number;
  threshold: number;
  compression_ms: number;
}

export interface CacheInfo {
  hit: boolean;
  score?: number | null;
  age_seconds?: number | null;
  ttl_seconds?: number | null;
}

export interface PillarScores {
  linguistic_uncertainty: number;
  answer_integrity: number;
  source_provenance: number;
}

export interface QualityReport {
  composite_score: number;
  threshold: number;
  pillar_scores: PillarScores;
  hard_failures: string[];
  reasons: string[];
  pre_escalation_score?: number | null;
}

export interface RoutingAttempt {
  model: string;
  quality_score: number;
  below_threshold: boolean;
  hard_failures: string[];
  citation_count: number;
}

export interface RoutingMetrics {
  total_queries: number;
  escalations: number;
}

export interface RoutingDetails {
  selected_model: string;
  escalated: boolean;
  attempts: RoutingAttempt[];
  estimated_cost_usd: number;
  metrics: RoutingMetrics;
}

export interface RagResponsePayload {
  answer: string;
  citations: RagCitation[];
  sources: SearchResultChunk[];
  latency_ms: number;
  compression: CompressionStats;
  cache: CacheInfo;
  quality: QualityReport;
  routing: RoutingDetails;
}

export interface SearchQueryParams {
  query: string;
  top_k?: number;
  project_id?: string;
  document_id?: string;
  source_type?: string;
  hnsw_ef?: number;
  temperature?: number;
  max_tokens?: number;
}

export interface SearchHistoryEntryPayload {
  id: string;
  query_text: string;
  search_mode: string;
  filters: Record<string, unknown>;
  result_count: number;
  top_k: number;
  duration_ms?: number | null;
  cache_hit: boolean;
  user_label?: string | null;
  metadata: Record<string, unknown>;
  top_chunks: string[];
  created_at: string;
}

export interface SearchHistoryResponse {
  entries: SearchHistoryEntryPayload[];
  retention: {
    max_entries: number;
    max_age_days: number;
  };
}

export interface SearchReplayResponse {
  entry: SearchHistoryEntryPayload;
  rag: RagResponsePayload;
  semantic: SemanticSearchResponse;
}
