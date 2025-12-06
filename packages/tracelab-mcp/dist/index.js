#!/usr/bin/env node
/**
 * TraceLab MCP Server
 *
 * Provides 8 tools for AI agents to perform complete research-to-output loops
 * against TraceLab's knowledge base.
 *
 * Tools:
 * 1. search_knowledge - Semantic search across the knowledge base
 * 2. list_projects - Browse available projects
 * 3. list_collections - View existing collections
 * 4. get_collection - Get chunks in a collection
 * 5. export_collection - Export collection as markdown
 * 6. create_collection - Create new collection for research
 * 7. add_to_collection - Add chunk to collection
 * 8. synthesize - Generate summary/report from collected chunks
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
        description: 'Generate a summary or report from a collection of chunks. Includes citations.',
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
            },
            required: ['collection_id'],
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
        });
        return {
            content: [
                {
                    type: 'text',
                    text: JSON.stringify({
                        synthesis: result.content,
                        citations: result.citations,
                    }, null, 2),
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