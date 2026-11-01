// Controlled member acceptance. Credentials and signed drafts stay outside the repo.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createHash, randomBytes } from 'node:crypto';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const out = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(out, '../../../..');
const web = 'https://tracelab.aquex.ai', api = 'https://api.tracelab.aquex.ai';
const commit = process.env.WALK3_SERVING_COMMIT;
assert.match(commit || '', /^[a-f0-9]{40}$/, 'Exact serving commit required');
const mode = process.argv[2];
const privateFile = path.join(os.tmpdir(), 'tracelab-walk3-private.json');
const owner = JSON.parse(await fs.readFile(path.join(os.homedir(), '.config/tracelab-mcp/credentials.json'), 'utf8'));
assert.equal(owner.apiBaseUrl.replace(/\/$/, ''), api);
async function load(file, fallback) {
  try { return JSON.parse(await fs.readFile(file, 'utf8')); }
  catch (error) { if (error.code === 'ENOENT') return fallback; throw error; }
}
const state = await load(privateFile, { steps: {}, models: {}, documents: {} });
const receipt = await load(path.join(out, 'progress.json'), { checks: {} });
const hash = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const clean = value => JSON.parse(JSON.stringify(value, (key, item) => /token|password|^key$/i.test(key) ? undefined : item));
async function save() {
  await fs.writeFile(privateFile, JSON.stringify(state), { mode: 0o600 });
  await fs.chmod(privateFile, 0o600);
  await fs.writeFile(path.join(out, 'progress.json'), JSON.stringify(receipt, null, 2) + '\n');
}
async function request(route, method = 'GET', body, principal = 'member', expected) {
  const multipart = body instanceof FormData;
  const headers = { ...(multipart ? {} : { 'Content-Type': 'application/json' }),
    ...(principal === 'owner' ? { 'X-API-Key': owner.key } : principal === 'login' ? {} : { 'X-API-Key': state.key }) };
  const response = await fetch(api + '/api/v1' + route, { method, headers,
    body: body ? multipart ? body : JSON.stringify(body) : undefined });
  const text = await response.text(); let data;
  try { data = JSON.parse(text); } catch { data = text; }
  const ok = expected ? expected.includes(response.status) : response.ok;
  assert.ok(ok, `${method} ${route.split('?')[0]}: ${response.status}: ${typeof data?.detail === 'string' ? data.detail : 'unexpected response'}`);
  return expected ? { status: response.status, data } : data;
}
async function versions() {
  for (const endpoint of [api + '/api/v1/health', web + '/api/version']) {
    const response = await fetch(endpoint, { headers: { 'Cache-Control': 'no-cache' } });
    assert.equal(response.status, 200); assert.equal((await response.json()).commit, commit);
  }
}
await versions();
async function usage() {
  return (await request('/admin/usage?user_id=' + state.user.id, 'GET', undefined, 'owner')).rows
    .reduce((n, row) => n + row.records, 0);
}
async function corpus(projectId) {
  const docs = (await request(`/documents?project_id=${projectId}&page_size=100`)).data;
  return Promise.all(docs.sort((a, b) => a.id.localeCompare(b.id)).map(async doc => ({
    detail: await request('/documents/' + doc.id), content: await request(`/documents/${doc.id}/content`),
    chunks: await request(`/documents/${doc.id}/chunks?page_size=100`),
  })));
}
async function artifacts(projectId) {
  return { project: await request('/projects/' + projectId), corpus: await corpus(projectId),
    reports: await request(`/reports?project_id=${projectId}&page_size=100`),
    collections: await request(`/collections?project_id=${projectId}&page_size=100`),
    missions: await request(`/missions?project_id=${projectId}&page_size=100`) };
}
async function upload(key, projectId, name, content, principal = 'member') {
  if (!state.documents[key]) {
    const body = new FormData(); body.append('file', new Blob([content], { type: 'text/plain' }), name);
    const doc = await request(`/documents/upload?project_id=${projectId}&file_type=notes&source_type=interview`, 'POST', body, principal);
    state.documents[key] = { id: doc.id, project_id: projectId, name }; await save();
  }
  const doc = state.documents[key];
  if (!doc.processed) {
    assert.notEqual((await request(`/documents/${doc.id}/process`, 'POST', undefined, principal)).status, 'failed');
    assert.equal((await request(`/documents/${doc.id}/content`, 'GET', undefined, principal)).content.trim(), content.trim());
    const chunks = (await request(`/documents/${doc.id}/chunks?page_size=100`, 'GET', undefined, principal)).data;
    assert.equal(chunks.length, 1); assert.ok(chunks[0].content.length <= 4000);
    doc.chunks = chunks.map(c => c.id); doc.processed = true; await save();
  }
}
if (mode === 'setup') {
  if (!state.account) {
    state.account = { email: 'walk3-20260930@tracelab.local', password: randomBytes(32).toString('base64url'), display_name: 'WALK-3 acceptance', role: 'member' };
    await save();
  }
  if (!state.user) {
    const existing = (await request('/admin/users', 'GET', undefined, 'owner')).find(u => u.email === state.account.email);
    state.user = existing || await request('/admin/users', 'POST', state.account, 'owner');
    assert.equal(state.user.role, 'member'); assert.equal(state.user.is_active, true); await save();
  }
  if (!state.key) {
    const login = await request('/auth/login', 'POST', { email: state.account.email, password: state.account.password }, 'login');
    const response = await fetch(api + '/api/v1/auth/api-keys', { method: 'POST',
      headers: { Authorization: 'Bearer ' + login.access_token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'WALK-3 controlled acceptance', expires_in_days: 1 }) });
    assert.equal(response.status, 201); const key = await response.json();
    state.key = key.key; state.key_id = key.id; state.login = login; await save();
  }
  state.me = await request('/auth/me'); assert.equal(state.me.role, 'member');
  assert.equal(state.me.user_id, state.user.id);
  assert.equal((await request('/admin/users', 'GET', undefined, 'member', [403])).status, 403);
  for (const [key, title] of [['empty', 'WALK-3 empty planning fixture'], ['populated', 'WALK-3 synthetic onboarding feedback']]) {
    if (!state[key]) { state[key] = await request('/projects', 'POST', { name: title, description: 'Controlled WALK-3 synthetic acceptance fixture; not real participant research.' }); await save(); }
    assert.equal(state[key].owner_id, state.user.id);
  }
  const fixtures = await load(path.join(root, 'tests/fixtures/librarian_collection_feedback.json'));
  for (const [key, name] of [['a', 'onboarding-interview-a.txt'], ['c', 'onboarding-interview-c.txt'], ['copy', 'onboarding-interview-a.txt']]) {
    await upload(key, state.populated.id, key === 'copy' ? 'onboarding-interview-a-copy.txt' : name, fixtures[name]);
  }
  if (!state.shared) { state.shared = await request('/admin/spaces', 'POST', { name: 'WALK-3 isolated revocation fixture' }, 'owner'); await save(); }
  if (!state.foreign) { state.foreign = await request('/projects', 'POST', { name: 'WALK-3 revocable source fixture', description: 'Controlled source-access test only.', workspace_id: state.shared.id }, 'owner'); await save(); }
  await upload('revocable', state.foreign.id, 'revocable-synthetic-interview.txt', fixtures['onboarding-interview-c.txt'], 'owner');
  if (!state.membership) {
    await request(`/admin/spaces/${state.shared.id}/members`, 'POST', { user_id: state.user.id, role: 'member' }, 'owner');
    state.membership = true; await save();
  }
  assert.notEqual(state.foreign.owner_id, state.user.id);
  receipt.setup = { serving_commit: commit, caller_role: state.me.role, caller_id: state.me.user_id,
    agent_selected_temporary_member: true, empty_project: state.empty.id, populated_project: state.populated.id,
    revocable_project: state.foreign.id, revocable_space: state.shared.id, documents: clean(state.documents),
    personal_space: state.empty.workspace_id, admin_denied: true, no_email_sent: true,
    existing_guest_untouched: true, agent_acceptance_not_personal_Derek_walk: true };
  await save(); console.log(JSON.stringify({ stage: mode, ...receipt.setup }));
}

const browserModes = ['planning', 'mission', 'descriptions', 'description-accept', 'duplicates', 'organisation', 'collection', 'report', 'report-save', 'questions'];
if (browserModes.includes(mode)) {
  assert.ok(state.key && receipt.setup);
  assert.ok(!state.steps[mode], 'This completed stage must not be repeated blindly');
  const require = createRequire(path.join(root, 'frontend/package.json'));
  const { chromium } = require('playwright'), { expect } = require('@playwright/test');
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, colorScheme: 'light' });
  await context.route(api + '/**', async route => {
    const headers = { ...route.request().headers(), 'x-api-key': state.key }; delete headers.authorization;
    await route.continue({ headers });
  });
  await context.addInitScript(({ me, storage }) => {
    if (sessionStorage.getItem('walk3-initialized')) return;
    for (const [key, value] of Object.entries(storage || {})) localStorage.setItem(key, value);
    localStorage.setItem('tracelab.auth.v2', JSON.stringify({ token: 'member-via-private-api-header', ...me }));
    localStorage.setItem(`tracelab.theme.v1:${me.user_id}`, 'light');
    sessionStorage.setItem('walk3-initialized', 'yes');
  }, { me: state.me, storage: state.storage });
  const page = await context.newPage(); page.setDefaultTimeout(20000);
  const errors = [], writes = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', req => {
    if (req.url().startsWith(api + '/') && !['GET', 'HEAD', 'OPTIONS'].includes(req.method())) {
      const pathname = new URL(req.url()).pathname;
      writes.push({ method: req.method(), path: pathname,
        ...(pathname === '/api/v1/activity/viewed' ? { body: req.postDataJSON() } : {}) });
    }
  });
  const region = name => page.getByRole('region', { name, exact: true });
  async function go(project) {
    await page.goto(web + '/librarian?project=' + project.id);
    await expect(page.getByRole('combobox', { name: 'Project', exact: true })).toHaveValue(project.id);
    await region('Project description').getByText(project.description, { exact: true }).waitFor();
  }
  async function click(button) { await button.focus(); await page.keyboard.press('Enter'); }
  async function reply(name, route, button, paid = false) {
    if (paid) {
      assert.ok(!state.models[name], `Paid stage ${name} already started; inspect private response before retry`);
      state.models[name] = { started_at: new Date().toISOString() }; await save();
    }
    const pending = page.waitForResponse(r => r.url().split('?')[0] === api + '/api/v1' + route && r.request().method() === 'POST', { timeout: 180000 });
    await click(button); const response = await pending; const data = await response.json();
    if (paid) { state.models[name].status = response.status(); state.models[name].result = data; await save(); }
    assert.ok(response.ok(), `${route}: ${response.status()}: ${typeof data.detail === 'string' ? data.detail : 'failed'}`);
    return data;
  }
  async function checkpoint(name, data) { receipt.checks[name] = data; await save(); }
  async function rememberPreview(name) {
    state.preview_storage ||= {};
    state.preview_storage[name] = await page.evaluate(() => Object.fromEntries(Object.entries(localStorage).filter(([key]) => key.startsWith('tracelab.librarian.'))));
    await save();
  }
  try {
    if (mode === 'planning') {
      const before = hash(await artifacts(state.empty.id));
      await go(state.empty);
      const question = 'Help me plan a small desk-research study of how research tools make upload destinations clear. This is an empty synthetic acceptance project with no findings. Compare three public examples and produce a concise cited comparison with three actionable design questions. Do not start a research run.';
      await page.getByLabel('Message the Librarian').fill(question);
      const chat = await reply('chat', '/librarian/turns', page.getByRole('button', { name: 'Send', exact: true }), true);
      assert.ok(chat.segments.some(s => s.kind === 'prose' && s.text));
      assert.equal(chat.segments.filter(s => s.kind === 'corpus_claim').length, 0);
      const draft = await reply('mission', '/librarian/drafts', page.getByRole('button', { name: 'Draft a mission', exact: true }), true);
      await expect(region('Mission draft')).toBeFocused();
      assert.ok(draft.preview); assert.equal(draft.lint_errors.length, 0);
      assert.equal(hash(await artifacts(state.empty.id)), before);
      await rememberPreview('mission');
      await checkpoint(mode, { no_artifact_writes: true, empty_project: true, chat: clean(chat), draft: clean(draft) });
    }
    if (mode === 'mission') {
      let made;
      if (state.mission) {
        made = { mission: await request('/missions/' + state.mission.id) };
        await page.goto(web + '/missions/' + state.mission.id + '?from=librarian');
      } else {
        await go(state.empty); await region('Mission draft').waitFor();
        made = await reply('create-mission', '/librarian/missions', region('Mission draft').getByRole('button', { name: 'Create draft mission', exact: true }));
        state.mission = made.mission; await save();
      }
      assert.equal(made.mission.status, 'draft'); assert.equal(made.mission.project_id, state.empty.id);
      await page.waitForURL(url => url.origin === web && url.pathname === '/missions/' + made.mission.id);
      await expect(page.getByRole('button', { name: 'Submit to DeepSearch', exact: true })).toBeEnabled();
      assert.equal(writes.some(w => /submit/.test(w.path)), false);
      const replay = await request('/librarian/missions', 'POST', { project_id: state.empty.id, draft: state.models.mission.result.draft });
      assert.equal(replay.mission.id, made.mission.id); assert.equal(replay.created, false);
      await checkpoint(mode, { mission_id: made.mission.id, status: 'draft', separate_submission_enabled: true, submission_not_sent: true, retry_same_mission: true });
    }
    if (mode === 'descriptions') {
      const results = [];
      for (const [name, project, prompt] of [
        ['empty', state.empty, 'Describe this planned synthetic desk-research study of upload destination clarity in one short paragraph. There are no findings or documents yet.'],
        ['populated', state.populated, 'Describe the supplied synthetic onboarding interview fixtures in one short paragraph. Cite every assertion with supplied numeric markers, use only these excerpts, and never claim actual participant findings.'],
      ]) {
        await go(project); const before = hash(await artifacts(project.id));
        await page.getByLabel('What should the description explain?').fill(prompt);
        const proposal = await reply('description-' + name, '/librarian/descriptions/draft', region('Project description').getByRole('button', { name: 'Draft description', exact: true }), true);
        await expect(region('Review description')).toBeFocused();
        assert.equal(proposal.basis, name === 'empty' ? 'planning_brief' : 'corpus');
        assert.equal(hash(await artifacts(project.id)), before);
        await rememberPreview('description-' + name);
        results.push({ project_id: project.id, basis: proposal.basis, description: proposal.description, citations: proposal.citations, no_artifact_writes: true });
      }
      await checkpoint(mode, results);
    }
    if (mode === 'description-accept') {
      const results = [];
      for (const project of [state.empty, state.populated]) {
        await go(project); await region('Review description').waitFor();
        const original = await request('/librarian/descriptions/' + project.id);
        const accepted = await reply('description-accept', '/librarian/descriptions/accept', region('Review description').getByRole('button', { name: 'Accept description', exact: true }));
        assert.equal(accepted.provenance.accepted_by, state.me.user_id); assert.equal(accepted.provenance.current, true);
        await expect(region('Project description').getByRole('button', { name: 'Restore previous description', exact: true })).toBeVisible();
        const restored = await reply('description-restore', '/librarian/descriptions/restore', region('Project description').getByRole('button', { name: 'Restore previous description', exact: true }));
        assert.equal(restored.description, original.description); assert.equal(restored.can_restore, false);
        await expect(region('Project description').getByRole('button', { name: 'Restore previous description', exact: true })).toHaveCount(0);
        results.push({ project_id: project.id, accepted: hash(accepted.description), restored: hash(restored.description), previous: hash(original.description), provenance: clean(accepted.provenance) });
      }
      await checkpoint(mode, results);
    }
    if (mode === 'duplicates') {
      await go(state.populated); const before = hash(await artifacts(state.populated.id));
      const scan = await reply('duplicates', '/librarian/duplicates/scan', region('Duplicate review').getByRole('button', { name: 'Find possible duplicates', exact: true }));
      assert.equal(scan.candidates.length, 1); assert.equal(scan.candidates[0].kind, 'exact_text');
      assert.deepEqual(scan.candidates[0].documents.map(d => d.id).sort(), [state.documents.a.id, state.documents.copy.id].sort());
      await expect(region('Duplicate results')).toBeFocused();
      await reply('compare', '/librarian/duplicates/compare', region('Duplicate results').getByRole('button', { name: 'Compare sources', exact: true }));
      await expect(region('Compare documents')).toBeFocused();
      await click(region('Compare documents').getByRole('button', { name: 'Close comparison', exact: true }));
      await expect(region('Duplicate results').getByRole('button', { name: 'Compare sources', exact: true })).toBeFocused();
      await click(region('Duplicate results').getByRole('button', { name: 'Dismiss pair', exact: true }));
      await page.reload(); await expect(region('Duplicate results').getByText('1 pairs reviewed in your browser. No documents were changed.', { exact: true })).toBeVisible();
      assert.equal(hash(await artifacts(state.populated.id)), before);
      await checkpoint(mode, { exact_pairs: 1, compared_and_dismissed: true, persisted: true, artifacts_unchanged: true, scan: clean(scan) });
    }
    if (mode === 'organisation') {
      await go(state.populated); const before = hash(await artifacts(state.populated.id));
      await page.getByLabel('How should the research be organised?').fill('Propose two themed collections from these explicitly synthetic onboarding interviews. Include all three supplied excerpts in each group so I can review and remove the duplicate. Cite rationale statements with the supplied numeric markers. Do not claim real participant research.');
      const groups = await reply('organisation', '/librarian/collections/draft', region('Organise research').getByRole('button', { name: 'Suggest collections', exact: true }), true);
      await expect(region('Review suggested collections')).toBeFocused();
      assert.ok(groups.groups.length >= 2);
      assert.ok(groups.groups[0].members.some(m => m.chunk_id === state.documents.a.chunks[0]));
      assert.ok(groups.groups[0].members.some(m => m.chunk_id === state.documents.c.chunks[0]));
      assert.equal(hash(await artifacts(state.populated.id)), before);
      await rememberPreview(mode); await checkpoint(mode, { no_artifact_writes: true, proposal: clean(groups) });
    }
    if (mode === 'collection') {
      await go(state.populated); const before = hash(await artifacts(state.populated.id));
      const proposal = state.models.organisation.result, group = proposal.groups[0];
      const selected = group.members.filter(m => [state.documents.a.chunks[0], state.documents.c.chunks[0]].includes(m.chunk_id));
      assert.equal(selected.length, 2);
      const article = page.getByRole('article', { name: 'Suggested collection 1', exact: true });
      await article.getByLabel('Collection name 1', { exact: true }).fill('WALK-3 reviewed onboarding excerpts');
      await article.getByLabel('Collection description 1', { exact: true }).fill('Two explicitly reviewed synthetic interviews; duplicate copy excluded.');
      for (const member of group.members) if (!selected.some(m => m.chunk_id === member.chunk_id)) {
        await article.getByRole('checkbox', { name: `Include excerpt ${member.marker} in collection 1`, exact: true }).uncheck();
      }
      for (let index = 1; index < proposal.groups.length; index++) {
        await click(page.getByRole('article', { name: `Suggested collection ${index + 1}`, exact: true }).getByRole('button', { name: 'Dismiss group', exact: true }));
      }
      await page.reload(); await article.waitFor();
      assert.equal(hash(await artifacts(state.populated.id)), before, 'Editing/dismissal changed artifacts');
      state.collection_input = { project_id: state.populated.id, proposal_token: group.proposal_token,
        name: 'WALK-3 reviewed onboarding excerpts', description: 'Two explicitly reviewed synthetic interviews; duplicate copy excluded.', member_ids: selected.map(m => m.chunk_id) };
      await save();
      const paidBefore = await usage();
      const accepted = await reply('collection-accept', '/librarian/collections/accept', article.getByRole('button', { name: 'Accept this collection', exact: true }));
      state.collection = accepted; await save(); assert.equal(accepted.state, 'saved');
      const replay = await request('/librarian/collections/accept', 'POST', state.collection_input);
      assert.equal(replay.collection_id, accepted.collection_id);
      const detail = await request('/collections/' + accepted.collection_id);
      assert.deepEqual(detail.items.map(i => i.chunk_id), state.collection_input.member_ids);
      assert.equal((await usage()), paidBefore);
      await article.getByRole('link', { name: state.collection_input.name, exact: true }).click();
      await page.waitForURL(web + '/collections/' + accepted.collection_id);
      await expect(region('Collection origin')).toContainText('Machine suggested · Human accepted');
      await checkpoint(mode, { collection_id: accepted.collection_id, members: state.collection_input.member_ids,
        dismissed_groups: proposal.groups.slice(1).map(g => g.group_id), edited_subset: true, retry_same_collection: true, no_model_on_save: true });
    }
    if (mode === 'report') {
      await go(state.populated); const before = hash(await artifacts(state.populated.id));
      const panel = region('Draft a report');
      await panel.getByLabel('Report title', { exact: true }).fill('WALK-3 reviewed synthetic onboarding report');
      await panel.getByLabel('What should the report explain?').fill('Summarise the upload destination and collection navigation concerns in these synthetic interview fixtures. Use markdown # headings and three short paragraphs. Distinguish fixture observations from recommendations and real participant findings. Every paragraph, including the synthetic-data caveat and recommendations, must cite its supplied numeric source markers separately, such as [1] [2]. Do not use standalone bold labels. Cite both supplied excerpts.');
      await panel.getByLabel('Report format', { exact: true }).selectOption('report');
      await panel.getByRole('button', { name: 'Browse collections', exact: true }).click();
      await panel.getByLabel('Report source set').selectOption(state.collection.collection_id);
      const loaded = page.waitForResponse(r => r.url().startsWith(api + '/api/v1/librarian/reports/sources?'));
      await click(panel.getByRole('button', { name: 'Load excerpts for review', exact: true }));
      const sources = await (await loaded).json(); state.report_sources = sources; await save();
      assert.deepEqual(sources.members.map(m => m.chunk_id), state.collection_input.member_ids);
      assert.equal(sources.coverage.other_project_chunks, 0);
      for (const member of sources.members) {
        await panel.getByText(`Read supplied excerpt [${member.marker}]`, { exact: true }).click();
        await panel.getByRole('checkbox', { name: `Use report excerpt ${member.marker}`, exact: true }).check();
      }
      await expect(panel.getByRole('button', { name: 'Draft cited report', exact: true })).toBeDisabled();
      await panel.getByRole('checkbox', { name: `I reviewed the selected excerpts from ${state.populated.name}.`, exact: true }).check();
      const preview = await reply('report', '/librarian/reports/draft', panel.getByRole('button', { name: 'Draft cited report', exact: true }), true);
      await expect(region('Review report draft')).toBeFocused();
      assert.deepEqual(preview.citations.map(c => c.chunk_id), state.collection_input.member_ids);
      assert.equal(hash(await artifacts(state.populated.id)), before);
      await rememberPreview(mode); await checkpoint(mode, { no_artifact_writes: true, reviewed_inputs: sources.members.map(m => ({ chunk_id: m.chunk_id, characters: m.characters })), preview: clean(preview) });
    }
    if (mode === 'report-save') {
      await go(state.populated); const preview = state.models.report.result;
      await region('Review report draft').waitFor(); const paidBefore = await usage();
      const panel = region('Draft a report');
      let accepted = state.report;
      if (!accepted) {
        await panel.getByLabel('Report title', { exact: true }).fill('Changed title requires intentional generation');
        await expect(panel.getByRole('button', { name: 'Save reviewed report', exact: true })).toBeDisabled();
        await panel.getByLabel('Report title', { exact: true }).fill(preview.title);
        for (const citation of preview.citations) {
          const link = region('Review report draft').getByRole('link', { name: `[${citation.marker}] Open report source excerpt`, exact: true });
          await click(link); await page.waitForURL(web + citation.href);
          await page.locator(`[data-cited="true"] #chunk-${citation.chunk_id}`).waitFor();
          await go(state.populated); await region('Review report draft').waitFor();
        }
        accepted = await reply('report-save', '/librarian/reports/accept', panel.getByRole('button', { name: 'Save reviewed report', exact: true }));
        state.report = accepted; await save();
      }
      const repeated = await request('/librarian/reports/accept', 'POST', { project_id: state.populated.id, proposal_token: preview.proposal_token });
      assert.equal(repeated.report_id, accepted.report_id);
      await region('Review report draft').getByRole('link', { name: accepted.title, exact: true }).click();
      await page.waitForURL(web + accepted.href); await page.reload();
      await expect(page.getByText('Librarian drafted', { exact: false })).toContainText('Human accepted');
      for (const citation of preview.citations) {
        await click(region('Report source citations').getByRole('link', { name: `[${citation.marker}] Open source excerpt`, exact: true }));
        await page.waitForURL(web + citation.href);
        await page.locator(`[data-cited="true"] #chunk-${citation.chunk_id}`).waitFor();
        await expect(page.locator('[data-cited="true"] button[aria-expanded="true"]')).toBeVisible();
        await page.goto(web + accepted.href);
      }
      const detail = await request('/reports/' + accepted.report_id);
      assert.equal(hash(detail.content), hash(preview.content)); assert.deepEqual(detail.citations, preview.citations);
      assert.equal(detail.generation_provenance.accepted_by, state.me.user_id);
      assert.equal(detail.status, 'draft'); assert.equal(detail.project_id, state.populated.id);
      const exports = {};
      for (const format of ['md', 'json', 'txt']) {
        const data = await request(`/reports/${accepted.report_id}/export?format=${format}`);
        if (format === 'json') { assert.equal(hash(data.content), hash(preview.content)); assert.deepEqual(data.citations, preview.citations); }
        else { assert.ok(data.includes(preview.content)); for (const citation of preview.citations) assert.ok(data.includes(citation.href)); }
        exports[format] = hash(data);
      }
      assert.equal(await usage(), paidBefore);
      assert.equal((await request(`/reports?project_id=${state.populated.id}&page_size=100`)).total, 1);
      await checkpoint(mode, { report_id: accepted.report_id, exact_content: hash(preview.content), citations: preview.citations, exports,
        reloaded: true, keyboard_source_visits: preview.citations.length * 2, single_report: true, no_model_on_save_or_navigation: true });
    }
    if (mode === 'questions') {
      await go(state.populated);
      const before = hash(await artifacts(state.populated.id));
      const question = 'In the synthetic onboarding interviews, what did researchers want beside the upload action to clarify which project receives their notes?';
      await page.getByRole('radio', { name: 'Ask the documents', exact: true }).check();
      await page.getByRole('radio', { name: 'Short answer', exact: true }).check();
      await page.getByLabel('Message the Librarian').fill(question);
      const answer = await reply('answer', '/librarian/turns', page.getByRole('button', { name: 'Ask', exact: true }), true);
      assert.equal(answer.no_evidence, false); assert.ok(answer.chunks.length > 0);
      const cited = answer.segments.filter(s => s.kind === 'corpus_claim' && s.citations.length);
      assert.ok(cited.some(s => /project|destination/i.test(s.text)));
      for (const chunk of answer.chunks) {
        assert.equal((await request('/documents/' + chunk.document_id)).project_id, state.populated.id);
      }
      state.qa_question = question; state.qa = answer; await save();
      const refusalQuestion = 'How should Kubernetes horizontal pod autoscaling be tuned for bursty GPU inference traffic?';
      await page.getByLabel('Message the Librarian').fill(refusalQuestion);
      const refused = await reply('refusal', '/librarian/turns', page.getByRole('button', { name: 'Ask', exact: true }), true);
      assert.equal(refused.no_evidence, true); assert.equal(refused.usage, null); assert.equal(refused.chunks.length, 0);
      await expect(page.getByText('Nothing in this project answers that question.', { exact: true })).toBeVisible();
      assert.equal(hash(await artifacts(state.populated.id)), before);
      await rememberPreview('qa');
      await page.getByRole('radio', { name: 'List the chunks', exact: true }).check();
      await page.getByLabel('Message the Librarian').fill('upload destination project name onboarding');
      const pending = page.waitForResponse(r => r.url().endsWith('/pedr/search') && r.request().method() === 'POST');
      await click(page.getByRole('button', { name: 'List', exact: true }));
      const listing = await (await pending).json(); assert.ok(listing.results.length > 0);
      assert.ok(listing.results.every(row => row.project_id === state.populated.id));
      const list = region('Matching chunks'); await expect(list).toContainText('best match first');
      await list.getByLabel('Collection name', { exact: true }).fill('WALK-3 ranked chunk list');
      await click(list.getByRole('button', { name: /Save .* as a collection/ }));
      const link = list.getByRole('link', { name: 'WALK-3 ranked chunk list', exact: true }); await link.waitFor();
      state.list_collection_id = (await link.getAttribute('href')).split('/').at(-1); await save();
      const saved = await request('/collections/' + state.list_collection_id);
      assert.deepEqual(saved.items.map(i => i.chunk_id).sort(), listing.results.map(r => r.chunk_id).sort());
      await checkpoint(mode, { question, answer: clean(answer), refused: clean(refused), no_artifact_writes_before_explicit_list_save: true,
        ranked_chunk_ids: listing.results.map(r => r.chunk_id), list_collection_id: state.list_collection_id });
    }
    assert.deepEqual(errors, []);
    state.steps[mode] = { completed_at: new Date().toISOString(), serving_commit: commit };
    receipt.browser_stages ||= {};
    receipt.browser_stages[mode] = { ...state.steps[mode], errors, requests: writes };
    await save(); console.log(JSON.stringify({ stage: mode, result: receipt.checks[mode] }));
  } catch (error) {
    receipt.failed_stages ||= [];
    receipt.failed_stages.push({ stage: mode, at: new Date().toISOString(), message: error.message, requests: writes });
    throw error;
  } finally {
    state.storage = await page.evaluate(() => Object.fromEntries(Object.entries(localStorage).filter(([key]) => key.startsWith('tracelab.')))).catch(() => state.storage);
    await save(); await browser.close();
  }
}

if (mode === 'negatives') {
  assert.ok(state.report && state.collection && !state.steps.negatives);
  const beforeUsage = await usage(), checks = [];
  const deniedProject = '0d6c5b1d-72eb-4390-a40b-c48c88cdb302'; // Existing controlled owner fixture.
  for (const [route, method, body, expected] of [
    ['/projects/' + deniedProject, 'GET', undefined, [403]],
    ['/librarian/descriptions/draft', 'POST', { project_id: deniedProject, prompt: 'Describe this fixture.' }, [403]],
    ['/librarian/duplicates/scan', 'POST', { project_id: deniedProject }, [403]],
    ['/librarian/collections/draft', 'POST', { project_id: deniedProject, prompt: 'Group fixture excerpts.' }, [403]],
    ['/librarian/reports/sources?project_id=' + deniedProject, 'GET', undefined, [403]],
    ['/librarian/reports/accept', 'POST', { project_id: state.empty.id, proposal_token: state.models.report.result.proposal_token }, [422]],
    ['/librarian/reports/accept', 'POST', { project_id: state.populated.id, proposal_token: 'not-a-signed-proposal' }, [422]],
  ]) {
    const result = await request(route, method, body, 'member', expected);
    checks.push({ route: route.split('?')[0], status: result.status, detail: typeof result.data.detail === 'string' ? result.data.detail : 'Request rejected' });
  }
  const input = { project_id: state.populated.id, source_token: state.report_sources.source_token,
    chunk_ids: [state.documents.revocable.chunks[0]], reviewed_sources: true, title: 'Rejected cross-project source', prompt: 'Summarise supplied text.', format: 'summary' };
  assert.equal((await request('/librarian/reports/draft', 'POST', input, 'member', [422])).status, 422);
  assert.equal((await request('/librarian/reports/accept', 'POST', { project_id: state.populated.id, proposal_token: state.models.report.result.proposal_token }, 'owner', [422])).status, 422);
  checks.push({ wrong_source_denied: true, wrong_caller_denied: true });

  const source = await request('/librarian/reports/sources?project_id=' + state.populated.id);
  assert.ok(source.members.some(m => m.chunk_id === state.documents.copy.chunks[0]));
  const copyBefore = await request(`/documents/${state.documents.copy.id}/chunks?page_size=100`);
  await request(`/documents/${state.documents.copy.id}?confirm=true`, 'DELETE');
  try {
    const refused = await request('/librarian/reports/draft', 'POST', { ...input, source_token: source.source_token,
      chunk_ids: state.documents.copy.chunks, title: 'Deleted-source rejection' }, 'member', [409]);
    checks.push({ deleted_source_denied: true, status: refused.status, detail: refused.data.detail });
  } finally { await request(`/documents/${state.documents.copy.id}/restore`, 'POST'); }
  assert.equal(hash(await request(`/documents/${state.documents.copy.id}/chunks?page_size=100`)), hash(copyBefore));

  const revocable = await request('/librarian/reports/sources?project_id=' + state.foreign.id);
  assert.ok(revocable.members.length);
  await request(`/admin/spaces/${state.shared.id}/members/${state.user.id}`, 'DELETE', undefined, 'owner');
  state.membership = false; await save();
  assert.equal((await request('/librarian/reports/draft', 'POST', { ...input, project_id: state.foreign.id,
    source_token: revocable.source_token, chunk_ids: state.documents.revocable.chunks }, 'member', [403])).status, 403);
  assert.equal((await request('/documents/' + state.documents.revocable.id, 'GET', undefined, 'member', [403])).status, 403);
  checks.push({ revoked_source_denied: true, owner_independent_membership_revoked: true });

  const old = await request('/projects/' + state.empty.id);
  const manual = 'WALK-3 current human edit must survive a stale description proposal.';
  await request('/projects/' + state.empty.id, 'PUT', { description: manual });
  try {
    const stale = state.models['description-empty'].result;
    assert.equal((await request('/librarian/descriptions/accept', 'POST', { project_id: state.empty.id,
      proposal_token: stale.proposal_token, description: stale.description }, 'member', [409])).status, 409);
    assert.equal((await request('/projects/' + state.empty.id)).description, manual);
  } finally { await request('/projects/' + state.empty.id, 'PUT', { description: old.description }); }
  checks.push({ stale_description_denied: true, current_manual_edit_preserved: true, original_fixture_description_restored: true });

  const report = await request('/reports/' + state.report.report_id);
  await request('/reports/' + state.report.report_id, 'PUT', { title: 'WALK-3 manual report title protected from retry' });
  try {
    const retry = await request('/librarian/reports/accept', 'POST', { project_id: state.populated.id, proposal_token: state.models.report.result.proposal_token });
    assert.equal(retry.title, 'WALK-3 manual report title protected from retry');
    assert.equal((await request('/reports/' + state.report.report_id)).title, retry.title);
  } finally { await request('/reports/' + state.report.report_id, 'PUT', { title: report.title }); }
  assert.equal((await request(`/reports?project_id=${state.populated.id}&page_size=100`)).total, 1);
  assert.equal(await usage(), beforeUsage);
  checks.push({ retry_preserves_manual_report_title: true, single_report: true, no_model_calls: true });
  receipt.checks.negatives = { serving_commit: commit, checks, controlled_mutations: 'Soft-deleted/restored duplicate fixture only; revoked only dedicated fixture Space membership; temporarily edited/restored fixture description and Report title.' };
  state.steps.negatives = { completed_at: new Date().toISOString(), serving_commit: commit };
  await save(); console.log(JSON.stringify(receipt.checks.negatives));
}

if (mode === 'matrix') {
  assert.ok(state.report && state.mission && state.collection);
  const require = createRequire(path.join(root, 'frontend/package.json'));
  const { chromium } = require('playwright'), { expect } = require('@playwright/test');
  const browser = await chromium.launch(), results = [];
  const beforeUsage = await usage();
  const ownerProfile = await request('/auth/me', 'GET', undefined, 'owner');
  try {
    for (const theme of ['light', 'dark']) for (const width of [390, 820, 1440]) {
      let activeKey = state.key;
      const context = await browser.newContext({ viewport: { width, height: 1000 }, colorScheme: theme });
      await context.route(api + '/**', async route => {
        const headers = { ...route.request().headers(), 'x-api-key': activeKey }; delete headers.authorization;
        await route.continue({ headers });
      });
      await context.addInitScript(({ me, storage, theme }) => {
        if (sessionStorage.getItem('walk3-initialized')) return;
        for (const [key, value] of Object.entries(storage)) localStorage.setItem(key, value);
        localStorage.setItem('tracelab.auth.v2', JSON.stringify({ token: 'private-header-principal', ...me }));
        localStorage.setItem(`tracelab.theme.v1:${me.user_id}`, theme);
        sessionStorage.setItem('walk3-initialized', 'yes');
      }, { me: state.me, storage: state.storage, theme });
      const page = await context.newPage(); page.setDefaultTimeout(20000);
      const errors = [], writes = [], failures = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('response', response => { if (response.url().startsWith(api + '/') && response.status() >= 400) failures.push({ path: new URL(response.url()).pathname, status: response.status() }); });
      page.on('request', req => { if (req.url().startsWith(api + '/') && !['GET', 'HEAD', 'OPTIONS'].includes(req.method())) writes.push({ method: req.method(), path: new URL(req.url()).pathname, body: req.postDataJSON() }); });
      const routes = [
        ['librarian', '/librarian?project=' + state.populated.id, 'Review report draft'],
        ['chunks', '/librarian?q=upload%20destination%20project%20name%20onboarding&project=' + state.populated.id, 'Matching chunks'],
        ['collection', '/collections/' + state.collection.collection_id, 'Collection origin'],
        ['report', state.report.href, 'Report source citations'],
        ['mission', '/missions/' + state.mission.id + '?from=librarian', null],
      ];
      for (const [name, route, landmark] of routes) {
        await page.goto(web + route, { waitUntil: 'networkidle' });
        if (landmark) await page.getByRole('region', { name: landmark, exact: true }).waitFor();
        else await expect(page.getByRole('button', { name: 'Submit to DeepSearch', exact: true })).toBeEnabled();
        if (name === 'report') await page.getByText('No accessible evidence is linked to this report.', { exact: true }).waitFor();
        await page.addScriptTag({ path: require.resolve('axe-core/axe.min.js') });
        const audit = await page.evaluate(async () => ({
          overflow: document.documentElement.scrollWidth > innerWidth + 1,
          theme: document.documentElement.dataset.theme,
          violations: (await window.axe.run(document)).violations.filter(v => ['serious', 'critical'].includes(v.impact)).map(v => ({ id: v.id, impact: v.impact, targets: v.nodes.map(n => n.target) })),
        }));
        assert.equal(audit.overflow, false); assert.equal(audit.theme, theme); assert.deepEqual(audit.violations, []);
        await page.evaluate(() => { document.activeElement?.blur(); window.scrollTo(0, 0); });
        const screenshot = `deployed-${name}-${theme}-${width}.png`;
        await page.screenshot({ path: path.join(out, screenshot), fullPage: true, mask: [page.getByText(state.me.email, { exact: true })] });
        results.push({ route, theme, width, ...audit, screenshot });
        if (name === 'report') for (const citation of state.models.report.result.citations) {
          const link = page.getByRole('region', { name: 'Report source citations', exact: true }).getByRole('link', { name: `[${citation.marker}] Open source excerpt`, exact: true });
          await link.focus(); await page.keyboard.press('Enter'); await page.waitForURL(web + citation.href);
          await page.locator(`[data-cited="true"] #chunk-${citation.chunk_id}`).waitFor();
          await expect(page.locator('[data-cited="true"] button[aria-expanded="true"]')).toBeVisible();
          await page.goto(web + route, { waitUntil: 'networkidle' });
        }
      }
      await page.goto(web + '/librarian?project=' + state.populated.id, { waitUntil: 'networkidle' });
      const panel = page.getByRole('region', { name: 'Draft a report', exact: true });
      await expect(panel.getByLabel('Report title', { exact: true })).toHaveValue(state.models.report.result.title);
      await page.getByRole('combobox', { name: 'Project', exact: true }).selectOption(state.empty.id);
      await expect(panel.getByLabel('Report title', { exact: true })).toHaveValue('');
      await expect(page.getByRole('region', { name: 'Review report draft', exact: true })).toHaveCount(0);
      await page.getByRole('combobox', { name: 'Project', exact: true }).selectOption(state.populated.id);
      await expect(panel.getByLabel('Report title', { exact: true })).toHaveValue(state.models.report.result.title);
      await page.reload({ waitUntil: 'networkidle' });
      await expect(panel.getByLabel('Report title', { exact: true })).toHaveValue(state.models.report.result.title);
      await page.bringToFront();
      if (theme === 'light' && width === 390) {
        activeKey = owner.key;
        await page.evaluate(me => localStorage.setItem('tracelab.auth.v2', JSON.stringify({ token: 'private-header-principal', ...me })), ownerProfile);
        await page.reload({ waitUntil: 'networkidle' });
        await expect(panel.getByLabel('Report title', { exact: true })).toHaveValue('');
        await expect(page.getByRole('region', { name: 'Review report draft', exact: true })).toHaveCount(0);
        activeKey = state.key;
        await page.evaluate(me => localStorage.setItem('tracelab.auth.v2', JSON.stringify({ token: 'private-header-principal', ...me })), state.me);
        await page.reload({ waitUntil: 'networkidle' });
        await expect(panel.getByLabel('Report title', { exact: true })).toHaveValue(state.models.report.result.title);
      }
      for (const write of writes) {
        if (write.method === 'POST' && write.path === '/api/v1/pedr/search') { assert.equal(write.body.project_id, state.populated.id); continue; }
        assert.equal(write.method, 'PUT'); assert.equal(write.path, '/api/v1/activity/viewed');
        assert.ok(write.body.items.every(item => (item.type === 'report' && item.id === state.report.report_id) || (item.type === 'mission' && item.id === state.mission.id)));
      }
      assert.deepEqual(errors, []); assert.deepEqual(failures, []);
      receipt.matrix_progress = { layouts_completed: results.length / routes.length, results }; await save();
      await context.close();
    }
  } finally { await browser.close(); }
  assert.equal(await usage(), beforeUsage);
  receipt.checks.matrix = { serving_commit: commit, results, no_automatic_model_calls: true,
    no_artifact_writes: true, activity_updates_only_fixture_report_and_mission: true, account_and_project_state_isolated: true,
    keyboard_report_source_visits: 12, navigation_reload_and_focus_preserved: true };
  state.steps.matrix = { completed_at: new Date().toISOString(), serving_commit: commit }; await save();
  console.log(JSON.stringify({ stage: mode, routes: results.length, layouts: 6, violations: 0 }));
}

if (mode === 'mcp') {
  assert.ok(state.report && state.qa && !state.steps.mcp);
  const require = createRequire(path.join(root, 'packages/tracelab-mcp/package.json'));
  const { Client } = require('@modelcontextprotocol/sdk/client/index.js');
  const { StdioClientTransport } = require('@modelcontextprotocol/sdk/client/stdio.js');
  const temp = await fs.mkdtemp(path.join(os.tmpdir(), 'walk3-published-mcp-'));
  const client = new Client({ name: 'walk3-member-acceptance', version: '1.0.0' });
  const transport = new StdioClientTransport({ command: 'npx', args: ['-y', '@aquex/tracelab-mcp@2.1.0'], cwd: temp,
    env: { PATH: process.env.PATH, HOME: process.env.HOME, TRACELAB_API_URL: api, TRACELAB_API_KEY: state.key, TRACELAB_FRONTEND_URL: web }, stderr: 'pipe' });
  const before = hash(await artifacts(state.populated.id));
  const checks = {};
  async function call(tool, args) {
    const result = await client.callTool({ name: 'tracelab_' + tool, arguments: args });
    assert.ok(!result.isError, `${tool}.${args.action} returned a tool error`);
    return JSON.parse(result.content[0].text);
  }
  try {
    await client.connect(transport);
    assert.equal(client.getServerVersion()?.version, '2.1.0');
    const tools = (await client.listTools()).tools;
    assert.equal(tools.length, 9);
    assert.equal(tools.reduce((n, tool) => n + tool.inputSchema.properties.action.enum.length, 0), 50);
    const report = await call('report', { action: 'get', report_id: state.report.report_id });
    const rest = await request('/reports/' + state.report.report_id);
    assert.equal(hash(report.content), hash(rest.content)); assert.deepEqual(report.citations, rest.citations);
    assert.equal(report.project_id, state.populated.id); assert.equal(report.status, 'draft');
    checks.report = { id: report.id, exact_content: hash(report.content), exact_citations: hash(report.citations) };
    const collection = await call('collection', { action: 'get', collection_id: state.collection.collection_id });
    assert.deepEqual(collection.items.map(i => i.chunk_id), state.collection_input.member_ids);
    checks.collection = { id: collection.id, members: collection.items.map(i => i.chunk_id) };
    const listing = await call('search', { action: 'knowledge', query: 'upload destination project name onboarding', project_id: state.populated.id, limit: 10 });
    assert.ok(listing.results.length);
    for (const [index, row] of listing.results.entries()) {
      assert.equal(row.rank, index + 1);
      assert.equal((await request('/documents/' + row.document_id)).project_id, state.populated.id);
    }
    checks.list = listing;
    // Same question/budget as the UI exercises the shared service and its cache.
    // Preserve the actual cache field; do not claim another provider generation.
    assert.ok(!state.models.mcp_ask, 'Inspect a prior attempt before repeating ask');
    state.models.mcp_ask = { started_at: new Date().toISOString() }; await save();
    const answer = await call('search', { action: 'ask', project_id: state.populated.id, question: state.qa_question, max_tokens: 600 });
    state.models.mcp_ask.result = answer; await save();
    assert.equal(answer.no_evidence, false); assert.ok(answer.citations.length);
    for (const citation of answer.citations) {
      assert.equal(citation.url, web + citation.href);
      assert.equal((await request('/documents/' + citation.document_id)).project_id, state.populated.id);
      assert.ok((await request(`/documents/${citation.document_id}/chunks?page_size=100`)).data.some(c => c.id === citation.chunk_id));
      assert.equal((await fetch(citation.url)).status, 200);
    }
    checks.answer = clean(answer);
    const refused = await call('search', { action: 'ask', project_id: state.populated.id,
      question: 'How should Kubernetes horizontal pod autoscaling be tuned for bursty GPU inference traffic?', max_tokens: 600 });
    assert.equal(refused.no_evidence, true); assert.equal(refused.answer, 'Nothing in this project answers that question.');
    assert.deepEqual(refused.citations, []); checks.refusal = clean(refused);
    const denied = await client.callTool({ name: 'tracelab_search', arguments: { action: 'ask',
      project_id: '0d6c5b1d-72eb-4390-a40b-c48c88cdb302', question: 'What do the interview notes say?' } });
    assert.equal(denied.isError, true); assert.match(denied.content[0].text, /API Error \(403\)/);
    checks.foreign_project_denied = true;
    assert.equal(hash(await artifacts(state.populated.id)), before);
  } finally { await client.close(); await transport.close(); await fs.rm(temp, { recursive: true, force: true }); }
  receipt.checks.mcp = { serving_commit: commit, published_version: '2.1.0', empty_working_directory: true,
    caller_role: 'member', tools: 9, actions: 50, artifacts_unchanged: true, checks };
  state.steps.mcp = { completed_at: new Date().toISOString(), serving_commit: commit };
  await save(); console.log(JSON.stringify(receipt.checks.mcp));
}

if (mode === 'disable') {
  assert.ok(state.steps.mcp && state.steps.matrix && state.steps.negatives);
  if (!state.key_revoked) {
    await request('/auth/api-keys/' + state.key_id, 'DELETE');
    state.key_revoked = true; await save();
  }
  await request('/admin/users/' + state.user.id + '/active', 'PATCH', { is_active: false }, 'owner');
  const account = (await request('/admin/users', 'GET', undefined, 'owner')).find(u => u.id === state.user.id);
  assert.equal(account.is_active, false);
  const keyDenied = await request('/auth/me', 'GET', undefined, 'member', [401, 403]);
  const loginDenied = await request('/auth/login', 'POST', { email: state.account.email, password: state.account.password }, 'login', [401, 403]);
  receipt.checks.cleanup = { at: new Date().toISOString(), caller_id: state.user.id, account_disabled: true,
    temporary_key_revoked: true, key_status: keyDenied.status, login_status: loginDenied.status,
    fixtures_retained: true, shared_fixture_membership_revoked: state.membership === false, existing_guest_untouched: true };
  state.steps.disable = { completed_at: new Date().toISOString() };
  await save(); console.log(JSON.stringify(receipt.checks.cleanup));
}

if (mode === 'read-only') {
  assert.ok(state.steps.disable);
  const detail = await request('/reports/' + state.report.report_id, 'GET', undefined, 'owner');
  const preview = state.models.report.result;
  assert.equal(hash(detail.content), hash(preview.content)); assert.deepEqual(detail.citations, preview.citations);
  assert.equal(detail.generation_provenance.accepted_by, state.user.id);
  const collection = await request('/collections/' + state.collection.collection_id, 'GET', undefined, 'owner');
  assert.deepEqual(collection.items.map(i => i.chunk_id), state.collection_input.member_ids);
  for (const citation of detail.citations) {
    const chunks = await request(`/documents/${citation.document_id}/chunks?page_size=100`, 'GET', undefined, 'owner');
    assert.ok(chunks.data.some(c => c.id === citation.chunk_id));
  }
  const exported = await request(`/reports/${detail.id}/export?format=json`, 'GET', undefined, 'owner');
  assert.equal(hash(exported.content), hash(detail.content)); assert.deepEqual(exported.citations, detail.citations);
  const account = (await request('/admin/users', 'GET', undefined, 'owner')).find(u => u.id === state.user.id);
  assert.equal(account.is_active, false);
  await request('/auth/me', 'GET', undefined, 'member', [401, 403]);
  console.log(JSON.stringify({ verified_at: new Date().toISOString(), serving_commit: commit, read_only: true,
    member_account_disabled: true, revoked_key_denied: true, exact_report_content: hash(detail.content),
    report_id: detail.id, collection_id: collection.id, exact_members: state.collection_input.member_ids,
    citations_and_json_export_verified: true }));
}
