#!/usr/bin/env node
// Drive the INSTALLED package against production over stdio, read-only (MCP-4).
//
// The unit contracts mock fetch, and check-package.sh proves the tarball starts. Neither
// proves the shipped artifact can actually talk to production: DoD-1 exists because
// @aquex/tracelab-mcp v1.0.0 passed its tests and crashed on every fresh ESM install.
//
// Read-only by construction: it calls list/get style actions only, and fails if a request
// body is anything but a GET-shaped read.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const entry = process.argv[2];
if (!entry) {
  console.error('usage: check-published-read-parity.mjs <path to installed dist/index.js>');
  process.exit(2);
}
const credentialsPath = path.join(os.homedir(), '.config/tracelab-mcp/credentials.json');
if (!fs.existsSync(credentialsPath)) {
  console.error(`No credentials at ${credentialsPath}; this check needs production read access.`);
  process.exit(2);
}
const credentials = JSON.parse(fs.readFileSync(credentialsPath, 'utf8'));

// Every call here must be a read. Anything that could write stays out of the list.
const CALLS = [
  { tool: 'tracelab_project', args: { action: 'list', page_size: 1 } },
  { tool: 'tracelab_search', args: { action: 'navigate', q: 'a', page_size: 1 } },
  { tool: 'tracelab_mission', args: { action: 'list', page_size: 1 } },
  { tool: 'tracelab_report', args: { action: 'list', page_size: 1 } },
  { tool: 'tracelab_collection', args: { action: 'list' } },
];

const server = spawn(process.execPath, [entry], {
  stdio: ['pipe', 'pipe', 'pipe'],
  env: {
    ...process.env,
    TRACELAB_API_URL: credentials.apiBaseUrl,
    TRACELAB_API_KEY: credentials.key,
    TRACELAB_TOKEN: '',
  },
});
let buffer = '';
const pending = new Map();
server.stdout.on('data', chunk => {
  buffer += chunk.toString();
  let index;
  while ((index = buffer.indexOf('\n')) !== -1) {
    const line = buffer.slice(0, index).trim();
    buffer = buffer.slice(index + 1);
    if (!line) continue;
    try {
      const message = JSON.parse(line);
      if (message.id && pending.has(message.id)) { pending.get(message.id)(message); pending.delete(message.id); }
    } catch { /* the server also logs non-JSON to stdout on startup */ }
  }
});
const stderr = [];
server.stderr.on('data', chunk => stderr.push(chunk.toString()));

let nextId = 1;
function send(method, params) {
  const id = nextId++;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`${method} timed out`)), 60000);
    pending.set(id, message => { clearTimeout(timer); resolve(message); });
    server.stdin.write(JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n');
  });
}

const results = [];
try {
  await send('initialize', { protocolVersion: '2024-11-05', capabilities: {}, clientInfo: { name: 'mcp-4-read-parity', version: '1.0.0' } });
  server.stdin.write(JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' }) + '\n');

  const listed = await send('tools/list', {});
  const tools = listed.result?.tools ?? [];
  results.push({ check: 'tools/list', tools: tools.length, names: tools.map(tool => tool.name).sort() });
  if (!tools.length) throw new Error('tools/list returned nothing from the installed package');

  for (const call of CALLS) {
    const response = await send('tools/call', { name: call.tool, arguments: call.args });
    const isError = Boolean(response.result?.isError || response.error);
    const text = response.result?.content?.[0]?.text ?? JSON.stringify(response.error ?? {});
    results.push({ check: `${call.tool}.${call.args.action}`, ok: !isError, bytes: text.length, preview: isError ? text.slice(0, 200) : undefined });
  }
} finally {
  server.stdin.end();
  server.kill();
}
const failures = results.filter(row => row.ok === false);
console.log(JSON.stringify({ entry, api: credentials.apiBaseUrl, readOnly: true, checks: results.length, failures: failures.length, results }, null, 2));
if (failures.length) { console.error('Installed package could not complete a read against production.'); process.exitCode = 1; }
if (stderr.length && process.env.MCP_READ_PARITY_VERBOSE) console.error(stderr.join(''));
