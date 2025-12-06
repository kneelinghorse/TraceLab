/**
 * TraceLab API Client
 *
 * Handles all HTTP communication with the TraceLab API.
 * Supports both JWT token and API key authentication.
 */
export interface TraceLabConfig {
    baseUrl: string;
    token?: string;
    apiKey?: string;
}
export interface RetrievalQuery {
    query: string;
    top_k?: number;
    project_id?: string;
    document_id?: string;
    source_type?: string;
    document_types?: string[];
    source_types?: string[];
    date_from?: string;
    date_to?: string;
    tags?: string[];
}
export interface RetrievedChunk {
    chunk_id: string;
    content: string;
    document_id?: string;
    project_id?: string;
    chunk_index?: number;
    source_type?: string;
    document_type?: string;
    collection_date?: string;
    tags?: string[];
    score: number;
    quality_score?: number;
    quality_gates_passed?: number;
    quality_gates_total?: number;
}
export interface RetrievalResponse {
    results: RetrievedChunk[];
}
export interface Project {
    id: string;
    name: string;
    description?: string;
    research_type?: string;
    methodology?: string;
    status?: string;
    quality_score?: number;
    created_at: string;
    updated_at: string;
}
export interface PaginatedResponse<T> {
    data: T[];
    pagination: {
        page: number;
        page_size: number;
        total: number;
        pages: number;
    };
}
export interface Collection {
    id: string;
    name: string;
    description?: string;
    created_at: string;
    updated_at: string;
    item_count: number;
}
export interface CollectionItem {
    id: string;
    collection_id: string;
    chunk_id: string;
    notes?: string;
    added_at: string;
    chunk_content?: string;
    document_id?: string;
}
export interface CollectionDetail extends Collection {
    items: CollectionItem[];
}
export interface CollectionListResponse {
    data: Collection[];
    total: number;
}
export interface CollectionCreate {
    name: string;
    description?: string;
}
export interface CollectionItemCreate {
    chunk_id: string;
    notes?: string;
}
export interface SynthesizeRequest {
    collection_id: string;
    prompt?: string;
    format?: 'markdown' | 'summary' | 'report';
}
export interface SynthesizeResponse {
    content: string;
    citations: Array<{
        chunk_id: string;
        document_id?: string;
        excerpt: string;
    }>;
}
export declare class TraceLabAPIError extends Error {
    statusCode: number;
    response?: unknown | undefined;
    constructor(message: string, statusCode: number, response?: unknown | undefined);
}
export declare class TraceLabClient {
    private baseUrl;
    private headers;
    constructor(config: TraceLabConfig);
    private request;
    /**
     * Search for relevant chunks via semantic search
     */
    searchKnowledge(query: RetrievalQuery): Promise<RetrievalResponse>;
    /**
     * List all projects
     */
    listProjects(page?: number, pageSize?: number, search?: string): Promise<PaginatedResponse<Project>>;
    /**
     * List all collections
     */
    listCollections(): Promise<CollectionListResponse>;
    /**
     * Get a collection with its chunks
     */
    getCollection(collectionId: string): Promise<CollectionDetail>;
    /**
     * Export a collection as markdown
     */
    exportCollection(collectionId: string): Promise<string>;
    /**
     * Create a new collection
     */
    createCollection(data: CollectionCreate): Promise<Collection>;
    /**
     * Add a chunk to a collection
     */
    addToCollection(collectionId: string, data: CollectionItemCreate): Promise<CollectionItem>;
    /**
     * Synthesize content from a collection
     * Note: This endpoint may not be available until B14.2 is implemented
     */
    synthesize(data: SynthesizeRequest): Promise<SynthesizeResponse>;
}
//# sourceMappingURL=api-client.d.ts.map