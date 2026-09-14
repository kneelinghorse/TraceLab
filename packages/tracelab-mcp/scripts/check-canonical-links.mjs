// Exercise the actual stdio entrypoint and HTTP verbs, including from an installed tarball.
import assert from 'node:assert/strict';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';

const root = fileURLToPath(new URL('../', import.meta.url));
const entrypoint = path.resolve(process.argv[2] ?? path.join(root, 'dist/index.js'));
const web = 'https://tracelab.aquex.ai';
const ids = Object.fromEntries(['project', 'document', 'mission', 'report', 'collection', 'evidence', 'chunk', 'note'].map((kind, i) => [kind, `00000000-0000-4000-8000-${String(i + 1).padStart(12, '0')}`]));
const archivedUrl = web + '/console/missions/ARCHIVED-1?q=original';
const markdown = `# Authored evidence\n\n[Original reference](${archivedUrl})\n`;
const references = [{ title: 'Original reference', url: archivedUrl }];
const pagination = { page: 1, page_size: 20, total: 1, pages: 1 };
const project = { id: ids.project, project_id: ids.project, name: 'Project', status: 'active' };
const document = { id: ids.document, name: 'Document', project_id: ids.project, file_type: 'md' };
const chunk = { chunk_id: ids.chunk, document_id: ids.document, content: markdown, score: 0.9, chunk_index: 0 };
const collection = { instructions: markdown, id: ids.collection, name: 'Collection', item_count: 1, items: [{ id: ids.chunk, chunk_id: ids.chunk, document_id: ids.document, chunk_content: markdown }] };
const report = { id: ids.report, title: 'Report', content: markdown, citations: references, sources: [] };
const mission = { id: ids.mission, mission_id: 'MIGRATION-1', title: 'Mission', objective: 'Preserve authored evidence', status: 'completed', project_id: ids.project, context: { references }, references, success_criteria: ['Canonical navigation'], result_report_id: ids.report, result_document_ids: [ids.document] };
const evidence = { id: ids.evidence, project_id: ids.project, claim: 'Sourced claim', source_url: archivedUrl, disposition: 'supporting' };
const note = { id: ids.note, project_id: ids.project, content: markdown };
const preview = { mission_id: mission.mission_id, mission_uuid: ids.mission, objectives: [], evidence_slots: [], acceptance_checks: [], deliverable_schemas: [], references };
const calls = [];
const routes = new Map();
const route = (method, pathname, payload) => routes.set(method + ' ' + pathname, payload);
route('POST', '/retrieval/search', { results: [chunk] });
const pedrMetadata = { degraded: false, total_candidates: 83, layer_diagnostics: [{ layer: 'lexical', status: 'ok' }] };
route('POST', '/pedr/search', { results: [{ ...chunk, rrf_score: 0.7 }], metadata: pedrMetadata });
route('GET', '/projects', { data: [project], pagination });
route('POST', '/projects', project);
route('PUT', `/projects/${ids.project}`, project);
route('GET', `/projects/${ids.project}/stats`, project);
route('GET', '/collections', { data: [collection], total: 1 });
route('GET', `/collections/${ids.collection}`, collection);
route('POST', '/collections', collection);
route('POST', `/collections/${ids.collection}/chunks`, collection.items[0]);
route('GET', `/collections/${ids.collection}/export`, markdown);
route('POST', '/synthesize', { content: markdown, citations: references, report_id: ids.report });
route('GET', '/reports', { items: [report], ...pagination });
route('GET', `/reports/${ids.report}`, report);
route('POST', '/reports', report);
route('GET', `/documents/${ids.document}`, document);
route('GET', `/documents/${ids.document}/chunks`, { data: [chunk], pagination });
route('POST', '/documents/upload', document);
route('GET', '/missions', { data: [mission], pagination });
route('GET', `/missions/${ids.mission}`, mission);
route('POST', '/missions', mission);
route('PATCH', `/missions/${ids.mission}`, mission);
route('POST', `/missions/${ids.mission}/submit`, { uuid: ids.mission, mission_id: mission.mission_id, status: 'queued', mode: 'worker' });
route('GET', `/missions/${ids.mission}/status`, mission);
route('GET', `/missions/${ids.mission}/contract-preview`, preview);
route('GET', '/evidence', { entries: [evidence], notes: [note], entry_total: 1, note_total: 1 });
route('GET', '/evidence/search', { entries: [evidence], total: 1 });
route('POST', '/evidence/capture', { entries: [evidence], count: 1 });
route('PUT', '/evidence/notes/working', note);
route('POST', '/evidence/promote', { project_id: ids.project, report_id: ids.report, document_id: ids.document, target: 'document' });

const section = items => ({ total: 83, items });
const recentProject = { id: ids.project, title: 'Project', href: `/projects/${ids.project}` };
const recentReport = { id: ids.report, title: markdown, href: `/reports/${ids.report}` };
const home = { missions: { total: 83, by_status: { completed: 83 } }, attention: section([{ ...mission, evidence_href: `/evidence?project_id=${ids.project}` }]), active_runs: section([mission]), recent_reports: section([recentReport]), recent_projects: section([recentProject]), favorites: section([recentProject]), evidence_activity: section([{ project_id: ids.project, href: `/evidence?project_id=${ids.project}` }]) };
const seed = { collection_id: ids.collection, project_id: ids.project, background: markdown, references: [{ document_id: ids.document, title: markdown, href: `/documents/${ids.document}`, url: archivedUrl }], context: { references } };
const jsonExport = '{\n "content": "Keep exact JSON whitespace"\n}\n';
route('GET', '/home', home);
route('GET', '/home/favorites', section([recentProject]));
route('GET', '/navigation/search', { query: 'A & B', groups: [{ entity_type: 'document', total: 83, page: 2, page_size: 3, items: [{ id: ids.document, title: markdown, href: `/documents/${ids.document}` }] }] });
route('GET', `/evidence/${ids.evidence}`, { entry: evidence, links: [{ id: ids.report, title: markdown, href: `/reports/${ids.report}`, kind: 'report' }] });
route('GET', '/documents', { data: [document], pagination: { ...pagination, total: 83 } });
route('GET', `/projects/${ids.project}`, project);
route('GET', `/collections/${ids.collection}/documents`, { items: [document], total: 83, page: 2, page_size: 3 });
route('GET', `/collections/${ids.collection}/mission-seed`, seed);
route('GET', `/missions/${ids.mission}/logs`, [{ id: ids.note, message: markdown }]);
route('GET', '/missions/events/recent', [{ mission_id: ids.mission, event_type: 'mission.completed', details: { references } }]);
route('GET', `/reports/${ids.report}/export`, requestUrl => ({ bytes: requestUrl.searchParams.get('format') === 'json' ? jsonExport : markdown, contentType: requestUrl.searchParams.get('format') === 'json' ? 'application/json' : 'text/plain' }));

const server = http.createServer(async (request, response) => {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  const requestUrl = new URL(request.url, 'http://localhost');
  const pathname = requestUrl.pathname.replace(/^\/api\/v1/, '');
  const key = request.method + ' ' + pathname;
  calls.push({ key, query: requestUrl.search.slice(1), authenticated: request.headers['x-api-key'] === 'tl_contract_test', body: request.headers['content-type']?.includes('application/json') ? JSON.parse(Buffer.concat(chunks).toString() || 'null') : null });
  if (!routes.has(key)) { response.writeHead(405); response.end('Unexpected HTTP verb or route'); return; }
  const payload = routes.get(key);
  if (typeof payload === 'function') {
    const exported = payload(requestUrl);
    response.writeHead(200, { 'Content-Type': exported.contentType });
    response.end(exported.bytes);
    return;
  }
  response.writeHead(200, { 'Content-Type': typeof payload === 'string' ? 'text/markdown' : 'application/json' });
  response.end(typeof payload === 'string' ? payload : JSON.stringify(payload));
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const api = `http://127.0.0.1:${server.address().port}`;
const transport = new StdioClientTransport({ command: process.execPath, args: [entrypoint], env: { TRACELAB_API_URL: api, TRACELAB_FRONTEND_URL: web, TRACELAB_API_KEY: 'tl_contract_test' }, stderr: 'pipe' });
transport.stderr?.on('data', () => {});
const client = new Client({ name: 'canonical-link-contract', version: '1.0.0' });
const checks = [];
const url = (kind) => `${web}/${kind === 'evidence' ? kind : kind + 's'}/${ids[kind]}`;
async function check(tool, args, expectedCalls, links, verify, expectedQueries) {
  const start = calls.length;
  const result = await client.callTool({ name: `tracelab_${tool}`, arguments: args });
  assert.ok(!result.isError, `${tool}/${args.action}: ${JSON.stringify(result)}`);
  assert.deepEqual(calls.slice(start).map(call => call.key), expectedCalls);
  assert.ok(calls.slice(start).every(call => call.authenticated), 'Every HTTP request uses the MCP API-key credential');
  const value = args.action === 'export' ? result.content[0].text : JSON.parse(result.content[0].text);
  for (const [field, target] of Object.entries(links)) {
    const actual = field.split('.').reduce((node, key) => node?.[key], value);
    assert.equal(actual, target, `${tool}/${args.action} canonical ${field}`);
  }
  if (expectedQueries !== undefined) assert.deepEqual(calls.slice(start).map(call => call.query), expectedQueries, `${tool}/${args.action} exact query strings`);
  verify?.(value);
  checks.push({ tool, action: args.action, links: Object.keys(links).length, http: expectedCalls, queries: calls.slice(start).map(call => call.query) });
}
try {
  await client.connect(transport);
  assert.equal((await client.listTools()).tools.length, 9);
  await check('search', { action: 'knowledge', query: 'provenance' }, ['POST /retrieval/search'], { 'results.0.document_url': url('document') });
  await check('project', { action: 'list' }, ['GET /projects'], { 'projects.0.url': url('project') });
  await check('project', { action: 'create', name: 'Project' }, ['POST /projects'], { 'project.url': url('project') });
  await check('project', { action: 'update', project_id: ids.project, name: 'Project' }, [`PUT /projects/${ids.project}`], { 'project.url': url('project') });
  await check('project', { action: 'stats', project_id: ids.project }, [`GET /projects/${ids.project}/stats`], { url: url('project') });
  await check('collection', { action: 'list' }, ['GET /collections'], { 'collections.0.url': url('collection') });
  await check('collection', { action: 'get', collection_id: ids.collection }, [`GET /collections/${ids.collection}`], { url: url('collection'), 'items.0.document_url': url('document') });
  await check('collection', { action: 'create', name: 'Collection' }, ['POST /collections'], { 'collection.url': url('collection') });
  await check('collection', { action: 'add', collection_id: ids.collection, chunk_id: ids.chunk }, [`POST /collections/${ids.collection}/chunks`], { collection_url: url('collection') });
  await check('collection', { action: 'synthesize', collection_id: ids.collection, save_as_report: true, report_title: 'Report' }, ['POST /synthesize'], { collection_url: url('collection'), report_url: url('report') }, value => assert.equal(value.synthesis, markdown));
  await check('collection', { action: 'export', collection_id: ids.collection }, [`GET /collections/${ids.collection}/export`], {}, value => assert.equal(value, markdown));
  await check('report', { action: 'list' }, ['GET /reports'], { 'reports.0.url': url('report') });
  await check('report', { action: 'get', report_id: ids.report }, [`GET /reports/${ids.report}`], { url: url('report') }, value => { assert.equal(value.content, markdown); assert.deepEqual(value.citations, references); });
  await check('report', { action: 'create', title: 'Report', collection_id: ids.collection }, ['POST /reports'], { 'report.url': url('report') });
  await check('report', { action: 'export', report_id: ids.report }, [`GET /reports/${ids.report}`], {}, value => assert.equal(value, markdown));
  await check('document', { action: 'get_content', document_id: ids.document }, [`GET /documents/${ids.document}`, `GET /documents/${ids.document}/chunks`], { url: url('document') }, value => assert.equal(value.content, markdown));
  await check('document', { action: 'upload', project_id: ids.project, name: 'Document', content: Buffer.from(markdown).toString('base64'), content_type: 'text/markdown' }, ['POST /documents/upload'], { 'document.url': url('document') });
  await check('mission', { action: 'list' }, ['GET /missions'], { 'missions.0.url': url('mission') }, value => assert.deepEqual(value.missions[0].references, references));
  await check('mission', { action: 'get', mission_id: ids.mission }, [`GET /missions/${ids.mission}`], { url: url('mission') }, value => { assert.deepEqual(value.references, references); assert.deepEqual(value.context, mission.context); });
  await check('mission', { action: 'create', mission_id: 'MIGRATION-1', title: 'Mission', objective: mission.objective, success_criteria: mission.success_criteria, project_id: ids.project, references }, ['POST /missions'], { 'mission.url': url('mission') }, () => assert.deepEqual(calls.at(-1).body.references, references));
  await check('mission', { action: 'update', mission_id: ids.mission, title: 'Mission', references }, [`PATCH /missions/${ids.mission}`], { 'mission.url': url('mission') }, () => assert.deepEqual(calls.at(-1).body.references, references));
  await check('mission_execution', { action: 'submit', mission_id: ids.mission }, [`POST /missions/${ids.mission}/submit`], { url: url('mission') });
  await check('mission_execution', { action: 'status', mission_id: ids.mission }, [`GET /missions/${ids.mission}/status`], { url: url('mission') });
  await check('mission_execution', { action: 'preview', mission_id: ids.mission }, [`GET /missions/${ids.mission}/contract-preview`], { 'preview.url': url('mission') }, value => assert.deepEqual(value.full, preview));
  await check('evidence', { action: 'list', project_id: ids.project }, ['GET /evidence'], { 'entries.0.url': url('evidence'), 'notes.0.project_url': url('project') }, value => assert.equal(value.entries[0].source_url, archivedUrl));
  await check('evidence', { action: 'search', project_id: ids.project, q: 'claim' }, ['GET /evidence/search'], { 'entries.0.url': url('evidence') }, value => assert.equal(value.entries[0].source_url, archivedUrl));
  await check('evidence', { action: 'capture', project_id: ids.project, session_key: 'test', entries: [{ claim: 'Claim', source_url: archivedUrl, disposition: 'supporting' }] }, ['POST /evidence/capture'], { 'entries.0.url': url('evidence') });
  await check('evidence', { action: 'note', project_id: ids.project, session_key: 'test', note_key: 'working', content: markdown }, ['PUT /evidence/notes/working'], { project_url: url('project') }, value => assert.equal(value.content, markdown));
  await check('evidence', { action: 'promote', project_id: ids.project, session_key: 'test', target: 'document' }, ['POST /evidence/promote'], { report_url: url('report'), document_url: url('document') });

  await check('home', { action: 'snapshot' }, ['GET /home'], { 'attention.items.0.url': url('mission'), 'recent_reports.items.0.url': url('report'), 'recent_projects.items.0.url': url('project'), 'favorites.items.0.url': url('project'), 'evidence_activity.items.0.url': `${web}/evidence?project_id=${ids.project}` }, value => { assert.equal(value.missions.total, 83); assert.equal(value.recent_reports.items[0].title, markdown); assert.equal(value.recent_reports.items[0].href, recentReport.href); }, ['']);
  await check('home', { action: 'favorites', page: 2, page_size: 3, project_id: ids.project }, ['GET /home/favorites'], { 'items.0.url': url('project') }, value => assert.equal(value.total, 83), [`page=2&page_size=3&project_id=${ids.project}`]);
  await check('search', { action: 'navigate', q: 'A & B', entity_type: 'document', page: 2, page_size: 3 }, ['GET /navigation/search'], { 'groups.0.items.0.url': url('document') }, value => { assert.equal(value.groups[0].total, 83); assert.equal(value.groups[0].items[0].href, `/documents/${ids.document}`); }, ['q=A+%26+B&entity_type=document&page=2&page_size=3']);
  await check('evidence', { action: 'get', entry_id: ids.evidence }, [`GET /evidence/${ids.evidence}`], { 'entry.url': url('evidence'), 'links.0.url': url('report') }, value => assert.equal(value.entry.source_url, archivedUrl), ['']);
  await check('document', { action: 'list', project_id: ids.project, processed: false, search: 'A & B', page: 2, page_size: 3 }, ['GET /documents'], { 'data.0.url': url('document') }, value => assert.equal(value.total, 83), [`project_id=${ids.project}&processed=false&search=A+%26+B&page=2&page_size=3`]);
  await check('project', { action: 'get', project_id: ids.project }, [`GET /projects/${ids.project}`], { url: url('project') }, undefined, ['']);
  await check('collection', { action: 'documents', collection_id: ids.collection, page: 2, page_size: 3 }, [`GET /collections/${ids.collection}/documents`], { url: url('collection'), 'items.0.url': url('document') }, value => assert.equal(value.total, 83), ['page=2&page_size=3']);
  await check('collection', { action: 'mission_seed', collection_id: ids.collection }, [`GET /collections/${ids.collection}/mission-seed`], { url: url('collection'), project_url: url('project'), 'references.0.document_url': url('document') }, value => { assert.equal(value.background, markdown); assert.deepEqual(value.references, [{ ...seed.references[0], document_url: url('document') }]); assert.deepEqual(value.context, seed.context); }, ['']);
  await check('mission_execution', { action: 'logs', mission_id: ids.mission, limit: 3 }, [`GET /missions/${ids.mission}/logs`], { url: url('mission'), 'logs.0.url': url('mission') }, value => { assert.equal(value.empty, false); assert.equal(value.logs[0].message, markdown); }, ['limit=3']);
  await check('mission_execution', { action: 'events', mission_id: ids.mission, limit: 3 }, ['GET /missions/events/recent'], { 'events.0.url': url('mission') }, value => { assert.equal(value.empty, false); assert.deepEqual(value.events[0].details.references, references); }, [`mission_id=${ids.mission}&limit=3`]);
  await check('mission', { action: 'list', project_id: ids.project, view: 'attention', page: 2, page_size: 3 }, ['GET /missions'], {}, undefined, [`page=2&page_size=3&project_id=${ids.project}&view=attention`]);
  await check('collection', { action: 'list', project_id: ids.project, page: 2, page_size: 3 }, ['GET /collections'], {}, undefined, [`project_id=${ids.project}&page=2&page_size=3`]);
  await check('collection', { action: 'get', collection_id: ids.collection }, [`GET /collections/${ids.collection}`], {}, value => assert.equal(value.instructions, markdown), ['']);
  await check('collection', { action: 'create', name: 'Collection', instructions: markdown }, ['POST /collections'], {}, value => { assert.equal(calls.at(-1).body.instructions, markdown); assert.equal(value.collection.instructions, markdown); }, ['']);
  const filters = { tag: 'A & B', created_from: '2026-09-01T00:00:00Z', created_until: '2026-09-14T00:00:00Z', source_id: 'source/hash', report_id: ids.report, document_id: ids.document };
  const filterQuery = new URLSearchParams(filters).toString();
  await check('evidence', { action: 'list', project_id: ids.project, ...filters }, ['GET /evidence'], {}, undefined, [`project_id=${ids.project}&${filterQuery}&page=1&page_size=20`]);
  await check('evidence', { action: 'search', project_id: ids.project, q: 'A & B', ...filters }, ['GET /evidence/search'], {}, undefined, [`project_id=${ids.project}&q=A+%26+B&${filterQuery}&page=1&page_size=20`]);
  await check('report', { action: 'export', report_id: ids.report, format: 'md' }, [`GET /reports/${ids.report}/export`], {}, value => assert.equal(value, markdown), ['format=md']);
  await check('report', { action: 'export', report_id: ids.report, format: 'json' }, [`GET /reports/${ids.report}/export`], {}, value => assert.equal(value, jsonExport), ['format=json']);
  await check('report', { action: 'export', report_id: ids.report, format: 'txt' }, [`GET /reports/${ids.report}/export`], {}, value => assert.equal(value, markdown), ['format=txt']);
  for (const enable_graph of [false, true]) {
    const body = { query: 'Research', top_k: 3, project_id: ids.project, source_type: 'report', date_from: '2026-01-01', date_to: '2026-09-14', enable_graph };
    await check('search', { action: 'pedr', ...body }, ['POST /pedr/search'], { 'results.0.document_url': url('document') }, value => { assert.deepEqual(value.metadata, pedrMetadata); assert.equal(value.results[0].content, markdown); assert.deepEqual(calls.at(-1).body, body); }, ['']);
  }
  await check('search', { action: 'knowledge', query: 'Research', source_type: 'report', date_from: '2026-01-01', date_to: '2026-09-14' }, ['POST /retrieval/search'], {}, () => assert.deepEqual(calls.at(-1).body, { query: 'Research', top_k: 10, source_type: 'report', date_from: '2026-01-01', date_to: '2026-09-14' }), ['']);
  console.log(JSON.stringify({ passed: checks.length, generatedLinks: checks.reduce((sum, row) => sum + row.links, 0), httpRequests: calls.length, checks }, null, 2));
} finally {
  await client.close();
  await transport.close();
  await new Promise(resolve => server.close(resolve));
}
