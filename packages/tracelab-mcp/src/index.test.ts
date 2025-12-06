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
        json: () => Promise.resolve({ detail: 'Invalid token' }),
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
        json: () => Promise.resolve({ detail: 'Not found' }),
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
