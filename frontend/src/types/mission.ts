// Legacy Mission Protocol status (for MissionProtocolDraft)
export type MissionProtocolStatus = "draft" | "in_progress" | "review" | "complete";

// New mission status aligned with backend API
export type MissionStatus = "draft" | "queued" | "in_progress" | "completed" | "blocked" | "cancelled";

export type QualityGateName =
  | "research_statement"
  | "evidence_links"
  | "contradictions_resolved"
  | "synthesis_quality"
  | "traceability";

export type QualityGateStatus = "pending" | "pass" | "fail";

export interface ResearchStatement {
  topic: string;
  objective: string;
  scope: string;
  audience?: string | null;
  methodology?: string | null;
  success_metrics: string[];
  risks: string[];
}

export interface KeyQuestion {
  question: string;
  status: "open" | "researching" | "answered";
  answer?: string | null;
  confidence?: number | null;
  owner?: string | null;
}

export interface Evidence {
  evidence_id: string;
  source: string;
  summary: string;
  chunk_id?: string | null;
  insight_id?: string | null;
  source_type?: string | null;
  relevance_score?: number | null;
  tags: string[];
}

export interface Synthesis {
  key_insights: string[];
  surprising_findings: string[];
  contradictory_information: string[];
  contradiction_resolutions: string[];
  recommendations: string[];
  next_steps: string[];
}

export interface QualityCheckpoint {
  gate: QualityGateName;
  status: QualityGateStatus;
  notes?: string | null;
  validated_by?: string | null;
  validated_at?: string | null;
}

export interface MissionProtocolDraft {
  mission_id: string;
  version: string;
  title?: string | null;
  summary?: string | null;
  project_id?: string | null;
  status: MissionProtocolStatus;
  owner?: string | null;
  research_statement?: ResearchStatement | null;
  key_questions: KeyQuestion[];
  synthesis?: Synthesis | null;
  evidence: Evidence[];
  quality_checkpoints: QualityCheckpoint[];
  tags: string[];
  created_at?: string | null;
  updated_at?: string | null;
}

export interface Mission {
  id: string;
  project_id: string | null;
  mission_data: MissionProtocolDraft;
  quality_gates?: Record<string, Record<string, unknown>> | null;
  status?: MissionProtocolStatus | null;
  completion_percentage?: number | null;
  created_at: string;
  updated_at: string;
}

export interface MissionCreatePayload {
  project_id: string;
  mission_data: MissionProtocolDraft;
  quality_gates?: Record<string, Record<string, unknown>>;
  status?: MissionProtocolStatus;
}

export type MissionUpdatePayload = Partial<MissionCreatePayload>;

export interface QualityGateReport {
  mission_id: string;
  protocol_mission_id: string;
  evaluated_at: string;
  all_passed: boolean;
  failing_gates: string[];
  gates: Record<
    QualityGateName,
    {
      gate: QualityGateName;
      status: QualityGateStatus;
      blocking: boolean;
      details?: string | null;
      evaluated_at: string;
      metadata?: Record<string, unknown> | null;
    }
  >;
}

export interface EvidenceLinkPayload {
  evidence_id: string;
  chunk_id: string;
  insight_id?: string;
}

// ============================================
// API Mission types (aligned with backend)
// ============================================

/**
 * Mission entity from the API (B16.1+ schema)
 */
export type ResearchDepth = "baseline" | "deep" | "alpha";

export interface ApiMission {
  id: string;
  project_id: string | null;
  project_name: string | null;
  mission_id: string;
  title: string;
  objective: string;
  success_criteria: string[];
  context: Record<string, unknown>;
  deliverables: string[];
  research_phases: Record<string, unknown>;
  tags: string[];
  metadata: Record<string, unknown>;
  research_depth: ResearchDepth;
  status: MissionStatus;
  queued_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  deepsearch_job_id: string | null;
  execution_metadata: Record<string, unknown>;
  result_document_ids: string[];
  result_report_id: string | null;
  result_markdown: string | null;
  result_protocol: Record<string, unknown> | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  created_by: string | null;
}

export interface ApiMissionCreate {
  mission_id: string;
  title: string;
  objective: string;
  success_criteria: string[];
  project_id?: string;
  context?: Record<string, unknown>;
  deliverables?: string[];
  research_phases?: Record<string, unknown>;
  tags?: string[];
  metadata?: Record<string, unknown>;
  research_depth?: ResearchDepth;
  status?: MissionStatus;
  created_by?: string;
}

export interface ApiMissionUpdate {
  title?: string;
  objective?: string;
  success_criteria?: string[];
  context?: Record<string, unknown>;
  deliverables?: string[];
  research_phases?: Record<string, unknown>;
  tags?: string[];
  metadata?: Record<string, unknown>;
  status?: MissionStatus;
  deepsearch_job_id?: string;
  result_document_ids?: string[];
  result_report_id?: string;
  result_markdown?: string;
  result_protocol?: Record<string, unknown>;
  error_message?: string;
  execution_metadata?: Record<string, unknown>;
}

export interface MissionListParams {
  page?: number;
  page_size?: number;
  status?: MissionStatus;
  project_id?: string;
}

export interface ReportPromotionResponse {
  document_id: string;
  document_name: string;
  status: "processing" | "completed";
  message: string;
  chunk_count: number | null;
}
