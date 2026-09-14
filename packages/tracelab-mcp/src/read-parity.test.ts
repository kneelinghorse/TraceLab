import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { TraceLabClient } from './api-client.js';

const id = '00000000-0000-4000-8000-000000000001';
const base = 'https://api.tracelab.aquex.ai';
const web = 'https://tracelab.aquex.ai';
const authored = '# Keep bytes\r\n\n[Original](https://example.org/authored)\n';
const fetchMock = vi.fn();
let dispatch: typeof import('./index.js').resolveClusterHandler;

beforeAll(async () => {
  vi.stubEnv('TRACELAB_API_URL', base);
  vi.stubEnv('TRACELAB_API_KEY', 'tl_read_contract');
  vi.stubEnv('TRACELAB_TOKEN', '');
  vi.stubGlobal('fetch', fetchMock);
  dispatch = (await import('./index.js')).resolveClusterHandler;
});
beforeEach(() => fetchMock.mockReset());
afterAll(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

function respond(payload: unknown) {
  fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(payload), { headers: { 'content-type': 'application/json' } }));
}
async function invoke(tool: string, args: Record<string, unknown>) {
  const handler = dispatch(`tracelab_${tool}`);
  expect(handler, `Callable ${tool} cluster`).toBeTypeOf('function');
  const response = await handler!(args);
  expect(response).not.toHaveProperty('isError', true);
  return JSON.parse(response.content[0].text);
}

const section = (items: unknown[], total = 37) => ({ items, total });
const home = {
  missions: { total: 83, by_status: { completed: 83 } },
  attention: section([{ id, evidence_href: `/evidence?project_id=${id}`, title: authored }]),
  active_runs: section([{ id }]),
  recent_reports: section([{ id, href: `/reports/${id}`, title: authored }]),
  recent_projects: section([{ id, href: `/projects/${id}` }]),
  favorites: section([{ id, href: `/projects/${id}` }]),
  evidence_activity: section([{ project_id: id, href: `/evidence?project_id=${id}` }]),
};

describe('MCP-1 read parity', () => {
  it.each([
    ['home', { action: 'snapshot' }, '/home', home, 'missions.total', 83],
    ['home', { action: 'favorites', page: 2, page_size: 3, project_id: id }, `/home/favorites?page=2&page_size=3&project_id=${id}`, section([{ id, href: `/projects/${id}` }]), 'items.0.url', `${web}/projects/${id}`],
    ['search', { action: 'navigate', q: 'A & B', entity_type: 'document', page: 2, page_size: 3 }, '/navigation/search?q=A+%26+B&entity_type=document&page=2&page_size=3', { query: 'A & B', groups: [{ entity_type: 'document', total: 37, items: [{ id, href: `/documents/${id}` }] }] }, 'groups.0.items.0.url', `${web}/documents/${id}`],
    ['evidence', { action: 'get', entry_id: id }, `/evidence/${id}`, { entry: { id, source_url: 'https://example.org/authored' }, links: [{ id, href: `/reports/${id}`, kind: 'report' }] }, 'entry.url', `${web}/evidence/${id}`],
    ['document', { action: 'list', project_id: id, processed: false, search: 'A & B', page: 2, page_size: 3 }, `/documents?project_id=${id}&processed=false&search=A+%26+B&page=2&page_size=3`, { data: [{ id, name: authored }], pagination: { total: 83, page: 2, page_size: 3 } }, 'total', 83],
    ['project', { action: 'get', project_id: id }, `/projects/${id}`, { id, name: authored }, 'url', `${web}/projects/${id}`],
    ['collection', { action: 'documents', collection_id: id, page: 2, page_size: 3 }, `/collections/${id}/documents?page=2&page_size=3`, { items: [{ id, name: authored }], total: 83, page: 2, page_size: 3 }, 'items.0.url', `${web}/documents/${id}`],
    ['collection', { action: 'mission_seed', collection_id: id }, `/collections/${id}/mission-seed`, { collection_id: id, background: authored, references: [{ document_id: id, href: `/documents/${id}`, title: authored }], context: { original: authored } }, 'url', `${web}/collections/${id}`],
    ['mission_execution', { action: 'logs', mission_id: id, limit: 3 }, `/missions/${id}/logs?limit=3`, [], 'empty', true],
    ['mission_execution', { action: 'events', mission_id: id, limit: 3 }, `/missions/events/recent?mission_id=${id}&limit=3`, [], 'empty', true],
  ])('%s.%s uses the scoped REST contract and keeps server totals', async (tool, args, route, payload, field, expected) => {
    respond(payload);
    const value = await invoke(tool as string, args as Record<string, unknown>);
    expect((field as string).split('.').reduce((node, key) => node[key], value)).toEqual(expected);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(base + '/api/v1' + route, expect.objectContaining({ method: 'GET', headers: expect.objectContaining({ 'X-API-Key': 'tl_read_contract' }) }));
  });

  it.each([false, true])('offers optional PEDR with graph=%s and preserves diagnostics', async enable_graph => {
    const metadata = { degraded: false, layers_used: ['lexical', 'semantic'], graph_enabled: enable_graph, total_candidates: 83, layer_diagnostics: [{ layer: 'graph', status: enable_graph ? 'ok' : 'disabled' }] };
    respond({ results: [{ chunk_id: id, document_id: id, project_id: id, content: authored, url: 'https://example.org/authored', rrf_score: 0.7 }], metadata });
    const payload = { query: 'Research', top_k: 3, project_id: id, source_type: 'report', date_from: '2026-01-01', date_to: '2026-09-14', enable_graph };
    const value = await invoke('search', { action: 'pedr', ...payload });
    expect(value.metadata).toEqual(metadata);
    expect(value.results[0]).toMatchObject({ content: authored, url: 'https://example.org/authored', document_url: `${web}/documents/${id}` });
    expect(fetchMock).toHaveBeenCalledWith(`${base}/api/v1/pedr/search`, expect.objectContaining({ method: 'POST', body: JSON.stringify(payload) }));
  });

  it('keeps knowledge on plain retrieval while forwarding UI source/date filters', async () => {
    respond({ results: [] });
    const filters = { source_type: 'report', date_from: '2026-01-01', date_to: '2026-09-14' };
    await invoke('search', { action: 'knowledge', query: 'Research', limit: 3, project_id: id, ...filters });
    expect(fetchMock).toHaveBeenCalledWith(`${base}/api/v1/retrieval/search`, expect.objectContaining({ method: 'POST', body: JSON.stringify({ query: 'Research', top_k: 3, project_id: id, ...filters }) }));
  });

  for (const action of ['list', 'search']) {
    it.each(['report_id', 'document_id'])('accepts REST calendar dates and one %s filter for evidence.' + action, async field => {
      respond({ entries: [], notes: [], total: 0, entry_total: 0 });
      const filters = { tag: 'research', created_from: '2026-09-01', created_until: '2026-09-14', source_id: id, [field]: id };
      await invoke('evidence', { action, project_id: id, ...(action === 'search' ? { q: 'research' } : {}), ...filters });
      const requestUrl = new URL(fetchMock.mock.calls[0][0]);
      for (const [key, value] of Object.entries(filters)) expect(requestUrl.searchParams.get(key)).toBe(value);
      expect(requestUrl.pathname).toBe('/api/v1/evidence' + (action === 'search' ? '/search' : ''));
    });
    it.each([
      { created_from: '2026-09-01T12:00:00Z' },
      { created_until: '2026-02-30' },
      { source_id: 'source/hash' },
      { report_id: id, document_id: id },
      { created_from: '2026-09-14', created_until: '2026-09-01' },
      { created_until: '9999-12-31' },
      { tag: '' },
    ])('rejects API-invalid evidence.' + action + ' filters before HTTP: %j', async filters => {
      await expect(invoke('evidence', { action, project_id: id, ...(action === 'search' ? { q: 'research' } : {}), ...filters })).rejects.toThrow();
      expect(fetchMock).not.toHaveBeenCalled();
    });
  }

  it('keeps every home href and authored field, without caching snapshot totals', async () => {
    respond(home);
    respond({ ...home, missions: { total: 84, by_status: {} } });
    const first = await invoke('home', { action: 'snapshot' });
    const second = await invoke('home', { action: 'snapshot' });
    expect(first.recent_reports.items[0]).toMatchObject(home.recent_reports.items[0]);
    expect(first.recent_reports.items[0].url).toBe(`${web}/reports/${id}`);
    expect(first.attention.items[0].title).toBe(authored);
    expect(first.attention.items[0].evidence_href).toBe(home.attention.items[0].evidence_href);
    expect(second.missions.total).toBe(84);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('preserves mission-seed references, background and context', async () => {
    const payload = { collection_id: id, background: authored, references: [{ document_id: id, href: `/documents/${id}`, title: authored, url: 'https://example.org/authored' }], context: { references: [{ url: 'https://example.org/authored' }] } };
    respond(payload);
    const value = await invoke('collection', { action: 'mission_seed', collection_id: id });
    expect(value.background).toBe(authored);
    expect(value.context).toEqual(payload.context);
    expect(value.references[0]).toMatchObject(payload.references[0]);
    expect(value.references[0].document_url).toBe(`${web}/documents/${id}`);
  });

  it.each(['md', 'json', 'txt'] as const)('preserves exported %s response bytes', async format => {
    const bytes = format === 'json' ? '{\n "content": "Keep whitespace"\n}\n' : authored;
    fetchMock.mockResolvedValueOnce(new Response(bytes, { headers: { 'content-type': format === 'json' ? 'application/json' : 'text/plain' } }));
    const client = new TraceLabClient({ baseUrl: base, apiKey: 'tl_read_contract' });
    expect(await client.exportReport(id, format)).toBe(bytes);
    expect(fetchMock).toHaveBeenCalledWith(`${base}/api/v1/reports/${id}/export?format=${format}`, expect.objectContaining({ method: 'GET' }));
  });

  it('keeps no-format export byte-identical to report.content', async () => {
    respond({ id, content: authored });
    const client = new TraceLabClient({ baseUrl: base, apiKey: 'tl_read_contract' });
    expect(await client.exportReport(id)).toBe(authored);
    expect(fetchMock).toHaveBeenCalledWith(`${base}/api/v1/reports/${id}`, expect.objectContaining({ method: 'GET' }));
  });

  it.each([
    ['search', { action: 'navigate', q: 'name', entity_type: 'user' }],
    ['search', { action: 'navigate', q: 'name', page_size: 51 }],
    ['mission_execution', { action: 'logs', mission_id: id, limit: 501 }],
    ['mission_execution', { action: 'events', mission_id: id, limit: 201 }],
    ['document', { action: 'list', processed: 'false' }],
    ['report', { action: 'export', report_id: id, format: 'pdf' }],
  ])('rejects invalid %s input before HTTP', async (tool, args) => {
    await expect(dispatch(`tracelab_${tool}`)!(args)).rejects.toThrow();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
