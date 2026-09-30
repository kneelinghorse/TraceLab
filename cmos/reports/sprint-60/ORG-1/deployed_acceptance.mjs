// Controlled synthetic fixtures; real configured-model proposal, browser acceptance,
// then fresh REST and published MCP reads. No credentials or proposal tokens in receipts.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

const out = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(out, '../../../..');
const api = 'https://api.tracelab.aquex.ai';
const web = 'https://tracelab.aquex.ai';
const projectId = '0d6c5b1d-72eb-4390-a40b-c48c88cdb302';
const commit = process.env.ORG1_SERVING_COMMIT;
assert.match(commit || '', /^[a-f0-9]{40}$/, 'Exact deployed commit required');
const mode = process.argv[2] || 'all';
assert.ok(['all', 'prepare', 'browser', 'verify', 'read-only'].includes(mode));
const credentials = JSON.parse(await fs.readFile(path.join(os.homedir(), '.config/tracelab-mcp/credentials.json'), 'utf8'));
assert.equal(credentials.apiBaseUrl.replace(/\/$/, ''), api);
const hash = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
async function jsonFile(filename, fallback) {
  try { return JSON.parse(await fs.readFile(filename, 'utf8')); }
  catch (error) { if (error.code === 'ENOENT') return fallback; throw error; }
}
async function request(route, method = 'GET', body, asText = false) {
  const multipart = body instanceof FormData;
  const response = await fetch(api + '/api/v1' + route, { method,
    headers: { 'X-API-Key': credentials.key, ...(multipart ? {} : { 'Content-Type': 'application/json' }) },
    body: body ? multipart ? body : JSON.stringify(body) : undefined });
  assert.ok(response.ok, `${method} ${route.split('?')[0]}: ${response.status}`);
  return asText ? response.text() : response.json();
}
for (const endpoint of [api + '/api/v1/health', web + '/api/version']) {
  const response = await fetch(endpoint, { headers: { 'Cache-Control': 'no-cache' } });
  assert.equal(response.status, 200);
  assert.equal((await response.json()).commit, commit);
}
const me = await request('/auth/me');
assert.notEqual(me.role, 'service');
assert.equal((await request('/projects/' + projectId)).name, 'Sprint 60 Librarian acceptance — onboarding feedback');
const progressFile = path.join(out, 'deployed-progress.json');
const progress = await jsonFile(progressFile, { project_id: projectId, documents: {} });
const saveProgress = () => fs.writeFile(progressFile, JSON.stringify(progress, null, 2) + '\n');
const privateFile = path.join(os.tmpdir(), 'tracelab-org1-review.json');
let review = await jsonFile(privateFile, null);
async function corpus() {
  const documents = (await request(`/documents?project_id=${projectId}&page_size=100`)).data;
  return Promise.all(documents.sort((a, b) => a.id.localeCompare(b.id)).map(async doc => ({
    id: doc.id, detail: await request(`/documents/${doc.id}`), content: await request(`/documents/${doc.id}/content`),
    chunks: await request(`/documents/${doc.id}/chunks?page_size=100`),
  })));
}
if (mode === 'all' || mode === 'prepare') {
  const fixture = await jsonFile(path.join(root, 'tests/fixtures/librarian_collection_feedback.json'));
  for (const [name, content] of Object.entries(fixture)) {
    if (!progress.documents[name]) {
      const body = new FormData(); body.append('file', new Blob([content], { type: 'text/plain' }), name);
      const doc = await request(`/documents/upload?project_id=${projectId}&file_type=notes&source_type=interview`, 'POST', body);
      progress.documents[name] = { id: doc.id, processed: false };
      await saveProgress();
    }
    const doc = progress.documents[name];
    if (!doc.processed) {
      assert.notEqual((await request(`/documents/${doc.id}/process`, 'POST')).status, 'failed');
      assert.equal((await request(`/documents/${doc.id}/content`)).content.trim(), content.trim());
      doc.processed = true; await saveProgress();
    }
    const chunks = (await request(`/documents/${doc.id}/chunks?page_size=100`)).data;
    assert.ok(chunks.length > 0 && chunks.every(c => c.content.trim().length > 0 && c.content.length <= 4000), 'Actual eligible saved chunks required');
    doc.chunk_ids = chunks.map(c => c.id); await saveProgress();
  }
  if (!review) {
    assert.ok(!progress.draft_started, 'Proposal cache missing after a prior request; inspect before making another paid call');
    const before = await corpus();
    const collections = await request(`/collections?project_id=${projectId}&page_size=100`);
    progress.draft_started = new Date().toISOString(); await saveProgress();
    const proposal = await request('/librarian/collections/draft', 'POST', { project_id: projectId,
      prompt: 'Group this synthetic onboarding feedback by pain point. Propose two useful themed collections, each drawing on all three available interview excerpts. Keep exact excerpt membership visible. Describe these as controlled fixtures, not real participant findings.' });
    review = { user_id: me.user_id, proposal, corpus_hash: hash(before), collections_before: collections };
    await fs.writeFile(privateFile, JSON.stringify(review), { mode: 0o600 });
    assert.deepEqual(await corpus(), before, 'Draft changed research sources');
    assert.deepEqual(await request(`/collections?project_id=${projectId}&page_size=100`), collections);
  }
  assert.equal(review.user_id, me.user_id);
  assert.equal(review.proposal.project_id, projectId);
  assert.equal(review.proposal.coverage.used_documents, 3);
  assert.equal(review.proposal.coverage.readable_documents, 9);
  assert.ok(review.proposal.groups.length >= 2 && review.proposal.groups[0].members.length >= 2, 'Need an editable multi-member group and an independent dismissible group');
  progress.proposal = { model: review.proposal.model, coverage: review.proposal.coverage,
    group_ids: review.proposal.groups.map(g => g.group_id), corpus_hash: review.corpus_hash,
    draft_created_no_collections: true, caller_role: me.role };
  await saveProgress();
  console.log(JSON.stringify({ stage: 'prepared', chunks: review.proposal.coverage.used_chunks, groups: review.proposal.groups.length }));
}
if (mode === 'all' || mode === 'browser') {
  assert.equal(review?.user_id, me.user_id, 'Private reviewed proposal must belong to this caller');
  const require = createRequire(path.join(root, 'frontend/package.json'));
  const { chromium } = require('@playwright/test');
  const browser = await chromium.launch();
  const results = [];
  const group = review.proposal.groups[0];
  const selected = group.members.slice(1).map(m => m.chunk_id);
  const name = 'ORG-1 reviewed onboarding feedback';
  const description = 'Human-reviewed synthetic onboarding excerpts for the Sprint 60 report workflow.';
  try {
    for (const [theme, width] of [['light', 390], ['dark', 1440]]) {
      const context = await browser.newContext({ viewport: { width, height: 1000 }, colorScheme: theme });
      await context.route(api + '/**', async route => {
        const headers = { ...route.request().headers(), 'x-api-key': credentials.key }; delete headers.authorization;
        await route.continue({ headers });
      });
      await context.addInitScript(({ user, theme, proposal }) => {
        localStorage.setItem('tracelab.auth.v2', JSON.stringify({ token: 'browser-auth-via-header', ...user }));
        localStorage.setItem(`tracelab.theme.v1:${user.user_id}`, theme);
        const key = `tracelab.librarian.collections.v1:${user.user_id}:${proposal.project_id}`;
        if (!localStorage.getItem(key)) localStorage.setItem(key, JSON.stringify({ proposal,
          reviews: Object.fromEntries(proposal.groups.map(g => [g.group_id, { name: g.name, description: g.description,
            memberIds: g.members.map(m => m.chunk_id), dismissed: false }])) }));
      }, { user: me, theme, proposal: review.proposal });
      const page = await context.newPage();
      const errors = [], writes = [], accepts = []; let drafts = 0;
      page.on('pageerror', error => errors.push(error.message));
      page.on('request', req => {
        if (!req.url().startsWith(api + '/') || ['GET', 'HEAD', 'OPTIONS'].includes(req.method())) return;
        const pathname = new URL(req.url()).pathname;
        if (pathname.endsWith('/collections/draft')) drafts++;
        else if (pathname.endsWith('/librarian/collections/accept')) accepts.push(req.postDataJSON());
        else writes.push({ method: req.method(), path: pathname });
      });
      const librarian = web + '/librarian?project=' + projectId;
      await page.goto(librarian);
      await page.getByRole('region', { name: 'Review suggested collections', exact: true }).waitFor();
      await page.getByLabel('Collection name 1', { exact: true }).fill(name);
      await page.getByLabel('Collection description 1', { exact: true }).fill(description);
      await page.getByRole('checkbox', { name: `Include excerpt ${group.members[0].marker} in collection 1`, exact: true }).uncheck();
      for (let i = 1; i < review.proposal.groups.length; i++) await page.getByRole('article', { name: `Suggested collection ${i + 1}`, exact: true }).getByRole('button', { name: 'Dismiss group' }).click();
      await page.reload();
      assert.equal(await page.getByLabel('Collection name 1', { exact: true }).inputValue(), name);
      const first = page.getByRole('article', { name: 'Suggested collection 1', exact: true });
      let sourceLinks = 0;
      for (const member of group.members) {
        const link = first.getByRole('link', { name: `Open excerpt [${member.marker}]`, exact: true });
        assert.equal(await link.getAttribute('href'), member.href);
        await link.focus(); await page.keyboard.press('Enter');
        await page.waitForURL(web + member.href);
        await page.getByRole('heading', { level: 1, name: member.document_name, exact: true }).waitFor();
        await page.locator(`[data-cited="true"] #chunk-${member.chunk_id}`).waitFor();
        sourceLinks++; await page.goto(librarian);
        await page.getByLabel('Collection name 1', { exact: true }).waitFor();
      }
      assert.equal(drafts, 0); assert.deepEqual(accepts, []);
      const saving = page.waitForResponse(response => response.url().endsWith('/librarian/collections/accept') && response.request().method() === 'POST');
      await first.getByRole('button', { name: 'Accept this collection', exact: true }).focus(); await page.keyboard.press('Enter');
      const response = await saving;
      assert.equal(response.status(), 200);
      const saved = await response.json();
      assert.equal(saved.state, 'saved'); assert.deepEqual(saved.completed_member_ids, selected);
      assert.equal(saved.collection_id, group.group_id);
      progress.accepted = { collection_id: saved.collection_id, name, description, member_ids: selected,
        destination: saved.destination, source_members: group.members.filter(m => selected.includes(m.chunk_id)) };
      await saveProgress();
      await page.getByText('Reviewed collection saved.', { exact: true }).waitFor();
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      await page.getByRole('region', { name: 'Organise research', exact: true }).scrollIntoViewIfNeeded();
      await page.screenshot({ path: path.join(out, `deployed-review-${theme}-${width}.png`), fullPage: true, mask: [page.getByText(me.email, { exact: true })] });
      await first.getByRole('link', { name, exact: true }).click();
      const origin = page.getByRole('region', { name: 'Collection origin', exact: true });
      await origin.waitFor();
      await origin.getByText('Originally accepted sources', { exact: true }).click();
      assert.equal(await origin.locator('a').count(), selected.length);
      await page.reload(); await origin.waitFor();
      await page.screenshot({ path: path.join(out, `deployed-collection-${theme}-${width}.png`), fullPage: true, mask: [page.getByText(me.email, { exact: true })] });
      assert.equal(accepts.length, 1);
      assert.deepEqual(accepts[0].member_ids, selected);
      assert.equal(drafts, 0); assert.deepEqual(writes, []); assert.deepEqual(errors, []);
      results.push({ theme, width, accepted_collection_id: saved.collection_id, source_links_opened: sourceLinks,
        edited_subset_persisted_after_navigation: true, dismissed_groups: review.proposal.groups.length - 1,
        accepts: accepts.length, automatic_model_requests: drafts, other_writes: writes, page_errors: errors, overflow: false });
      await context.close();
    }
  } finally { await browser.close(); }
  await fs.writeFile(path.join(out, 'deployed-browser.json'), JSON.stringify({ verified_at: new Date().toISOString(), serving_commit: commit,
    results, mocked_responses: false, proposal_source: 'Real API-generated proposal restored from private browser draft state; both themes accept the same signed group.', personal_user_acceptance: false }, null, 2) + '\n');
}
if (mode === 'all' || mode === 'verify' || mode === 'read-only') {
  const accepted = progress.accepted;
  assert.ok(accepted, 'Complete explicit browser acceptance first');
  const detail = await request('/collections/' + accepted.collection_id);
  assert.equal(detail.name, accepted.name); assert.equal(detail.description, accepted.description);
  assert.equal(detail.item_count, accepted.member_ids.length);
  assert.deepEqual(detail.items.map(item => item.chunk_id), accepted.member_ids);
  assert.equal(detail.librarian_generated, true);
  const origin = (await request('/librarian/collections/' + accepted.collection_id)).provenance;
  assert.equal(origin.accepted_by, me.user_id); assert.ok(origin.completed_at);
  assert.equal(origin.model, progress.proposal.model);
  assert.deepEqual(origin.members.map(m => m.chunk_id), accepted.member_ids);
  for (const member of origin.members) {
    assert.ok(member.available);
    assert.equal((await request('/documents/' + member.document_id)).project_id, projectId);
    assert.ok((await request(`/documents/${member.document_id}/chunks?page_size=100`)).data.some(c => c.id === member.chunk_id));
    assert.equal((await fetch(web + member.href)).status, 200);
  }
  const collections = await request(`/collections?project_id=${projectId}&page_size=100`);
  const createdGroups = collections.data.filter(c => progress.proposal.group_ids.includes(c.id));
  assert.deepEqual(createdGroups.map(c => c.id), [accepted.collection_id]);
  assert.equal(hash(await corpus()), progress.proposal.corpus_hash, 'Acceptance changed original source records');
  const markdown = await request(`/collections/${accepted.collection_id}/export`, 'GET', undefined, true);
  let previous = -1;
  for (const item of detail.items) {
    const position = markdown.indexOf(item.chunk_content.trim());
    assert.ok(position > previous); previous = position;
  }
  const require = createRequire(path.join(root, 'packages/tracelab-mcp/package.json'));
  const { Client } = require('@modelcontextprotocol/sdk/client/index.js');
  const { StdioClientTransport } = require('@modelcontextprotocol/sdk/client/stdio.js');
  const client = new Client({ name: 'org1-deployed-contract', version: '1.0.0' });
  const temp = await fs.mkdtemp(path.join(os.tmpdir(), 'org1-published-mcp-'));
  const transport = new StdioClientTransport({ command: 'npx', args: ['-y', '@aquex/tracelab-mcp@2.1.0'], cwd: temp,
    env: { PATH: process.env.PATH, HOME: process.env.HOME, TRACELAB_API_URL: api, TRACELAB_API_KEY: credentials.key, TRACELAB_FRONTEND_URL: web }, stderr: 'pipe' });
  let mcpVersion;
  try {
    await client.connect(transport);
    const result = await client.callTool({ name: 'tracelab_collection', arguments: { action: 'get', collection_id: accepted.collection_id } });
    assert.ok(!result.isError);
    const read = JSON.parse(result.content[0].text);
    assert.deepEqual(read.items.map(item => item.chunk_id), accepted.member_ids);
    assert.equal(read.item_count, detail.item_count);
    assert.deepEqual(read.items.map(i => i.chunk_content), detail.items.map(i => i.chunk_content));
    mcpVersion = client.getServerVersion()?.version;
  } finally { await client.close(); }
  const receipt = { verified_at: new Date().toISOString(), serving_commit: commit, project_id: projectId,
    collection_id: accepted.collection_id, reviewed_member_ids: accepted.member_ids, model: origin.model,
    coverage: progress.proposal.coverage, destination: accepted.destination, published_mcp_version: mcpVersion,
    original_source_sha256: progress.proposal.corpus_hash, sources_unchanged: true, saved_group_count: 1,
    dismissed_group_ids: progress.proposal.group_ids.filter(id => id !== accepted.collection_id),
    exact_membership_order_reopen_export_and_mcp: true, resolving_sources: origin.members.length,
    verification: 'Agent acceptance, not Derek personal acceptance', read_only: mode === 'read-only' };
  if (mode !== 'read-only') await fs.writeFile(path.join(out, 'deployed-acceptance.json'), JSON.stringify(receipt, null, 2) + '\n');
  console.log(JSON.stringify(receipt));
}
