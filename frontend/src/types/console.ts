/**
 * Types for the Operator Console - relationships and corrections.
 * Mirrors backend schemas from app/schemas/relationships.py and app/schemas/corrections.py
 */

// ==================== Relationship Types ====================

export interface RelationshipEdgeInfo {
  relationship_type: string;
  evidence_ids: string[];
  summary?: string | null;
  source?: string | null;
  relevance_score?: number | null;
}

export interface RelatedChunk {
  id: string;
  document_id: string;
  document_name?: string | null;
  chunk_index: number;
  preview?: string | null;
  relationship: RelationshipEdgeInfo;
}

export interface RelatedDocument {
  id: string;
  name: string;
  file_type?: string | null;
  source_type?: string | null;
  evidence_chunks: number;
  chunk_ids: string[];
  relationship: RelationshipEdgeInfo;
}

export interface RelatedInsight {
  id: string;
  title: string;
  insight_type?: string | null;
  validated: boolean;
  relationship: RelationshipEdgeInfo;
}

export interface RelatedMission {
  id: string;
  mission_identifier?: string | null;
  title?: string | null;
  status: string;
  completion_percentage: number;
  shared_documents: number;
  shared_chunks: number;
  shared_insights: number;
  relationship: RelationshipEdgeInfo;
}

export interface RelationshipFilters {
  entity_types: string[];
  min_relevance?: number | null;
}

export interface RelationshipTotals {
  documents: number;
  insights: number;
  chunks: number;
  missions: number;
}

export interface RelationshipContextResponse {
  mission_id: string;
  mission_identifier?: string | null;
  project_id: string;
  depth: number;
  filters: RelationshipFilters;
  documents: RelatedDocument[];
  insights: RelatedInsight[];
  chunks: RelatedChunk[];
  related_missions: RelatedMission[];
  totals: RelationshipTotals;
  warnings: string[];
  cached: boolean;
}

// ==================== Correction Types ====================

export type CorrectionStatus = "pending" | "in_progress" | "completed" | "failed" | "skipped";

export type CorrectionErrorType =
  | "no_embedding"
  | "low_similarity"
  | "no_chunks"
  | "timeout"
  | "validation_error"
  | "empty_content"
  | "database_error";

export interface CorrectionItem {
  correction_id: string;
  mission_uuid: string;
  evidence_id: string;
  status: CorrectionStatus;
  error_type: CorrectionErrorType;
  retry_count: number;
  max_retries: number;
  last_error?: string | null;
  best_similarity?: number | null;
  similarity_threshold: number;
  chunk_id?: string | null;
  created_at: string;
  updated_at: string;
  next_retry_at?: string | null;
  callback_url?: string | null;
}

export interface CorrectionQueueStats {
  pending: number;
  in_progress: number;
  completed: number;
  failed: number;
  skipped: number;
  total: number;
}

export interface CorrectionStatusResponse {
  stats: CorrectionQueueStats;
  error_distribution: Record<string, number>;
  recent_items: CorrectionItem[];
  last_updated: string;
}

export interface CorrectionTelemetry {
  queue_counts: CorrectionQueueStats;
  success_rate: number;
  webhook_stats?: {
    delivered: number;
    failed: number;
    pending: number;
  };
  last_updated: string;
}

// ==================== Console Dashboard Types ====================

export interface ConsoleMissionSummary {
  id: string;
  mission_id: string;
  title?: string | null;
  status: string;
  completion_percentage: number;
  quality_score?: number | null;
  failing_gates: number;
  passing_gates: number;
  evidence_count: number;
  linked_chunks: number;
  created_at: string;
  updated_at: string;
}

export interface ConsoleDashboardStats {
  total_missions: number;
  missions_by_status: Record<string, number>;
  quality_distribution: {
    excellent: number; // 80-100%
    good: number;      // 60-79%
    fair: number;      // 40-59%
    poor: number;      // 0-39%
  };
  corrections_pending: number;
  corrections_failed: number;
  recent_activity: Array<{
    type: "mission_created" | "mission_completed" | "correction_failed" | "evidence_linked";
    mission_id: string;
    timestamp: string;
    details?: string;
  }>;
}

// ==================== Export Types ====================

export type ExportFormat = "json" | "yaml";

export interface ExportOptions {
  format: ExportFormat;
  includeRelationships?: boolean;
  includeEvidence?: boolean;
  includeQualityGates?: boolean;
}
