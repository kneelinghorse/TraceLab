import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import { check, parse } from './mcp_argument_parity.mjs';

/** Build a throwaway package whose index.ts is the only thing the parser reads. */
function fixture(t, source) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'mcp-argument-parity-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const directory = path.join(root, 'packages/tracelab-mcp/src');
  fs.mkdirSync(directory, { recursive: true });
  fs.writeFileSync(path.join(root, 'packages/tracelab-mcp/package.json'), JSON.stringify({ name: 'fixture' }));
  fs.writeFileSync(path.join(directory, 'index.ts'), source);
  return root;
}

const TOOL = (properties) => `
const TOOLS = [{
  name: 'fixture_tool',
  description: 'fixture',
  inputSchema: { type: 'object', properties: { ${properties} }, required: [] },
}];
`;

const BASE = `
const Shared = { project_id: z.string().optional() };
const ListInput = z.object({ ...Shared, page: z.number().optional() });
const SearchInput = ListInput.extend({ q: z.string() }).superRefine(() => {});
async function handleList(args: unknown) { const input = ListInput.parse(args); return input; }
async function handleSearch(args: unknown) { const input = SearchInput.parse(args); return input; }
export async function handleFixtureTool(args: unknown) {
  const action = getAction(args);
  switch (action) {
    case 'list': return await handleList(args);
    case 'search': return await handleSearch(args);
    default: return null;
  }
}
const CLUSTER_HANDLERS = { fixture_tool: handleFixtureTool };
`;

test('a composed schema counts as accepting every field it composes', t => {
  const root = fixture(t, TOOL(`
    action: { type: 'string' },
    project_id: { type: 'string' },
    page: { type: 'number' },
    q: { type: 'string' },
  `) + BASE);
  // q arrives through ListInput.extend({...}).superRefine(...) and project_id through a
  // spread. Resolving only the outermost call would report both as gaps.
  assert.deepEqual(check(parse(root)), []);
});

test('an argument no handler accepts is reported, because Zod strips it silently', t => {
  const root = fixture(t, TOOL(`
    action: { type: 'string' },
    project_id: { type: 'string' },
    page: { type: 'number' },
    q: { type: 'string' },
    ghost: { type: 'string' },
  `) + BASE);
  const gaps = check(parse(root));
  assert.equal(gaps.length, 1);
  assert.equal(gaps[0].kind, 'advertised-but-never-accepted');
  assert.equal(gaps[0].argument, 'ghost');
});

test('an accepted argument that no client can discover is reported', t => {
  const root = fixture(t, TOOL(`
    action: { type: 'string' },
    project_id: { type: 'string' },
    page: { type: 'number' },
  `) + BASE);
  const gaps = check(parse(root));
  assert.equal(gaps.length, 1);
  assert.equal(gaps[0].kind, 'accepted-but-not-advertised');
  assert.equal(gaps[0].argument, 'q');
});

test('a type the client is told to send that the handler will reject is reported', t => {
  const root = fixture(t, TOOL(`
    action: { type: 'string' },
    project_id: { type: 'string' },
    page: { type: 'number' },
    q: { type: 'boolean' },
  `) + BASE);
  const gaps = check(parse(root));
  assert.equal(gaps.length, 1);
  assert.equal(gaps[0].kind, 'type-mismatch');
  assert.match(gaps[0].detail, /inputSchema says boolean; Zod says string/);
});

test('integer narrows number rather than counting as a mismatch', t => {
  const root = fixture(t, TOOL(`
    action: { type: 'string' },
    project_id: { type: 'string' },
    page: { type: 'integer' },
    q: { type: 'string' },
  `) + BASE);
  assert.deepEqual(check(parse(root)), []);
});

test('a handler whose schema cannot be resolved is reported rather than assumed empty', t => {
  const root = fixture(t, TOOL(`action: { type: 'string' },`) + `
async function handleMystery(args: unknown) { return args; }
export async function handleFixtureTool(args: unknown) {
  switch (getAction(args)) { case 'mystery': return await handleMystery(args); default: return null; }
}
const CLUSTER_HANDLERS = { fixture_tool: handleFixtureTool };
`);
  const gaps = check(parse(root));
  assert.equal(gaps.length, 1);
  assert.equal(gaps[0].kind, 'handler-schema-unresolved');
});

test('the real package reports zero argument-level gaps', () => {
  assert.deepEqual(check(parse()), []);
});
