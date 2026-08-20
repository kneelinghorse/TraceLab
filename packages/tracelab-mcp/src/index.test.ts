/**
 * Integration tests for TraceLab MCP Server
 *
 * These tests verify the tool implementations work correctly with mocked API responses.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { TraceLabClient, TraceLabAPIError } from './api-client.js';

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

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
//   1. Exactly 7 visible MCP tools, all named tracelab_*
//   2. Every legacy tool name maps to a (cluster, action) pair where
//      action is in the cluster's action enum
//   3. Each cluster dispatches to the correct per-action handler
// ─────────────────────────────────────────────────────────────────────────

describe('T41.7 — cluster surface', () => {
  it('exposes exactly 7 tracelab_* tools', async () => {
    const indexSource = await import('./index.js');
    const { CLUSTER_ACTIONS } = indexSource as unknown as {
      CLUSTER_ACTIONS: Record<string, readonly string[]>;
    };
    const toolNames = Object.keys(CLUSTER_ACTIONS);
    expect(toolNames).toHaveLength(7);
    expect(toolNames.sort()).toEqual([
      'tracelab_collection',
      'tracelab_document',
      'tracelab_mission',
      'tracelab_mission_execution',
      'tracelab_project',
      'tracelab_report',
      'tracelab_search',
    ]);
  });

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
        materialization_status: 'retry_pending',
        materialization_attempt_count: 2,
        materialization_error: 'embedding provider unavailable',
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
      materialization_status: 'retry_pending',
      materialization_attempt_count: 2,
      materialization_error: 'embedding provider unavailable',
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
