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

// Report types
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

// Document upload types
export interface DocumentUploadRequest {
  name: string;
  content: string; // base64 encoded file content
  content_type: string; // MIME type
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

// Document retrieval types
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

// Mission types
export interface MissionReference {
  title: string;
  [key: string]: unknown;
}

// Mission-authoring fields consumed by DeepSearch's contract compiler (T40.1/T40.2).
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
  // T41.5: project_id is mutable post-create. Server validates target exists.
  project_id?: string;
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

export class TraceLabAPIError extends Error {
  constructor(
    message: string,
    public statusCode: number,
    public response?: unknown
  ) {
    super(message);
    this.name = 'TraceLabAPIError';
  }
}

export class TraceLabClient {
  private baseUrl: string;
  private headers: Record<string, string>;

  constructor(config: TraceLabConfig) {
    this.baseUrl = config.baseUrl.replace(/\/$/, '');
    this.headers = {
      'Content-Type': 'application/json',
    };

    if (config.token) {
      this.headers['Authorization'] = `Bearer ${config.token}`;
    } else if (config.apiKey) {
      this.headers['X-API-Key'] = config.apiKey;
    }
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;

    const options: RequestInit = {
      method,
      headers: this.headers,
    };

    if (body) {
      options.body = JSON.stringify(body);
    }

    const response = await fetch(url, options);

    if (!response.ok) {
      const text = await response.text();
      let errorBody: unknown;
      try {
        errorBody = JSON.parse(text);
      } catch {
        errorBody = text;
      }

      throw new TraceLabAPIError(
        `API request failed: ${response.status} ${response.statusText}`,
        response.status,
        errorBody
      );
    }

    // Handle non-JSON responses (like markdown exports)
    const contentType = response.headers.get('content-type');
    if (contentType?.includes('text/markdown') || contentType?.includes('text/plain')) {
      const text = await response.text();
      return text as unknown as T;
    }

    const json = await response.json();
    return json as T;
  }

  /**
   * Search for relevant chunks via semantic search
   */
  async searchKnowledge(query: RetrievalQuery): Promise<RetrievalResponse> {
    return this.request<RetrievalResponse>(
      'POST',
      '/api/v1/retrieval/search',
      query
    );
  }

  /**
   * List all projects
   */
  async listProjects(
    page = 1,
    pageSize = 20,
    search?: string
  ): Promise<PaginatedResponse<Project>> {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });
    if (search) {
      params.set('search', search);
    }
    return this.request<PaginatedResponse<Project>>(
      'GET',
      `/api/v1/projects?${params}`
    );
  }

  /**
   * List all collections
   */
  async listCollections(): Promise<CollectionListResponse> {
    return this.request<CollectionListResponse>('GET', '/api/v1/collections');
  }

  /**
   * Get a collection with its chunks
   */
  async getCollection(collectionId: string): Promise<CollectionDetail> {
    return this.request<CollectionDetail>(
      'GET',
      `/api/v1/collections/${collectionId}`
    );
  }

  /**
   * Export a collection as markdown
   */
  async exportCollection(collectionId: string): Promise<string> {
    return this.request<string>(
      'GET',
      `/api/v1/collections/${collectionId}/export`
    );
  }

  /**
   * Create a new collection
   */
  async createCollection(data: CollectionCreate): Promise<Collection> {
    return this.request<Collection>('POST', '/api/v1/collections', data);
  }

  /**
   * Add a chunk to a collection
   */
  async addToCollection(
    collectionId: string,
    data: CollectionItemCreate
  ): Promise<CollectionItem> {
    return this.request<CollectionItem>(
      'POST',
      `/api/v1/collections/${collectionId}/chunks`,
      data
    );
  }

  /**
   * Synthesize content from a collection
   * Note: This endpoint may not be available until B14.2 is implemented
   */
  async synthesize(data: SynthesizeRequest): Promise<SynthesizeResponse> {
    return this.request<SynthesizeResponse>('POST', '/api/v1/synthesize', data);
  }

  /**
   * Create a new report by synthesizing from collection or chunks
   */
  async createReport(data: ReportCreate): Promise<Report> {
    return this.request<Report>('POST', '/api/v1/reports', data);
  }

  /**
   * List reports with optional filtering
   */
  async listReports(
    page = 1,
    pageSize = 20,
    projectId?: string,
    status?: string
  ): Promise<ReportListResponse> {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });
    if (projectId) {
      params.set('project_id', projectId);
    }
    if (status) {
      params.set('status', status);
    }
    return this.request<ReportListResponse>(
      'GET',
      `/api/v1/reports?${params}`
    );
  }

  /**
   * Get a single report with full details
   */
  async getReport(reportId: string): Promise<ReportDetail> {
    return this.request<ReportDetail>('GET', `/api/v1/reports/${reportId}`);
  }

  /**
   * Export a report as markdown text
   * For MVP, returns the content field directly
   */
  async exportReport(reportId: string): Promise<string> {
    const report = await this.getReport(reportId);
    return report.content;
  }

  /**
   * Upload a document to TraceLab
   * Accepts base64 encoded content and sends as multipart/form-data
   */
  async uploadDocument(data: DocumentUploadRequest): Promise<DocumentUploadResponse> {
    const url = `${this.baseUrl}/api/v1/documents/upload?project_id=${encodeURIComponent(data.project_id)}`;

    // Decode base64 content to binary
    const binaryContent = Buffer.from(data.content, 'base64');

    // Create a Blob from the binary content
    const blob = new Blob([binaryContent], { type: data.content_type });

    // Create FormData with the file
    const formData = new FormData();
    formData.append('file', blob, data.name);

    // Build headers without Content-Type (browser sets it with boundary)
    const headers: Record<string, string> = {};
    if (this.headers['Authorization']) {
      headers['Authorization'] = this.headers['Authorization'];
    }
    if (this.headers['X-API-Key']) {
      headers['X-API-Key'] = this.headers['X-API-Key'];
    }

    const response = await fetch(url, {
      method: 'POST',
      headers,
      body: formData,
    });

    if (!response.ok) {
      let errorBody: unknown;
      try {
        errorBody = await response.json();
      } catch {
        errorBody = await response.text();
      }

      throw new TraceLabAPIError(
        `Upload failed: ${response.status} ${response.statusText}`,
        response.status,
        errorBody
      );
    }

    return (await response.json()) as DocumentUploadResponse;
  }

  /**
   * Create a new project
   */
  async createProject(data: ProjectCreate): Promise<Project> {
    return this.request<Project>('POST', '/api/v1/projects', data);
  }

  /**
   * Update an existing project
   */
  async updateProject(projectId: string, data: ProjectUpdate): Promise<Project> {
    return this.request<Project>('PUT', `/api/v1/projects/${projectId}`, data);
  }

  /**
   * Get aggregated statistics for a project
   */
  async getProjectStats(projectId: string): Promise<ProjectStats> {
    return this.request<ProjectStats>('GET', `/api/v1/projects/${projectId}/stats`);
  }

  // ============================================
  // Document Methods
  // ============================================

  /**
   * Get a document by ID with metadata and optional chunks
   */
  async getDocument(documentId: string): Promise<Document> {
    return this.request<Document>('GET', `/api/v1/documents/${documentId}`);
  }

  /**
   * Get paginated chunks for a document
   */
  async getDocumentChunks(
    documentId: string,
    page = 1,
    pageSize = 20
  ): Promise<DocumentChunksResponse> {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });
    return this.request<DocumentChunksResponse>(
      'GET',
      `/api/v1/documents/${documentId}/chunks?${params}`
    );
  }

  // ============================================
  // Mission Methods
  // ============================================

  /**
   * List missions with optional filtering
   */
  async listMissions(
    page = 1,
    pageSize = 20,
    status?: string,
    projectId?: string
  ): Promise<MissionListResponse> {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });
    if (status) {
      params.set('status', status);
    }
    if (projectId) {
      params.set('project_id', projectId);
    }
    return this.request<MissionListResponse>(
      'GET',
      `/api/v1/missions?${params}`
    );
  }

  /**
   * Get a single mission by ID
   */
  async getMission(missionId: string): Promise<Mission> {
    return this.request<Mission>('GET', `/api/v1/missions/${missionId}`);
  }

  /**
   * Create a new mission
   */
  async createMission(data: MissionCreate): Promise<Mission> {
    return this.request<Mission>('POST', '/api/v1/missions', data);
  }

  /**
   * Update an existing mission
   */
  async updateMission(missionId: string, data: MissionUpdate): Promise<Mission> {
    return this.request<Mission>('PATCH', `/api/v1/missions/${missionId}`, data);
  }

  /**
   * Submit a mission for execution (sets status to queued)
   * In worker mode, the DeepSearch worker will poll and pick it up
   */
  async submitMission(missionId: string): Promise<MissionSubmitResponse> {
    return this.request<MissionSubmitResponse>(
      'POST',
      `/api/v1/missions/${missionId}/submit`
    );
  }

  /**
   * Get the current status of a mission
   */
  async getMissionStatus(missionId: string): Promise<{ status: string; progress?: number }> {
    const mission = await this.getMission(missionId);
    return {
      status: mission.status,
      progress: mission.execution_metadata?.progress_percent as number | undefined,
    };
  }

  /**
   * Fetch the compiled DeepSearch contract preview for a mission (T40.4).
   * Read-only — does not change mission state.
   */
  async previewMissionContract(missionId: string): Promise<MissionContractPreview> {
    return this.request<MissionContractPreview>(
      'GET',
      `/api/v1/missions/${missionId}/contract-preview`
    );
  }
}

export interface MissionContractPreview {
  mission_id: string;
  mission_uuid: string;
  project_id?: string | null;
  named_entities: string[];
  objectives: Array<Record<string, unknown>>;
  evidence_slots: Array<Record<string, unknown>>;
  acceptance_checks: Array<Record<string, unknown>>;
  deliverable_schemas: Array<Record<string, unknown>>;
  coverage_thresholds: Record<string, number>;
  validation_thresholds: Record<string, number>;
}
