/**
 * TraceLab API Client
 *
 * Handles all HTTP communication with the TraceLab API.
 * Supports both JWT token and API key authentication.
 */
export class TraceLabAPIError extends Error {
    statusCode;
    response;
    constructor(message, statusCode, response) {
        super(message);
        this.statusCode = statusCode;
        this.response = response;
        this.name = 'TraceLabAPIError';
    }
}
export class TraceLabClient {
    baseUrl;
    headers;
    constructor(config) {
        this.baseUrl = config.baseUrl.replace(/\/$/, '');
        this.headers = {
            'Content-Type': 'application/json',
        };
        if (config.token) {
            this.headers['Authorization'] = `Bearer ${config.token}`;
        }
        else if (config.apiKey) {
            this.headers['X-API-Key'] = config.apiKey;
        }
    }
    async request(method, path, body) {
        const url = `${this.baseUrl}${path}`;
        const options = {
            method,
            headers: this.headers,
        };
        if (body) {
            options.body = JSON.stringify(body);
        }
        const response = await fetch(url, options);
        if (!response.ok) {
            let errorBody;
            try {
                errorBody = await response.json();
            }
            catch {
                errorBody = await response.text();
            }
            throw new TraceLabAPIError(`API request failed: ${response.status} ${response.statusText}`, response.status, errorBody);
        }
        // Handle non-JSON responses (like markdown exports)
        const contentType = response.headers.get('content-type');
        if (contentType?.includes('text/markdown') || contentType?.includes('text/plain')) {
            const text = await response.text();
            return text;
        }
        const json = await response.json();
        return json;
    }
    /**
     * Search for relevant chunks via semantic search
     */
    async searchKnowledge(query) {
        return this.request('POST', '/api/v1/retrieval/search', query);
    }
    /**
     * List all projects
     */
    async listProjects(page = 1, pageSize = 20, search) {
        const params = new URLSearchParams({
            page: String(page),
            page_size: String(pageSize),
        });
        if (search) {
            params.set('search', search);
        }
        return this.request('GET', `/api/v1/projects?${params}`);
    }
    /**
     * List all collections
     */
    async listCollections() {
        return this.request('GET', '/api/v1/collections');
    }
    /**
     * Get a collection with its chunks
     */
    async getCollection(collectionId) {
        return this.request('GET', `/api/v1/collections/${collectionId}`);
    }
    /**
     * Export a collection as markdown
     */
    async exportCollection(collectionId) {
        return this.request('GET', `/api/v1/collections/${collectionId}/export`);
    }
    /**
     * Create a new collection
     */
    async createCollection(data) {
        return this.request('POST', '/api/v1/collections', data);
    }
    /**
     * Add a chunk to a collection
     */
    async addToCollection(collectionId, data) {
        return this.request('POST', `/api/v1/collections/${collectionId}/chunks`, data);
    }
    /**
     * Synthesize content from a collection
     * Note: This endpoint may not be available until B14.2 is implemented
     */
    async synthesize(data) {
        return this.request('POST', '/api/v1/synthesize', data);
    }
    /**
     * Create a new report by synthesizing from collection or chunks
     */
    async createReport(data) {
        return this.request('POST', '/api/v1/reports', data);
    }
    /**
     * List reports with optional filtering
     */
    async listReports(page = 1, pageSize = 20, projectId, status) {
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
        return this.request('GET', `/api/v1/reports?${params}`);
    }
    /**
     * Get a single report with full details
     */
    async getReport(reportId) {
        return this.request('GET', `/api/v1/reports/${reportId}`);
    }
    /**
     * Export a report as markdown text
     * For MVP, returns the content field directly
     */
    async exportReport(reportId) {
        const report = await this.getReport(reportId);
        return report.content;
    }
    /**
     * Upload a document to TraceLab
     * Accepts base64 encoded content and sends as multipart/form-data
     */
    async uploadDocument(data) {
        const url = `${this.baseUrl}/api/v1/documents/upload?project_id=${encodeURIComponent(data.project_id)}`;
        // Decode base64 content to binary
        const binaryContent = Buffer.from(data.content, 'base64');
        // Create a Blob from the binary content
        const blob = new Blob([binaryContent], { type: data.content_type });
        // Create FormData with the file
        const formData = new FormData();
        formData.append('file', blob, data.name);
        // Build headers without Content-Type (browser sets it with boundary)
        const headers = {};
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
            let errorBody;
            try {
                errorBody = await response.json();
            }
            catch {
                errorBody = await response.text();
            }
            throw new TraceLabAPIError(`Upload failed: ${response.status} ${response.statusText}`, response.status, errorBody);
        }
        return (await response.json());
    }
    /**
     * Create a new project
     */
    async createProject(data) {
        return this.request('POST', '/api/v1/projects', data);
    }
    /**
     * Update an existing project
     */
    async updateProject(projectId, data) {
        return this.request('PUT', `/api/v1/projects/${projectId}`, data);
    }
    /**
     * Get aggregated statistics for a project
     */
    async getProjectStats(projectId) {
        return this.request('GET', `/api/v1/projects/${projectId}/stats`);
    }
}
//# sourceMappingURL=api-client.js.map