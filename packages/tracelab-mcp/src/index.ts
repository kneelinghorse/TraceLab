#!/usr/bin/env node
/**
 * TraceLab MCP Server
 *
 * Provides 7 action-clustered tools for AI agents to perform complete
 * research-to-output loops against TraceLab's knowledge base. T41.7
 * (sprint-41) collapsed the prior ~24 flat tools into topical clusters
 * matching the cmos-mcp pattern. Each cluster dispatches by an `action`
 * parameter to the existing per-action handlers below.
 *
 * Clusters:
 * 1. tracelab_search           — actions: knowledge
 * 2. tracelab_project          — actions: list, create, update, stats
 * 3. tracelab_collection       — actions: list, get, export, create, add, synthesize
 * 4. tracelab_report           — actions: create, list, get, export
 * 5. tracelab_document         — actions: upload, get_content
 * 6. tracelab_mission          — actions: create, list, get, update (CRUD)
 * 7. tracelab_mission_execution — actions: submit, status, preview (DS-bound lifecycle)
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  Tool,
} from '@modelcontextprotocol/sdk/types.js';
import { z } from 'zod';
import {
  TraceLabClient,
  TraceLabAPIError,
  type TraceLabConfig,
} from './api-client.js';
import { CredentialStore, type StoredCredential } from './auth/credential-store.js';
import {
  DeviceCodeError,
  runDeviceCodeFlow,
  readPackageVersion,
} from './auth/device-code.js';

// Module-load: construct the client with whatever env credentials the
// shell already exposes. main() replaces this client (with one carrying a
// fresh device-flow-minted key) when neither env path provides one.
//
// Why two-phase: the existing test suite dynamic-imports this module to
// reach handler exports that close over `client`. Constructing here keeps
// those tests working without touching their fetch mocks. The module-load
// client also covers the CI / scripted-automation path where env vars
// supply credentials and the device-code flow never runs.
const baseUrl = (process.env.TRACELAB_API_URL || 'http://localhost:8000').replace(
  /\/+$/,
  ''
);

let client: TraceLabClient = new TraceLabClient({
  baseUrl,
  token: process.env.TRACELAB_TOKEN,
  apiKey: process.env.TRACELAB_API_KEY,
});

// Tool definitions
// T41.7 (sprint-41): Tool surface refactored from ~24 flat tools into 7
// action-clustered tools, matching the cmos-mcp pattern. Each tool dispatches
// by an `action` parameter to the existing per-action handlers below. Cluster
// boundaries chosen to mirror domain nouns (search/project/collection/report/
// document/mission). Mission CRUD and DeepSearch-bound execution lifecycle
// are split into two clusters because their callers and lifecycles differ —
// matches the cmos-mcp cmos_mission vs cmos_mission_transition precedent.
const TOOLS: Tool[] = [
  // ─────────────────────────────────────────────────────────────────────────
  // 1. tracelab_search — semantic knowledge-base search
  // ─────────────────────────────────────────────────────────────────────────
  {
    name: 'tracelab_search',
    description:
      'Semantic search across the TraceLab knowledge base. Returns ranked chunks with content excerpts and document references. Actions: knowledge (find chunks matching a natural-language query). Required for action="knowledge": query. Related clusters: tracelab_document (read full text), tracelab_collection (organize chunks).',
    inputSchema: {
      type: 'object',
      properties: {
        action: {
          type: 'string',
          enum: ['knowledge'],
          description: 'Search action. knowledge: semantic search across the knowledge base.',
        },
        query: {
          type: 'string',
          description: 'Natural language search query. Example: "user onboarding best practices", "competitive analysis methods", "interview synthesis techniques"',
        },
        project_id: {
          type: 'string',
          description: 'Scope search to a specific project UUID. Get project IDs from tracelab_project(action="list").',
        },
        limit: {
          type: 'number',
          description: 'Maximum results to return (1-50, default: 10). Increase for broader exploration, decrease for focused lookups.',
          minimum: 1,
          maximum: 50,
        },
        tags: {
          type: 'array',
          items: { type: 'string' },
          description: 'Filter results to chunks with any of these tags (OR logic). Example: ["interview", "synthesis"]',
        },
      },
      required: ['action'],
    },
  },
  // ─────────────────────────────────────────────────────────────────────────
  // 2. tracelab_project — project CRUD + stats
  // ─────────────────────────────────────────────────────────────────────────
  {
    name: 'tracelab_project',
    description:
      'Projects organize documents and research. Actions: list (browse), create (new project), update (edit metadata), stats (aggregated counts: documents, chunks, reports, tokens). Required: action="create" needs name; action="update"/"stats" needs project_id.',
    inputSchema: {
      type: 'object',
      properties: {
        action: {
          type: 'string',
          enum: ['list', 'create', 'update', 'stats'],
          description: 'Project action. list: browse projects. create: new project. update: edit metadata. stats: aggregated counts for one project.',
        },
        project_id: {
          type: 'string',
          description: 'UUID of the project. Required for action="update" and action="stats".',
        },
        name: {
          type: 'string',
          description: 'Project name. Required for action="create"; optional rename for action="update".',
        },
        description: {
          type: 'string',
          description: 'Project description (optional for create/update).',
        },
        research_type: {
          type: 'string',
          enum: ['strategic', 'tactical', 'generative', 'evaluative'],
          description: 'Type of research (optional for create/update).',
        },
        methodology: {
          type: 'string',
          enum: ['qualitative', 'quantitative', 'mixed'],
          description: 'Research methodology (optional for create/update).',
        },
        status: {
          type: 'string',
          enum: ['active', 'archived', 'completed'],
          description: 'Project status (optional for action="update").',
        },
        page: {
          type: 'number',
          description: 'Page number for action="list" (1-indexed, default: 1).',
          minimum: 1,
        },
        page_size: {
          type: 'number',
          description: 'Results per page for action="list" (1-100, default: 20).',
          minimum: 1,
          maximum: 100,
        },
        search: {
          type: 'string',
          description: 'Optional name-search filter for action="list".',
        },
      },
      required: ['action'],
    },
  },
  // ─────────────────────────────────────────────────────────────────────────
  // 3. tracelab_collection — collection CRUD + synthesize
  // ─────────────────────────────────────────────────────────────────────────
  {
    name: 'tracelab_collection',
    description:
      'Collections group related chunks for synthesis. Actions: list, get (with chunks), export (as markdown), create, add (a chunk), synthesize (generate summary/report from chunks; optional save as report). Required: action="get"/"export" needs collection_id; action="create" needs name; action="add" needs collection_id+chunk_id; action="synthesize" needs collection_id.',
    inputSchema: {
      type: 'object',
      properties: {
        action: {
          type: 'string',
          enum: ['list', 'get', 'export', 'create', 'add', 'synthesize'],
          description: 'Collection action. list: browse. get: detail with chunks. export: markdown bundle. create: new collection. add: add a chunk. synthesize: summary/report from chunks (citations included; optional save as report).',
        },
        collection_id: {
          type: 'string',
          description: 'UUID of the collection. Required for action="get"/"export"/"add"/"synthesize".',
        },
        name: {
          type: 'string',
          description: 'Collection name. Required for action="create" (max 255 chars).',
          maxLength: 255,
        },
        description: {
          type: 'string',
          description: 'Optional collection description for action="create" (max 2000 chars).',
          maxLength: 2000,
        },
        chunk_id: {
          type: 'string',
          description: 'UUID of a chunk to add. Required for action="add". Get from tracelab_search results.',
        },
        notes: {
          type: 'string',
          description: 'Optional notes about why a chunk is relevant. Used with action="add" (max 2000 chars).',
          maxLength: 2000,
        },
        prompt: {
          type: 'string',
          description: 'Optional custom synthesis prompt for action="synthesize" (e.g., "Summarize the key findings").',
        },
        format: {
          type: 'string',
          enum: ['markdown', 'summary', 'report'],
          description: 'Output format for action="synthesize" (default: markdown).',
        },
        save_as_report: {
          type: 'boolean',
          description: 'For action="synthesize": persist result as a report. Default false.',
        },
        report_title: {
          type: 'string',
          description: 'For action="synthesize" with save_as_report=true: report title (required when saving; max 255 chars).',
          maxLength: 255,
        },
        project_id: {
          type: 'string',
          description: 'For action="synthesize" with save_as_report=true: project UUID to associate the report with.',
        },
      },
      required: ['action'],
    },
  },
  // ─────────────────────────────────────────────────────────────────────────
  // 4. tracelab_report — persistent report CRUD
  // ─────────────────────────────────────────────────────────────────────────
  {
    name: 'tracelab_report',
    description:
      'Persistent reports — synthesized artifacts that survive across sessions. Actions: create (from a collection or specific chunks), list (with optional project/status filter), get (full content + citations + sources), export (markdown). Required: action="create" needs title (and one of collection_id/chunk_ids); action="get"/"export" needs report_id.',
    inputSchema: {
      type: 'object',
      properties: {
        action: {
          type: 'string',
          enum: ['create', 'list', 'get', 'export'],
          description: 'Report action. create: synthesize a new persistent report. list: browse with filters. get: full details. export: markdown.',
        },
        report_id: {
          type: 'string',
          description: 'UUID of the report. Required for action="get" and action="export".',
        },
        title: {
          type: 'string',
          description: 'Report title. Required for action="create" (max 255 chars).',
          maxLength: 255,
        },
        collection_id: {
          type: 'string',
          description: 'For action="create": UUID of collection to synthesize (mutually exclusive with chunk_ids).',
        },
        chunk_ids: {
          type: 'array',
          items: { type: 'string' },
          description: 'For action="create": UUIDs of specific chunks to synthesize (mutually exclusive with collection_id).',
        },
        project_id: {
          type: 'string',
          description: 'For action="create": UUID of project to associate the report with. For action="list": filter by project.',
        },
        prompt: {
          type: 'string',
          description: 'For action="create": optional custom synthesis prompt (max 2000 chars).',
          maxLength: 2000,
        },
        format: {
          type: 'string',
          enum: ['summary', 'report', 'bullets', 'markdown'],
          description: 'For action="create": output format (default: summary).',
        },
        status: {
          type: 'string',
          enum: ['draft', 'final'],
          description: 'For action="list": filter by report status.',
        },
        page: {
          type: 'number',
          description: 'For action="list": page number (1-indexed, default: 1).',
          minimum: 1,
        },
        page_size: {
          type: 'number',
          description: 'For action="list": results per page (1-100, default: 20).',
          minimum: 1,
          maximum: 100,
        },
      },
      required: ['action'],
    },
  },
  // ─────────────────────────────────────────────────────────────────────────
  // 5. tracelab_document — document upload + content retrieval
  // ─────────────────────────────────────────────────────────────────────────
  {
    name: 'tracelab_document',
    description:
      'Document upload + retrieval. Actions: upload (new doc through ingestion pipeline; supports PDF, DOCX, PPTX, CSV, XLSX, MD, TXT, JSON, XML, YAML), get_content (paginated full text assembled from chunks). Required: action="upload" needs name, content (base64), content_type, project_id; action="get_content" needs document_id.',
    inputSchema: {
      type: 'object',
      properties: {
        action: {
          type: 'string',
          enum: ['upload', 'get_content'],
          description: 'Document action. upload: ingest a new document. get_content: read full text with pagination.',
        },
        document_id: {
          type: 'string',
          description: 'UUID of the document. Required for action="get_content". Get from tracelab_search results (document_id field) or upload response.',
        },
        name: {
          type: 'string',
          description: 'Filename or document name (e.g., "research-paper.pdf"). Required for action="upload".',
        },
        content: {
          type: 'string',
          description: 'Base64 encoded file content. Required for action="upload".',
        },
        content_type: {
          type: 'string',
          description: 'MIME type of the file. Required for action="upload".',
          enum: [
            'application/pdf',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'text/csv',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'text/markdown',
            'text/plain',
            'application/json',
            'application/xml',
            'text/xml',
            'application/x-yaml',
            'text/yaml',
          ],
        },
        project_id: {
          type: 'string',
          description: 'UUID of the project to add the document to. Required for action="upload".',
        },
        description: {
          type: 'string',
          description: 'Optional description of the document for action="upload".',
        },
        page: {
          type: 'number',
          description: 'For action="get_content": page number for large documents (1-indexed, default: 1). Response includes has_more flag and next_page hint.',
          minimum: 1,
        },
        page_size: {
          type: 'number',
          description: 'For action="get_content": chunks per page (1-100, default: 20). Reduce for very long documents to stay within context limits.',
          minimum: 1,
          maximum: 100,
        },
        include_metadata: {
          type: 'boolean',
          description: 'For action="get_content": include document metadata (name, file_type, word_count, chunk_count). Default: true.',
        },
      },
      required: ['action'],
    },
  },
  // ─────────────────────────────────────────────────────────────────────────
  // 6. tracelab_mission — mission CRUD (create/list/get/update)
  // ─────────────────────────────────────────────────────────────────────────
  {
    name: 'tracelab_mission',
    description:
      'Research mission CRUD. Use tracelab_mission_execution for submit/status/preview (DeepSearch-bound lifecycle). Actions: create, list, get, update. project_id is required at create (T41.6) and editable on update (T41.5). action="get" returns slim payload by default; pass include_execution_metadata=true for full execution_metadata/result_protocol/result_markdown (T41.4). Required: action="create" needs mission_id, title, objective, success_criteria, project_id; action="get"/"update" needs mission_id. Related cluster: tracelab_mission_execution.',
    inputSchema: {
      type: 'object',
      properties: {
        action: {
          type: 'string',
          enum: ['create', 'list', 'get', 'update'],
          description: 'Mission CRUD action. create: new mission. list: browse with filters. get: full details (slim by default). update: modify before submission.',
        },
        mission_id: {
          type: 'string',
          description: 'For action="create": unique mission identifier ("R001", "B17.1", "market-analysis-q4"). For action="get"/"update": UUID of the mission.',
        },
        title: {
          type: 'string',
          description: 'For action="create": short descriptive title. For action="update": new title.',
        },
        objective: {
          type: 'string',
          description: 'For action="create": clear research objective. For action="update": revised objective.',
        },
        success_criteria: {
          type: 'array',
          items: { type: 'string' },
          description: 'Measurable outcomes that define success. Required for action="create"; replaces existing list on action="update".',
        },
        project_id: {
          type: 'string',
          description: 'For action="create": UUID of project (REQUIRED as of T41.6 — orphan missions cannot be created; use tracelab_project(action="list"|"create") to find/make one). For action="update": re-parent to a different project (T41.5; 404 if target project does not exist).',
        },
        deliverables: {
          type: 'array',
          items: { type: 'string' },
          description: 'Expected output artifacts. Example: ["Market analysis report", "Competitor matrix", "Trend forecast"]',
        },
        tags: {
          type: 'array',
          items: { type: 'string' },
          description: 'Categorization tags. Example: ["market-research", "competitive", "q4-2024"]',
        },
        // T41.4 slim/full toggle (action="get" only)
        include_execution_metadata: {
          type: 'boolean',
          default: false,
          description: 'For action="get": when true, return full execution_metadata, result_protocol, and result_markdown without size-based summarization. Use sparingly — completed missions can carry tens of KB of execution telemetry. Default: false (slim).',
        },
        // List filters
        status: {
          type: 'string',
          enum: ['draft', 'queued', 'in_progress', 'completed', 'blocked', 'cancelled', 'validation_failed'],
          description: 'For action="list": filter by execution status. draft: Not yet submitted. queued: Waiting for execution. in_progress: Currently executing. completed: Finished successfully. blocked: Awaiting resolution. cancelled: Terminated. validation_failed: Synthesized output but failed coverage/structural gates (reviewable artifact, distinct from blocked).',
        },
        page: {
          type: 'number',
          description: 'For action="list": page number (1-indexed, default: 1).',
          minimum: 1,
        },
        page_size: {
          type: 'number',
          description: 'For action="list": missions per page (1-100, default: 20).',
          minimum: 1,
          maximum: 100,
        },
        // DEPRECATED back-compat shim (action="update" only)
        context: {
          type: 'object',
          description: 'For action="update" only. DEPRECATED: kept for back-compat. Prefer the explicit authoring fields below (background, focus, references, required_entities, excluded_entities, expected_output_schema, coverage_thresholds, validation_thresholds, deliverable_format, max_loops, min_loops, constraints).',
        },
        // T40.1 mission-authoring fields (used by both create and update)
        background: {
          type: 'string',
          description: 'Free-form prose orienting the research. Consumed by the DeepSearch contract compiler as high-level framing. Example: "Internal teams keep conflating Contrast-Consistent Search (CCS) with CCS-style probing..."',
        },
        focus: {
          type: 'string',
          description: 'Narrow framing for the research question. Sharpens what counts as on-topic vs. off-topic. Example: "Only papers that benchmark CCS against at least one supervised probing baseline."',
        },
        references: {
          type: 'array',
          items: { type: 'object', properties: { title: { type: 'string' } }, required: ['title'] },
          description: 'Seed references the author already trusts. Each entry at minimum {title}; optional URL/author/year fields are preserved. Example: [{"title": "Contrast-Consistent Search (Burns et al. 2022)"}]',
        },
        required_entities: {
          type: 'array',
          items: { type: 'string' },
          description: 'Entities that MUST appear in the synthesized output. Feeds DeepSearch\'s coverage gate. Example: ["Contrast-Consistent Search", "CCS", "latent truth"]',
        },
        excluded_entities: {
          type: 'array',
          items: { type: 'string' },
          description: 'Entities that MUST NOT appear — use to rule out unrelated homonyms or adjacent-but-distinct concepts. Example: ["Amazon CloudFront", "CCS Insurance"]',
        },
        expected_output_schema: {
          type: 'object',
          description: 'DeepSearch OutputSchema describing the deliverable shape. Used by the contract compiler to steer synthesis. Example: {"type": "object", "properties": {"executive_summary": {"type": "string"}, "comparison_table": {"type": "array"}}}',
        },
        coverage_thresholds: {
          type: 'object',
          description: 'Coverage gate thresholds applied during synthesis. Example: {"min_sources": 12, "min_per_required_entity": 2}',
        },
        validation_thresholds: {
          type: 'object',
          description: 'Validation gate thresholds applied during synthesis. Example: {"structural": 0.85, "coverage": 0.70}',
        },
        deliverable_format: {
          type: 'string',
          description: 'Output rendering hint DeepSearch uses when formatting the deliverable. Example: "executive summary with comparison table", "markdown report", "evidence matrix".',
        },
        max_loops: {
          type: 'integer',
          minimum: 1,
          description: 'Upper bound on DeepSearch research loop count. Guards against runaway deep-depth missions.',
        },
        min_loops: {
          type: 'integer',
          minimum: 1,
          description: 'Lower bound on DeepSearch research loop count. Forces a minimum number of evidence-gathering passes.',
        },
        constraints: {
          type: 'array',
          items: { type: 'string' },
          description: 'Author-level constraints DeepSearch must respect. Example: ["no paywalled sources", "prefer peer-reviewed", "published 2020 or later"]',
        },
      },
      required: ['action'],
    },
  },
  // ─────────────────────────────────────────────────────────────────────────
  // 7. tracelab_mission_execution — DeepSearch lifecycle (submit/status/preview)
  //    Mirrors cmos-mcp's cmos_mission_transition split. Submit and preview
  //    talk to DeepSearch's contract compiler; status polls execution state.
  // ─────────────────────────────────────────────────────────────────────────
  {
    name: 'tracelab_mission_execution',
    description:
      'Mission execution lifecycle (DeepSearch-bound). Use tracelab_mission for create/list/get/update. Actions: submit (queue for execution), status (lightweight progress poll), preview (compile DS contract without spending a paid loop — returns named_entities, objectives, evidence_slots, acceptance_checks, deliverable_schemas, coverage/validation thresholds; useful for iterating on authoring fields). All actions require mission_id. Related cluster: tracelab_mission.',
    inputSchema: {
      type: 'object',
      properties: {
        action: {
          type: 'string',
          enum: ['submit', 'status', 'preview'],
          description: 'Execution action. submit: queue for DeepSearch (draft → queued). status: lightweight status+progress poll. preview: compile contract without submitting (read-only, free).',
        },
        mission_id: {
          type: 'string',
          description: 'UUID of the mission. Required for all actions.',
        },
      },
      required: ['action', 'mission_id'],
    },
  },
];

// Legacy → cluster action mapping (T41.7). Kept as a const for the
// compile-time parity test in index.test.ts and for the migration sketch
// pushed to cmos://derek/deepsearch.
const LEGACY_TO_CLUSTER: Record<string, { tool: string; action: string }> = {
  search_knowledge: { tool: 'tracelab_search', action: 'knowledge' },
  list_projects: { tool: 'tracelab_project', action: 'list' },
  create_project: { tool: 'tracelab_project', action: 'create' },
  update_project: { tool: 'tracelab_project', action: 'update' },
  get_project_stats: { tool: 'tracelab_project', action: 'stats' },
  list_collections: { tool: 'tracelab_collection', action: 'list' },
  get_collection: { tool: 'tracelab_collection', action: 'get' },
  export_collection: { tool: 'tracelab_collection', action: 'export' },
  create_collection: { tool: 'tracelab_collection', action: 'create' },
  add_to_collection: { tool: 'tracelab_collection', action: 'add' },
  synthesize: { tool: 'tracelab_collection', action: 'synthesize' },
  create_report: { tool: 'tracelab_report', action: 'create' },
  list_reports: { tool: 'tracelab_report', action: 'list' },
  get_report: { tool: 'tracelab_report', action: 'get' },
  export_report: { tool: 'tracelab_report', action: 'export' },
  upload_document: { tool: 'tracelab_document', action: 'upload' },
  get_document_content: { tool: 'tracelab_document', action: 'get_content' },
  create_mission: { tool: 'tracelab_mission', action: 'create' },
  list_missions: { tool: 'tracelab_mission', action: 'list' },
  get_mission: { tool: 'tracelab_mission', action: 'get' },
  update_mission: { tool: 'tracelab_mission', action: 'update' },
  submit_mission: { tool: 'tracelab_mission_execution', action: 'submit' },
  get_mission_status: { tool: 'tracelab_mission_execution', action: 'status' },
  preview_mission_contract: { tool: 'tracelab_mission_execution', action: 'preview' },
};
export { LEGACY_TO_CLUSTER };


// Input validation schemas
const SearchKnowledgeInput = z.object({
  query: z.string().min(1),
  project_id: z.string().uuid().optional(),
  limit: z.number().min(1).max(50).optional().default(10),
  tags: z.array(z.string()).optional(),
});

const ListProjectsInput = z.object({
  page: z.number().min(1).optional().default(1),
  page_size: z.number().min(1).max(100).optional().default(20),
  search: z.string().optional(),
});

const CreateProjectInput = z.object({
  name: z.string().min(1),
  description: z.string().optional(),
  research_type: z.enum(['strategic', 'tactical', 'generative', 'evaluative']).optional(),
  methodology: z.enum(['qualitative', 'quantitative', 'mixed']).optional(),
});

const UpdateProjectInput = z.object({
  project_id: z.string().uuid(),
  name: z.string().min(1).optional(),
  description: z.string().optional(),
  research_type: z.enum(['strategic', 'tactical', 'generative', 'evaluative']).optional(),
  methodology: z.enum(['qualitative', 'quantitative', 'mixed']).optional(),
  status: z.enum(['active', 'archived', 'completed']).optional(),
});

const GetProjectStatsInput = z.object({
  project_id: z.string().uuid(),
});

const GetCollectionInput = z.object({
  collection_id: z.string().uuid(),
});

const ExportCollectionInput = z.object({
  collection_id: z.string().uuid(),
});

const CreateCollectionInput = z.object({
  name: z.string().min(1).max(255),
  description: z.string().max(2000).optional(),
});

const AddToCollectionInput = z.object({
  collection_id: z.string().uuid(),
  chunk_id: z.string().uuid(),
  notes: z.string().max(2000).optional(),
});

const SynthesizeInput = z.object({
  collection_id: z.string().uuid(),
  prompt: z.string().optional(),
  format: z.enum(['markdown', 'summary', 'report']).optional().default('markdown'),
  save_as_report: z.boolean().optional().default(false),
  report_title: z.string().max(255).optional(),
  project_id: z.string().uuid().optional(),
}).refine(
  (data) => !data.save_as_report || data.report_title,
  {
    message: 'report_title is required when save_as_report is true',
    path: ['report_title'],
  }
);

const CreateReportInput = z.object({
  title: z.string().min(1).max(255),
  collection_id: z.string().uuid().optional(),
  chunk_ids: z.array(z.string().uuid()).optional(),
  project_id: z.string().uuid().optional(),
  prompt: z.string().max(2000).optional(),
  format: z.enum(['summary', 'report', 'bullets', 'markdown']).optional().default('summary'),
});

const ListReportsInput = z.object({
  project_id: z.string().uuid().optional(),
  status: z.enum(['draft', 'final']).optional(),
  page: z.number().min(1).optional().default(1),
  page_size: z.number().min(1).max(100).optional().default(20),
});

const GetReportInput = z.object({
  report_id: z.string().uuid(),
});

const ExportReportInput = z.object({
  report_id: z.string().uuid(),
});

const UploadDocumentInput = z.object({
  name: z.string().min(1),
  content: z.string().min(1), // base64 encoded
  content_type: z.enum([
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'text/csv',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'text/markdown',
    'text/plain',
    'application/json',
    'application/xml',
    'text/xml',
    'application/x-yaml',
    'text/yaml',
  ]),
  project_id: z.string().uuid(),
  description: z.string().optional(),
});

const GetDocumentContentInput = z.object({
  document_id: z.string().uuid(),
  page: z.number().min(1).optional().default(1),
  page_size: z.number().min(1).max(100).optional().default(20),
  include_metadata: z.boolean().optional().default(true),
});

// Mission input schemas
// Mission-authoring fields (T40.1/T40.2). All optional; consumed by
// DeepSearch's contract compiler at submit/preview time.
const MissionAuthoringFieldsSchema = {
  background: z.string().optional(),
  focus: z.string().optional(),
  references: z
    .array(z.object({ title: z.string() }).passthrough())
    .optional(),
  required_entities: z.array(z.string()).optional(),
  excluded_entities: z.array(z.string()).optional(),
  expected_output_schema: z.record(z.unknown()).optional(),
  coverage_thresholds: z.record(z.unknown()).optional(),
  validation_thresholds: z.record(z.unknown()).optional(),
  deliverable_format: z.string().optional(),
  max_loops: z.number().int().min(1).optional(),
  min_loops: z.number().int().min(1).optional(),
  constraints: z.array(z.string()).optional(),
} as const;

const CreateMissionInput = z.object({
  mission_id: z.string().min(1),
  title: z.string().min(1),
  objective: z.string().min(1),
  success_criteria: z.array(z.string()).min(1),
  // T41.6: project_id required at create. Pre-T41.6 the field was optional
  // and orphan missions accumulated (1.3% of stock at sprint-41 cutover).
  project_id: z.string().uuid(),
  deliverables: z.array(z.string()).optional(),
  tags: z.array(z.string()).optional(),
  ...MissionAuthoringFieldsSchema,
});

const ListMissionsInput = z.object({
  status: z.enum(['draft', 'queued', 'in_progress', 'completed', 'blocked', 'cancelled', 'validation_failed']).optional(),
  project_id: z.string().uuid().optional(),
  page: z.number().min(1).optional().default(1),
  page_size: z.number().min(1).max(100).optional().default(20),
});

const GetMissionInput = z.object({
  mission_id: z.string().uuid(),
  include_execution_metadata: z.boolean().optional(),
});

const UpdateMissionInput = z.object({
  mission_id: z.string().uuid(),
  // T41.5 (sprint-41): project_id is now mutable on existing missions.
  // Pre-T41.5 missions were stuck with their original project assignment.
  // Server validates: 404 if the target project doesn't exist.
  project_id: z.string().uuid().optional(),
  title: z.string().min(1).optional(),
  objective: z.string().min(1).optional(),
  success_criteria: z.array(z.string()).optional(),
  deliverables: z.array(z.string()).optional(),
  tags: z.array(z.string()).optional(),
  // DEPRECATED: prefer explicit authoring fields below. Kept for back-compat.
  context: z.record(z.unknown()).optional(),
  ...MissionAuthoringFieldsSchema,
});

const SubmitMissionInput = z.object({
  mission_id: z.string().uuid(),
});

const GetMissionStatusInput = z.object({
  mission_id: z.string().uuid(),
});

const PreviewMissionContractInput = z.object({
  mission_id: z.string().uuid(),
});

// Tool handlers
async function handleSearchKnowledge(args: unknown) {
  const input = SearchKnowledgeInput.parse(args);
  const result = await client.searchKnowledge({
    query: input.query,
    top_k: input.limit,
    project_id: input.project_id,
    tags: input.tags,
  });

  const chunks = result.results.map((chunk, i) => ({
    rank: i + 1,
    chunk_id: chunk.chunk_id,
    score: chunk.score.toFixed(3),
    content_preview: chunk.content.substring(0, 500) + (chunk.content.length > 500 ? '...' : ''),
    document_id: chunk.document_id,
    source_type: chunk.source_type,
    tags: chunk.tags,
  }));

  return {
    content: [
      {
        type: 'text',
        text: JSON.stringify(
          {
            query: input.query,
            total_results: chunks.length,
            results: chunks,
          },
          null,
          2
        ),
      },
    ],
  };
}

async function handleListProjects(args: unknown) {
  const input = ListProjectsInput.parse(args);
  const result = await client.listProjects(
    input.page,
    input.page_size,
    input.search
  );

  return {
    content: [
      {
        type: 'text',
        text: JSON.stringify(
          {
            projects: result.data.map((p) => ({
              id: p.id,
              name: p.name,
              description: p.description,
              status: p.status,
              research_type: p.research_type,
            })),
            pagination: result.pagination,
          },
          null,
          2
        ),
      },
    ],
  };
}

async function handleCreateProject(args: unknown) {
  const input = CreateProjectInput.parse(args);
  const result = await client.createProject({
    name: input.name,
    description: input.description,
    research_type: input.research_type,
    methodology: input.methodology,
  });

  return {
    content: [
      {
        type: 'text',
        text: JSON.stringify(
          {
            message: `Project "${result.name}" created successfully`,
            project: {
              id: result.id,
              name: result.name,
              description: result.description,
              status: result.status,
              research_type: result.research_type,
              created_at: result.created_at,
            },
          },
          null,
          2
        ),
      },
    ],
  };
}

async function handleUpdateProject(args: unknown) {
  const input = UpdateProjectInput.parse(args);
  const result = await client.updateProject(input.project_id, {
    name: input.name,
    description: input.description,
    research_type: input.research_type,
    methodology: input.methodology,
    status: input.status,
  });

  return {
    content: [
      {
        type: 'text',
        text: JSON.stringify(
          {
            message: `Project "${result.name}" updated successfully`,
            project: {
              id: result.id,
              name: result.name,
              description: result.description,
              status: result.status,
              research_type: result.research_type,
              updated_at: result.updated_at,
            },
          },
          null,
          2
        ),
      },
    ],
  };
}

async function handleGetProjectStats(args: unknown) {
  const input = GetProjectStatsInput.parse(args);
  const result = await client.getProjectStats(input.project_id);

  return {
    content: [
      {
        type: 'text',
        text: JSON.stringify(
          {
            project_id: result.project_id,
            name: result.name,
            document_count: result.document_count,
            chunk_count: result.chunk_count,
            report_count: result.report_count,
            total_tokens: result.total_tokens,
            last_updated: result.last_updated,
          },
          null,
          2
        ),
      },
    ],
  };
}

async function handleListCollections() {
  const result = await client.listCollections();

  return {
    content: [
      {
        type: 'text',
        text: JSON.stringify(
          {
            collections: result.data.map((c) => ({
              id: c.id,
              name: c.name,
              description: c.description,
              item_count: c.item_count,
              created_at: c.created_at,
            })),
            total: result.total,
          },
          null,
          2
        ),
      },
    ],
  };
}

async function handleGetCollection(args: unknown) {
  const input = GetCollectionInput.parse(args);
  const result = await client.getCollection(input.collection_id);

  return {
    content: [
      {
        type: 'text',
        text: JSON.stringify(
          {
            id: result.id,
            name: result.name,
            description: result.description,
            item_count: result.item_count,
            items: result.items.map((item) => ({
              id: item.id,
              chunk_id: item.chunk_id,
              notes: item.notes,
              chunk_content: item.chunk_content,
              document_id: item.document_id,
              added_at: item.added_at,
            })),
          },
          null,
          2
        ),
      },
    ],
  };
}

async function handleExportCollection(args: unknown) {
  const input = ExportCollectionInput.parse(args);
  const markdown = await client.exportCollection(input.collection_id);

  return {
    content: [
      {
        type: 'text',
        text: markdown,
      },
    ],
  };
}

async function handleCreateCollection(args: unknown) {
  const input = CreateCollectionInput.parse(args);
  const result = await client.createCollection({
    name: input.name,
    description: input.description,
  });

  return {
    content: [
      {
        type: 'text',
        text: JSON.stringify(
          {
            message: `Collection "${result.name}" created successfully`,
            collection: {
              id: result.id,
              name: result.name,
              description: result.description,
              created_at: result.created_at,
            },
          },
          null,
          2
        ),
      },
    ],
  };
}

async function handleAddToCollection(args: unknown) {
  const input = AddToCollectionInput.parse(args);
  const result = await client.addToCollection(input.collection_id, {
    chunk_id: input.chunk_id,
    notes: input.notes,
  });

  return {
    content: [
      {
        type: 'text',
        text: JSON.stringify(
          {
            message: 'Chunk added to collection successfully',
            item: {
              id: result.id,
              chunk_id: result.chunk_id,
              notes: result.notes,
              chunk_content: result.chunk_content,
              added_at: result.added_at,
            },
          },
          null,
          2
        ),
      },
    ],
  };
}

async function handleSynthesize(args: unknown) {
  const input = SynthesizeInput.parse(args);

  try {
    const result = await client.synthesize({
      collection_id: input.collection_id,
      prompt: input.prompt,
      format: input.format,
      save_as_report: input.save_as_report,
      report_title: input.report_title,
      project_id: input.project_id,
    });

    const response: Record<string, unknown> = {
      synthesis: result.content,
      citations: result.citations,
    };

    // Include report_id if saved as report
    if (result.report_id) {
      response.report_id = result.report_id;
      response.message = `Synthesis saved as report "${input.report_title}"`;
    }

    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify(response, null, 2),
        },
      ],
    };
  } catch (error) {
    if (error instanceof TraceLabAPIError && error.statusCode === 404) {
      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify(
              {
                error: 'Synthesize endpoint not available',
                message:
                  'The synthesize endpoint is not yet implemented. Use export_collection to get the raw chunks instead.',
                suggestion:
                  'Export the collection and synthesize the content manually using the chunks.',
              },
              null,
              2
            ),
          },
        ],
        isError: true,
      };
    }
    throw error;
  }
}

async function handleCreateReport(args: unknown) {
  const input = CreateReportInput.parse(args);

  if (!input.collection_id && !input.chunk_ids) {
    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify(
            {
              error: 'Invalid input',
              message: 'Either collection_id or chunk_ids must be provided.',
            },
            null,
            2
          ),
        },
      ],
      isError: true,
    };
  }

  const result = await client.createReport({
    title: input.title,
    collection_id: input.collection_id,
    chunk_ids: input.chunk_ids,
    project_id: input.project_id,
    prompt: input.prompt,
    format: input.format,
  });

  return {
    content: [
      {
        type: 'text',
        text: JSON.stringify(
          {
            message: `Report "${result.title}" created successfully`,
            report: {
              id: result.id,
              title: result.title,
              status: result.status,
              tokens_used: result.tokens_used,
              created_at: result.created_at,
              content_preview: result.content.substring(0, 500) + (result.content.length > 500 ? '...' : ''),
              citations: result.citations,
            },
          },
          null,
          2
        ),
      },
    ],
  };
}

async function handleListReports(args: unknown) {
  const input = ListReportsInput.parse(args);
  const result = await client.listReports(
    input.page,
    input.page_size,
    input.project_id,
    input.status
  );

  return {
    content: [
      {
        type: 'text',
        text: JSON.stringify(
          {
            reports: result.items.map((r) => ({
              id: r.id,
              title: r.title,
              status: r.status,
              report_type: r.report_type,
              tokens_used: r.tokens_used,
              chunk_count: r.chunk_count,
              project_id: r.project_id,
              created_at: r.created_at,
            })),
            pagination: {
              page: result.page,
              page_size: result.page_size,
              total: result.total,
            },
          },
          null,
          2
        ),
      },
    ],
  };
}

async function handleGetReport(args: unknown) {
  const input = GetReportInput.parse(args);
  const result = await client.getReport(input.report_id);

  return {
    content: [
      {
        type: 'text',
        text: JSON.stringify(
          {
            id: result.id,
            title: result.title,
            content: result.content,
            status: result.status,
            report_type: result.report_type,
            tokens_used: result.tokens_used,
            chunk_count: result.chunk_count,
            project_id: result.project_id,
            prompt: result.prompt,
            citations: result.citations,
            sources: result.sources.map((s) => ({
              id: s.id,
              source_type: s.source_type,
              source_id: s.source_id,
              added_at: s.added_at,
            })),
            created_at: result.created_at,
            updated_at: result.updated_at,
          },
          null,
          2
        ),
      },
    ],
  };
}

async function handleExportReport(args: unknown) {
  const input = ExportReportInput.parse(args);
  const markdown = await client.exportReport(input.report_id);

  return {
    content: [
      {
        type: 'text',
        text: markdown,
      },
    ],
  };
}

async function handleUploadDocument(args: unknown) {
  const input = UploadDocumentInput.parse(args);

  // Validate base64 content (basic check)
  try {
    const decoded = Buffer.from(input.content, 'base64');
    if (decoded.length === 0) {
      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify(
              {
                error: 'Invalid content',
                message: 'Base64 content decodes to empty data',
              },
              null,
              2
            ),
          },
        ],
        isError: true,
      };
    }
  } catch {
    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify(
            {
              error: 'Invalid base64',
              message: 'Content must be valid base64 encoded data',
            },
            null,
            2
          ),
        },
      ],
      isError: true,
    };
  }

  const result = await client.uploadDocument({
    name: input.name,
    content: input.content,
    content_type: input.content_type,
    project_id: input.project_id,
    description: input.description,
  });

  return {
    content: [
      {
        type: 'text',
        text: JSON.stringify(
          {
            message: `Document "${result.name}" uploaded successfully`,
            document: {
              id: result.id,
              name: result.name,
              project_id: result.project_id,
              file_type: result.file_type,
              file_size: result.file_size,
              mime_type: result.mime_type,
              processed: result.processed,
              validation_status: result.validation_status,
              created_at: result.created_at,
            },
            next_steps: [
              `Document ID: ${result.id}`,
              'The document is now queued for processing (parsing, PII redaction, chunking, embedding).',
              `To process immediately, call POST /api/v1/documents/${result.id}/process`,
              'Once processed, the document will be searchable via search_knowledge.',
            ],
          },
          null,
          2
        ),
      },
    ],
  };
}

async function handleGetDocumentContent(args: unknown) {
  const input = GetDocumentContentInput.parse(args);

  // Fetch document metadata if requested
  let documentMeta: { name: string; file_type?: string; word_count?: number; chunk_count?: number } | undefined;
  if (input.include_metadata) {
    const doc = await client.getDocument(input.document_id);
    documentMeta = {
      name: doc.name,
      file_type: doc.file_type,
      word_count: doc.word_count,
      chunk_count: doc.chunk_count,
    };
  }

  // Fetch chunks with pagination
  const chunksResponse = await client.getDocumentChunks(
    input.document_id,
    input.page,
    input.page_size
  );

  // Assemble content from chunks
  const content = chunksResponse.data
    .sort((a, b) => a.chunk_index - b.chunk_index)
    .map((chunk) => chunk.content)
    .join('\n\n');

  const response: Record<string, unknown> = {
    document_id: input.document_id,
    content,
    pagination: {
      page: chunksResponse.pagination.page,
      page_size: chunksResponse.pagination.page_size,
      total_chunks: chunksResponse.pagination.total,
      total_pages: chunksResponse.pagination.pages,
      has_more: chunksResponse.pagination.page < chunksResponse.pagination.pages,
    },
  };

  if (documentMeta) {
    response.metadata = documentMeta;
  }

  // Provide continuation hint for large documents
  if (chunksResponse.pagination.page < chunksResponse.pagination.pages) {
    response.continuation = {
      message: `Document has more content. Call get_document_content with page=${chunksResponse.pagination.page + 1} to continue.`,
      next_page: chunksResponse.pagination.page + 1,
    };
  }

  return {
    content: [
      {
        type: 'text',
        text: JSON.stringify(response, null, 2),
      },
    ],
  };
}

// Mission-authoring field names — kept in one place so create/update stay in sync.
const MISSION_AUTHORING_FIELD_NAMES = [
  'background',
  'focus',
  'references',
  'required_entities',
  'excluded_entities',
  'expected_output_schema',
  'coverage_thresholds',
  'validation_thresholds',
  'deliverable_format',
  'max_loops',
  'min_loops',
  'constraints',
] as const;

function pickAuthoringFields(
  input: Record<string, unknown>
): Record<string, unknown> {
  const picked: Record<string, unknown> = {};
  for (const key of MISSION_AUTHORING_FIELD_NAMES) {
    if (input[key] !== undefined) picked[key] = input[key];
  }
  return picked;
}

// Mission handlers
async function handleCreateMission(args: unknown) {
  const input = CreateMissionInput.parse(args);
  const result = await client.createMission({
    mission_id: input.mission_id,
    title: input.title,
    objective: input.objective,
    success_criteria: input.success_criteria,
    project_id: input.project_id,
    deliverables: input.deliverables,
    tags: input.tags,
    ...pickAuthoringFields(input),
  });

  return {
    content: [
      {
        type: 'text',
        text: JSON.stringify(
          {
            message: `Mission "${result.mission_id}" created successfully`,
            mission: {
              id: result.id,
              mission_id: result.mission_id,
              title: result.title,
              objective: result.objective,
              status: result.status,
              created_at: result.created_at,
            },
          },
          null,
          2
        ),
      },
    ],
  };
}

// T41.4 — bytes above which heavy-blob fields are summarized in slim mode.
// Matches the Python serializer's _LARGE_BLOB_THRESHOLD_BYTES so REST and
// MCP responses agree on what counts as "too big to inline".
const LARGE_BLOB_THRESHOLD_BYTES = 5_000;

interface TrimSummary {
  _trimmed: true;
  field: string;
  byte_size: number;
  hint: string;
  preview?: string;
}

function summarizeBlob(value: unknown, fieldName: string): TrimSummary {
  const serialized = JSON.stringify(value) ?? '';
  return {
    _trimmed: true,
    field: fieldName,
    byte_size: Buffer.byteLength(serialized, 'utf8'),
    hint: 'Pass include_execution_metadata=true to get_mission to fetch the full payload.',
  };
}

function maybeSummarizeBlob<T>(
  value: T | null | undefined,
  fieldName: string
): T | TrimSummary | null | undefined {
  if (value === null || value === undefined) return value;
  if (typeof value === 'string' && value.length === 0) return value;
  if (typeof value === 'object' && value !== null && Object.keys(value).length === 0)
    return value;
  const serialized = JSON.stringify(value) ?? '';
  if (Buffer.byteLength(serialized, 'utf8') <= LARGE_BLOB_THRESHOLD_BYTES) return value;
  return summarizeBlob(value, fieldName);
}

function maybeSummarizeMarkdown(
  value: string | null | undefined
): string | TrimSummary | null | undefined {
  if (value === null || value === undefined || value === '') return value;
  if (Buffer.byteLength(value, 'utf8') <= LARGE_BLOB_THRESHOLD_BYTES) return value;
  const preview = value.slice(0, 500) + (value.length > 500 ? '...' : '');
  return {
    _trimmed: true,
    field: 'result_markdown',
    byte_size: Buffer.byteLength(value, 'utf8'),
    preview,
    hint: 'Pass include_execution_metadata=true to get_mission to fetch the full markdown.',
  };
}

export async function handleListMissions(args: unknown) {
  const input = ListMissionsInput.parse(args);
  const result = await client.listMissions(
    input.page,
    input.page_size,
    input.status,
    input.project_id
  );

  // T41.4: list responses are always slim — N×full was the original payload
  // bomb. Agents who need full per-mission detail call get_mission with
  // include_execution_metadata=true. The api-client list shape doesn't
  // surface execution_metadata/result_protocol/result_markdown anyway, so
  // the field set here is implicitly trim already.
  return {
    content: [
      {
        type: 'text',
        text: JSON.stringify(
          {
            missions: result.data.map((m) => ({
              id: m.id,
              mission_id: m.mission_id,
              title: m.title,
              status: m.status,
              project_id: m.project_id,
              created_at: m.created_at,
              // Mission-authoring fields (T40.1/T41.2) — small enough to
              // always include so agents can inspect contract-authoring
              // state without a follow-up get_mission call.
              background: m.background,
              focus: m.focus,
              references: m.references,
              required_entities: m.required_entities,
              excluded_entities: m.excluded_entities,
              expected_output_schema: m.expected_output_schema,
              coverage_thresholds: m.coverage_thresholds,
              validation_thresholds: m.validation_thresholds,
              deliverable_format: m.deliverable_format,
              max_loops: m.max_loops,
              min_loops: m.min_loops,
              constraints: m.constraints,
            })),
            pagination: result.pagination,
          },
          null,
          2
        ),
      },
    ],
  };
}

export async function handleGetMission(args: unknown) {
  const input = GetMissionInput.parse(args);
  const result = await client.getMission(input.mission_id);

  // T41.4: slim by default; opt into the full payload via the explicit flag.
  const slim = !input.include_execution_metadata;
  const executionMetadata = slim
    ? maybeSummarizeBlob(result.execution_metadata, 'execution_metadata')
    : result.execution_metadata;
  const resultProtocol = slim
    ? maybeSummarizeBlob(
        result.result_protocol as Record<string, unknown> | null | undefined,
        'result_protocol'
      )
    : result.result_protocol;
  const resultMarkdown = slim
    ? maybeSummarizeMarkdown(result.result_markdown)
    : result.result_markdown;

  return {
    content: [
      {
        type: 'text',
        text: JSON.stringify(
          {
            id: result.id,
            mission_id: result.mission_id,
            title: result.title,
            objective: result.objective,
            success_criteria: result.success_criteria,
            status: result.status,
            project_id: result.project_id,
            context: result.context,
            deliverables: result.deliverables,
            research_phases: result.research_phases,
            tags: result.tags,
            metadata: result.metadata,
            // Mission-authoring fields (T40.1/T41.2). REST returns these but
            // the previous hand-rolled response shape stripped them, leaving
            // MCP agents with no visibility into contract-authoring state.
            background: result.background,
            focus: result.focus,
            references: result.references,
            required_entities: result.required_entities,
            excluded_entities: result.excluded_entities,
            expected_output_schema: result.expected_output_schema,
            coverage_thresholds: result.coverage_thresholds,
            validation_thresholds: result.validation_thresholds,
            deliverable_format: result.deliverable_format,
            max_loops: result.max_loops,
            min_loops: result.min_loops,
            constraints: result.constraints,
            queued_at: result.queued_at,
            started_at: result.started_at,
            completed_at: result.completed_at,
            deepsearch_job_id: result.deepsearch_job_id,
            // Heavy blobs go through the T41.4 trim path above.
            execution_metadata: executionMetadata,
            result_document_ids: result.result_document_ids,
            result_report_id: result.result_report_id,
            result_markdown: resultMarkdown,
            result_protocol: resultProtocol,
            error_message: result.error_message,
            created_at: result.created_at,
            updated_at: result.updated_at,
          },
          null,
          2
        ),
      },
    ],
  };
}

async function handleUpdateMission(args: unknown) {
  const input = UpdateMissionInput.parse(args);

  // Build update payload with only provided fields
  const updateData: Record<string, unknown> = {};
  // T41.5: project_id can now be re-parented via update_mission. Server
  // returns 404 if the target project doesn't exist.
  if (input.project_id !== undefined) updateData.project_id = input.project_id;
  if (input.title !== undefined) updateData.title = input.title;
  if (input.objective !== undefined) updateData.objective = input.objective;
  if (input.success_criteria !== undefined) updateData.success_criteria = input.success_criteria;
  if (input.deliverables !== undefined) updateData.deliverables = input.deliverables;
  if (input.tags !== undefined) updateData.tags = input.tags;
  if (input.context !== undefined) updateData.context = input.context;
  Object.assign(updateData, pickAuthoringFields(input));

  const result = await client.updateMission(input.mission_id, updateData);

  return {
    content: [
      {
        type: 'text',
        text: JSON.stringify(
          {
            message: `Mission "${result.mission_id}" updated successfully`,
            mission: {
              id: result.id,
              mission_id: result.mission_id,
              title: result.title,
              objective: result.objective,
              success_criteria: result.success_criteria,
              status: result.status,
              project_id: result.project_id,
              deliverables: result.deliverables,
              tags: result.tags,
              updated_at: result.updated_at,
            },
          },
          null,
          2
        ),
      },
    ],
  };
}

async function handlePreviewMissionContract(args: unknown) {
  const input = PreviewMissionContractInput.parse(args);
  const preview = await client.previewMissionContract(input.mission_id);
  return {
    content: [
      {
        type: 'text',
        text: JSON.stringify(
          {
            message: `Contract preview for mission "${preview.mission_id}"`,
            preview: {
              mission_id: preview.mission_id,
              mission_uuid: preview.mission_uuid,
              project_id: preview.project_id ?? null,
              contract_version: preview.contract_version,
              compiler_revision: preview.compiler_revision,
              fidelity: preview.fidelity,
              named_entities: preview.named_entities,
              objectives_count: preview.objectives.length,
              evidence_slots_count: preview.evidence_slots.length,
              acceptance_checks_count: preview.acceptance_checks.length,
              deliverable_schemas_count: preview.deliverable_schemas.length,
              coverage_thresholds: preview.coverage_thresholds,
              validation_thresholds: preview.validation_thresholds,
            },
            full: preview,
          },
          null,
          2
        ),
      },
    ],
  };
}

async function handleSubmitMission(args: unknown) {
  const input = SubmitMissionInput.parse(args);

  const result = await client.submitMission(input.mission_id);

  return {
    content: [
      {
        type: 'text',
        text: JSON.stringify(
          {
            message: `Mission ${result.mission_id} submitted for execution`,
            status: result.status,
            mode: result.mode,
            mission_id: result.mission_id,
            uuid: result.uuid,
            job_id: result.job_id,
          },
          null,
          2
        ),
      },
    ],
  };
}

async function handleGetMissionStatus(args: unknown) {
  const input = GetMissionStatusInput.parse(args);
  const result = await client.getMissionStatus(input.mission_id);

  return {
    content: [
      {
        type: 'text',
        text: JSON.stringify(
          {
            mission_id: input.mission_id,
            status: result.status,
            progress: result.progress_percent,
            current_phase: result.current_phase,
            attempts: result.deepsearch_attempt_count,
            materialization_pending: result.materialization_pending,
            materialization_status: result.materialization_status,
            materialization_attempt_count: result.materialization_attempt_count,
            materialization_error: result.materialization_error,
            search_ready: result.search_ready,
            error_message: result.error_message,
          },
          null,
          2
        ),
      },
    ],
  };
}

// ─────────────────────────────────────────────────────────────────────────
// T41.7 cluster dispatchers
//
// Each visible MCP tool is a cluster that dispatches by its `action` param to
// the existing per-action handlers above. Handlers consume `args` directly
// and run their own Zod parse — the per-handler input schemas use Zod's
// default `.strip()` mode, so the extra `action` key is harmlessly removed.
//
// The cluster dispatchers do not re-validate `action` with Zod because we
// want a friendlier error message ("Unknown action 'foo' for tracelab_mission;
// valid: create, list, get, update") than Zod produces by default. A bad
// action is a recoverable agent mistake — surface it cleanly.
// ─────────────────────────────────────────────────────────────────────────

interface ClusterArgs {
  action?: unknown;
}

function getAction(args: unknown): string {
  return typeof (args as ClusterArgs)?.action === 'string'
    ? ((args as ClusterArgs).action as string)
    : '';
}

function unknownAction(tool: string, action: string, valid: readonly string[]) {
  return {
    content: [
      {
        type: 'text',
        text: `Unknown action "${action}" for ${tool}. Valid actions: ${valid.join(', ')}`,
      },
    ],
    isError: true,
  };
}

const SEARCH_ACTIONS = ['knowledge'] as const;
export async function handleTracelabSearch(args: unknown) {
  const action = getAction(args);
  switch (action) {
    case 'knowledge':
      return await handleSearchKnowledge(args);
    default:
      return unknownAction('tracelab_search', action, SEARCH_ACTIONS);
  }
}

const PROJECT_ACTIONS = ['list', 'create', 'update', 'stats'] as const;
export async function handleTracelabProject(args: unknown) {
  const action = getAction(args);
  switch (action) {
    case 'list':
      return await handleListProjects(args);
    case 'create':
      return await handleCreateProject(args);
    case 'update':
      return await handleUpdateProject(args);
    case 'stats':
      return await handleGetProjectStats(args);
    default:
      return unknownAction('tracelab_project', action, PROJECT_ACTIONS);
  }
}

const COLLECTION_ACTIONS = [
  'list',
  'get',
  'export',
  'create',
  'add',
  'synthesize',
] as const;
export async function handleTracelabCollection(args: unknown) {
  const action = getAction(args);
  switch (action) {
    case 'list':
      return await handleListCollections();
    case 'get':
      return await handleGetCollection(args);
    case 'export':
      return await handleExportCollection(args);
    case 'create':
      return await handleCreateCollection(args);
    case 'add':
      return await handleAddToCollection(args);
    case 'synthesize':
      return await handleSynthesize(args);
    default:
      return unknownAction('tracelab_collection', action, COLLECTION_ACTIONS);
  }
}

const REPORT_ACTIONS = ['create', 'list', 'get', 'export'] as const;
export async function handleTracelabReport(args: unknown) {
  const action = getAction(args);
  switch (action) {
    case 'create':
      return await handleCreateReport(args);
    case 'list':
      return await handleListReports(args);
    case 'get':
      return await handleGetReport(args);
    case 'export':
      return await handleExportReport(args);
    default:
      return unknownAction('tracelab_report', action, REPORT_ACTIONS);
  }
}

const DOCUMENT_ACTIONS = ['upload', 'get_content'] as const;
export async function handleTracelabDocument(args: unknown) {
  const action = getAction(args);
  switch (action) {
    case 'upload':
      return await handleUploadDocument(args);
    case 'get_content':
      return await handleGetDocumentContent(args);
    default:
      return unknownAction('tracelab_document', action, DOCUMENT_ACTIONS);
  }
}

const MISSION_ACTIONS = ['create', 'list', 'get', 'update'] as const;
export async function handleTracelabMission(args: unknown) {
  const action = getAction(args);
  switch (action) {
    case 'create':
      return await handleCreateMission(args);
    case 'list':
      return await handleListMissions(args);
    case 'get':
      return await handleGetMission(args);
    case 'update':
      return await handleUpdateMission(args);
    default:
      return unknownAction('tracelab_mission', action, MISSION_ACTIONS);
  }
}

const MISSION_EXECUTION_ACTIONS = ['submit', 'status', 'preview'] as const;
export async function handleTracelabMissionExecution(args: unknown) {
  const action = getAction(args);
  switch (action) {
    case 'submit':
      return await handleSubmitMission(args);
    case 'status':
      return await handleGetMissionStatus(args);
    case 'preview':
      return await handlePreviewMissionContract(args);
    default:
      return unknownAction(
        'tracelab_mission_execution',
        action,
        MISSION_EXECUTION_ACTIONS
      );
  }
}

// Exported for the parity test in index.test.ts — every legacy tool name in
// LEGACY_TO_CLUSTER must map to a (cluster, action) pair where action ∈ the
// cluster's action enum. Compile-time guarded by the readonly tuples above.
export const CLUSTER_ACTIONS = {
  tracelab_search: SEARCH_ACTIONS,
  tracelab_project: PROJECT_ACTIONS,
  tracelab_collection: COLLECTION_ACTIONS,
  tracelab_report: REPORT_ACTIONS,
  tracelab_document: DOCUMENT_ACTIONS,
  tracelab_mission: MISSION_ACTIONS,
  tracelab_mission_execution: MISSION_EXECUTION_ACTIONS,
} as const;

/**
 * Resolve the auth credential the MCP client will use against TraceLab.
 *
 * Order of precedence (highest first):
 *   1. `TRACELAB_TOKEN` env var (JWT, kept for CI / scripted automation).
 *   2. `TRACELAB_API_KEY` env var (legacy `tl_*` API key, also CI/automation).
 *   3. Stored credential at `~/.config/tracelab-mcp/credentials.json`,
 *      provided its `apiBaseUrl` matches the effective base URL.
 *   4. Interactive device-code flow (T42.4) — prints a URL + short code to
 *      stderr, polls until the human approves on the web /device page,
 *      stores the minted key in the credential store for next launch.
 *
 * Step 4 is what makes a fresh `npx @aquex/tracelab-mcp` install work
 * without the user pasting any key into env first.
 */
async function resolveAuthConfig(
  store: CredentialStore = new CredentialStore()
): Promise<TraceLabConfig> {
  if (process.env.TRACELAB_TOKEN) {
    return { baseUrl, token: process.env.TRACELAB_TOKEN };
  }
  if (process.env.TRACELAB_API_KEY) {
    return { baseUrl, apiKey: process.env.TRACELAB_API_KEY };
  }

  const stored = await store.read();
  if (stored && stored.apiBaseUrl === baseUrl) {
    return { baseUrl, apiKey: stored.key };
  }
  if (stored) {
    console.error(
      `[tracelab-mcp] Stored credential targets ${stored.apiBaseUrl}, ` +
        `but TRACELAB_API_URL is ${baseUrl}. Re-running device login.`
    );
  }

  const version = await readPackageVersion();
  let token: { accessToken: string; keyId: string; label: string };
  try {
    token = await runDeviceCodeFlow({ baseUrl, version });
  } catch (err) {
    if (err instanceof DeviceCodeError) {
      console.error(
        `[tracelab-mcp] Device login failed (${err.code}): ${err.message}`
      );
    } else {
      console.error('[tracelab-mcp] Device login failed:', err);
    }
    throw err;
  }

  const record: StoredCredential = {
    apiBaseUrl: baseUrl,
    key: token.accessToken,
    keyId: token.keyId,
    label: token.label,
    issuedAt: new Date().toISOString(),
  };
  await store.write(record);
  console.error(
    `[tracelab-mcp] Logged in as "${token.label}". Credential saved to ${store.path}.`
  );
  return { baseUrl, apiKey: token.accessToken };
}

// Create and run the server
async function main() {
  const config = await resolveAuthConfig();
  client = new TraceLabClient(config);

  const server = new Server(
    {
      name: 'tracelab-mcp',
      version: '1.0.0',
    },
    {
      capabilities: {
        tools: {},
      },
    }
  );

  // Handle list tools request
  server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: TOOLS,
  }));

  // Handle tool calls
  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args } = request.params;

    try {
      // T41.7: 7 cluster tools. Each cluster dispatches by `action`
      // internally (see handleTracelab* functions above). Hard-cut from
      // the prior 24 flat tools — no deprecation period (rationale:
      // pre-v1 npm publish, internal use, cmos-mcp precedent). Legacy
      // tool name → cluster mapping documented in LEGACY_TO_CLUSTER.
      switch (name) {
        case 'tracelab_search':
          return await handleTracelabSearch(args);
        case 'tracelab_project':
          return await handleTracelabProject(args);
        case 'tracelab_collection':
          return await handleTracelabCollection(args);
        case 'tracelab_report':
          return await handleTracelabReport(args);
        case 'tracelab_document':
          return await handleTracelabDocument(args);
        case 'tracelab_mission':
          return await handleTracelabMission(args);
        case 'tracelab_mission_execution':
          return await handleTracelabMissionExecution(args);
        default: {
          // T41.7 hard-cut: surface the migration target if an agent
          // calls a legacy tool name. The mapping is exported for tests.
          const migrated = LEGACY_TO_CLUSTER[name];
          if (migrated) {
            return {
              content: [
                {
                  type: 'text',
                  text:
                    `Tool "${name}" was renamed in T41.7 (sprint-41). ` +
                    `Use ${migrated.tool}(action="${migrated.action}", ...) ` +
                    `with the same parameters. See packages/tracelab-mcp/CHANGELOG ` +
                    `or cmos/contracts/mission-authoring-contract.md for the ` +
                    `full legacy → cluster mapping.`,
                },
              ],
              isError: true,
            };
          }
          return {
            content: [
              {
                type: 'text',
                text: `Unknown tool: ${name}`,
              },
            ],
            isError: true,
          };
        }
      }
    } catch (error) {
      if (error instanceof z.ZodError) {
        return {
          content: [
            {
              type: 'text',
              text: `Invalid input: ${error.errors.map((e) => `${e.path.join('.')}: ${e.message}`).join(', ')}`,
            },
          ],
          isError: true,
        };
      }

      if (error instanceof TraceLabAPIError) {
        return {
          content: [
            {
              type: 'text',
              text: `API Error (${error.statusCode}): ${error.message}${error.response ? '\nDetails: ' + JSON.stringify(error.response) : ''}`,
            },
          ],
          isError: true,
        };
      }

      const message = error instanceof Error ? error.message : String(error);
      return {
        content: [
          {
            type: 'text',
            text: `Error: ${message}`,
          },
        ],
        isError: true,
      };
    }
  });

  // Run with stdio transport
  const transport = new StdioServerTransport();
  await server.connect(transport);

  // Log startup to stderr (stdout is for MCP protocol)
  console.error('TraceLab MCP server started');
  console.error(`API URL: ${baseUrl}`);
  console.error(
    `Auth: ${
      process.env.TRACELAB_TOKEN
        ? 'JWT Token (env)'
        : process.env.TRACELAB_API_KEY
          ? 'API Key (env)'
          : 'API Key (device-login credential store)'
    }`
  );
}

// Only kick the server when this module is invoked as the bin entry. Vitest
// imports the module to test handler exports — auto-running main() there
// would hang on the device-code flow with no env credentials configured.
if (!process.env.VITEST) {
  main().catch((error) => {
    console.error('Failed to start server:', error);
    process.exit(1);
  });
}
