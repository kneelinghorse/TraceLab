// UX-13 production checks for the priority inbox. Credentials stay in Node; the
// browser receives a placeholder token and an injected X-API-Key on production
// API requests only. INBOX_MODE=readonly blocks every write. INBOX_MODE=liveflow
// permits exactly two own-account writes: one PUT /home/missions/{id}/review and
// one PUT /inbox/seen, both recorded with their bodies and responses.
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';

const FRONTEND = process.env.FRONTEND_DIR || '/Users/systemsystems/portfolio/TraceLab/frontend';
const require = createRequire(path.join(FRONTEND, 'package.json'));
const { chromium } = require('playwright');
const base = process.env.UI_BASE || 'https://tracelab.aquex.ai';
const api = 'https://api.tracelab.aquex.ai';
const out = process.env.UI_OUT || path.join(os.tmpdir(), 'tracelab-inbox-production');
const mode = process.env.INBOX_MODE === 'liveflow' ? 'liveflow' : 'readonly';
const timezoneId = 'America/Chicago';
const SECTION_LABEL = { failures: 'Agent failures', completions: 'Mission completions', evidence: 'New evidence' };
const started = new Date().toISOString();
const checks = [];
function check(name, actual, expected) { const passed = JSON.stringify(actual) === JSON.stringify(expected); checks.push({ name, actual, expected, passed }); return passed; }
function ensure(condition, message) { if (!condition) throw new Error(message); }
function quantile(values, q) { const sorted = [...values].sort((a, b) => a - b); return sorted[Math.max(0, Math.ceil(q * sorted.length) - 1)]; }
const accessibleName = element => element.getAttribute('aria-label') ?? element.textContent.trim();
let browser;
let stage = 'preflight';
try {
  const creds = JSON.parse(await fs.readFile(path.join(os.homedir(), '.config/tracelab-mcp/credentials.json'), 'utf8'));
  ensure(creds.apiBaseUrl.replace(/\/$/, '') === api, 'Unexpected credential scope');
  const headers = { 'X-API-Key': creds.key, 'content-type': 'application/json' };
  async function call(route, init = {}) {
    const t = performance.now();
    const response = await fetch(api + '/api/v1' + route, { ...init, headers });
    const ms = performance.now() - t;
    const text = await response.text();
    return { status: response.status, ms, cache: response.headers.get('cache-control'), json: text ? JSON.parse(text) : null };
  }
  async function get(route) { const r = await call(route); ensure(r.status === 200, `API ${route.split('?')[0]} ${r.status}`); return r; }
  await fs.mkdir(out, { recursive: true });
  const me = (await get('/auth/me')).json;

  stage = 'latency';
  const summaryMs = []; const baselineMs = [];
  for (let i = 0; i < 20; i++) {
    const s = await get('/inbox/summary'); summaryMs.push(s.ms); check(`summary cache ${i + 1}`, s.cache, 'private, no-store');
    const b = await get('/auth/me'); baselineMs.push(b.ms);
  }
  const latency = { calls: 20, method: 'nearest-rank', summary_ms: { p50: quantile(summaryMs, 0.5), p95: quantile(summaryMs, 0.95), samples: summaryMs }, auth_me_baseline_ms: { p50: quantile(baselineMs, 0.5), p95: quantile(baselineMs, 0.95), samples: baselineMs } };

  stage = 'totals';
  const summary = (await get('/inbox/summary')).json;
  check('summary fields', Object.keys(summary).sort(), ['default_lookback_seconds', 'generated_at', 'refresh_seconds', 'seen_through', 'unread']);
  check('summary total equals section sum', summary.unread.total, summary.unread.failures + summary.unread.completions + summary.unread.evidence);
  const sections = {};
  for (const section of ['failures', 'completions', 'evidence']) {
    const all = await get(`/inbox?section=${section}&page_size=100`);
    const unread = await get(`/inbox?section=${section}&unread_only=true&page_size=100`);
    check(`${section} cache`, all.cache, 'private, no-store');
    check(`${section} unread total equals summary`, unread.json.total, summary.unread[section]);
    check(`${section} unread items flagged`, unread.json.items.every(item => item.unread), true);
    check(`${section} ordered by occurred_at desc`, all.json.items.every((item, i, arr) => i === 0 || arr[i - 1].occurred_at >= item.occurred_at), true);
    check(`${section} items carry href, occurred_at and unread`, all.json.items.every(item => typeof item.href === 'string' && item.href.startsWith('/') && typeof item.occurred_at === 'string' && typeof item.unread === 'boolean' && (section !== 'completions' || typeof item.reviewed === 'boolean')), true);
    const page2 = await get(`/inbox?section=${section}&page_size=1&page=2`);
    check(`${section} total counted before paging`, page2.json.total, all.json.total);
    sections[section] = { total: all.json.total, unread_total: unread.json.total, first: all.json.items[0] ? { id: all.json.items[0].id, occurred_at: all.json.items[0].occurred_at, unread: all.json.items[0].unread } : null };
  }
  const invalid = await call('/inbox?section=invented');
  check('unknown section is 422', invalid.status, 422);
  const home = (await get('/home')).json;
  const attention = (await get('/home/attention')).json;
  check('evidence groups equal Home evidence_activity total', sections.evidence.total, home.evidence_activity.total);
  check('failures total equals attention validation_failed + blocked', sections.failures.total, attention.by_reason.validation_failed + attention.by_reason.blocked);
  check('completions total equals missions by_status completed', sections.completions.total, home.missions.by_status.completed);

  stage = 'browser';
  browser = await chromium.launch({ headless: true });
  const screenshots = []; const browserResults = []; const writes = [];
  function routeApi(context, allowWrites) {
    return context.route(/https?:\/\/api\.tracelab\.aquex\.ai\/.*/, async route => {
      const request = route.request(); const url = new URL(request.url()); const method = request.method();
      if (method === 'OPTIONS') { await route.continue(); return; }
      const allowed = allowWrites && method === 'PUT' && (url.pathname === '/api/v1/inbox/seen' || /^\/api\/v1\/home\/missions\/[^/]+\/review$/.test(url.pathname));
      if (method !== 'GET' && !allowed) { await route.abort(); return; }
      if (allowed) writes.push({ at: new Date().toISOString(), method, path: url.pathname, body: request.postDataJSON() });
      const h = { ...request.headers(), 'x-api-key': creds.key }; delete h.authorization;
      await route.continue({ headers: h });
    });
  }
  async function open(theme, width, allowWrites = false) {
    const context = await browser.newContext({ timezoneId, viewport: { width, height: 1000 }, colorScheme: theme });
    const transportErrors = []; const pageErrors = [];
    await routeApi(context, allowWrites);
    await context.addInitScript(({ user, theme }) => {
      localStorage.setItem('tracelab.auth.v2', JSON.stringify({ token: 'ui-smoke-placeholder', user_id: user.user_id, email: user.email, display_name: 'UX validation' }));
      localStorage.setItem('tracelab.theme.v1:' + user.user_id, theme);
    }, { user: me, theme });
    const page = await context.newPage();
    page.on('pageerror', () => pageErrors.push('Client-side exception (detail suppressed)'));
    page.on('response', r => { const u = new URL(r.url()); if (u.origin === api && r.status() >= 400) transportErrors.push({ path: u.pathname, status: r.status() }); });
    page.on('requestfailed', r => { const u = new URL(r.url()); if (u.origin === api && r.failure()?.errorText !== 'net::ERR_ABORTED') transportErrors.push({ path: u.pathname, error: r.failure()?.errorText }); });
    await page.goto(base + '/inbox', { waitUntil: 'networkidle', timeout: 60000 });
    return { context, page, transportErrors, pageErrors };
  }
  async function measure(page) {
    await page.addScriptTag({ path: require.resolve('axe-core/axe.min.js') });
    return page.evaluate(async () => {
      const axe = await window.axe.run(document, { resultTypes: ['violations'] });
      return { scrollWidth: document.documentElement.scrollWidth, width: innerWidth, theme: document.documentElement.dataset.theme, mainCount: document.querySelectorAll('main').length,
        violations: axe.violations.filter(v => ['critical', 'serious'].includes(v.impact)).map(v => ({ id: v.id, impact: v.impact, nodes: v.nodes.length })) };
    });
  }
  for (const theme of ['light', 'dark']) for (const width of [1440, 390]) {
    stage = `${theme}-${width}`;
    const { context, page, transportErrors, pageErrors } = await open(theme, width);
    const live = (await get('/inbox/summary')).json;
    const expectedName = live.unread.total > 0 ? `Inbox, ${live.unread.total} unread` : 'Inbox';
    const banner = page.getByRole('banner');
    await banner.getByRole('link', { name: expectedName, exact: true }).waitFor();
    check(`${stage} toolbar badge name`, await banner.getByRole('link', { name: /^Inbox/ }).first().evaluate(accessibleName), expectedName);
    check(`${stage} unread headline`, (await page.getByText(/^[\d,]+ unread$/).first().textContent()).trim(), `${live.unread.total.toLocaleString('en-US')} unread`);
    for (const section of ['failures', 'completions', 'evidence']) {
      const text = await page.getByRole('heading', { level: 2, name: new RegExp(SECTION_LABEL[section]) }).textContent();
      check(`${stage} ${section} heading total`, text.includes(sections[section].total.toLocaleString('en-US')), true);
      if (live.unread[section] > 0) check(`${stage} ${section} heading unread`, text.includes(`${live.unread[section].toLocaleString('en-US')} unread`), true);
    }
    const measured = await measure(page);
    const shot = `${theme}-${width}-inbox.png`; await page.screenshot({ path: path.join(out, shot), fullPage: true }); screenshots.push(shot);
    const toolbarShot = `${theme}-${width}-toolbar-badge.png`; await page.locator('header.app-toolbar').screenshot({ path: path.join(out, toolbarShot) }); screenshots.push(toolbarShot);
    if (width < 900) {
      await page.getByRole('button', { name: 'Open navigation' }).click();
      const drawer = page.getByRole('dialog', { name: 'Navigation' });
      await drawer.getByRole('link', { name: expectedName, exact: true }).waitFor();
      check(`${stage} drawer badge name`, await drawer.getByRole('link', { name: /^Inbox/ }).first().evaluate(accessibleName), expectedName);
      const drawerShot = `${theme}-${width}-drawer-badge.png`; await page.screenshot({ path: path.join(out, drawerShot) }); screenshots.push(drawerShot);
      await page.getByRole('button', { name: 'Close navigation' }).click();
    } else {
      const nav = page.getByRole('navigation', { name: 'Main navigation' });
      check(`${stage} sidebar badge name`, await nav.getByRole('link', { name: /^Inbox/ }).first().evaluate(accessibleName), expectedName);
      const sidebarShot = `${theme}-${width}-sidebar-badge.png`; await page.locator('aside.app-sidebar').screenshot({ path: path.join(out, sidebarShot) }); screenshots.push(sidebarShot);
    }
    browserResults.push({ theme, width, ...measured, pageErrors, transportErrors: [...transportErrors] });
    await context.close();
  }

  let liveFlow = null;
  if (mode === 'liveflow') {
    stage = 'liveflow';
    const before = (await get('/inbox/summary')).json;
    const candidates = (await get('/inbox?section=completions&unread_only=true&page_size=100')).json.items.filter(item => item.reviewed === false);
    const target = candidates.find(item => /^(TL-UX|UX\d+-LIVE)/.test(item.label)) || candidates[0] || null;
    const { context, page, transportErrors, pageErrors } = await open('light', 1440, true);
    const flowChecks = [];
    const flow = (name, actual, expected) => flowChecks.push({ name, actual, expected, passed: JSON.stringify(actual) === JSON.stringify(expected) });
    await page.screenshot({ path: path.join(out, 'liveflow-before.png'), fullPage: true });
    let reviewResponse = null;
    if (target) {
      const item = page.getByRole('listitem').filter({ hasText: target.title }).first();
      const waiter = page.waitForResponse(r => r.request().method() === 'PUT' && r.url().endsWith(`/home/missions/${target.id}/review`));
      await item.getByRole('button', { name: 'Mark reviewed' }).click();
      const response = await waiter;
      reviewResponse = { status: response.status(), at: new Date().toISOString() };
      flow('review response 204', response.status(), 204);
      await item.getByText('Reviewed', { exact: true }).waitFor();
      const after = (await get('/inbox?section=completions&page_size=100')).json.items.find(i => i.id === target.id);
      flow('reviewed completion reads reviewed and not unread', after ? { reviewed: after.reviewed, unread: after.unread } : null, { reviewed: true, unread: false });
      await page.screenshot({ path: path.join(out, 'liveflow-reviewed.png'), fullPage: true });
    }
    const middle = (await get('/inbox/summary')).json;
    if (target) flow('review lowers unread completions by one', middle.unread.completions, before.unread.completions - 1);
    const seenWaiter = page.waitForResponse(r => r.request().method() === 'PUT' && r.url().endsWith('/inbox/seen'));
    await page.getByRole('button', { name: 'Mark all as seen' }).click();
    const seenResponse = await seenWaiter;
    const seenBody = await seenResponse.json();
    flow('mark seen response 200', seenResponse.status(), 200);
    await page.getByRole('banner').getByRole('link', { name: 'Inbox', exact: true }).waitFor();
    const after = (await get('/inbox/summary')).json;
    const sent = writes.find(w => w.path === '/api/v1/inbox/seen');
    flow('client sent a server generated_at string verbatim', typeof sent?.body?.seen_through === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$/.test(sent.body.seen_through), true);
    flow('server stored the sent watermark', seenBody.seen_through, sent?.body?.seen_through);
    flow('summary reports the new watermark', after.seen_through, seenBody.seen_through);
    flow('nothing older than the watermark stays unread', after.unread.total, 0);
    await page.screenshot({ path: path.join(out, 'liveflow-after.png'), fullPage: true });
    liveFlow = { user_id: me.user_id, before: { generated_at: before.generated_at, seen_through: before.seen_through, unread: before.unread }, target: target ? { id: target.id, label: target.label, title: target.title, updated_at: target.updated_at, href: target.href } : null, review_response: reviewResponse, writes, seen_response: seenBody, after: { generated_at: after.generated_at, seen_through: after.seen_through, unread: after.unread }, checks: flowChecks, transportErrors, pageErrors, passed: flowChecks.every(c => c.passed) && !transportErrors.length && !pageErrors.length };
    await context.close();
  }

  const browserFailures = browserResults.filter(r => r.scrollWidth > r.width + 1 || r.violations.length || r.pageErrors.length || r.transportErrors.length || r.mainCount !== 1 || r.theme !== r.theme);
  const results = { started_at: started, finished_at: new Date().toISOString(), base, api, mode, timezoneId, user_id: me.user_id, deployment_ids: (process.env.DEPLOYMENT_IDS || '').split(',').filter(Boolean), source_commit: process.env.SOURCE_COMMIT || null, latency, summary, sections, checks, browser: browserResults, screenshots, live_flow: liveFlow, passed: checks.every(c => c.passed) && !browserFailures.length && (liveFlow ? liveFlow.passed : true) };
  await fs.writeFile(path.join(out, mode === 'liveflow' ? 'live-flow.json' : 'inbox-production.json'), JSON.stringify(results, null, 2));
  console.log(JSON.stringify({ mode, checks: checks.length, failedChecks: checks.filter(c => !c.passed).map(c => c.name), browserFailures: browserFailures.length, liveFlowPassed: liveFlow?.passed ?? null, latency: { summary: latency.summary_ms.p50 + '/' + latency.summary_ms.p95, baseline: latency.auth_me_baseline_ms.p50 + '/' + latency.auth_me_baseline_ms.p95 }, passed: results.passed }));
  if (!results.passed) process.exitCode = 1;
} catch (error) {
  console.error(`Inbox production check failed during ${stage}: ${String(error?.message || error).slice(0, 200)}`);
  process.exitCode = 1;
} finally { await browser?.close(); }
