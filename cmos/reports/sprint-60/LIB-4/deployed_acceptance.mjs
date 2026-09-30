// One real model draft from the accepted ORG-1 collection; explicit browser save,
// then fresh REST/export/published MCP reads. Private proposals never enter receipts.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

const out = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(out, '../../../..');
const api = 'https://api.tracelab.aquex.ai', web = 'https://tracelab.aquex.ai';
const projectId = '0d6c5b1d-72eb-4390-a40b-c48c88cdb302';
const collectionId = 'cf1dd7ec-25f1-4141-9210-4a805e311137';
const expectedChunks = ['27a6eb7e-581c-43cd-bad9-3f7c3a5332ee', '5382d30e-4343-4f3e-bca2-08b0cb1ff792'];
const commit = process.env.LIB4_SERVING_COMMIT;
assert.match(commit || '', /^[a-f0-9]{40}$/, 'Exact deployed commit required');
const mode = process.argv[2] || 'verify';
assert.ok(['prepare', 'browser', 'verify', 'read-only'].includes(mode));
const credentials = JSON.parse(await fs.readFile(path.join(os.homedir(), '.config/tracelab-mcp/credentials.json'), 'utf8'));
assert.equal(credentials.apiBaseUrl.replace(/\/$/, ''), api);
const hash = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
async function jsonFile(filename, fallback) {
  try { return JSON.parse(await fs.readFile(filename, 'utf8')); }
  catch (error) { if (error.code === 'ENOENT') return fallback; throw error; }
}
async function request(route, method = 'GET', body, asText = false) {
  const response = await fetch(api + '/api/v1' + route, { method,
    headers: { 'X-API-Key': credentials.key, 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
  assert.ok(response.ok, `${method} ${route.split('?')[0]}: ${response.status}`);
  return asText ? response.text() : response.json();
}
for (const endpoint of [api + '/api/v1/health', web + '/api/version']) {
  const response = await fetch(endpoint, { headers: { 'Cache-Control': 'no-cache' } });
  assert.equal(response.status, 200); assert.equal((await response.json()).commit, commit);
}
const me = await request('/auth/me');
assert.notEqual(me.role, 'service');
assert.equal((await request('/projects/' + projectId)).name, 'Sprint 60 Librarian acceptance — onboarding feedback');
const progressFile = path.join(out, 'deployed-progress.json');
const progress = await jsonFile(progressFile, { project_id: projectId, collection_id: collectionId });
const saveProgress = () => fs.writeFile(progressFile, JSON.stringify(progress, null, 2) + '\n');
const privateFile = path.join(os.tmpdir(), 'tracelab-lib4-review.json');
let review = await jsonFile(privateFile, null);
async function snapshot() {
  const documents = (await request(`/documents?project_id=${projectId}&page_size=100`)).data;
  return { project: await request('/projects/' + projectId), collection: await request('/collections/' + collectionId),
    sources: await Promise.all(documents.sort((a, b) => a.id.localeCompare(b.id)).map(async doc => ({
      detail: await request(`/documents/${doc.id}`), content: await request(`/documents/${doc.id}/content`),
      chunks: await request(`/documents/${doc.id}/chunks?page_size=100`),
    }))) };
}
async function usage() {
  const result = await request('/admin/usage?user_id=' + me.user_id);
  return result.rows.filter(row => row.kind === 'librarian_draft').reduce((n, row) => n + row.records, 0);
}
if (mode === 'prepare') {
  if (!review) {
    assert.ok(!progress.draft_started, 'A prior draft was requested; inspect before another paid call');
    const before = await snapshot();
    const reports = await request(`/reports?project_id=${projectId}&page_size=100`);
    assert.ok(reports.total <= 100);
    const sources = await request(`/librarian/reports/sources?project_id=${projectId}&collection_id=${collectionId}`);
    assert.deepEqual(sources.members.map(member => member.chunk_id), expectedChunks);
    assert.equal(sources.coverage.other_project_chunks, 0); assert.equal(sources.coverage.limited, false);
    const beforeUsage = await usage();
    progress.draft_started = new Date().toISOString(); await saveProgress();
    const preview = await request('/librarian/reports/draft', 'POST', { project_id: projectId, source_token: sources.source_token,
      chunk_ids: expectedChunks, reviewed_sources: true, title: 'LIB-4 reviewed synthetic onboarding report', format: 'report',
      prompt: 'Summarise the onboarding navigation pain points in these two explicitly synthetic interview fixtures. Cite each supplied excerpt. Keep observed fixture statements separate from recommendations and do not claim real participant findings. Give a short report grounded only in these excerpts.' });
    review = { user_id: me.user_id, sources, preview };
    await fs.writeFile(privateFile, JSON.stringify(review), { mode: 0o600 });
    assert.deepEqual(preview.citations.map(citation => citation.chunk_id), expectedChunks);
    assert.equal(hash(await snapshot()), hash(before));
    assert.deepEqual(await request(`/reports?project_id=${projectId}&page_size=100`), reports);
    const afterUsage = await usage(); assert.equal(afterUsage - beforeUsage, 1);
    progress.preview = { report_id: preview.report_id, title: preview.title, model: preview.model, content_hash: hash(preview.content),
      citations: preview.citations, input_chunk_ids: preview.input_chunk_ids, input_characters: preview.input_characters,
      snapshot_hash: hash(before), reports_before: reports.items.map(report => report.id), draft_created_no_reports: true,
      caller_role: me.role, usage_before: beforeUsage, usage_after_draft: afterUsage };
    await saveProgress();
  }
  assert.equal(review.user_id, me.user_id);
  console.log(JSON.stringify({ stage: 'prepared', report_id: review.preview.report_id, model: review.preview.model,
    content: review.preview.content, citations: review.preview.citations, inputs: review.preview.input_chunk_ids }));
}
if (mode === 'browser') {
  assert.ok(review && progress.preview); assert.equal(review.user_id, me.user_id);
  const require = createRequire(path.join(root, 'frontend/package.json'));
  const { chromium } = require('playwright'), { expect } = require('@playwright/test');
  const browser = await chromium.launch();
  const checks = [];
  try {
    for (const [theme, width] of [['light', 390], ['dark', 1440]]) {
      const context = await browser.newContext({ viewport: { width, height: 1000 }, colorScheme: theme });
      await context.route(api + '/**', async route => {
        const headers = { ...route.request().headers(), 'x-api-key': credentials.key }; delete headers.authorization;
        await route.continue({ headers });
      });
      await context.addInitScript(({ user, theme, sources, preview }) => {
        localStorage.setItem('tracelab.auth.v2', JSON.stringify({ token: 'browser-auth-via-header', ...user }));
        localStorage.setItem(`tracelab.theme.v1:${user.user_id}`, theme);
        const key = `tracelab.librarian.reports.v1:${user.user_id}:${preview.project_id}`;
        if (!localStorage.getItem(key)) localStorage.setItem(key, JSON.stringify({ title: preview.title, prompt: preview.prompt,
          format: preview.format, collectionId: sources.collection_id, sources, selected: preview.input_chunk_ids,
          reviewed: true, preview, saved: null }));
      }, { user: me, theme, sources: review.sources, preview: review.preview });
      const page = await context.newPage();
      const errors = [], writes = []; let drafts = 0, accepts = 0, sourceVisits = 0;
      page.on('pageerror', error => errors.push(error.message));
      page.on('request', req => {
        if (!req.url().startsWith(api + '/') || ['GET', 'HEAD', 'OPTIONS'].includes(req.method())) return;
        const pathname = new URL(req.url()).pathname;
        if (pathname.endsWith('/librarian/reports/draft')) drafts++;
        else if (pathname.endsWith('/librarian/reports/accept')) accepts++;
        else writes.push({ method: req.method(), path: pathname });
      });
      const librarian = web + '/librarian?project=' + projectId;
      const panel = page.getByRole('region', { name: 'Draft a report', exact: true });
      const preview = page.getByRole('region', { name: 'Review report draft', exact: true });
      await page.goto(librarian); await preview.waitFor();
      await expect(panel.getByText(/2 of 12 excerpts/)).toBeVisible();
      await panel.getByLabel('Report title', { exact: true }).fill('A changed title requires a new draft');
      await expect(preview.getByRole('button', { name: 'Save reviewed report' })).toBeDisabled();
      await panel.getByLabel('Report title', { exact: true }).fill(review.preview.title);
      await page.reload(); await preview.waitFor();
      assert.equal(await panel.getByLabel('Report title', { exact: true }).inputValue(), review.preview.title);
      for (const citation of review.preview.citations) {
        assert.ok(citation.available && citation.href);
        const link = preview.getByRole('link', { name: `[${citation.marker}] Open report source excerpt`, exact: true });
        assert.equal(await link.getAttribute('href'), citation.href);
        await link.focus(); await page.keyboard.press('Enter');
        await page.waitForURL(web + citation.href);
        await page.locator(`[data-cited="true"] #chunk-${citation.chunk_id}`).waitFor();
        await expect(page.locator('[data-cited="true"] button[aria-expanded="true"]')).toBeVisible();
        sourceVisits++; await page.goto(librarian); await preview.waitFor();
      }
      assert.equal(drafts, 0); assert.equal(accepts, 0);
      const saving = page.waitForResponse(r => r.url().endsWith('/librarian/reports/accept') && r.request().method() === 'POST');
      await preview.getByRole('button', { name: 'Save reviewed report' }).focus(); await page.keyboard.press('Enter');
      const response = await saving; assert.equal(response.status(), 200);
      const saved = await response.json(); assert.equal(saved.report_id, review.preview.report_id);
      progress.saved = saved; await saveProgress();
      await preview.getByRole('link', { name: saved.title, exact: true }).waitFor();
      await page.evaluate(() => document.activeElement?.blur());
      await panel.screenshot({ path: path.join(out, `deployed-preview-${theme}-${width}.png`) });
      await preview.getByRole('link', { name: saved.title, exact: true }).click();
      await page.getByRole('heading', { level: 1, name: saved.title, exact: true }).waitFor();
      await expect(page.getByText('Librarian drafted', { exact: false })).toContainText('Human accepted');
      await page.reload();
      const citations = page.getByRole('region', { name: 'Report source citations', exact: true });
      await citations.waitFor();
      await page.evaluate(() => { document.activeElement?.blur(); window.scrollTo(0, 0); });
      await page.screenshot({ path: path.join(out, `deployed-report-${theme}-${width}.png`), fullPage: true, mask: [page.getByText(me.email, { exact: true })] });
      for (const citation of review.preview.citations) {
        const link = citations.getByRole('link', { name: `[${citation.marker}] Open source excerpt`, exact: true });
        await link.focus(); await page.keyboard.press('Enter'); await page.waitForURL(web + citation.href);
        await page.locator(`[data-cited="true"] #chunk-${citation.chunk_id}`).waitFor();
        await expect(page.locator('[data-cited="true"] button[aria-expanded="true"]')).toBeVisible();
        sourceVisits++; await page.goto(web + saved.href); await citations.waitFor();
      }
      assert.equal(drafts, 0); assert.equal(accepts, 1); assert.deepEqual(writes, []); assert.deepEqual(errors, []);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      checks.push({ theme, width, explicit_accepts: accepts, model_calls: drafts, exact_source_visits: sourceVisits,
        navigation_and_reload_preserved_preview: true, report_id: saved.report_id, unrelated_writes: writes, page_errors: errors, overflow: false });
      await context.close();
    }
  } finally { await browser.close(); }
  assert.equal(await usage(), progress.preview.usage_after_draft, 'Save or navigation recorded new provider usage');
  await fs.writeFile(path.join(out, 'deployed-browser.json'), JSON.stringify({ serving_commit: commit, checks,
    source: 'Real privately cached server proposal; live acceptance and reads; no mocked API responses', agent_acceptance: true }, null, 2) + '\n');
}
if (mode === 'verify' || mode === 'read-only') {
  assert.ok(progress.saved && progress.preview);
  const preview = progress.preview, saved = progress.saved;
  const detail = await request('/reports/' + saved.report_id);
  assert.equal(hash(detail.content), preview.content_hash); assert.equal(detail.title, preview.title);
  assert.equal(detail.status, 'draft'); assert.equal(detail.project_id, projectId);
  assert.equal(detail.generation_provenance.origin, 'librarian'); assert.equal(detail.generation_provenance.accepted_by, me.user_id);
  assert.deepEqual(detail.citations, preview.citations);
  assert.deepEqual(detail.sources.filter(s => s.source_type === 'chunk').map(s => s.source_id).sort(), [...expectedChunks].sort());
  assert.deepEqual(detail.sources.filter(s => s.source_type === 'collection').map(s => s.source_id), [collectionId]);
  const reports = await request(`/reports?project_id=${projectId}&page_size=100`);
  assert.deepEqual(reports.items.map(report => report.id).sort(), [...preview.reports_before, saved.report_id].sort());
  assert.equal(hash(await snapshot()), preview.snapshot_hash, 'Report workflow changed its source corpus, collection or project');
  const exports = {};
  for (const format of ['md', 'json', 'txt']) {
    const exported = await request(`/reports/${saved.report_id}/export?format=${format}`, 'GET', undefined, format !== 'json');
    if (format === 'json') { assert.equal(exported.content, detail.content); assert.deepEqual(exported.citations, preview.citations); }
    else { assert.ok(exported.includes(detail.content)); for (const c of detail.citations) assert.ok(exported.includes(c.href)); }
    exports[format] = hash(exported);
  }
  const require = createRequire(path.join(root, 'packages/tracelab-mcp/package.json'));
  const { Client } = require('@modelcontextprotocol/sdk/client/index.js'), { StdioClientTransport } = require('@modelcontextprotocol/sdk/client/stdio.js');
  const client = new Client({ name: 'lib4-deployed-contract', version: '1.0.0' });
  const temp = await fs.mkdtemp(path.join(os.tmpdir(), 'lib4-published-mcp-'));
  const transport = new StdioClientTransport({ command: 'npx', args: ['-y', '@aquex/tracelab-mcp@2.1.0'], cwd: temp,
    env: { PATH: process.env.PATH, HOME: process.env.HOME, TRACELAB_API_URL: api, TRACELAB_API_KEY: credentials.key, TRACELAB_FRONTEND_URL: web }, stderr: 'pipe' });
  let mcpVersion;
  try {
    await client.connect(transport);
    const result = await client.callTool({ name: 'tracelab_report', arguments: { action: 'get', report_id: saved.report_id } });
    assert.ok(!result.isError);
    const read = JSON.parse(result.content[0].text);
    assert.equal(read.content, detail.content); assert.deepEqual(read.citations, detail.citations);
    assert.equal(read.status, 'draft'); assert.equal(read.project_id, projectId);
    mcpVersion = client.getServerVersion()?.version;
  } finally { await client.close(); await fs.rm(temp, { recursive: true, force: true }); }
  const receipt = { verified_at: new Date().toISOString(), serving_commit: commit, project_id: projectId, collection_id: collectionId,
    report_id: saved.report_id, reviewed_content_sha256: preview.content_hash, citations: preview.citations, input_chunk_ids: expectedChunks,
    model: preview.model, caller_role: preview.caller_role, single_report: true, sources_collection_project_unchanged: true,
    snapshot_sha256: preview.snapshot_hash, exports_sha256: exports, published_mcp_version: mcpVersion,
    exact_preview_content_and_citations_reopened_exported_and_mcp: true, verification: 'Agent acceptance, not Derek personal acceptance', read_only: mode === 'read-only' };
  if (mode !== 'read-only') await fs.writeFile(path.join(out, 'deployed-acceptance.json'), JSON.stringify(receipt, null, 2) + '\n');
  console.log(JSON.stringify(receipt));
}
