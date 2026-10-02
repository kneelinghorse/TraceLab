// Authenticated GET-only scope review and exact exports on the serving UI.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { chromium, expect } from '@playwright/test';
import { handleSmokeApiRequest } from './ui-shell-transport.mjs';

const [expectedCommit, output] = process.argv.slice(2);
assert.ok(expectedCommit && output, 'Usage: node scope-production-smoke.mjs <serving commit> <output directory>');
const base = 'https://tracelab.aquex.ai', api = 'https://api.tracelab.aquex.ai';
const missionId = '3f5c2641-7a47-45ed-a092-feebe9143ed1';
const credentials = JSON.parse(await fs.readFile(path.join(os.homedir(), '.config/tracelab-mcp/credentials.json'), 'utf8'));
assert.equal(credentials.apiBaseUrl.replace(/\/$/, ''), api);
async function get(endpoint) {
  const response = await fetch(api + '/api/v1' + endpoint, { headers: { 'X-API-Key': credentials.key } });
  assert.ok(response.ok, `Read-only API status ${response.status}`);
  return response.json();
}
const [user, before, backend, frontend] = await Promise.all([
  get('/auth/me'), get('/missions/' + missionId), get('/health'),
  fetch(base + '/api/version', { cache: 'no-store' }).then(response => response.json()),
]);
assert.equal(backend.commit, expectedCommit); assert.equal(frontend.commit, expectedCommit);
await fs.mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
const results = [], sha = value => createHash('sha256').update(value).digest('hex');
try {
  for (const theme of ['light', 'dark']) for (const width of [390, 820, 1440]) {
    const errors = [], suppressedWrites = [], calls = [];
    const context = await browser.newContext({ viewport: { width, height: 1000 }, colorScheme: theme });
    await context.route('**/api/v1/**', async route => {
      const request = route.request(), endpoint = new URL(request.url()).pathname;
      calls.push({ method: request.method(), path: endpoint });
      const viewed = request.method() === 'PUT' && endpoint === '/api/v1/activity/viewed';
      if (!['GET', 'OPTIONS'].includes(request.method()) && !viewed) { errors.push('Unexpected mutation: ' + endpoint); await route.abort(); return; }
      await handleSmokeApiRequest(route, { api, base, directProduction: true, apiKey: credentials.key, transportErrors: errors, suppressedWrites });
    });
    await context.addInitScript(({ user, theme }) => {
      localStorage.setItem('tracelab.auth.v2', JSON.stringify({ token: 'scope-smoke-placeholder', user_id: user.user_id, email: user.email }));
      localStorage.setItem('tracelab.theme.v1:' + user.user_id, theme);
    }, { user, theme });
    const page = await context.newPage();
    page.on('pageerror', () => errors.push('Client-side exception'));
    await page.goto(base + '/missions/' + missionId);
    await expect(page.getByRole('region', { name: 'Scope outcome' })).toBeVisible();
    if (!before.execution_metadata?.final_outcome?.authored_scope_validation) await expect(page.getByRole('heading', { name: 'Scope outcome unknown' })).toBeVisible();
    await page.getByRole('button', { name: 'Preview contract', exact: true }).click();
    const plan = page.getByRole('region', { name: 'Planned scope' });
    await expect(plan.getByText(/300–500 words/)).toBeVisible();
    await expect(plan.getByText(/At most 2 distinct consulted pages/)).toBeVisible();
    await expect(plan.getByText(/does not verify the deployed worker/)).toBeVisible();
    await page.addScriptTag({ path: path.resolve('node_modules/axe-core/axe.min.js') });
    async function audit() {
      const result = await page.evaluate(async () => ({ overflow: document.documentElement.scrollWidth > innerWidth, theme: document.documentElement.dataset.theme, violations: (await window.axe.run(document)).violations.filter(v => ['critical', 'serious'].includes(v.impact)).map(v => v.id) }));
      assert.deepEqual(result, { overflow: false, theme, violations: [] });
      return result;
    }
    const preview = await audit();
    await page.screenshot({ path: path.join(output, `${theme}-${width}-preview.png`), fullPage: true });
    await page.getByRole('tab', { name: 'Results', exact: true }).click();
    for (const [label, expected, json] of [['Export as .md', before.result_markdown, false], ['Export full protocol', before.result_protocol, true]]) {
      const download = page.waitForEvent('download');
      await page.getByRole('button', { name: label, exact: true }).click();
      const content = await fs.readFile(await (await download).path(), 'utf8');
      assert.deepEqual(json ? JSON.parse(content) : content, expected);
    }
    const result = await audit();
    await page.screenshot({ path: path.join(output, `${theme}-${width}-result.png`), fullPage: true });
    assert.deepEqual(errors, []);
    results.push({ theme, width, preview, result, calls, suppressedWrites, errors });
    await context.close();
  }
  const after = await get('/missions/' + missionId);
  for (const key of ['status', 'deepsearch_attempt_count', 'deepsearch_job_id', 'result_markdown', 'result_protocol', 'execution_metadata']) assert.deepEqual(after[key], before[key]);
  await fs.writeFile(path.join(output, 'summary.json'), JSON.stringify({ accepted_at: new Date().toISOString(), serving_commit: expectedCommit, mission_id: missionId, results, markdown_sha256: sha(before.result_markdown), protocol_sha256: sha(JSON.stringify(before.result_protocol)), read_only: true, worker_delivery_proven: false }, null, 2) + '\n');
  console.log(JSON.stringify({ passed: true, checks: results.length, serving_commit: expectedCommit }));
} finally { await browser.close(); }
