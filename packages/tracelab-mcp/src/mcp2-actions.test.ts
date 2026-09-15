import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

// MCP-2 (sprint-52): every new action must call exactly the REST route the UI
// calls, with the same verb, query string and body, and generated links must go
// through the canonical helper while hrefs and authored fields are preserved.
const id = '00000000-0000-4000-8000-000000000001';
const other = '00000000-0000-4000-8000-000000000002';
const base = 'https://api.tracelab.aquex.ai';
const web = 'https://tracelab.aquex.ai';
const authored = '# Keep bytes\r\n\n[Original](https://example.org/authored)\n';
const fetchMock = vi.fn();
let dispatch: typeof import('./index.js').resolveClusterHandler;

beforeAll(async () => {
  vi.stubEnv('TRACELAB_API_URL', base);
  vi.stubEnv('TRACELAB_API_KEY', 'tl_action_contract');
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
function lastRequest() {
  const [url, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
  return { url, method: init.method, body: typeof init.body === 'string' ? JSON.parse(init.body) : undefined, headers: init.headers as Record<string, string> };
}
async function rejects(tool: string, args: Record<string, unknown>) {
  await expect(dispatch(`tracelab_${tool}`)!(args)).rejects.toThrow();
}

describe('MCP-2 non-destructive actions', () => {
  it('cancel sends only status=cancelled through PATCH and rejects every other status', async () => {
    respond({ id, mission_id: 'R-1', title: authored, status: 'cancelled', updated_at: '2026-09-15T00:00:00' });
    const value = await invoke('mission_execution', { action: 'cancel', mission_id: id });
    expect(lastRequest()).toMatchObject({ url: `${base}/api/v1/missions/${id}`, method: 'PATCH', body: { status: 'cancelled' } });
    expect(lastRequest().headers['X-API-Key']).toBe('tl_action_contract');
    expect(value.mission).toMatchObject({ id, url: `${web}/missions/${id}`, status: 'cancelled', title: authored });
    for (const status of ['completed', 'queued', 'in_progress', 'blocked', 'validation_failed', 'draft', 'CANCELLED', '']) {
      await rejects('mission_execution', { action: 'cancel', mission_id: id, status });
    }
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('mission update strips status so the generic PATCH never becomes a status write', async () => {
    respond({ id, mission_id: 'R-1', title: authored, status: 'draft' });
    await invoke('mission', { action: 'update', mission_id: id, title: authored, status: 'completed' });
    expect(lastRequest()).toMatchObject({ method: 'PATCH', body: { title: authored } });
    expect(lastRequest().body).not.toHaveProperty('status');
  });

  it('promote_report posts to the promotion route and links mission and document', async () => {
    respond({ document_id: other, document_name: authored, status: 'completed', message: 'Promoted', chunk_count: 3 });
    const value = await invoke('mission_execution', { action: 'promote_report', mission_id: id });
    expect(lastRequest()).toMatchObject({ url: `${base}/api/v1/missions/${id}/promote-report`, method: 'POST', body: undefined });
    expect(value).toMatchObject({ document_name: authored, chunk_count: 3, url: `${web}/missions/${id}`, document_url: `${web}/documents/${other}` });
  });

  it('document process posts the ingestion route exactly as the upload page does', async () => {
    respond({ document_id: id, status: 'processing' });
    const value = await invoke('document', { action: 'process', document_id: id });
    expect(lastRequest()).toMatchObject({ url: `${base}/api/v1/documents/${id}/process`, method: 'POST', body: {} });
    expect(value).toMatchObject({ document_id: id, status: 'processing', url: `${web}/documents/${id}` });
    await rejects('document', { action: 'process', document_id: 'not-a-uuid' });
  });

  it('collection update requires at least one field and sends only the provided ones', async () => {
    await rejects('collection', { action: 'update', collection_id: id });
    respond({ id, name: 'Renamed', instructions: authored, item_count: 1 });
    const value = await invoke('collection', { action: 'update', collection_id: id, instructions: authored });
    expect(lastRequest()).toMatchObject({ url: `${base}/api/v1/collections/${id}`, method: 'PUT', body: { instructions: authored } });
    expect(lastRequest().body).not.toHaveProperty('name');
    expect(value.collection).toMatchObject({ id, instructions: authored, url: `${web}/collections/${id}` });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('collection add_document posts the document id the picker sends', async () => {
    respond({ id: other, name: authored, project_id: id, file_type: 'md' });
    const value = await invoke('collection', { action: 'add_document', collection_id: id, document_id: other });
    expect(lastRequest()).toMatchObject({ url: `${base}/api/v1/collections/${id}/documents`, method: 'POST', body: { document_id: other } });
    expect(value).toMatchObject({ id: other, name: authored, url: `${web}/documents/${other}`, collection_url: `${web}/collections/${id}` });
  });

  it('report update PUTs title and status and rejects statuses the UI cannot set', async () => {
    await rejects('report', { action: 'update', report_id: id });
    await rejects('report', { action: 'update', report_id: id, status: 'archived' });
    respond({ id, title: authored, status: 'final', content: authored, sources: [] });
    const value = await invoke('report', { action: 'update', report_id: id, status: 'final' });
    expect(lastRequest()).toMatchObject({ url: `${base}/api/v1/reports/${id}`, method: 'PUT', body: { status: 'final' } });
    expect(value.report).toMatchObject({ id, title: authored, content: authored, url: `${web}/reports/${id}` });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe('MCP-2 Sprint 52 surface reads', () => {
  const kinds = ['project', 'document', 'collection', 'mission', 'report', 'evidence'] as const;
  const node = (type: (typeof kinds)[number]) => ({ key: `${type}:${id}`, type, id, title: authored, href: `/${type === 'evidence' ? type : `${type}s`}/${id}`, attributes: {} });

  it('neighborhood forwards the UI query defaults and links all six node types', async () => {
    respond({ root: node('project'), nodes: kinds.map(node), edges: [{ from: `project:${id}`, to: `document:${id}`, relation: 'documents', basis: 'persisted' }], groups: [{ from_key: `project:${id}`, relation: 'documents', target_type: 'document', total: 83, shown: 1 }], truncated: true });
    const value = await invoke('project', { action: 'neighborhood', root_type: 'project', root_id: id });
    expect(lastRequest()).toMatchObject({ url: `${base}/api/v1/graph/neighborhood?root_type=project&root_id=${id}&depth=1&per_relation_limit=12&max_nodes=60`, method: 'GET' });
    expect(value.root).toMatchObject({ href: `/projects/${id}`, url: `${web}/projects/${id}`, title: authored });
    expect(value.nodes.map((entry: { url: string }) => entry.url)).toEqual(kinds.map(type => `${web}/${type === 'evidence' ? type : `${type}s`}/${id}`));
    expect(value.groups[0].total).toBe(83);
    expect(value.truncated).toBe(true);
    await rejects('project', { action: 'neighborhood', root_type: 'project', root_id: id, depth: 3 });
    await rejects('project', { action: 'neighborhood', root_type: 'chunk', root_id: id });
  });

  it('attention keeps the bare route without a project and scopes it with one', async () => {
    const attention = { generated_at: '2026-09-15T00:00:00', stalled_after_seconds: 3600, total: 5, by_reason: { validation_failed: 1, blocked: 1, stalled: 1, unreviewed: 2 }, dashboards: [{ key: 'at_risk', total: 3 }, { key: 'unreviewed', total: 2 }] };
    respond(attention);
    expect(await invoke('home', { action: 'attention' })).toEqual(attention);
    expect(lastRequest().url).toBe(`${base}/api/v1/home/attention`);
    respond(attention);
    await invoke('home', { action: 'attention', project_id: id });
    expect(lastRequest().url).toBe(`${base}/api/v1/home/attention?project_id=${id}`);
  });

  it('mission list forwards repeatable reasons after view and keeps the plain URL byte-identical', async () => {
    const page = { data: [], pagination: { page: 1, page_size: 20, total: 0, pages: 0 } };
    respond(page);
    await invoke('mission', { action: 'list' });
    expect(lastRequest().url).toBe(`${base}/api/v1/missions?page=1&page_size=20`);
    respond(page);
    await invoke('mission', { action: 'list', view: 'attention', reason: ['blocked', 'stalled'], project_id: id });
    expect(lastRequest().url).toBe(`${base}/api/v1/missions?page=1&page_size=20&project_id=${id}&view=attention&reason=blocked&reason=stalled`);
    await rejects('mission', { action: 'list', reason: ['blocked'] });
    await rejects('mission', { action: 'list', view: 'queue', reason: ['blocked'] });
    await rejects('mission', { action: 'list', view: 'attention', reason: ['invented'] });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('views returns saved mission views with live totals and UI-equivalent links', async () => {
    respond({ items: [{ id, name: authored, entity_type: 'missions', filters: { view: 'attention', reason: ['blocked', 'stalled'], project_id: other }, total: 83, created_at: '2026-09-14T00:00:00', updated_at: '2026-09-14T00:00:00' }, { id: other, name: 'Everything', entity_type: 'missions', filters: {}, total: 4 }] });
    const value = await invoke('mission', { action: 'views' });
    expect(lastRequest()).toMatchObject({ url: `${base}/api/v1/mission-views`, method: 'GET' });
    expect(value.items[0]).toMatchObject({ name: authored, total: 83, href: `/missions?view=attention&reason=blocked&reason=stalled&project_id=${other}`, url: `${web}/missions?view=attention&reason=blocked&reason=stalled&project_id=${other}` });
    expect(value.items[1]).toMatchObject({ href: '/missions', url: `${web}/missions` });
  });

  it('inbox_summary and inbox_list use the scoped inbox routes and link items', async () => {
    const summary = { generated_at: '2026-09-15T00:00:00.123456', refresh_seconds: 30, seen_through: '2026-09-08T00:00:00', default_lookback_seconds: 604800, unread: { failures: 0, completions: 4, evidence: 6, total: 10 } };
    respond(summary);
    expect(await invoke('home', { action: 'inbox_summary' })).toEqual(summary);
    expect(lastRequest().url).toBe(`${base}/api/v1/inbox/summary`);
    respond({ section: 'evidence', generated_at: summary.generated_at, seen_through: summary.seen_through, total: 59, items: [{ section: 'evidence', id: `${id}:${other}:run:mcp-agent`, title: 'run', label: 'mcp-agent', occurred_at: '2026-09-14T23:00:00', unread: true, href: `/evidence?project_id=${id}&mission_id=${other}&session_key=run`, entry_count: 12 }] });
    const page = await invoke('home', { action: 'inbox_list', section: 'evidence', unread_only: true });
    expect(lastRequest().url).toBe(`${base}/api/v1/inbox?section=evidence&page=1&page_size=20&unread_only=true`);
    expect(page.total).toBe(59);
    expect(page.items[0]).toMatchObject({ entry_count: 12, href: `/evidence?project_id=${id}&mission_id=${other}&session_key=run`, url: `${web}/evidence?project_id=${id}&mission_id=${other}&session_key=run` });
    await rejects('home', { action: 'inbox_list' });
    await rejects('home', { action: 'inbox_list', section: 'everything' });
  });
});
