import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { audit, clusterActions, inventory } from './mcp_parity_audit.mjs';

function fixture(t, entries) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'mcp-parity-audit-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  for (const [name, contents] of Object.entries(entries)) {
    const filename = path.join(root, name);
    fs.mkdirSync(path.dirname(filename), { recursive: true });
    fs.writeFileSync(filename, contents);
  }
  return root;
}
const transport = `export const httpClient = { get: (path: string) => null, post: (path: string) => null };
export function apiRequest(path: string, options: object) { return null; }
export function buildApiUrl(path: string) { return path; }`;

test('follows aliased clients, constants, multiline calls and callbacks; unused hooks stay dead', t => {
  const root = fixture(t, {
    'frontend/src/lib/api/http.ts': transport,
    'frontend/src/lib/api/documents.ts': `import { httpClient as http, apiRequest as request, buildApiUrl } from './http';
const BASE = '/documents';
export const docs = {
  list: () => http.get(\n BASE\n),
  get: (id: string) => http.get(\n \`\${BASE}/\${id}\`\n),
  download: (id: string) => fetch(buildApiUrl(\`\${BASE}/\${id}/download\`), { method: 'GET' }),
  create: () => request(BASE, { method: 'POST' }),
  unused: () => http.get('/unused'),
};`,
    'frontend/src/lib/hooks/documents.ts': `import { docs } from '../api/documents'; export function useUnused() { return docs.unused(); }`,
    'frontend/src/pages/index.tsx': `import { docs } from '../lib/api/documents';
declare function useCallback(value: unknown): unknown;
declare function useMutation(value: unknown): unknown;
export default function Page() {
  docs.list(); docs.get('id'); useCallback(() => docs.download('id'));
  useMutation({ mutationFn: () => docs.create() });
  return null;
}`,
  });
  const rows = inventory(root);
  assert.equal(rows.length, 5);
  assert.deepEqual(rows.filter(row => row.live).map(row => row.operation).sort(), ['docs.create', 'docs.download', 'docs.get', 'docs.list']);
  assert.equal(rows.find(row => row.operation === 'docs.get').path, '/api/v1/documents/{id}');
  assert.equal(rows.find(row => row.operation === 'docs.unused').live, false);
  assert.ok(rows.filter(row => row.live).every(row => row.ui_consumers.includes('frontend/src/pages/index.tsx')));
});

test('counts XMLHttpRequest upload operations as well as API request helpers', t => {
  const root = fixture(t, {
    'frontend/src/lib/api/http.ts': transport,
    'frontend/src/lib/api/upload.ts': `import { buildApiUrl } from './http';
export function upload() { const xhr = new XMLHttpRequest(); xhr.open('POST', buildApiUrl('/documents/upload')); }`,
    'frontend/src/pages/index.tsx': `import { upload } from '../lib/api/upload'; export default function Page() { upload(); return null; }`,
  });
  assert.deepEqual(inventory(root).map(row => [row.method, row.path, row.live]), [['POST', '/api/v1/documents/upload', true]]);
});

test('rejects new operations, missing MCP actions and stale consumer dispositions', () => {
  const operation = { id: 'operation', method: 'GET', path: '/api/v1/home', live: true, ui_consumers: ['frontend/src/pages/index.tsx'] };
  const row = { ...operation, mcp: 'tracelab_home.snapshot', classification: 'closed-MCP-1', rationale: 'Read parity.' };
  const actions = { tracelab_home: ['snapshot'] };
  assert.deepEqual(audit([operation], { operations: [row] }, actions), []);
  assert.match(audit([operation], { operations: [] }, actions).join('\n'), /Unclassified operation/);
  assert.match(audit([operation], { operations: [row] }, {}).join('\n'), /Missing CLUSTER_ACTIONS/);
  assert.match(audit([{ ...operation, live: false }], { operations: [row] }, actions).join('\n'), /Incorrect live\/dead/);
  assert.match(audit([{ ...operation, ui_consumers: ['another consumer'] }], { operations: [row] }, actions).join('\n'), /Stale route\/consumer/);
  assert.match(audit([], { operations: [row] }, actions).join('\n'), /Stale manifest/);
});

test('reads the source action registry without importing the running MCP server', t => {
  const root = fixture(t, { 'packages/tracelab-mcp/src/index.ts': `const HOME = ['snapshot', 'favorites'] as const; export const CLUSTER_ACTIONS = { tracelab_home: HOME } as const; throw new Error('Do not execute');` });
  assert.deepEqual(clusterActions(root), { tracelab_home: ['snapshot', 'favorites'] });
});
