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
export interface ReportCreate {
    title: string;
    collection_id?: string;
    chunk_ids?: string[];
    project_id?: string;
    prompt?: string;
    format?: 'summary' | 'report' | 'bullets' | 'markdown';
}
export interface ReportCitation {
    chunk_id: string;
    document_id?: string;
    excerpt: string;
}
export interface Report {
    id: string;
    title: string;
    content: string;
    citations: ReportCitation[];
    tokens_used: number;
    status: string;
    created_at: string;
}
export interface ReportSource {
    id: string;
    report_id: string;
    source_type: string;
    source_id: string;
    added_at: string;
}
export interface ReportDetail extends Report {
    project_id?: string;
    report_type: string;
    prompt?: string;
    chunk_count: number;
    sources: ReportSource[];
    updated_at: string;
}
export interface ReportListItem {
    id: string;
    title: string;
    status: string;
    report_type: string;
    tokens_used: number;
    chunk_count: number;
    project_id?: string;
    created_at: string;
    updated_at: string;
}
export interface ReportListResponse {
    items: ReportListItem[];
    total: number;
    page: number;
    page_size: number;
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
    /**
     * Create a new report by synthesizing from collection or chunks
     */
    createReport(data: ReportCreate): Promise<Report>;
    /**
     * List reports with optional filtering
     */
    listReports(page?: number, pageSize?: number, projectId?: string, status?: string): Promise<ReportListResponse>;
    /**
     * Get a single report with full details
     */
    getReport(reportId: string): Promise<ReportDetail>;
    /**
     * Export a report as markdown text
     * For MVP, returns the content field directly
     */
    exportReport(reportId: string): Promise<string>;
}
//# sourceMappingURL=api-client.d.ts.map