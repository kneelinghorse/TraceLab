export type MissionStatus = "draft" | "in_progress" | "review" | "complete";

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
  status: MissionStatus;
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
  status?: MissionStatus | null;
  completion_percentage?: number | null;
  created_at: string;
  updated_at: string;
}

export interface MissionCreatePayload {
  project_id: string;
  mission_data: MissionProtocolDraft;
  quality_gates?: Record<string, Record<string, unknown>>;
  status?: MissionStatus;
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
