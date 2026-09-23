import { httpClient } from "@/lib/api/http";
import type { ApiMission } from "@/types/mission";

/** One message of the client-held transcript; resent on every call (decision #519). */
export interface TranscriptMessage {
  role: "user" | "assistant";
  content: string;
}

/**
 * One span of a Librarian reply. `prose` may use world knowledge freely;
 * `corpus_claim` is a statement about this project's evidence and carries
 * citations that resolve to `/evidence/{id}`; `withheld` is a claim the server
 * refused to render because its provenance did not hold.
 */
export interface ReplySegment {
  kind: "prose" | "corpus_claim" | "withheld";
  text: string;
  citations: string[];
}

export interface EvidenceRef {
  id: string;
  claim: string;
  source_url: string;
  disposition: string;
  href: string;
}

/** A document chunk an answer cites; `href` opens the document at that chunk (QA-1). */
export interface ChunkRef {
  id: string;
  document_id: string;
  document_name: string;
  chunk_index: number | null;
  snippet: string | null;
  href: string;
}

export interface TurnResponse {
  segments: ReplySegment[];
  suggested_action: "draft_mission" | null;
  evidence: EvidenceRef[];
  /** Chunks an answer turn cites; empty for a conversational turn. */
  chunks: ChunkRef[];
  /** True when an answer turn was refused: nothing in the project answers the question. */
  no_evidence: boolean;
  withheld_count: number;
  usage: Record<string, number> | null;
  model: string;
}

/**
 * The answer budgets, in tokens (decision #543). A citation label costs about 33
 * tokens, so 600 fits a short answer of about 150 words with its citations, and
 * 2000 a full synthesis of about 500. The server tells the model the length.
 */
export const ANSWER_BUDGETS = { short: 600, full: 2000 } as const;
export type AnswerBudget = keyof typeof ANSWER_BUDGETS;

export interface MissionDraft {
  mission_id: string;
  title: string;
  objective: string;
  success_criteria: string[];
  background?: string | null;
  focus?: string | null;
  required_entities?: string[] | null;
  excluded_entities?: string[] | null;
  constraints?: string[] | null;
  deliverable_format?: string | null;
  deliverables?: string[];
  tags?: string[];
}

export interface LintViolation {
  rule: string;
  field: string | null;
  message: string;
  suggestion: string | null;
}

export interface DraftPreview {
  contract_version: string;
  compiler_revision: string;
  fidelity: string;
  named_entities: string[];
  objectives: Array<Record<string, unknown>>;
  evidence_slots: Array<Record<string, unknown>>;
  acceptance_checks: Array<Record<string, unknown>>;
  deliverable_schemas: Array<Record<string, unknown>>;
  coverage_thresholds: Record<string, number>;
  validation_thresholds: Record<string, number>;
}

export interface DraftResponse {
  draft: MissionDraft;
  preview: DraftPreview | null;
  preview_error: string | null;
  lint_errors: LintViolation[];
  lint_warnings: LintViolation[];
  notes: string[];
  usage: Record<string, number> | null;
  model: string;
}

export interface CreatedMissionResponse {
  mission: ApiMission;
  created: boolean;
}

export const librarianApi = {
  /**
   * One turn; `projectId` scopes the evidence the Librarian may cite. With
   * `answer`, the last message is a question answered from the project's
   * documents within `maxTokens`, or refused.
   */
  turn(
    messages: TranscriptMessage[],
    projectId: string | null,
    answer?: { maxTokens: number },
  ): Promise<TurnResponse> {
    return httpClient.post<TurnResponse>(
      "/librarian/turns",
      answer
        ? { project_id: projectId, messages, mode: "answer", max_tokens: answer.maxTokens }
        : { project_id: projectId, messages },
    );
  },

  /** Turn the conversation into a compiled, linted mission draft. Nothing is saved. */
  draft(messages: TranscriptMessage[], projectId: string): Promise<DraftResponse> {
    return httpClient.post<DraftResponse>("/librarian/drafts", { project_id: projectId, messages });
  },

  /** Create the reviewed draft as a pristine draft mission. Explicit and idempotent. */
  createMission(draft: MissionDraft, projectId: string): Promise<CreatedMissionResponse> {
    return httpClient.post<CreatedMissionResponse>("/librarian/missions", { project_id: projectId, draft });
  },
};

/** Plain-text form of a reply, used when the transcript is resent to the server. */
export function replyToTranscriptText(segments: ReplySegment[], chunks: ChunkRef[] = []): string {
  const byId = new Map(chunks.map((chunk) => [chunk.id, chunk]));
  const cite = (id: string) => {
    const chunk = byId.get(id);
    return chunk ? `[document ${chunk.document_name}, chunk ${chunk.chunk_index ?? "?"}]` : `[evidence:${id}]`;
  };
  return segments
    .map((segment) =>
      segment.kind === "withheld"
        ? "[withheld claim]"
        : segment.citations.length
          ? `${segment.text} ${segment.citations.map(cite).join(" ")}`
          : segment.text,
    )
    .join("\n\n")
    .trim();
}
