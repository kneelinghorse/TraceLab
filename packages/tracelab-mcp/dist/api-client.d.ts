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
export interface ProjectCreate {
    name: string;
    description?: string;
    research_type?: string;
    methodology?: string;
    status?: string;
}
export interface ProjectUpdate {
    name?: string;
    description?: string;
    research_type?: string;
    methodology?: string;
    status?: string;
}
export interface ProjectStats {
    project_id: string;
    name: string;
    document_count: number;
    chunk_count: number;
    report_count: number;
    total_tokens: number;
    last_updated?: string;
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
    save_as_report?: boolean;
    report_title?: string;
    project_id?: string;
}
export interface SynthesizeResponse {
    content: string;
    citations: Array<{
        chunk_id: string;
        document_id?: string;
        excerpt: string;
    }>;
    report_id?: string;
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
export interface DocumentUploadRequest {
    name: string;
    content: string;
    content_type: string;
    project_id: string;
    description?: string;
}
export interface DocumentUploadResponse {
    id: string;
    name: string;
    project_id: string;
    file_type: string;
    file_size: number;
    mime_type: string;
    processed: boolean;
    validation_status: string;
    created_at: string;
}
export interface DocumentChunk {
    id: string;
    document_id: string;
    chunk_index: number;
    content: string;
    embedding_id?: string;
    token_count?: number;
    start_char?: number;
    end_char?: number;
    created_at: string;
}
export interface Document {
    id: string;
    project_id: string;
    name: string;
    file_type?: string;
    file_size?: number;
    mime_type?: string;
    source_type?: string;
    uploaded_at: string;
    processed: boolean;
    chunked: boolean;
    embedded: boolean;
    validation_status: string;
    chunk_count?: number;
    total_tokens?: number;
    word_count?: number;
    preview?: string;
    chunks?: DocumentChunk[];
}
export interface DocumentChunksResponse {
    data: DocumentChunk[];
    pagination: {
        page: number;
        page_size: number;
        total: number;
        pages: number;
    };
}
export interface MissionReference {
    title: string;
    [key: string]: unknown;
}
export interface MissionAuthoringFields {
    background?: string | null;
    focus?: string | null;
    references?: MissionReference[] | null;
    required_entities?: string[] | null;
    excluded_entities?: string[] | null;
    expected_output_schema?: Record<string, unknown> | null;
    coverage_thresholds?: Record<string, unknown> | null;
    validation_thresholds?: Record<string, unknown> | null;
    deliverable_format?: string | null;
    max_loops?: number | null;
    min_loops?: number | null;
    constraints?: string[] | null;
}
export interface Mission extends MissionAuthoringFields {
    id: string;
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
    research_depth?: 'baseline' | 'deep' | 'alpha';
    status: 'draft' | 'queued' | 'in_progress' | 'completed' | 'blocked' | 'cancelled' | 'validation_failed';
    queued_at?: string;
    started_at?: string;
    completed_at?: string;
    deepsearch_job_id?: string;
    execution_metadata?: Record<string, unknown>;
    result_document_ids?: string[];
    result_report_id?: string;
    result_markdown?: string;
    result_protocol?: Record<string, unknown>;
    error_message?: string;
    created_at: string;
    updated_at: string;
    created_by?: string;
}
export interface MissionCreate extends MissionAuthoringFields {
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
    research_depth?: 'baseline' | 'deep' | 'alpha';
    status?: string;
}
export interface MissionUpdate extends MissionAuthoringFields {
    title?: string;
    objective?: string;
    success_criteria?: string[];
    context?: Record<string, unknown>;
    deliverables?: string[];
    research_phases?: Record<string, unknown>;
    tags?: string[];
    metadata?: Record<string, unknown>;
    research_depth?: 'baseline' | 'deep' | 'alpha';
    status?: string;
}
export interface MissionListResponse {
    data: Mission[];
    pagination: {
        page: number;
        page_size: number;
        total: number;
        pages: number;
    };
}
export interface MissionSubmitResponse {
    status: string;
    mode: string;
    mission_id: string;
    uuid: string;
    message: string;
    job_id?: string;
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
    /**
     * Upload a document to TraceLab
     * Accepts base64 encoded content and sends as multipart/form-data
     */
    uploadDocument(data: DocumentUploadRequest): Promise<DocumentUploadResponse>;
    /**
     * Create a new project
     */
    createProject(data: ProjectCreate): Promise<Project>;
    /**
     * Update an existing project
     */
    updateProject(projectId: string, data: ProjectUpdate): Promise<Project>;
    /**
     * Get aggregated statistics for a project
     */
    getProjectStats(projectId: string): Promise<ProjectStats>;
    /**
     * Get a document by ID with metadata and optional chunks
     */
    getDocument(documentId: string): Promise<Document>;
    /**
     * Get paginated chunks for a document
     */
    getDocumentChunks(documentId: string, page?: number, pageSize?: number): Promise<DocumentChunksResponse>;
    /**
     * List missions with optional filtering
     */
    listMissions(page?: number, pageSize?: number, status?: string, projectId?: string): Promise<MissionListResponse>;
    /**
     * Get a single mission by ID
     */
    getMission(missionId: string): Promise<Mission>;
    /**
     * Create a new mission
     */
    createMission(data: MissionCreate): Promise<Mission>;
    /**
     * Update an existing mission
     */
    updateMission(missionId: string, data: MissionUpdate): Promise<Mission>;
    /**
     * Submit a mission for execution (sets status to queued)
     * In worker mode, the DeepSearch worker will poll and pick it up
     */
    submitMission(missionId: string): Promise<MissionSubmitResponse>;
    /**
     * Get the current status of a mission
     */
    getMissionStatus(missionId: string): Promise<{
        status: string;
        progress?: number;
    }>;
}
//# sourceMappingURL=api-client.d.ts.map