// MCP-3 fresh-install smoke: start the PUBLISHED @aquex/tracelab-mcp@<version> with
// `npx -y` from an empty working directory (no repo, no local dist), connect a
// real stdio client, compare listTools with the parity manifest, run one
// read-only action per tool against production with a human X-API-Key (passed
// to the child environment only) and resolve every generated canonical link
// with HTTP 200 on the public frontend. Nothing is written.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';

const VERSION = process.env.MCP_VERSION || '1.2.0';
const REPO = '/Users/systemsystems/portfolio/TraceLab';
const require = createRequire(path.join(REPO, 'packages/tracelab-mcp/package.json'));
const { Client } = require('@modelcontextprotocol/sdk/client/index.js');
const { StdioClientTransport } = require('@modelcontextprotocol/sdk/client/stdio.js');
const api = 'https://api.tracelab.aquex.ai';
const web = 'https://tracelab.aquex.ai';
const out = process.env.UI_OUT || path.join(os.tmpdir(), 'tracelab-mcp3-smoke');
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
  command: 'npx', args: ['-y', `@aquex/tracelab-mcp@${VERSION}`], cwd: fresh,
  env: { PATH: process.env.PATH, HOME: process.env.HOME, TRACELAB_API_URL: api, TRACELAB_API_KEY: creds.key, TRACELAB_FRONTEND_URL: web, NPM_CONFIG_UPDATE_NOTIFIER: 'false' },
  stderr: 'pipe',
});
let stderr = '';
transport.stderr?.on('data', chunk => { stderr += String(chunk); });
const client = new Client({ name: 'mcp-3-npx-smoke', version: '1.0.0' });
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
  record('published package starts and lists tools', tools.length === 9 && actions === 51, { tools: tools.length, actions, server_version: serverInfo?.version ?? null, startup_stderr: stderr.replace(creds.key, '[redacted]').trim().split('\n').slice(0, 3) });
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
    process.env.DRYRUN ? ['home', { action: 'snapshot' }, value => typeof value.missions?.total === 'number'] : ['home', { action: 'inbox_summary' }, value => typeof value.unread?.total === 'number'],
  ];
  for (const [tool, args, verify] of reads) {
    const { value, ms, error } = await call(tool, args);
    const found = value ? collectLinks(value) : [];
    links.push(...found.map(url => ({ tool, url })));
    record(`tracelab_${tool}.${args.action} read-only`, value !== null && verify(value), { ms, generated_links: found.length, ...(error ? { error } : {}) });
  }
  // Every generated canonical link must resolve on the public frontend.
  const unique = [...new Map(links.map(item => [item.url, item])).values()].slice(0, 40);
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
  mission_id: 'MCP-3', sprint_id: 'sprint-52', started_at: started, finished_at: new Date().toISOString(), version: VERSION, api, frontend: web, read_only: true,
  install: { command: `npx -y @aquex/tracelab-mcp@${VERSION}`, fresh_directory: true, minimal_environment: ['PATH', 'HOME', 'TRACELAB_API_URL', 'TRACELAB_API_KEY', 'TRACELAB_FRONTEND_URL'], server_version: serverInfo?.version ?? null },
  authentication: { kind: 'human X-API-Key', source: 'existing local credential store', credential_logged: false, credential_in_receipt: false },
  checks, passed: checks.every(c => c.passed),
};
await fs.writeFile(path.join(out, 'mcp-3-production-smoke.json'), JSON.stringify(report, null, 2));
console.log(JSON.stringify({ passed: report.passed, checks: checks.length, failed: checks.filter(c => !c.passed).map(c => c.label), version: VERSION }));
if (!report.passed) process.exitCode = 1;
