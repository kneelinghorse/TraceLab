#!/usr/bin/env node
/**
 * TraceLab MCP Server
 *
 * Provides 23 tools for AI agents to perform complete research-to-output loops
 * against TraceLab's knowledge base.
 *
 * Tools:
 * 1. search_knowledge - Semantic search across the knowledge base
 * 2. list_projects - Browse available projects
 * 3. create_project - Create a new project
 * 4. update_project - Update project metadata
 * 5. get_project_stats - Get project statistics
 * 6. list_collections - View existing collections
 * 7. get_collection - Get chunks in a collection
 * 8. export_collection - Export collection as markdown
 * 9. create_collection - Create new collection for research
 * 10. add_to_collection - Add chunk to collection
 * 11. synthesize - Generate summary/report from collected chunks
 * 12. create_report - Create a persistent report from collection/chunks
 * 13. list_reports - Browse existing reports
 * 14. get_report - Get full report details
 * 15. export_report - Export report as markdown
 * 16. upload_document - Upload a new document to TraceLab
 * 17. get_document_content - Retrieve full document content with pagination
 * 18. create_mission - Create a new research mission
 * 19. list_missions - Browse existing missions
 * 20. get_mission - Get mission details
 * 21. update_mission - Update mission details (title, objective, research_depth, etc.)
 * 22. submit_mission - Submit mission for DeepSearch execution
 * 23. get_mission_status - Get current mission status
 */
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { CallToolRequestSchema, ListToolsRequestSchema, } from '@modelcontextprotocol/sdk/types.js';
import { z } from 'zod';
import { TraceLabClient, TraceLabAPIError, } from './api-client.js';
// Environment configuration
const config = {
    baseUrl: process.env.TRACELAB_API_URL || 'http://localhost:8000',
    token: process.env.TRACELAB_TOKEN,
    apiKey: process.env.TRACELAB_API_KEY,
};
const client = new TraceLabClient(config);
// Tool definitions
const TOOLS = [
    {
        name: 'search_knowledge',
        description: 'Find relevant information in the TraceLab knowledge base using semantic search. Returns ranked chunks with content excerpts and document references. Use get_document_content to read full documents. Related tools: get_document_content, add_to_collection.',
        inputSchema: {
            type: 'object',
            properties: {
                query: {
                    type: 'string',
                    description: 'Natural language search query. Example: "user onboarding best practices", "competitive analysis methods", "interview synthesis techniques"',
                },
                project_id: {
                    type: 'string',
                    description: 'Scope search to a specific project UUID. Get project IDs from list_projects.',
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
            required: ['query'],
        },
    },
    {
        name: 'list_projects',
        description: 'List all available projects in TraceLab. Projects organize documents and research.',
        inputSchema: {
            type: 'object',
            properties: {
                page: {
                    type: 'number',
                    description: 'Page number (1-indexed, default: 1)',
                    minimum: 1,
                },
                page_size: {
                    type: 'number',
                    description: 'Results per page (1-100, default: 20)',
                    minimum: 1,
                    maximum: 100,
                },
                search: {
                    type: 'string',
                    description: 'Optional: Search by project name',
                },
            },
        },
    },
    {
        name: 'create_project',
        description: 'Create a new project to organize documents and research.',
        inputSchema: {
            type: 'object',
            properties: {
                name: {
                    type: 'string',
                    description: 'Name for the project (required)',
                },
                description: {
                    type: 'string',
                    description: 'Optional: Description of the project',
                },
                research_type: {
                    type: 'string',
                    enum: ['strategic', 'tactical', 'generative', 'evaluative'],
                    description: 'Optional: Type of research',
                },
                methodology: {
                    type: 'string',
                    enum: ['qualitative', 'quantitative', 'mixed'],
                    description: 'Optional: Research methodology',
                },
            },
            required: ['name'],
        },
    },
    {
        name: 'update_project',
        description: 'Update an existing project\'s metadata.',
        inputSchema: {
            type: 'object',
            properties: {
                project_id: {
                    type: 'string',
                    description: 'UUID of the project to update',
                },
                name: {
                    type: 'string',
                    description: 'Optional: New name for the project',
                },
                description: {
                    type: 'string',
                    description: 'Optional: New description',
                },
                research_type: {
                    type: 'string',
                    enum: ['strategic', 'tactical', 'generative', 'evaluative'],
                    description: 'Optional: Type of research',
                },
                methodology: {
                    type: 'string',
                    enum: ['qualitative', 'quantitative', 'mixed'],
                    description: 'Optional: Research methodology',
                },
                status: {
                    type: 'string',
                    enum: ['active', 'archived', 'completed'],
                    description: 'Optional: Project status',
                },
            },
            required: ['project_id'],
        },
    },
    {
        name: 'get_project_stats',
        description: 'Get aggregated statistics for a project, including document count, chunk count, report count, and total tokens.',
        inputSchema: {
            type: 'object',
            properties: {
                project_id: {
                    type: 'string',
                    description: 'UUID of the project',
                },
            },
            required: ['project_id'],
        },
    },
    {
        name: 'list_collections',
        description: 'List all research collections. Collections group related chunks for synthesis.',
        inputSchema: {
            type: 'object',
            properties: {},
        },
    },
    {
        name: 'get_collection',
        description: 'Get detailed information about a collection including all its chunks.',
        inputSchema: {
            type: 'object',
            properties: {
                collection_id: {
                    type: 'string',
                    description: 'UUID of the collection',
                },
            },
            required: ['collection_id'],
        },
    },
    {
        name: 'export_collection',
        description: 'Export a collection as a markdown document with all chunks and metadata.',
        inputSchema: {
            type: 'object',
            properties: {
                collection_id: {
                    type: 'string',
                    description: 'UUID of the collection to export',
                },
            },
            required: ['collection_id'],
        },
    },
    {
        name: 'create_collection',
        description: 'Create a new collection to organize research chunks. Use this before adding chunks.',
        inputSchema: {
            type: 'object',
            properties: {
                name: {
                    type: 'string',
                    description: 'Name for the collection (max 255 chars)',
                    maxLength: 255,
                },
                description: {
                    type: 'string',
                    description: 'Optional description (max 2000 chars)',
                    maxLength: 2000,
                },
            },
            required: ['name'],
        },
    },
    {
        name: 'add_to_collection',
        description: 'Add a knowledge chunk to a collection. Use chunk_id from search results.',
        inputSchema: {
            type: 'object',
            properties: {
                collection_id: {
                    type: 'string',
                    description: 'UUID of the collection',
                },
                chunk_id: {
                    type: 'string',
                    description: 'UUID of the chunk to add (from search results)',
                },
                notes: {
                    type: 'string',
                    description: 'Optional notes about why this chunk is relevant',
                    maxLength: 2000,
                },
            },
            required: ['collection_id', 'chunk_id'],
        },
    },
    {
        name: 'synthesize',
        description: 'Generate a summary or report from a collection of chunks. Includes citations. Optionally save the result as a persistent report.',
        inputSchema: {
            type: 'object',
            properties: {
                collection_id: {
                    type: 'string',
                    description: 'UUID of the collection to synthesize',
                },
                prompt: {
                    type: 'string',
                    description: 'Optional: Custom prompt for synthesis (e.g., "Summarize the key findings")',
                },
                format: {
                    type: 'string',
                    enum: ['markdown', 'summary', 'report'],
                    description: 'Output format (default: markdown)',
                },
                save_as_report: {
                    type: 'boolean',
                    description: 'Optional: If true, persist the synthesis result as a report (default: false)',
                },
                report_title: {
                    type: 'string',
                    description: 'Optional: Title for the report (required if save_as_report is true)',
                    maxLength: 255,
                },
                project_id: {
                    type: 'string',
                    description: 'Optional: UUID of project to associate the report with',
                },
            },
            required: ['collection_id'],
        },
    },
    {
        name: 'create_report',
        description: 'Create a new report by synthesizing content from a collection or specific chunks. Reports are persistent artifacts that survive across sessions.',
        inputSchema: {
            type: 'object',
            properties: {
                title: {
                    type: 'string',
                    description: 'Title for the report (max 255 chars)',
                    maxLength: 255,
                },
                collection_id: {
                    type: 'string',
                    description: 'UUID of collection to synthesize (mutually exclusive with chunk_ids)',
                },
                chunk_ids: {
                    type: 'array',
                    items: { type: 'string' },
                    description: 'UUIDs of specific chunks to synthesize (mutually exclusive with collection_id)',
                },
                project_id: {
                    type: 'string',
                    description: 'Optional: UUID of project to associate report with',
                },
                prompt: {
                    type: 'string',
                    description: 'Optional: Custom synthesis prompt (max 2000 chars)',
                    maxLength: 2000,
                },
                format: {
                    type: 'string',
                    enum: ['summary', 'report', 'bullets', 'markdown'],
                    description: 'Output format (default: summary)',
                },
            },
            required: ['title'],
        },
    },
    {
        name: 'list_reports',
        description: 'Browse existing reports with optional filtering by project or status.',
        inputSchema: {
            type: 'object',
            properties: {
                project_id: {
                    type: 'string',
                    description: 'Optional: Filter by project UUID',
                },
                status: {
                    type: 'string',
                    enum: ['draft', 'final'],
                    description: 'Optional: Filter by status',
                },
                page: {
                    type: 'number',
                    description: 'Page number (1-indexed, default: 1)',
                    minimum: 1,
                },
                page_size: {
                    type: 'number',
                    description: 'Results per page (1-100, default: 20)',
                    minimum: 1,
                    maximum: 100,
                },
            },
        },
    },
    {
        name: 'get_report',
        description: 'Get full report details including content, citations, and source references.',
        inputSchema: {
            type: 'object',
            properties: {
                report_id: {
                    type: 'string',
                    description: 'UUID of the report',
                },
            },
            required: ['report_id'],
        },
    },
    {
        name: 'export_report',
        description: 'Export a report as markdown text. Returns the synthesized content directly.',
        inputSchema: {
            type: 'object',
            properties: {
                report_id: {
                    type: 'string',
                    description: 'UUID of the report to export',
                },
            },
            required: ['report_id'],
        },
    },
    {
        name: 'upload_document',
        description: 'Upload a new document to TraceLab for ingestion. Supports PDF, DOCX, PPTX, CSV, XLSX, Markdown, TXT, JSON, XML, and YAML files. The document will be processed through the ingestion pipeline (parsing, PII redaction, chunking, embedding).',
        inputSchema: {
            type: 'object',
            properties: {
                name: {
                    type: 'string',
                    description: 'Filename or document name (e.g., "research-paper.pdf")',
                },
                content: {
                    type: 'string',
                    description: 'Base64 encoded file content',
                },
                content_type: {
                    type: 'string',
                    description: 'MIME type of the file (e.g., "application/pdf", "text/markdown", "text/plain")',
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
                    description: 'UUID of the project to add the document to',
                },
                description: {
                    type: 'string',
                    description: 'Optional description of the document',
                },
            },
            required: ['name', 'content', 'content_type', 'project_id'],
        },
    },
    {
        name: 'get_document_content',
        description: 'Read the full text content of a document. Returns assembled text from document chunks with optional metadata. Use pagination for large documents (continuation hints provided). Get document_id from search_knowledge results or list documents by project. Related tools: search_knowledge, upload_document.',
        inputSchema: {
            type: 'object',
            properties: {
                document_id: {
                    type: 'string',
                    description: 'UUID of the document. Get from search_knowledge results (document_id field) or from document upload response.',
                },
                page: {
                    type: 'number',
                    description: 'Page number for large documents (1-indexed, default: 1). Response includes has_more flag and next_page hint for continuation.',
                    minimum: 1,
                },
                page_size: {
                    type: 'number',
                    description: 'Chunks per page (1-100, default: 20). Reduce for very long documents or to stay within context limits.',
                    minimum: 1,
                    maximum: 100,
                },
                include_metadata: {
                    type: 'boolean',
                    description: 'Include document metadata (name, file_type, word_count, chunk_count) in response. Default: true. Set false for content-only retrieval.',
                },
            },
            required: ['document_id'],
        },
    },
    // Mission tools
    {
        name: 'create_mission',
        description: 'Create a new research mission for DeepSearch execution. After creation, use update_mission to modify details or submit_mission to queue for execution. Related tools: update_mission, submit_mission, get_mission, list_missions.',
        inputSchema: {
            type: 'object',
            properties: {
                mission_id: {
                    type: 'string',
                    description: 'Unique mission identifier. Example: "R001", "B17.1", "market-analysis-q4"',
                },
                title: {
                    type: 'string',
                    description: 'Short descriptive title. Example: "Q4 Market Analysis", "User Interview Synthesis"',
                },
                objective: {
                    type: 'string',
                    description: 'Clear research objective describing what to find or analyze. Example: "Identify key market trends and competitive positioning in enterprise SaaS"',
                },
                success_criteria: {
                    type: 'array',
                    items: { type: 'string' },
                    description: 'Measurable outcomes that define success. Example: ["Identify 5+ market trends", "Analyze 3+ competitors", "Produce executive summary"]',
                },
                project_id: {
                    type: 'string',
                    description: 'UUID of project to associate with. Links mission results to project knowledge base.',
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
                research_depth: {
                    type: 'string',
                    enum: ['baseline', 'deep', 'alpha'],
                    description: 'Controls research thoroughness and duration. BASELINE (8-12 min): Thorough reports with 50-60 sources across multiple loops — the standard tier for most research. DEEP (20-25 min): Higher-rigor research with 30-40 carefully vetted sources, stricter quality gates, minimum 5 loops — use when you need higher confidence. ALPHA (1+ hour): Maximum-rigor with ~20 highly scrutinized sources, very strict quality gates that may reject research if evidence is insufficient — use only when precision and source authority are critical. Default: baseline. Can be changed later via update_mission or at submission via submit_mission.',
                    default: 'baseline',
                },
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
            required: ['mission_id', 'title', 'objective', 'success_criteria'],
        },
    },
    {
        name: 'list_missions',
        description: 'Browse existing research missions with optional filtering. Returns mission summaries including status and research_depth. Use get_mission for full details. Related tools: get_mission, create_mission.',
        inputSchema: {
            type: 'object',
            properties: {
                status: {
                    type: 'string',
                    enum: ['draft', 'queued', 'in_progress', 'completed', 'blocked', 'cancelled', 'validation_failed'],
                    description: 'Filter by execution status. draft: Not yet submitted. queued: Waiting for execution. in_progress: Currently executing. completed: Finished successfully. blocked: Awaiting resolution. cancelled: Terminated. validation_failed: Synthesized output but failed coverage/structural gates (reviewable artifact, distinct from blocked).',
                },
                project_id: {
                    type: 'string',
                    description: 'Filter to missions associated with this project UUID.',
                },
                page: {
                    type: 'number',
                    description: 'Page number for pagination (1-indexed, default: 1)',
                    minimum: 1,
                },
                page_size: {
                    type: 'number',
                    description: 'Number of missions per page (1-100, default: 20)',
                    minimum: 1,
                    maximum: 100,
                },
            },
        },
    },
    {
        name: 'get_mission',
        description: 'Retrieve full mission details including objective, success criteria, research_depth, execution status, and results. Use this to check mission progress or access completed research outputs. Related tools: list_missions, update_mission, submit_mission.',
        inputSchema: {
            type: 'object',
            properties: {
                mission_id: {
                    type: 'string',
                    description: 'UUID of the mission to retrieve. Get mission UUIDs from list_missions or create_mission response.',
                },
            },
            required: ['mission_id'],
        },
    },
    {
        name: 'update_mission',
        description: 'Modify an existing mission before submission. Change research_depth to control thoroughness, refine the contract-authoring fields (background/focus/references/entities/schemas/thresholds/constraints), or update the objective and success criteria. Only draft missions can be modified. Related tools: create_mission, get_mission, submit_mission.',
        inputSchema: {
            type: 'object',
            properties: {
                mission_id: {
                    type: 'string',
                    description: 'UUID of the mission to update. Get from list_missions or create_mission response.',
                },
                title: {
                    type: 'string',
                    description: 'New mission title. Example: "Updated Market Analysis"',
                },
                objective: {
                    type: 'string',
                    description: 'Revised research objective. Be specific about what to find or analyze.',
                },
                success_criteria: {
                    type: 'array',
                    items: { type: 'string' },
                    description: 'New measurable success criteria. Example: ["Identify 10+ data points", "Compare 5 competitors"]',
                },
                research_depth: {
                    type: 'string',
                    enum: ['baseline', 'deep', 'alpha'],
                    description: 'Change research thoroughness. BASELINE (8-12 min): Thorough reports with 50-60 sources — standard default. DEEP (20-25 min): 30-40 vetted sources, stricter quality gates, min 5 loops. ALPHA (1+ hour): ~20 scrutinized sources, may reject if evidence insufficient.',
                },
                deliverables: {
                    type: 'array',
                    items: { type: 'string' },
                    description: 'Updated expected outputs. Example: ["Executive summary", "Data appendix"]',
                },
                tags: {
                    type: 'array',
                    items: { type: 'string' },
                    description: 'New categorization tags. Example: ["priority", "q4-research"]',
                },
                context: {
                    type: 'object',
                    description: 'DEPRECATED: kept for back-compat. Prefer the explicit authoring fields (background, focus, references, required_entities, excluded_entities, expected_output_schema, coverage_thresholds, validation_thresholds, deliverable_format, max_loops, min_loops, constraints). Authors who still write to context["constraints"] will keep working during the transition.',
                },
                background: {
                    type: 'string',
                    description: 'Replace the mission\'s background prose. See create_mission for full semantics.',
                },
                focus: {
                    type: 'string',
                    description: 'Replace the narrow focus framing. See create_mission for full semantics.',
                },
                references: {
                    type: 'array',
                    items: { type: 'object', properties: { title: { type: 'string' } }, required: ['title'] },
                    description: 'Replace the seed reference list. Each entry at minimum {title}.',
                },
                required_entities: {
                    type: 'array',
                    items: { type: 'string' },
                    description: 'Replace the list of entities that MUST appear in synthesis.',
                },
                excluded_entities: {
                    type: 'array',
                    items: { type: 'string' },
                    description: 'Replace the list of entities that MUST NOT appear in synthesis.',
                },
                expected_output_schema: {
                    type: 'object',
                    description: 'Replace the DeepSearch OutputSchema describing the deliverable shape.',
                },
                coverage_thresholds: {
                    type: 'object',
                    description: 'Replace coverage gate thresholds. Example: {"min_sources": 12}',
                },
                validation_thresholds: {
                    type: 'object',
                    description: 'Replace validation gate thresholds. Example: {"structural": 0.85}',
                },
                deliverable_format: {
                    type: 'string',
                    description: 'Replace the output rendering hint.',
                },
                max_loops: {
                    type: 'integer',
                    minimum: 1,
                    description: 'Replace the upper bound on DeepSearch research loop count.',
                },
                min_loops: {
                    type: 'integer',
                    minimum: 1,
                    description: 'Replace the lower bound on DeepSearch research loop count.',
                },
                constraints: {
                    type: 'array',
                    items: { type: 'string' },
                    description: 'Replace the author-level constraints list.',
                },
            },
            required: ['mission_id'],
        },
    },
    {
        name: 'submit_mission',
        description: 'Queue a mission for DeepSearch execution. The mission transitions from draft to queued status. Optionally override research_depth at submission time. Monitor progress with get_mission. Related tools: create_mission, update_mission, get_mission, get_mission_status.',
        inputSchema: {
            type: 'object',
            properties: {
                mission_id: {
                    type: 'string',
                    description: 'UUID of the mission to submit for execution. Must be in draft status.',
                },
                research_depth: {
                    type: 'string',
                    enum: ['baseline', 'deep', 'alpha'],
                    description: 'Override mission research_depth at submission. BASELINE (8-12 min): Thorough reports with 50-60 sources — standard default. DEEP (20-25 min): 30-40 vetted sources, stricter quality gates, min 5 loops. ALPHA (1+ hour): ~20 scrutinized sources, may reject if evidence insufficient. If not provided, uses the depth set on the mission.',
                },
            },
            required: ['mission_id'],
        },
    },
    {
        name: 'get_mission_status',
        description: 'Check execution progress of a submitted mission. Returns current status (queued/in_progress/completed/blocked) and progress percentage. Lightweight alternative to get_mission for status polling. Related tools: submit_mission, get_mission.',
        inputSchema: {
            type: 'object',
            properties: {
                mission_id: {
                    type: 'string',
                    description: 'UUID of the mission to check. Get from submit_mission response or list_missions.',
                },
            },
            required: ['mission_id'],
        },
    },
    {
        name: 'preview_mission_contract',
        description: 'Preview the DeepSearch contract that would be compiled from this mission without submitting it. Returns named_entities, objectives, evidence_slots, acceptance_checks, deliverable_schemas, coverage_thresholds, and validation_thresholds — useful for iterating on authoring fields (background, focus, required_entities, expected_output_schema, thresholds) before spending a paid research loop. Related tools: update_mission, submit_mission.',
        inputSchema: {
            type: 'object',
            properties: {
                mission_id: {
                    type: 'string',
                    description: 'UUID of the mission to preview. Mission may be in any status — preview is read-only.',
                },
            },
            required: ['mission_id'],
        },
    },
];
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
}).refine((data) => !data.save_as_report || data.report_title, {
    message: 'report_title is required when save_as_report is true',
    path: ['report_title'],
});
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
};
const CreateMissionInput = z.object({
    mission_id: z.string().min(1),
    title: z.string().min(1),
    objective: z.string().min(1),
    success_criteria: z.array(z.string()).min(1),
    project_id: z.string().uuid().optional(),
    deliverables: z.array(z.string()).optional(),
    tags: z.array(z.string()).optional(),
    research_depth: z.enum(['baseline', 'deep', 'alpha']).optional().default('baseline'),
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
});
const UpdateMissionInput = z.object({
    mission_id: z.string().uuid(),
    title: z.string().min(1).optional(),
    objective: z.string().min(1).optional(),
    success_criteria: z.array(z.string()).optional(),
    research_depth: z.enum(['baseline', 'deep', 'alpha']).optional(),
    deliverables: z.array(z.string()).optional(),
    tags: z.array(z.string()).optional(),
    // DEPRECATED: prefer explicit authoring fields below. Kept for back-compat.
    context: z.record(z.unknown()).optional(),
    ...MissionAuthoringFieldsSchema,
});
const SubmitMissionInput = z.object({
    mission_id: z.string().uuid(),
    research_depth: z.enum(['baseline', 'deep', 'alpha']).optional(),
});
const GetMissionStatusInput = z.object({
    mission_id: z.string().uuid(),
});
const PreviewMissionContractInput = z.object({
    mission_id: z.string().uuid(),
});
// Tool handlers
async function handleSearchKnowledge(args) {
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
                text: JSON.stringify({
                    query: input.query,
                    total_results: chunks.length,
                    results: chunks,
                }, null, 2),
            },
        ],
    };
}
async function handleListProjects(args) {
    const input = ListProjectsInput.parse(args);
    const result = await client.listProjects(input.page, input.page_size, input.search);
    return {
        content: [
            {
                type: 'text',
                text: JSON.stringify({
                    projects: result.data.map((p) => ({
                        id: p.id,
                        name: p.name,
                        description: p.description,
                        status: p.status,
                        research_type: p.research_type,
                    })),
                    pagination: result.pagination,
                }, null, 2),
            },
        ],
    };
}
async function handleCreateProject(args) {
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
                text: JSON.stringify({
                    message: `Project "${result.name}" created successfully`,
                    project: {
                        id: result.id,
                        name: result.name,
                        description: result.description,
                        status: result.status,
                        research_type: result.research_type,
                        created_at: result.created_at,
                    },
                }, null, 2),
            },
        ],
    };
}
async function handleUpdateProject(args) {
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
                text: JSON.stringify({
                    message: `Project "${result.name}" updated successfully`,
                    project: {
                        id: result.id,
                        name: result.name,
                        description: result.description,
                        status: result.status,
                        research_type: result.research_type,
                        updated_at: result.updated_at,
                    },
                }, null, 2),
            },
        ],
    };
}
async function handleGetProjectStats(args) {
    const input = GetProjectStatsInput.parse(args);
    const result = await client.getProjectStats(input.project_id);
    return {
        content: [
            {
                type: 'text',
                text: JSON.stringify({
                    project_id: result.project_id,
                    name: result.name,
                    document_count: result.document_count,
                    chunk_count: result.chunk_count,
                    report_count: result.report_count,
                    total_tokens: result.total_tokens,
                    last_updated: result.last_updated,
                }, null, 2),
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
                text: JSON.stringify({
                    collections: result.data.map((c) => ({
                        id: c.id,
                        name: c.name,
                        description: c.description,
                        item_count: c.item_count,
                        created_at: c.created_at,
                    })),
                    total: result.total,
                }, null, 2),
            },
        ],
    };
}
async function handleGetCollection(args) {
    const input = GetCollectionInput.parse(args);
    const result = await client.getCollection(input.collection_id);
    return {
        content: [
            {
                type: 'text',
                text: JSON.stringify({
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
                }, null, 2),
            },
        ],
    };
}
async function handleExportCollection(args) {
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
async function handleCreateCollection(args) {
    const input = CreateCollectionInput.parse(args);
    const result = await client.createCollection({
        name: input.name,
        description: input.description,
    });
    return {
        content: [
            {
                type: 'text',
                text: JSON.stringify({
                    message: `Collection "${result.name}" created successfully`,
                    collection: {
                        id: result.id,
                        name: result.name,
                        description: result.description,
                        created_at: result.created_at,
                    },
                }, null, 2),
            },
        ],
    };
}
async function handleAddToCollection(args) {
    const input = AddToCollectionInput.parse(args);
    const result = await client.addToCollection(input.collection_id, {
        chunk_id: input.chunk_id,
        notes: input.notes,
    });
    return {
        content: [
            {
                type: 'text',
                text: JSON.stringify({
                    message: 'Chunk added to collection successfully',
                    item: {
                        id: result.id,
                        chunk_id: result.chunk_id,
                        notes: result.notes,
                        chunk_content: result.chunk_content,
                        added_at: result.added_at,
                    },
                }, null, 2),
            },
        ],
    };
}
async function handleSynthesize(args) {
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
        const response = {
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
    }
    catch (error) {
        if (error instanceof TraceLabAPIError && error.statusCode === 404) {
            return {
                content: [
                    {
                        type: 'text',
                        text: JSON.stringify({
                            error: 'Synthesize endpoint not available',
                            message: 'The synthesize endpoint is not yet implemented. Use export_collection to get the raw chunks instead.',
                            suggestion: 'Export the collection and synthesize the content manually using the chunks.',
                        }, null, 2),
                    },
                ],
                isError: true,
            };
        }
        throw error;
    }
}
async function handleCreateReport(args) {
    const input = CreateReportInput.parse(args);
    if (!input.collection_id && !input.chunk_ids) {
        return {
            content: [
                {
                    type: 'text',
                    text: JSON.stringify({
                        error: 'Invalid input',
                        message: 'Either collection_id or chunk_ids must be provided.',
                    }, null, 2),
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
                text: JSON.stringify({
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
                }, null, 2),
            },
        ],
    };
}
async function handleListReports(args) {
    const input = ListReportsInput.parse(args);
    const result = await client.listReports(input.page, input.page_size, input.project_id, input.status);
    return {
        content: [
            {
                type: 'text',
                text: JSON.stringify({
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
                }, null, 2),
            },
        ],
    };
}
async function handleGetReport(args) {
    const input = GetReportInput.parse(args);
    const result = await client.getReport(input.report_id);
    return {
        content: [
            {
                type: 'text',
                text: JSON.stringify({
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
                }, null, 2),
            },
        ],
    };
}
async function handleExportReport(args) {
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
async function handleUploadDocument(args) {
    const input = UploadDocumentInput.parse(args);
    // Validate base64 content (basic check)
    try {
        const decoded = Buffer.from(input.content, 'base64');
        if (decoded.length === 0) {
            return {
                content: [
                    {
                        type: 'text',
                        text: JSON.stringify({
                            error: 'Invalid content',
                            message: 'Base64 content decodes to empty data',
                        }, null, 2),
                    },
                ],
                isError: true,
            };
        }
    }
    catch {
        return {
            content: [
                {
                    type: 'text',
                    text: JSON.stringify({
                        error: 'Invalid base64',
                        message: 'Content must be valid base64 encoded data',
                    }, null, 2),
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
                text: JSON.stringify({
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
                }, null, 2),
            },
        ],
    };
}
async function handleGetDocumentContent(args) {
    const input = GetDocumentContentInput.parse(args);
    // Fetch document metadata if requested
    let documentMeta;
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
    const chunksResponse = await client.getDocumentChunks(input.document_id, input.page, input.page_size);
    // Assemble content from chunks
    const content = chunksResponse.data
        .sort((a, b) => a.chunk_index - b.chunk_index)
        .map((chunk) => chunk.content)
        .join('\n\n');
    const response = {
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
];
function pickAuthoringFields(input) {
    const picked = {};
    for (const key of MISSION_AUTHORING_FIELD_NAMES) {
        if (input[key] !== undefined)
            picked[key] = input[key];
    }
    return picked;
}
// Mission handlers
async function handleCreateMission(args) {
    const input = CreateMissionInput.parse(args);
    const result = await client.createMission({
        mission_id: input.mission_id,
        title: input.title,
        objective: input.objective,
        success_criteria: input.success_criteria,
        project_id: input.project_id,
        deliverables: input.deliverables,
        tags: input.tags,
        research_depth: input.research_depth,
        ...pickAuthoringFields(input),
    });
    return {
        content: [
            {
                type: 'text',
                text: JSON.stringify({
                    message: `Mission "${result.mission_id}" created successfully`,
                    mission: {
                        id: result.id,
                        mission_id: result.mission_id,
                        title: result.title,
                        objective: result.objective,
                        status: result.status,
                        research_depth: result.research_depth,
                        created_at: result.created_at,
                    },
                }, null, 2),
            },
        ],
    };
}
async function handleListMissions(args) {
    const input = ListMissionsInput.parse(args);
    const result = await client.listMissions(input.page, input.page_size, input.status, input.project_id);
    return {
        content: [
            {
                type: 'text',
                text: JSON.stringify({
                    missions: result.data.map((m) => ({
                        id: m.id,
                        mission_id: m.mission_id,
                        title: m.title,
                        status: m.status,
                        project_id: m.project_id,
                        created_at: m.created_at,
                    })),
                    pagination: result.pagination,
                }, null, 2),
            },
        ],
    };
}
async function handleGetMission(args) {
    const input = GetMissionInput.parse(args);
    const result = await client.getMission(input.mission_id);
    return {
        content: [
            {
                type: 'text',
                text: JSON.stringify({
                    id: result.id,
                    mission_id: result.mission_id,
                    title: result.title,
                    objective: result.objective,
                    success_criteria: result.success_criteria,
                    status: result.status,
                    research_depth: result.research_depth,
                    project_id: result.project_id,
                    deliverables: result.deliverables,
                    tags: result.tags,
                    queued_at: result.queued_at,
                    started_at: result.started_at,
                    completed_at: result.completed_at,
                    deepsearch_job_id: result.deepsearch_job_id,
                    execution_metadata: result.execution_metadata,
                    result_document_ids: result.result_document_ids,
                    result_report_id: result.result_report_id,
                    error_message: result.error_message,
                    created_at: result.created_at,
                    updated_at: result.updated_at,
                }, null, 2),
            },
        ],
    };
}
async function handleUpdateMission(args) {
    const input = UpdateMissionInput.parse(args);
    // Build update payload with only provided fields
    const updateData = {};
    if (input.title !== undefined)
        updateData.title = input.title;
    if (input.objective !== undefined)
        updateData.objective = input.objective;
    if (input.success_criteria !== undefined)
        updateData.success_criteria = input.success_criteria;
    if (input.research_depth !== undefined)
        updateData.research_depth = input.research_depth;
    if (input.deliverables !== undefined)
        updateData.deliverables = input.deliverables;
    if (input.tags !== undefined)
        updateData.tags = input.tags;
    if (input.context !== undefined)
        updateData.context = input.context;
    Object.assign(updateData, pickAuthoringFields(input));
    const result = await client.updateMission(input.mission_id, updateData);
    return {
        content: [
            {
                type: 'text',
                text: JSON.stringify({
                    message: `Mission "${result.mission_id}" updated successfully`,
                    mission: {
                        id: result.id,
                        mission_id: result.mission_id,
                        title: result.title,
                        objective: result.objective,
                        success_criteria: result.success_criteria,
                        status: result.status,
                        research_depth: result.research_depth,
                        project_id: result.project_id,
                        deliverables: result.deliverables,
                        tags: result.tags,
                        updated_at: result.updated_at,
                    },
                }, null, 2),
            },
        ],
    };
}
async function handlePreviewMissionContract(args) {
    const input = PreviewMissionContractInput.parse(args);
    const preview = await client.previewMissionContract(input.mission_id);
    return {
        content: [
            {
                type: 'text',
                text: JSON.stringify({
                    message: `Contract preview for mission "${preview.mission_id}"`,
                    preview: {
                        mission_id: preview.mission_id,
                        mission_uuid: preview.mission_uuid,
                        project_id: preview.project_id ?? null,
                        named_entities: preview.named_entities,
                        objectives_count: preview.objectives.length,
                        evidence_slots_count: preview.evidence_slots.length,
                        acceptance_checks_count: preview.acceptance_checks.length,
                        deliverable_schemas_count: preview.deliverable_schemas.length,
                        coverage_thresholds: preview.coverage_thresholds,
                        validation_thresholds: preview.validation_thresholds,
                    },
                    full: preview,
                }, null, 2),
            },
        ],
    };
}
async function handleSubmitMission(args) {
    const input = SubmitMissionInput.parse(args);
    // If research_depth override is provided, update the mission first
    if (input.research_depth) {
        await client.updateMission(input.mission_id, {
            research_depth: input.research_depth,
        });
    }
    const result = await client.submitMission(input.mission_id);
    return {
        content: [
            {
                type: 'text',
                text: JSON.stringify({
                    message: `Mission ${result.mission_id} submitted for execution`,
                    status: result.status,
                    mode: result.mode,
                    mission_id: result.mission_id,
                    uuid: result.uuid,
                    job_id: result.job_id,
                    research_depth: input.research_depth || 'unchanged',
                }, null, 2),
            },
        ],
    };
}
async function handleGetMissionStatus(args) {
    const input = GetMissionStatusInput.parse(args);
    const result = await client.getMissionStatus(input.mission_id);
    return {
        content: [
            {
                type: 'text',
                text: JSON.stringify({
                    mission_id: input.mission_id,
                    status: result.status,
                    progress: result.progress,
                }, null, 2),
            },
        ],
    };
}
// Create and run the server
async function main() {
    const server = new Server({
        name: 'tracelab-mcp',
        version: '1.0.0',
    }, {
        capabilities: {
            tools: {},
        },
    });
    // Handle list tools request
    server.setRequestHandler(ListToolsRequestSchema, async () => ({
        tools: TOOLS,
    }));
    // Handle tool calls
    server.setRequestHandler(CallToolRequestSchema, async (request) => {
        const { name, arguments: args } = request.params;
        try {
            switch (name) {
                case 'search_knowledge':
                    return await handleSearchKnowledge(args);
                case 'list_projects':
                    return await handleListProjects(args);
                case 'create_project':
                    return await handleCreateProject(args);
                case 'update_project':
                    return await handleUpdateProject(args);
                case 'get_project_stats':
                    return await handleGetProjectStats(args);
                case 'list_collections':
                    return await handleListCollections();
                case 'get_collection':
                    return await handleGetCollection(args);
                case 'export_collection':
                    return await handleExportCollection(args);
                case 'create_collection':
                    return await handleCreateCollection(args);
                case 'add_to_collection':
                    return await handleAddToCollection(args);
                case 'synthesize':
                    return await handleSynthesize(args);
                case 'create_report':
                    return await handleCreateReport(args);
                case 'list_reports':
                    return await handleListReports(args);
                case 'get_report':
                    return await handleGetReport(args);
                case 'export_report':
                    return await handleExportReport(args);
                case 'upload_document':
                    return await handleUploadDocument(args);
                case 'get_document_content':
                    return await handleGetDocumentContent(args);
                case 'create_mission':
                    return await handleCreateMission(args);
                case 'list_missions':
                    return await handleListMissions(args);
                case 'get_mission':
                    return await handleGetMission(args);
                case 'update_mission':
                    return await handleUpdateMission(args);
                case 'submit_mission':
                    return await handleSubmitMission(args);
                case 'get_mission_status':
                    return await handleGetMissionStatus(args);
                case 'preview_mission_contract':
                    return await handlePreviewMissionContract(args);
                default:
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
        catch (error) {
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
    console.error(`API URL: ${config.baseUrl}`);
    console.error(`Auth: ${config.token ? 'JWT Token' : config.apiKey ? 'API Key' : 'None (unauthenticated)'}`);
}
main().catch((error) => {
    console.error('Failed to start server:', error);
    process.exit(1);
});
//# sourceMappingURL=index.js.map