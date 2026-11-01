// MCP-6 fresh-install smoke for 2.1.0, copied from MCP-5's 2.0.0 smoke and extended to
// call tracelab_search ask: start the PUBLISHED @aquex/tracelab-mcp@<version> with
// `npx -y` from an empty working directory (no repo, no local dist), connect a
// real stdio client, compare listTools with the parity manifest, run one
// read-only action per tool against production with a human X-API-Key (passed
// to the child environment only), ask TraceLab Research one question it can
// answer and one it cannot, ask a project that does not exist, and resolve every
// generated canonical link, citations included, with HTTP 200 on the public
// frontend. The only writes are the usage rows a paid ask records.
//
// MCP_TARBALL=<path to a local npm pack> runs the same checks against that tarball
// with `npx -y --package <tgz> tracelab-mcp` (learning #245), before the publish.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';

const VERSION = process.env.MCP_VERSION || '2.1.0';
const TARBALL = process.env.MCP_TARBALL;
const REPO = '/Users/systemsystems/portfolio/TraceLab';
const require = createRequire(path.join(REPO, 'packages/tracelab-mcp/package.json'));
const { Client } = require('@modelcontextprotocol/sdk/client/index.js');
const { StdioClientTransport } = require('@modelcontextprotocol/sdk/client/stdio.js');
const api = 'https://api.tracelab.aquex.ai';
const web = 'https://tracelab.aquex.ai';
const out = process.env.UI_OUT || path.join(os.tmpdir(), 'tracelab-mcp6-smoke');
const RESEARCH = '0afcc588-e722-45bd-8320-f486601b877c'; // TraceLab Research
const REFUSAL = 'Nothing in this project answers that question.';
const started = new Date().toISOString();
const creds = JSON.parse(await fs.readFile(path.join(os.homedir(), '.config/tracelab-mcp/credentials.json'), 'utf8'));
assert.equal(creds.apiBaseUrl.replace(/\/$/, ''), api, 'Unexpected credential scope');
const manifest = JSON.parse(await fs.readFile(path.join(REPO, 'cmos/contracts/mcp-parity-manifest.json'), 'utf8'));
const manifestTools = new Set(manifest.operations.map(row => row.mcp).filter(Boolean).map(value => value.slice(0, value.lastIndexOf('.'))));
async function rest(route) { const r = await fetch(api + '/api/v1' + route, { headers: { 'X-API-Key': creds.key } }); assert.ok(r.ok, `REST ${route.split('?')[0]} ${r.status}`); return r.json(); }
await fs.mkdir(out, { recursive: true });
const fresh = await fs.mkdtemp(path.join(os.tmpdir(), 'tracelab-npx-'));
const checks = [];
const record = (label, passed, detail = {}) => { checks.push({ label, passed, ...detail }); if (!passed) console.error('FAILED', label, JSON.stringify(detail)); };

// Fresh shell: minimal environment, empty cwd, published package only.
const transport = new StdioClientTransport({
  command: 'npx', args: TARBALL ? ['-y', '--package', TARBALL, 'tracelab-mcp'] : ['-y', `@aquex/tracelab-mcp@${VERSION}`], cwd: fresh,
  env: { PATH: process.env.PATH, HOME: process.env.HOME, TRACELAB_API_URL: api, TRACELAB_API_KEY: creds.key, TRACELAB_FRONTEND_URL: web, NPM_CONFIG_UPDATE_NOTIFIER: 'false' },
  stderr: 'pipe',
});
let stderr = '';
transport.stderr?.on('data', chunk => { stderr += String(chunk); });
const client = new Client({ name: 'mcp-6-npx-smoke', version: '1.0.0' });
const links = [];
async function call(tool, args) {
  const t = performance.now();
  const result = await client.callTool({ name: `tracelab_${tool}`, arguments: args });
  const ms = Math.round(performance.now() - t);
  if (result.isError) return { value: null, ms, error: String(result.content?.[0]?.text ?? '').replace(creds.key, '[redacted]').slice(0, 300) };
  return { value: JSON.parse(result.content[0].text), ms };
}
function collectLinks(value, found = []) {
  if (Array.isArray(value)) value.forEach(item => collectLinks(item, found));
  else if (value && typeof value === 'object') for (const [key, item] of Object.entries(value)) {
    if (/(^|_)url$/.test(key) && typeof item === 'string' && item.startsWith(web + '/')) found.push(item);
    else collectLinks(item, found);
  }
  return found;
}
let serverInfo = null;
try {
  await client.connect(transport);
  serverInfo = client.getServerVersion?.() ?? null;
  const tools = (await client.listTools()).tools;
  const actions = tools.reduce((n, tool) => n + tool.inputSchema.properties.action.enum.length, 0);
  const names = new Set(tools.map(tool => tool.name));
  record('published package starts and lists tools', tools.length === 9 && actions === 50 && serverInfo?.version === VERSION, { tools: tools.length, actions, server_version: serverInfo?.version ?? null, startup_stderr: stderr.replace(creds.key, '[redacted]').trim().split('\n').slice(0, 3) });
  const byName = Object.fromEntries(tools.map(tool => [tool.name, tool]));
  const homeActions = byName.tracelab_home.inputSchema.properties.action.enum;
  record('ACT-1 surface: activity present, attention and inbox gone', homeActions.includes('activity') && homeActions.includes('activity_summary') && !homeActions.some(a => ['attention', 'inbox_summary', 'inbox_list'].includes(a)) && !byName.tracelab_mission.inputSchema.properties.action.enum.includes('views'), { tracelab_home: homeActions });
  record('PERSONAL-2 surface: tracelab_project advertises workspace_id', 'workspace_id' in byName.tracelab_project.inputSchema.properties, {});
  const search = byName.tracelab_search.inputSchema.properties;
  record('MCP-6 surface: tracelab_search offers ask with question and max_tokens', search.action.enum.includes('ask') && 'question' in search && 'max_tokens' in search, { tracelab_search: search.action.enum });
  record('listTools matches the parity manifest tool set', [...manifestTools].every(name => names.has(name)) && manifestTools.size === 9, { manifest_tools: [...manifestTools].sort() });

  const projects = await rest('/projects?page_size=100');
  const project = projects.data.find(p => p.id === '0afcc588-e722-45bd-8320-f486601b877c') || projects.data[0];
  const missions = await rest(`/missions?page_size=1&project_id=${project.id}`);
  const mission = missions.data[0];
  const reads = [
    ['search', { action: 'navigate', q: project.name.slice(0, 40), entity_type: 'project', page_size: 5 }, value => value.groups.length >= 1],
    ['project', { action: 'get', project_id: project.id }, value => value.id === project.id],
    ['collection', { action: 'list', project_id: project.id, page_size: 5 }, value => Array.isArray(value.collections)],
    ['report', { action: 'list', page_size: 5 }, value => Array.isArray(value.reports)],
    ['document', { action: 'list', project_id: project.id, page_size: 5 }, value => typeof value.total === 'number'],
    ['mission', { action: 'list', project_id: project.id, page_size: 5 }, value => Array.isArray(value.missions)],
    ['mission_execution', { action: 'status', mission_id: mission.id }, value => typeof value.status === 'string'],
    ['evidence', { action: 'list', project_id: project.id, page_size: 5 }, value => Array.isArray(value.entries)],
    ['home', { action: 'activity_summary' }, value => typeof value.new_total === 'number'],
    ['project', { action: 'list', page_size: 5 }, value => Array.isArray(value.projects) && value.projects.every(p => 'workspace_id' in p)],
  ];
  for (const [tool, args, verify] of reads) {
    const { value, ms, error } = await call(tool, args);
    const found = value ? collectLinks(value) : [];
    links.push(...found.map(url => ({ tool, url })));
    record(`tracelab_${tool}.${args.action} read-only`, value !== null && verify(value), { ms, generated_links: found.length, ...(error ? { error } : {}) });
  }
  // MCP-6: a question TraceLab Research answers (QA-1's Q3, chunks 5 and 10 of the
  // TRACE-SHARE-58 report), with no budget so the server default applies, as it does
  // for an agent that sends none.
  {
    const question = "Out of the box, does Airtable's workspace setting that restricts adding new collaborators start switched on or off?";
    const { value, ms, error } = await call('search', { action: 'ask', project_id: RESEARCH, question });
    const citations = value?.citations ?? [];
    const cited = new Set(citations.map(citation => citation.chunk_id));
    const citedText = (value?.passages ?? []).filter(passage => passage.citations.length).map(passage => passage.text).join('\n');
    const found = value ? collectLinks(value) : [];
    links.push(...found.map(url => ({ tool: 'search.ask', url })));
    record('tracelab_search.ask answers with citations that open their chunks', value !== null
      && value.no_evidence === false
      && citations.length > 0
      && citations.every(citation => citation.url === web + citation.href && citation.href.startsWith(`/documents/${citation.document_id}?chunk=${citation.chunk_id}`))
      && value.passages.every(passage => passage.citations.every(id => cited.has(id)))
      && /\boff\b/i.test(citedText)
      && value.project_url === `${web}/projects/${RESEARCH}`,
    { ms, citations: citations.length, cited_documents: [...new Set(citations.map(citation => citation.document_name))], passages: value?.passages?.length ?? 0, cited_text: citedText.slice(0, 400), model: value?.model ?? null, ...(error ? { error } : {}) });
  }
  // RAG-4's unsupported in-domain question: refused before any model call.
  {
    const { value, ms, error } = await call('search', { action: 'ask', project_id: RESEARCH, question: 'How should Kubernetes horizontal pod autoscaling be tuned for bursty GPU inference traffic?', max_tokens: 600 });
    record('tracelab_search.ask returns the nothing-found result for a question the project cannot support', value !== null && value.no_evidence === true && value.answer === REFUSAL && value.citations.length === 0, { ms, answer: value?.answer ?? null, ...(error ? { error } : {}) });
  }
  // A project that does not exist is the API's 404, surfaced as a tool error.
  {
    const { value, ms, error } = await call('search', { action: 'ask', project_id: '00000000-0000-4000-8000-00000000abcd', question: 'What does it cost?' });
    record('tracelab_search.ask on an unknown project is the API 404, not an answer', value === null && /API Error \(404\)/.test(error ?? ''), { ms, error: error ?? null });
  }

  // Every generated canonical link must resolve on the public frontend.
  // No cap: the ask citations come last and must not be cut off.
  const unique = [...new Map(links.map(item => [item.url, item])).values()];
  const resolved = [];
  for (const { tool, url } of unique) {
    const response = await fetch(url, { redirect: 'manual' });
    resolved.push({ tool, url, status: response.status });
  }
  record('canonical links resolve with HTTP 200', resolved.length > 0 && resolved.every(item => item.status === 200), { checked: resolved.length, non_200: resolved.filter(item => item.status !== 200), sample: resolved.slice(0, 6) });
} finally {
  await client.close().catch(() => {});
  await transport.close().catch(() => {});
  await fs.rm(fresh, { recursive: true, force: true });
}
const report = {
  mission_id: 'MCP-6', sprint_id: 'sprint-59', started_at: started, finished_at: new Date().toISOString(), version: VERSION, api, frontend: web, read_only: false, writes: 'the usage rows a paid ask records',
  install: { command: TARBALL ? `npx -y --package ${path.basename(TARBALL)} tracelab-mcp` : `npx -y @aquex/tracelab-mcp@${VERSION}`, fresh_directory: true, minimal_environment: ['PATH', 'HOME', 'TRACELAB_API_URL', 'TRACELAB_API_KEY', 'TRACELAB_FRONTEND_URL'], server_version: serverInfo?.version ?? null },
  authentication: { kind: 'human X-API-Key', source: 'existing local credential store', credential_logged: false, credential_in_receipt: false },
  checks, passed: checks.every(c => c.passed),
};
await fs.writeFile(path.join(out, 'mcp-6-production-smoke.json'), JSON.stringify(report, null, 2));
console.log(JSON.stringify({ passed: report.passed, checks: checks.length, failed: checks.filter(c => !c.passed).map(c => c.label), version: VERSION }));
if (!report.passed) process.exitCode = 1;
