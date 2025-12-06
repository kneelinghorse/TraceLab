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
      let errorBody: unknown;
      try {
        errorBody = await response.json();
      } catch {
        errorBody = await response.text();
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
}
