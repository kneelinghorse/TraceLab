/**
 * Integration tests for TraceLab MCP Server
 *
 * These tests verify the tool implementations work correctly with mocked API responses.
 */

import { describe, it, expect, vi, beforeAll, beforeEach, afterEach, afterAll } from 'vitest';
import { TraceLabClient, TraceLabAPIError } from './api-client.js';

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Handler tests exercise the module-level shared client constructed by index.ts.
// Pin its credential before the first dynamic import so evidence calls prove the
// published MCP path forwards API-key authentication, not only URL/method/body.
const originalTraceLabToken = process.env.TRACELAB_TOKEN;
const originalTraceLabApiKey = process.env.TRACELAB_API_KEY;
const originalTraceLabApiUrl = process.env.TRACELAB_API_URL;

beforeAll(() => {
  delete process.env.TRACELAB_TOKEN;
  process.env.TRACELAB_API_KEY = 'tl_shared-client-test';
  process.env.TRACELAB_API_URL = 'http://localhost:8000';
});

afterAll(() => {
  if (originalTraceLabToken === undefined) delete process.env.TRACELAB_TOKEN;
  else process.env.TRACELAB_TOKEN = originalTraceLabToken;
  if (originalTraceLabApiKey === undefined) delete process.env.TRACELAB_API_KEY;
  else process.env.TRACELAB_API_KEY = originalTraceLabApiKey;
  if (originalTraceLabApiUrl === undefined) delete process.env.TRACELAB_API_URL;
  else process.env.TRACELAB_API_URL = originalTraceLabApiUrl;
});

describe('TraceLabClient', () => {
  let client: TraceLabClient;

  beforeEach(() => {
    client = new TraceLabClient({
      baseUrl: 'http://localhost:8000',
      token: 'test-token',
    });
    mockFetch.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('searchKnowledge', () => {
    it('should search for knowledge chunks', async () => {
      const mockResponse = {
        results: [
          {
            chunk_id: 'chunk-1',
            content: 'Test content about AI research',
            score: 0.95,
            document_id: 'doc-1',
            source_type: 'pdf',
          },
        ],
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve(mockResponse),
      });

      const result = await client.searchKnowledge({
        query: 'AI research',
        top_k: 10,
      });

      expect(result.results).toHaveLength(1);
      expect(result.results[0].chunk_id).toBe('chunk-1');
      expect(result.results[0].score).toBe(0.95);
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v1/retrieval/search',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            Authorization: 'Bearer test-token',
          }),
        })
      );
    });

    it('should handle API errors', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        statusText: 'Unauthorized',
        text: () => Promise.resolve(JSON.stringify({ detail: 'Invalid token' })),
      });

      await expect(
        client.searchKnowledge({ query: 'test' })
      ).rejects.toThrow(TraceLabAPIError);
    });
  });

  describe('listProjects', () => {
    it('should list projects with pagination', async () => {
      const mockResponse = {
        data: [
          {
            id: 'proj-1',
            name: 'Test Project',
            description: 'A test project',
            status: 'active',
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
          },
        ],
        pagination: {
          page: 1,
          page_size: 20,
          total: 1,
          pages: 1,
        },
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve(mockResponse),
      });

      const result = await client.listProjects(1, 20, 'Test');

      expect(result.data).toHaveLength(1);
      expect(result.data[0].name).toBe('Test Project');
      expect(result.pagination.total).toBe(1);
    });
  });

  describe('listCollections', () => {
    it('should list all collections', async () => {
      const mockResponse = {
        data: [
          {
            id: 'coll-1',
            name: 'Research Collection',
            description: 'My research',
            item_count: 5,
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
          },
        ],
        total: 1,
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve(mockResponse),
      });

      const result = await client.listCollections();

      expect(result.data).toHaveLength(1);
      expect(result.data[0].name).toBe('Research Collection');
      expect(result.total).toBe(1);
    });
  });

  describe('getCollection', () => {
    it('should get collection with items', async () => {
      const mockResponse = {
        id: 'coll-1',
        name: 'Research Collection',
        description: 'My research',
        item_count: 1,
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
        items: [
          {
            id: 'item-1',
            collection_id: 'coll-1',
            chunk_id: 'chunk-1',
            notes: 'Important finding',
            added_at: '2024-01-01T00:00:00Z',
            chunk_content: 'Preview content...',
            document_id: 'doc-1',
          },
        ],
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve(mockResponse),
      });

      const result = await client.getCollection('coll-1');

      expect(result.name).toBe('Research Collection');
      expect(result.items).toHaveLength(1);
      expect(result.items[0].notes).toBe('Important finding');
    });
  });

  describe('exportCollection', () => {
    it('should export collection as markdown', async () => {
      const mockMarkdown = `# Research Collection

## Chunk 1
Content here...

---
Exported from TraceLab`;

      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'text/markdown' }),
        text: () => Promise.resolve(mockMarkdown),
      });

      const result = await client.exportCollection('coll-1');

      expect(result).toContain('# Research Collection');
      expect(result).toContain('Exported from TraceLab');
    });
  });

  describe('createCollection', () => {
    it('should create a new collection', async () => {
      const mockResponse = {
        id: 'coll-new',
        name: 'New Collection',
        description: 'A new collection',
        item_count: 0,
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve(mockResponse),
      });

      const result = await client.createCollection({
        name: 'New Collection',
        description: 'A new collection',
      });

      expect(result.id).toBe('coll-new');
      expect(result.name).toBe('New Collection');
      expect(result.item_count).toBe(0);
    });
  });

  describe('addToCollection', () => {
    it('should add chunk to collection', async () => {
      const mockResponse = {
        id: 'item-new',
        collection_id: 'coll-1',
        chunk_id: 'chunk-1',
        notes: 'My notes',
        added_at: '2024-01-01T00:00:00Z',
        chunk_content: 'Preview...',
        document_id: 'doc-1',
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve(mockResponse),
      });

      const result = await client.addToCollection('coll-1', {
        chunk_id: 'chunk-1',
        notes: 'My notes',
      });

      expect(result.id).toBe('item-new');
      expect(result.chunk_id).toBe('chunk-1');
      expect(result.notes).toBe('My notes');
    });
  });

  describe('synthesize', () => {
    it('should synthesize collection content', async () => {
      const mockResponse = {
        content: '## Summary\n\nKey findings from the research...',
        citations: [
          {
            chunk_id: 'chunk-1',
            document_id: 'doc-1',
            excerpt: 'Supporting evidence...',
          },
        ],
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve(mockResponse),
      });

      const result = await client.synthesize({
        collection_id: 'coll-1',
        prompt: 'Summarize key findings',
        format: 'markdown',
      });

      expect(result.content).toContain('Summary');
      expect(result.citations).toHaveLength(1);
    });

    it('should handle 404 when synthesize endpoint not available', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        text: () => Promise.resolve(JSON.stringify({ detail: 'Not found' })),
      });

      await expect(
        client.synthesize({ collection_id: 'coll-1' })
      ).rejects.toThrow(TraceLabAPIError);
    });
  });

  describe('createReport', () => {
    it('should create a new report from collection', async () => {
      const mockResponse = {
        id: 'report-1',
        title: 'ML Best Practices Summary',
        content: '## Summary\n\nKey findings...',
        citations: [
          {
            chunk_id: 'chunk-1',
            document_id: 'doc-1',
            excerpt: 'Supporting evidence...',
          },
        ],
        tokens_used: 1500,
        status: 'draft',
        created_at: '2024-01-01T00:00:00Z',
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve(mockResponse),
      });

      const result = await client.createReport({
        title: 'ML Best Practices Summary',
        collection_id: 'coll-1',
        prompt: 'Summarize best practices',
        format: 'summary',
      });

      expect(result.id).toBe('report-1');
      expect(result.title).toBe('ML Best Practices Summary');
      expect(result.citations).toHaveLength(1);
      expect(result.tokens_used).toBe(1500);
    });
  });

  describe('listReports', () => {
    it('should list reports with pagination', async () => {
      const mockResponse = {
        items: [
          {
            id: 'report-1',
            title: 'ML Summary',
            status: 'final',
            report_type: 'summary',
            tokens_used: 1500,
            chunk_count: 5,
            project_id: 'proj-1',
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve(mockResponse),
      });

      const result = await client.listReports(1, 20, undefined, 'final');

      expect(result.items).toHaveLength(1);
      expect(result.items[0].title).toBe('ML Summary');
      expect(result.total).toBe(1);
    });
  });

  describe('getReport', () => {
    it('should get full report details', async () => {
      const mockResponse = {
        id: 'report-1',
        title: 'ML Summary',
        content: '## Full Report Content\n\nDetailed findings...',
        citations: [],
        tokens_used: 1500,
        status: 'final',
        created_at: '2024-01-01T00:00:00Z',
        project_id: 'proj-1',
        report_type: 'summary',
        prompt: 'Summarize findings',
        chunk_count: 5,
        sources: [
          {
            id: 'src-1',
            report_id: 'report-1',
            source_type: 'collection',
            source_id: 'coll-1',
            added_at: '2024-01-01T00:00:00Z',
          },
        ],
        updated_at: '2024-01-01T00:00:00Z',
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve(mockResponse),
      });

      const result = await client.getReport('report-1');

      expect(result.id).toBe('report-1');
      expect(result.content).toContain('Full Report Content');
      expect(result.sources).toHaveLength(1);
      expect(result.chunk_count).toBe(5);
    });
  });

  describe('exportReport', () => {
    it('should export report as markdown', async () => {
      const mockResponse = {
        id: 'report-1',
        title: 'ML Summary',
        content: '## ML Best Practices\n\n1. Use cross-validation\n2. Feature engineering matters',
        citations: [],
        tokens_used: 1500,
        status: 'final',
        created_at: '2024-01-01T00:00:00Z',
        project_id: null,
        report_type: 'summary',
        prompt: null,
        chunk_count: 5,
        sources: [],
        updated_at: '2024-01-01T00:00:00Z',
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve(mockResponse),
      });

      const result = await client.exportReport('report-1');

      expect(result).toContain('ML Best Practices');
      expect(result).toContain('cross-validation');
    });
  });
});

describe('uploadDocument', () => {
  let client: TraceLabClient;

  beforeEach(() => {
    client = new TraceLabClient({
      baseUrl: 'http://localhost:8000',
      token: 'test-token',
    });
    mockFetch.mockReset();
  });

  it('should upload a document with base64 content', async () => {
    const mockResponse = {
      id: 'doc-new',
      name: 'research.md',
      project_id: 'proj-1',
      file_type: 'notes',
      file_size: 1024,
      mime_type: 'text/markdown',
      processed: false,
      validation_status: 'pending',
      created_at: '2024-01-01T00:00:00Z',
    };

    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: () => Promise.resolve(mockResponse),
    });

    const result = await client.uploadDocument({
      name: 'research.md',
      content: 'IyBSZXNlYXJjaCBGaW5kaW5ncw==', // base64 for "# Research Findings"
      content_type: 'text/markdown',
      project_id: 'proj-1',
    });

    expect(result.id).toBe('doc-new');
    expect(result.name).toBe('research.md');
    expect(result.processed).toBe(false);
    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/documents/upload?project_id=proj-1',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          Authorization: 'Bearer test-token',
        }),
      })
    );
  });

  it('should handle upload errors', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 400,
      statusText: 'Bad Request',
      json: () => Promise.resolve({ detail: 'Unsupported file format' }),
    });

    await expect(
      client.uploadDocument({
        name: 'file.exe',
        content: 'YmFkY29udGVudA==',
        content_type: 'application/pdf', // lying about content type
        project_id: 'proj-1',
      })
    ).rejects.toThrow(TraceLabAPIError);
  });
});

describe('Authentication', () => {
  it('should use JWT token when provided', async () => {
    const client = new TraceLabClient({
      baseUrl: 'http://localhost:8000',
      token: 'my-jwt-token',
    });

    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: () => Promise.resolve({ data: [], total: 0 }),
    });

    await client.listCollections();

    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer my-jwt-token',
        }),
      })
    );
  });

  it('should use API key when provided', async () => {
    const client = new TraceLabClient({
      baseUrl: 'http://localhost:8000',
      apiKey: 'my-api-key',
    });

    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: () => Promise.resolve({ data: [], total: 0 }),
    });

    await client.listCollections();

    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({
          'X-API-Key': 'my-api-key',
        }),
      })
    );
  });
});

/**
 * T41.2 contract-guard tests for the MCP handler dispatch path.
 *
 * Mirrors the T40.0 codification rule: MCP surface changes need a regression
 * test that exercises the handler-emitted response shape, not just the
 * api-client. Discovered 2026-04-27 — the api-client returned all T40.1
 * fields but handleGetMission's hand-rolled JSON.stringify({...}) dropped
 * 12 of them, leaving DeepSearch unable to read mission-authoring state via
 * MCP get_mission for OODS-FIGMA-HOST-01.
 */
describe('MCP handlers — T40.1 mission-authoring fields surface through MCP', () => {
  const T40_1_FIELDS = [
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

  const TEST_UUID = '2a781109-6122-4576-b5c2-052e5450d22e';
  const fullMissionFixture = {
    id: TEST_UUID,
    mission_id: 'OODS-FIGMA-HOST-01',
    title: 'Hosted code-execution platforms',
    objective: 'Compare serverless container platforms for OODS evaluation',
    success_criteria: ['all 12 fields surface'],
    status: 'draft',
    project_id: 'project-1',
    context: {},
    deliverables: ['comparison.md'],
    research_phases: {},
    tags: ['ds', 'figma'],
    metadata: {},
    background: 'Hosted code-execution platforms for OODS evaluation.',
    focus: 'Serverless containerized execution with sub-second cold starts.',
    references: [{ title: 'AWS Lambda docs' }],
    required_entities: [
      'AWS Lambda',
      'Google Cloud Run',
      'Vercel Functions',
      'Fly.io',
      'Railway',
    ],
    excluded_entities: ['AWS EC2'],
    expected_output_schema: { type: 'comparison_matrix' },
    coverage_thresholds: { min_sources: 50 },
    validation_thresholds: { min_score: 7.0 },
    deliverable_format: 'comparison table',
    max_loops: 8,
    min_loops: 3,
    constraints: ['No AWS-only solutions'],
    queued_at: null,
    started_at: null,
    completed_at: null,
    deepsearch_job_id: null,
    execution_metadata: {},
    result_document_ids: [],
    result_report_id: null,
    result_markdown: null,
    result_protocol: null,
    error_message: null,
    created_at: '2026-04-27T06:00:00Z',
    updated_at: '2026-04-27T06:00:00Z',
    created_by: 'test',
  };

  beforeEach(() => {
    mockFetch.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('handleGetMission emits all 12 T40.1 mission-authoring fields', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: () => Promise.resolve(fullMissionFixture),
    });

    const { handleGetMission } = await import('./index.js');
    const response = await handleGetMission({ mission_id: TEST_UUID });

    const payload = JSON.parse(response.content[0].text);
    for (const field of T40_1_FIELDS) {
      expect(payload).toHaveProperty(field);
    }
    expect(payload.required_entities).toEqual([
      'AWS Lambda',
      'Google Cloud Run',
      'Vercel Functions',
      'Fly.io',
      'Railway',
    ]);
    expect(payload.constraints).toEqual(['No AWS-only solutions']);
    expect(payload.max_loops).toBe(8);
    expect(payload.background).toBe(
      'Hosted code-execution platforms for OODS evaluation.'
    );
  });

  it('handleListMissions emits T40.1 fields for each mission summary', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: () =>
        Promise.resolve({
          data: [fullMissionFixture],
          pagination: { page: 1, page_size: 20, total: 1, pages: 1 },
        }),
    });

    const { handleListMissions } = await import('./index.js');
    const response = await handleListMissions({});

    const payload = JSON.parse(response.content[0].text);
    expect(payload.missions).toHaveLength(1);
    const m = payload.missions[0];
    for (const field of T40_1_FIELDS) {
      expect(m).toHaveProperty(field);
    }
    expect(m.required_entities).toContain('AWS Lambda');
  });
});

/**
 * T41.4 contract-guard tests for slim/full payload split on get_mission.
 *
 * Same harness as T41.2 — mock fetch at the api-client boundary, invoke
 * the handler, assert on the trimmed shape. The OODS-FIGMA-HOST-01 trigger
 * mission's execution_metadata is ~16KB on its own; default-slim keeps the
 * full response under MCP transport limits, opt-in flag returns full.
 */
describe('MCP handlers — T41.4 slim/full payload split for get_mission', () => {
  const TEST_UUID = '585f20f1-10ec-4808-9ac1-b066b59e7648';

  // Build an execution_metadata-shaped object whose JSON serializes well
  // above the 5KB trim threshold so the trim branch fires deterministically.
  const buildLargeMetadata = (targetBytes = 8000) => {
    const chunk = 'x'.repeat(100);
    const items = Math.max(1, Math.floor(targetBytes / chunk.length));
    return {
      duration_ms: 663620,
      loops_executed: 3,
      trace: Array.from({ length: items }, () => chunk),
    };
  };

  const fixtureWithLargeBlobs = () => ({
    id: TEST_UUID,
    mission_id: 'OODS-FIGMA-HOST-01-S59-RUN-01',
    title: 'Backend hosting comparison',
    objective: 'Compare hosted code-execution platforms',
    success_criteria: ['compile contract correctly'],
    status: 'completed',
    project_id: 'fbd3bd03-5ddc-49ee-8013-529163a99290',
    context: {},
    deliverables: ['comparison.md'],
    research_phases: {},
    tags: [],
    metadata: {},
    background: 'Hosted code-execution platforms.',
    focus: null,
    references: null,
    required_entities: ['AWS Lambda', 'Google Cloud Run'],
    excluded_entities: null,
    expected_output_schema: null,
    coverage_thresholds: null,
    validation_thresholds: null,
    deliverable_format: null,
    max_loops: 3,
    min_loops: null,
    constraints: null,
    queued_at: null,
    started_at: null,
    completed_at: '2026-04-27T04:55:55Z',
    deepsearch_job_id: null,
    execution_metadata: buildLargeMetadata(16_000),
    result_document_ids: [],
    result_report_id: null,
    result_markdown:
      '# Hosting Comparison\n\n' + 'Body paragraph. '.repeat(1000),
    result_protocol: { version: '1.0', items: Array.from({ length: 100 }, () => 'x'.repeat(100)) },
    error_message: null,
    created_at: '2026-04-27T04:44:13Z',
    updated_at: '2026-04-27T04:55:55Z',
  });

  beforeEach(() => {
    mockFetch.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('default slim mode summarizes large execution_metadata', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: () => Promise.resolve(fixtureWithLargeBlobs()),
    });

    const { handleGetMission } = await import('./index.js');
    const response = await handleGetMission({ mission_id: TEST_UUID });
    const payload = JSON.parse(response.content[0].text);

    expect(payload.execution_metadata).toBeTypeOf('object');
    expect(payload.execution_metadata._trimmed).toBe(true);
    expect(payload.execution_metadata.field).toBe('execution_metadata');
    expect(payload.execution_metadata.byte_size).toBeGreaterThan(5_000);
    expect(payload.execution_metadata.hint).toContain(
      'include_execution_metadata=true'
    );
  });

  it('include_execution_metadata=true returns full execution_metadata', async () => {
    const fixture = fixtureWithLargeBlobs();
    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: () => Promise.resolve(fixture),
    });

    const { handleGetMission } = await import('./index.js');
    const response = await handleGetMission({
      mission_id: TEST_UUID,
      include_execution_metadata: true,
    });
    const payload = JSON.parse(response.content[0].text);

    expect(payload.execution_metadata).toEqual(fixture.execution_metadata);
    expect(payload.execution_metadata._trimmed).toBeUndefined();
  });

  it('default slim mode summarizes large result_markdown with preview', async () => {
    const fixture = fixtureWithLargeBlobs();
    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: () => Promise.resolve(fixture),
    });

    const { handleGetMission } = await import('./index.js');
    const response = await handleGetMission({ mission_id: TEST_UUID });
    const payload = JSON.parse(response.content[0].text);

    expect(payload.result_markdown).toBeTypeOf('object');
    expect(payload.result_markdown._trimmed).toBe(true);
    expect(payload.result_markdown.field).toBe('result_markdown');
    expect(payload.result_markdown.preview).toMatch(/^# Hosting Comparison/);
    expect(payload.result_markdown.preview.endsWith('...')).toBe(true);
    expect(payload.result_markdown.byte_size).toBe(
      Buffer.byteLength(fixture.result_markdown, 'utf8')
    );
  });

  it('default slim mode summarizes large result_protocol', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: () => Promise.resolve(fixtureWithLargeBlobs()),
    });

    const { handleGetMission } = await import('./index.js');
    const response = await handleGetMission({ mission_id: TEST_UUID });
    const payload = JSON.parse(response.content[0].text);

    expect(payload.result_protocol).toBeTypeOf('object');
    expect(payload.result_protocol._trimmed).toBe(true);
    expect(payload.result_protocol.field).toBe('result_protocol');
  });

  it('slim mode leaves small blobs alone', async () => {
    const smallFixture = {
      ...fixtureWithLargeBlobs(),
      execution_metadata: { duration_ms: 5000, loops: 3 },
      result_protocol: { version: '1.0' },
      result_markdown: '# Short report\n\nBrief findings.',
    };
    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: () => Promise.resolve(smallFixture),
    });

    const { handleGetMission } = await import('./index.js');
    const response = await handleGetMission({ mission_id: TEST_UUID });
    const payload = JSON.parse(response.content[0].text);

    expect(payload.execution_metadata).toEqual({ duration_ms: 5000, loops: 3 });
    expect(payload.result_protocol).toEqual({ version: '1.0' });
    expect(payload.result_markdown).toBe('# Short report\n\nBrief findings.');
  });

  it('slim payload stays under 8KB for a realistic completed mission', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: () => Promise.resolve(fixtureWithLargeBlobs()),
    });

    const { handleGetMission } = await import('./index.js');
    const response = await handleGetMission({ mission_id: TEST_UUID });
    const size = Buffer.byteLength(response.content[0].text, 'utf8');
    expect(size).toBeLessThan(8_000);
  });
});

// ─────────────────────────────────────────────────────────────────────────
// T41.7 — Tool-grouping refactor: cluster surface + parity
//
// Surface invariants:
//   1. Exactly 8 visible MCP tools, all named tracelab_*
//   2. Every legacy tool name maps to a (cluster, action) pair where
//      action is in the cluster's action enum
//   3. Each cluster dispatches to the correct per-action handler
// ─────────────────────────────────────────────────────────────────────────

describe('T41.7 — cluster surface', () => {
  it('exposes exactly 8 tracelab_* tools and keeps descriptors aligned with action enums', async () => {
    const indexSource = await import('./index.js');
    const { CLUSTER_ACTIONS, CLUSTER_HANDLERS, TOOLS } = indexSource as unknown as {
      CLUSTER_ACTIONS: Record<string, readonly string[]>;
      CLUSTER_HANDLERS: Record<string, (args: unknown) => Promise<unknown>>;
      TOOLS: Array<{
        name: string;
        inputSchema: {
          properties?: Record<string, { enum?: string[] }>;
        };
      }>;
    };
    const toolNames = Object.keys(CLUSTER_ACTIONS);
    expect(toolNames).toHaveLength(8);
    expect(toolNames.sort()).toEqual([
      'tracelab_collection',
      'tracelab_document',
      'tracelab_evidence',
      'tracelab_mission',
      'tracelab_mission_execution',
      'tracelab_project',
      'tracelab_report',
      'tracelab_search',
    ]);

    const descriptors = new Map(TOOLS.map((tool) => [tool.name, tool]));
    expect([...descriptors.keys()].sort()).toEqual(toolNames.sort());
    expect(Object.keys(CLUSTER_HANDLERS).sort()).toEqual(toolNames.sort());
    for (const [toolName, actions] of Object.entries(CLUSTER_ACTIONS)) {
      expect(
        descriptors.get(toolName)?.inputSchema.properties?.action?.enum,
        `${toolName} descriptor action enum must match CLUSTER_ACTIONS`
      ).toEqual([...actions]);
    }
  });

  it.each(['toString', 'constructor', '__proto__', 'hasOwnProperty'])(
    'never dispatches prototype-inherited tool name %s',
    async (name) => {
      const { resolveClusterHandler, resolveLegacyTool } = await import('./index.js');

      expect(resolveClusterHandler(name)).toBeUndefined();
      expect(resolveLegacyTool(name)).toBeUndefined();
    }
  );

  it('every legacy tool maps to a valid (cluster, action) pair', async () => {
    const { LEGACY_TO_CLUSTER, CLUSTER_ACTIONS } = (await import(
      './index.js'
    )) as unknown as {
      LEGACY_TO_CLUSTER: Record<string, { tool: string; action: string }>;
      CLUSTER_ACTIONS: Record<string, readonly string[]>;
    };

    // Every pre-T41.7 tool name has a migration target.
    const legacyTools = Object.keys(LEGACY_TO_CLUSTER).sort();
    expect(legacyTools).toEqual(
      [
        'add_to_collection',
        'create_collection',
        'create_mission',
        'create_project',
        'create_report',
        'export_collection',
        'export_report',
        'get_collection',
        'get_document_content',
        'get_mission',
        'get_mission_status',
        'get_project_stats',
        'get_report',
        'list_collections',
        'list_missions',
        'list_projects',
        'list_reports',
        'preview_mission_contract',
        'search_knowledge',
        'submit_mission',
        'synthesize',
        'update_mission',
        'update_project',
        'upload_document',
      ].sort()
    );

    // And every target lands in a valid (cluster, action) pair.
    for (const [legacy, { tool, action }] of Object.entries(LEGACY_TO_CLUSTER)) {
      expect(CLUSTER_ACTIONS[tool], `${legacy} → ${tool} must be a known cluster`).toBeDefined();
      expect(
        CLUSTER_ACTIONS[tool].includes(action),
        `${legacy} → ${tool}(action="${action}") action must be in cluster enum [${CLUSTER_ACTIONS[tool].join(', ')}]`
      ).toBe(true);
    }
  });
});

describe('T41.7 — cluster dispatch (per-cluster smoke)', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  // A minimal API response that the relevant handler will accept. The
  // dispatcher's job is just to route to the right handler — we do not
  // re-test handler bodies here (those have their own coverage above).
  const okJson = (body: unknown) => ({
    ok: true,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: () => Promise.resolve(body),
  });

  it('tracelab_search routes action="knowledge" to handleSearchKnowledge', async () => {
    mockFetch.mockResolvedValueOnce(okJson({ results: [] }));
    const { handleTracelabSearch } = (await import('./index.js')) as unknown as {
      handleTracelabSearch: (args: unknown) => Promise<{ content: { text: string }[] }>;
    };
    const res = await handleTracelabSearch({ action: 'knowledge', query: 'test' });
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(res.content[0].text).toContain('total_results');
  });

  it('tracelab_project routes action="list" to handleListProjects', async () => {
    mockFetch.mockResolvedValueOnce(
      okJson({ data: [], pagination: { page: 1, page_size: 20, total: 0, pages: 0 } })
    );
    const { handleTracelabProject } = (await import('./index.js')) as unknown as {
      handleTracelabProject: (args: unknown) => Promise<{ content: { text: string }[] }>;
    };
    const res = await handleTracelabProject({ action: 'list' });
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(res.content[0].text).toContain('projects');
  });

  it('tracelab_collection routes action="list" to handleListCollections', async () => {
    mockFetch.mockResolvedValueOnce(okJson({ data: [], total: 0 }));
    const { handleTracelabCollection } = (await import('./index.js')) as unknown as {
      handleTracelabCollection: (args: unknown) => Promise<{ content: { text: string }[] }>;
    };
    const res = await handleTracelabCollection({ action: 'list' });
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(res.content[0].text).toContain('collections');
  });

  it('tracelab_report routes action="list" to handleListReports', async () => {
    mockFetch.mockResolvedValueOnce(
      okJson({ items: [], page: 1, page_size: 20, total: 0 })
    );
    const { handleTracelabReport } = (await import('./index.js')) as unknown as {
      handleTracelabReport: (args: unknown) => Promise<{ content: { text: string }[] }>;
    };
    const res = await handleTracelabReport({ action: 'list' });
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(res.content[0].text).toContain('reports');
  });

  it('tracelab_document routes action="get_content" to handleGetDocumentContent', async () => {
    // get_content with include_metadata=false skips the document fetch and
    // only requests chunks.
    mockFetch.mockResolvedValueOnce(
      okJson({
        data: [],
        pagination: { page: 1, page_size: 20, total: 0, pages: 0 },
      })
    );
    const { handleTracelabDocument } = (await import('./index.js')) as unknown as {
      handleTracelabDocument: (args: unknown) => Promise<{ content: { text: string }[] }>;
    };
    const res = await handleTracelabDocument({
      action: 'get_content',
      document_id: '00000000-0000-0000-0000-000000000001',
      include_metadata: false,
    });
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(res.content[0].text).toContain('document_id');
  });

  it('tracelab_mission routes action="list" to handleListMissions', async () => {
    mockFetch.mockResolvedValueOnce(
      okJson({ data: [], pagination: { page: 1, page_size: 20, total: 0, pages: 0 } })
    );
    const { handleTracelabMission } = (await import('./index.js')) as unknown as {
      handleTracelabMission: (args: unknown) => Promise<{ content: { text: string }[] }>;
    };
    const res = await handleTracelabMission({ action: 'list' });
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(res.content[0].text).toContain('missions');
  });

  it('tracelab_mission routes action="get" with include_execution_metadata flag', async () => {
    // T41.4 flag must survive the cluster dispatch — Zod default-strip drops
    // the extra `action` key, but include_execution_metadata stays.
    mockFetch.mockResolvedValueOnce(
      okJson({
        id: '00000000-0000-0000-0000-000000000001',
        mission_id: 'M001',
        title: 'Test',
        objective: 'Test',
        success_criteria: ['x'],
        status: 'draft',
        project_id: null,
        deliverables: [],
        tags: [],
        created_at: '2026-04-27T00:00:00Z',
        updated_at: '2026-04-27T00:00:00Z',
      })
    );
    const { handleTracelabMission } = (await import('./index.js')) as unknown as {
      handleTracelabMission: (args: unknown) => Promise<{ content: { text: string }[] }>;
    };
    const res = await handleTracelabMission({
      action: 'get',
      mission_id: '00000000-0000-0000-0000-000000000001',
      include_execution_metadata: true,
    });
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(res.content[0].text).toContain('"mission_id": "M001"');
  });

  it('tracelab_mission_execution routes action="status" to handleGetMissionStatus', async () => {
    mockFetch.mockResolvedValueOnce(
      okJson({
        id: '00000000-0000-0000-0000-000000000001',
        mission_id: 'M001',
        status: 'queued',
        progress_percent: 0,
        deepsearch_attempt_count: 0,
        deepsearch_job_id: 'ds-job-42',
        lease_expires_at: '2026-08-20T12:00:00Z',
        result_document_ids: ['00000000-0000-0000-0000-00000000000d'],
        result_report_id: '00000000-0000-0000-0000-00000000000e',
        materialization_pending: true,
        materialization_status: 'failed',
        materialization_attempt_count: 2,
        materialization_error: 'ingestion_failed',
        search_ready: false,
      })
    );
    const { handleTracelabMissionExecution } = (await import('./index.js')) as unknown as {
      handleTracelabMissionExecution: (args: unknown) => Promise<{ content: { text: string }[] }>;
    };
    const res = await handleTracelabMissionExecution({
      action: 'status',
      mission_id: '00000000-0000-0000-0000-000000000001',
    });
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/missions/00000000-0000-0000-0000-000000000001/status',
      expect.objectContaining({ method: 'GET' })
    );
    expect(JSON.parse(res.content[0].text)).toMatchObject({
      status: 'queued',
      attempts: 0,
      // Cross-service lifecycle fields pass through under REST names.
      deepsearch_job_id: 'ds-job-42',
      lease_expires_at: '2026-08-20T12:00:00Z',
      result_document_ids: ['00000000-0000-0000-0000-00000000000d'],
      result_report_id: '00000000-0000-0000-0000-00000000000e',
      materialization_pending: true,
      materialization_status: 'failed',
      materialization_attempt_count: 2,
      materialization_error: 'ingestion_failed',
      search_ready: false,
    });
  });

  it('tracelab_mission_execution preview exposes compiler provenance', async () => {
    mockFetch.mockResolvedValueOnce(
      okJson({
        mission_id: 'M001',
        mission_uuid: '00000000-0000-0000-0000-000000000001',
        project_id: null,
        contract_version: '1.0',
        compiler_revision: '24e88100624e6221e5fa957508ab77c4b0f519f9',
        fidelity: 'structural_only',
        named_entities: [],
        objectives: [],
        evidence_slots: [],
        acceptance_checks: [],
        deliverable_schemas: [],
        coverage_thresholds: {},
        validation_thresholds: {},
      })
    );
    const { handleTracelabMissionExecution } = (await import('./index.js')) as unknown as {
      handleTracelabMissionExecution: (args: unknown) => Promise<{ content: { text: string }[] }>;
    };

    const res = await handleTracelabMissionExecution({
      action: 'preview',
      mission_id: '00000000-0000-0000-0000-000000000001',
    });

    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/missions/00000000-0000-0000-0000-000000000001/contract-preview',
      expect.objectContaining({ method: 'GET' })
    );
    const payload = JSON.parse(res.content[0].text);
    expect(payload.preview.contract_version).toBe('1.0');
    expect(payload.preview.compiler_revision).toBe(
      '24e88100624e6221e5fa957508ab77c4b0f519f9'
    );
    expect(payload.preview.fidelity).toBe('structural_only');
  });

  it('cluster returns a clean error for an unknown action', async () => {
    const { handleTracelabMission } = (await import('./index.js')) as unknown as {
      handleTracelabMission: (
        args: unknown
      ) => Promise<{ content: { text: string }[]; isError?: boolean }>;
    };
    const res = await handleTracelabMission({ action: 'frobnicate' });
    expect(res.isError).toBe(true);
    expect(res.content[0].text).toContain('tracelab_mission');
    expect(res.content[0].text).toContain('frobnicate');
    // The error should enumerate the valid actions.
    expect(res.content[0].text).toContain('create');
    expect(res.content[0].text).toContain('update');
  });
});

describe('LEDGER-1 — tracelab_evidence published contract', () => {
  const PROJECT_ID = '11111111-1111-4111-8111-111111111111';
  const MISSION_ID = '22222222-2222-4222-8222-222222222222';
  const ENTRY_ID = '33333333-3333-4333-8333-333333333333';
  const NOTE_ID = '44444444-4444-4444-8444-444444444444';
  const OWNER_ID = '55555555-5555-4555-8555-555555555555';
  const WORKSPACE_ID = '66666666-6666-4666-8666-666666666666';

  const entryFixture = {
    id: ENTRY_ID,
    project_id: PROJECT_ID,
    mission_id: MISSION_ID,
    session_key: 'session / 42',
    origin: 'mcp-agent',
    claim: 'The API preserves the full evidence record.',
    summary: 'Full evidence survives MCP serialization.',
    source_url: 'https://example.com/research?a=1&b=2',
    snippet: 'A directly supporting excerpt.',
    query: 'evidence serialization behavior',
    disposition: 'supporting',
    tags: ['contract', 'mcp'],
    owner_id: OWNER_ID,
    workspace_id: WORKSPACE_ID,
    created_at: '2026-08-20T12:00:00Z',
    updated_at: '2026-08-20T12:01:00Z',
  };

  const noteFixture = {
    id: NOTE_ID,
    project_id: PROJECT_ID,
    mission_id: MISSION_ID,
    session_key: 'session / 42',
    origin: 'mcp-agent',
    note_key: 'open/question ?',
    content: 'Resolve the contradictory source before promotion.',
    tags: ['working-note'],
    owner_id: OWNER_ID,
    workspace_id: WORKSPACE_ID,
    created_at: '2026-08-20T12:02:00Z',
    updated_at: '2026-08-20T12:03:00Z',
  };

  const okJson = (body: unknown) => ({
    ok: true,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: () => Promise.resolve(body),
  });

  beforeEach(() => {
    mockFetch.mockReset();
  });

  it('publishes explicit capture item fields and never accepts caller-supplied origin', async () => {
    type SchemaNode = {
      maxLength?: number;
      maxItems?: number;
      pattern?: string;
      properties?: Record<string, SchemaNode>;
      required?: string[];
      additionalProperties?: boolean;
      items?: SchemaNode;
    };
    const { TOOLS } = (await import('./index.js')) as unknown as {
      TOOLS: Array<{
        name: string;
        inputSchema: SchemaNode & { properties: Record<string, SchemaNode> };
      }>;
    };
    const schema = TOOLS.find((tool) => tool.name === 'tracelab_evidence')?.inputSchema;
    expect(schema).toBeDefined();
    expect(Object.keys(schema!.properties.entries.items!.properties!).sort()).toEqual([
      'claim',
      'disposition',
      'query',
      'snippet',
      'source_url',
      'summary',
      'tags',
    ]);
    expect(schema!.properties.entries.items!.required).toEqual([
      'claim',
      'source_url',
      'disposition',
    ]);
    expect(schema!.properties.entries.items!.additionalProperties).toBe(false);
    expect(schema!.properties.entries.maxItems).toBe(100);
    expect(schema!.properties.note_key.maxLength).toBe(100);
    expect(schema!.additionalProperties).toBe(false);
    expect(schema!.properties).not.toHaveProperty('origin');

    const captureFields = schema!.properties.entries.items!.properties!;
    expect('   ').not.toMatch(new RegExp(captureFields.claim.pattern!));
    expect(' claim ').toMatch(new RegExp(captureFields.claim.pattern!));
    expect('\t').not.toMatch(new RegExp(captureFields.tags.items!.pattern!));
    expect('  ').not.toMatch(new RegExp(schema!.properties.session_key.pattern!));
    expect('\n\t').not.toMatch(new RegExp(schema!.properties.content.pattern!));
    expect('  ').not.toMatch(new RegExp(schema!.properties.q.pattern!));
    expect('  ').not.toMatch(new RegExp(schema!.properties.title.pattern!));
    const noteKeyPattern = new RegExp(schema!.properties.note_key.pattern!);
    expect('.').not.toMatch(noteKeyPattern);
    expect(' .. ').not.toMatch(noteKeyPattern);
    expect('open/question').toMatch(noteKeyPattern);
  });

  it('rejects backend-invalid whitespace-only required text and tags before fetch', async () => {
    const { handleTracelabEvidence } = await import('./index.js');
    const validEntry = {
      claim: 'Valid claim',
      source_url: 'https://example.com/source',
      disposition: 'supporting',
    };
    const invalidCalls: Array<{ label: string; args: Record<string, unknown> }> = [
      {
        label: 'capture session_key',
        args: {
          action: 'capture',
          project_id: PROJECT_ID,
          session_key: '   ',
          entries: [validEntry],
        },
      },
      {
        label: 'capture claim',
        args: {
          action: 'capture',
          project_id: PROJECT_ID,
          session_key: 'session',
          entries: [{ ...validEntry, claim: '\t\n' }],
        },
      },
      {
        label: 'capture tag',
        args: {
          action: 'capture',
          project_id: PROJECT_ID,
          session_key: 'session',
          entries: [{ ...validEntry, tags: ['  '] }],
        },
      },
      {
        label: 'note note_key',
        args: {
          action: 'note',
          project_id: PROJECT_ID,
          session_key: 'session',
          note_key: '  ',
          content: 'content',
        },
      },
      {
        label: 'note content',
        args: {
          action: 'note',
          project_id: PROJECT_ID,
          session_key: 'session',
          note_key: 'key',
          content: '\n\t',
        },
      },
      {
        label: 'list session_key',
        args: { action: 'list', project_id: PROJECT_ID, session_key: '  ' },
      },
      {
        label: 'search q',
        args: { action: 'search', project_id: PROJECT_ID, q: '\t' },
      },
      {
        label: 'promote title',
        args: {
          action: 'promote',
          project_id: PROJECT_ID,
          session_key: 'session',
          title: '  ',
        },
      },
    ];

    for (const { label, args } of invalidCalls) {
      await expect(handleTracelabEvidence(args), label).rejects.toThrow(
        /empty|whitespace/
      );
    }
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it.each(['.', '..', ' . ', ' .. '])(
    'rejects URL-navigation note key %j in Zod before fetch',
    async (noteKey) => {
      const { handleTracelabEvidence } = await import('./index.js');

      await expect(
        handleTracelabEvidence({
          action: 'note',
          project_id: PROJECT_ID,
          session_key: 'session',
          note_key: noteKey,
          content: 'content',
        })
      ).rejects.toThrow(/note_key cannot be/);
      expect(mockFetch).not.toHaveBeenCalled();
    }
  );

  it.each(['.', '..'])(
    'guards direct API-client note key %j before WHATWG URL normalization',
    async (noteKey) => {
      const candidateUrl =
        `http://localhost:8000/api/v1/evidence/notes/` + encodeURIComponent(noteKey);
      expect(new URL(candidateUrl).pathname).not.toBe(
        `/api/v1/evidence/notes/${noteKey}`
      );
      const directClient = new TraceLabClient({
        baseUrl: 'http://localhost:8000',
        apiKey: 'tl_direct-client-test',
      });

      await expect(
        directClient.putEvidenceNote(noteKey, {
          project_id: PROJECT_ID,
          session_key: 'session',
          content: 'content',
        })
      ).rejects.toThrow('note_key cannot be "." or ".."');
      expect(mockFetch).not.toHaveBeenCalled();
    }
  );

  it('guards a whitespace-only direct API-client note key before fetch', async () => {
    const directClient = new TraceLabClient({
      baseUrl: 'http://localhost:8000',
      apiKey: 'tl_direct-client-test',
    });

    await expect(
      directClient.putEvidenceNote('   ', {
        project_id: PROJECT_ID,
        session_key: 'session',
        content: 'content',
      })
    ).rejects.toThrow(/empty or whitespace/);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('capture uses POST with API-key auth, exact body, and raw full-entry response', async () => {
    const apiResponse = { entries: [entryFixture], count: 1 };
    mockFetch.mockResolvedValueOnce(okJson(apiResponse));
    const { handleTracelabEvidence } = await import('./index.js');

    const result = await handleTracelabEvidence({
      action: 'capture',
      project_id: PROJECT_ID,
      session_key: ' session / 42 ',
      mission_id: MISSION_ID,
      entries: [
        {
          claim: ` ${entryFixture.claim} `,
          summary: entryFixture.summary,
          source_url: entryFixture.source_url,
          snippet: entryFixture.snippet,
          query: entryFixture.query,
          disposition: entryFixture.disposition,
          tags: [' contract ', 'mcp', 'contract'],
        },
      ],
    });

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, request] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('http://localhost:8000/api/v1/evidence/capture');
    expect(request.method).toBe('POST');
    expect(request.headers).toEqual(
      expect.objectContaining({
        'Content-Type': 'application/json',
        'X-API-Key': 'tl_shared-client-test',
      })
    );
    expect(JSON.parse(request.body as string)).toEqual({
      project_id: PROJECT_ID,
      session_key: 'session / 42',
      mission_id: MISSION_ID,
      entries: [
        {
          claim: entryFixture.claim,
          summary: entryFixture.summary,
          source_url: entryFixture.source_url,
          snippet: entryFixture.snippet,
          query: entryFixture.query,
          disposition: entryFixture.disposition,
          tags: entryFixture.tags,
        },
      ],
    });
    expect(JSON.parse(result.content[0].text)).toEqual(apiResponse);
  });

  it('rejects a non-HTTP source URL before issuing a capture request', async () => {
    const { handleTracelabEvidence } = await import('./index.js');

    await expect(
      handleTracelabEvidence({
        action: 'capture',
        project_id: PROJECT_ID,
        session_key: 'session / 42',
        entries: [
          {
            claim: 'FTP sources are outside the canonical web-source contract.',
            source_url: 'ftp://example.com/research',
            disposition: 'rejected',
          },
        ],
      })
    ).rejects.toThrow('source_url must be an absolute HTTP(S) URL');
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('note uses PUT with an encoded key, exact body, and raw full-note response', async () => {
    mockFetch.mockResolvedValueOnce(okJson(noteFixture));
    const { handleTracelabEvidence } = await import('./index.js');

    const result = await handleTracelabEvidence({
      action: 'note',
      project_id: PROJECT_ID,
      session_key: ' session / 42 ',
      note_key: ' open/question ? ',
      content: ` ${noteFixture.content} `,
      mission_id: MISSION_ID,
      tags: [' working-note ', 'working-note'],
    });

    const [url, request] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(
      'http://localhost:8000/api/v1/evidence/notes/open%2Fquestion%20%3F'
    );
    expect(request.method).toBe('PUT');
    expect(JSON.parse(request.body as string)).toEqual({
      project_id: PROJECT_ID,
      session_key: 'session / 42',
      content: noteFixture.content,
      mission_id: MISSION_ID,
      tags: noteFixture.tags,
    });
    expect(JSON.parse(result.content[0].text)).toEqual(noteFixture);
  });

  it('list uses GET with exact encoded filters and returns entries and notes unchanged', async () => {
    const apiResponse = {
      entries: [entryFixture],
      notes: [noteFixture],
      entry_total: 1,
      note_total: 1,
      page: 2,
      page_size: 5,
    };
    mockFetch.mockResolvedValueOnce(okJson(apiResponse));
    const { handleTracelabEvidence } = await import('./index.js');

    const result = await handleTracelabEvidence({
      action: 'list',
      project_id: PROJECT_ID,
      session_key: ' session / 42 ',
      mission_id: MISSION_ID,
      disposition: 'background',
      page: 2,
      page_size: 5,
    });

    const [url, request] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(
      `http://localhost:8000/api/v1/evidence?project_id=${PROJECT_ID}` +
        `&session_key=session+%2F+42&mission_id=${MISSION_ID}` +
        '&disposition=background&page=2&page_size=5'
    );
    expect(request.method).toBe('GET');
    expect(request.body).toBeUndefined();
    expect(JSON.parse(result.content[0].text)).toEqual(apiResponse);
  });

  it('search uses GET with q plus exact encoded filters and returns entries unchanged', async () => {
    const apiResponse = { entries: [entryFixture], total: 1, page: 3, page_size: 7 };
    mockFetch.mockResolvedValueOnce(okJson(apiResponse));
    const { handleTracelabEvidence } = await import('./index.js');

    const result = await handleTracelabEvidence({
      action: 'search',
      project_id: PROJECT_ID,
      q: ' conflicting source & context ',
      session_key: ' session / 42 ',
      mission_id: MISSION_ID,
      disposition: 'contradicting',
      page: 3,
      page_size: 7,
    });

    const [url, request] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(
      `http://localhost:8000/api/v1/evidence/search?project_id=${PROJECT_ID}` +
        '&q=conflicting+source+%26+context&session_key=session+%2F+42' +
        `&mission_id=${MISSION_ID}&disposition=contradicting&page=3&page_size=7`
    );
    expect(request.method).toBe('GET');
    expect(request.body).toBeUndefined();
    expect(JSON.parse(result.content[0].text)).toEqual(apiResponse);
  });

  it('promote defaults target to report, POSTs the exact body, and preserves every response field', async () => {
    const apiResponse = {
      project_id: PROJECT_ID,
      session_key: 'session / 42',
      target: 'report',
      report_id: '77777777-7777-4777-8777-777777777777',
      document_id: null,
      title: 'Session evidence',
      entry_count: 1,
      note_count: 1,
      status: 'created',
    };
    mockFetch.mockResolvedValueOnce(okJson(apiResponse));
    const { handleTracelabEvidence } = await import('./index.js');

    const result = await handleTracelabEvidence({
      action: 'promote',
      project_id: PROJECT_ID,
      session_key: ' session / 42 ',
      title: ' Session evidence ',
    });

    const [url, request] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('http://localhost:8000/api/v1/evidence/promote');
    expect(request.method).toBe('POST');
    expect(JSON.parse(request.body as string)).toEqual({
      project_id: PROJECT_ID,
      session_key: 'session / 42',
      title: 'Session evidence',
      target: 'report',
    });
    expect(JSON.parse(result.content[0].text)).toEqual(apiResponse);
  });

  it('returns an actionable error for an unknown evidence action without calling the API', async () => {
    const { handleTracelabEvidence } = await import('./index.js');
    const result = await handleTracelabEvidence({ action: 'erase' });

    expect(result.isError).toBe(true);
    expect(result.content[0].text).toContain('tracelab_evidence');
    expect(result.content[0].text).toContain('capture, note, list, search, promote');
    expect(mockFetch).not.toHaveBeenCalled();
  });
});
