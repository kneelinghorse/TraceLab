#!/usr/bin/env node
/**
 * TraceLab MCP Server
 *
 * Provides 21 tools for AI agents to perform complete research-to-output loops
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
 * 17. create_mission - Create a new research mission
 * 18. list_missions - Browse existing missions
 * 19. get_mission - Get mission details
 * 20. submit_mission - Submit mission for DeepSearch execution
 * 21. get_mission_status - Get current mission status
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
        description: 'Search for relevant knowledge chunks using semantic search. Returns scored results with content excerpts.',
        inputSchema: {
            type: 'object',
            properties: {
                query: {
                    type: 'string',
                    description: 'The search query - can be a question or topic',
                },
                project_id: {
                    type: 'string',
                    description: 'Optional: Filter by project UUID',
                },
                limit: {
                    type: 'number',
                    description: 'Maximum results to return (1-50, default: 10)',
                    minimum: 1,
                    maximum: 50,
                },
                tags: {
                    type: 'array',
                    items: { type: 'string' },
                    description: 'Optional: Filter by tags (OR semantics)',
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
    // Mission tools
    {
        name: 'create_mission',
        description: 'Create a new research mission. Missions define research objectives that can be executed by DeepSearch.',
        inputSchema: {
            type: 'object',
            properties: {
                mission_id: {
                    type: 'string',
                    description: 'Unique mission identifier (e.g., "B17.1")',
                },
                title: {
                    type: 'string',
                    description: 'Short title for the mission',
                },
                objective: {
                    type: 'string',
                    description: 'Primary research objective',
                },
                success_criteria: {
                    type: 'array',
                    items: { type: 'string' },
                    description: 'Measurable criteria for success',
                },
                project_id: {
                    type: 'string',
                    description: 'Optional: UUID of project to associate with',
                },
                deliverables: {
                    type: 'array',
                    items: { type: 'string' },
                    description: 'Optional: Expected deliverables',
                },
                tags: {
                    type: 'array',
                    items: { type: 'string' },
                    description: 'Optional: Tags for categorization',
                },
            },
            required: ['mission_id', 'title', 'objective', 'success_criteria'],
        },
    },
    {
        name: 'list_missions',
        description: 'List missions with optional filtering by status or project.',
        inputSchema: {
            type: 'object',
            properties: {
                status: {
                    type: 'string',
                    enum: ['draft', 'queued', 'in_progress', 'completed', 'blocked', 'cancelled'],
                    description: 'Optional: Filter by status',
                },
                project_id: {
                    type: 'string',
                    description: 'Optional: Filter by project UUID',
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
        name: 'get_mission',
        description: 'Get detailed information about a mission including execution status and results.',
        inputSchema: {
            type: 'object',
            properties: {
                mission_id: {
                    type: 'string',
                    description: 'UUID of the mission',
                },
            },
            required: ['mission_id'],
        },
    },
    {
        name: 'submit_mission',
        description: 'Submit a mission for execution. In worker mode, sets status to queued for DeepSearch worker to pick up. In HTTP mode, submits directly to DeepSearch API.',
        inputSchema: {
            type: 'object',
            properties: {
                mission_id: {
                    type: 'string',
                    description: 'UUID of the mission to submit',
                },
            },
            required: ['mission_id'],
        },
    },
    {
        name: 'get_mission_status',
        description: 'Get the current execution status of a mission.',
        inputSchema: {
            type: 'object',
            properties: {
                mission_id: {
                    type: 'string',
                    description: 'UUID of the mission',
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
// Mission input schemas
const CreateMissionInput = z.object({
    mission_id: z.string().min(1),
    title: z.string().min(1),
    objective: z.string().min(1),
    success_criteria: z.array(z.string()).min(1),
    project_id: z.string().uuid().optional(),
    deliverables: z.array(z.string()).optional(),
    tags: z.array(z.string()).optional(),
});
const ListMissionsInput = z.object({
    status: z.enum(['draft', 'queued', 'in_progress', 'completed', 'blocked', 'cancelled']).optional(),
    project_id: z.string().uuid().optional(),
    page: z.number().min(1).optional().default(1),
    page_size: z.number().min(1).max(100).optional().default(20),
});
const GetMissionInput = z.object({
    mission_id: z.string().uuid(),
});
const SubmitMissionInput = z.object({
    mission_id: z.string().uuid(),
});
const GetMissionStatusInput = z.object({
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
async function handleSubmitMission(args) {
    const input = SubmitMissionInput.parse(args);
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
                case 'create_mission':
                    return await handleCreateMission(args);
                case 'list_missions':
                    return await handleListMissions(args);
                case 'get_mission':
                    return await handleGetMission(args);
                case 'submit_mission':
                    return await handleSubmitMission(args);
                case 'get_mission_status':
                    return await handleGetMissionStatus(args);
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