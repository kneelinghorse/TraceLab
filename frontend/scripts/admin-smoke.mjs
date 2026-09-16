// Built-app and post-deploy Admin checks. Production credentials stay in Node;
// the browser receives a placeholder token and only read-only API requests run.
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(new URL('../package.json', import.meta.url));
const { chromium } = require('playwright');
const base = process.env.UI_BASE || 'https://tracelab.aquex.ai';
const out = process.env.UI_OUT || path.join(os.tmpdir(), 'tracelab-admin-smoke');
let browser;
let stage = 'preflight';
function ensure(value, message) { if (!value) throw new Error(message); }
try {
  const local = Boolean(process.env.ADMIN_SMOKE_AUTH_FILE);
  const auth = JSON.parse(await fs.readFile(process.env.ADMIN_SMOKE_AUTH_FILE || path.join(os.homedir(), '.config/tracelab-mcp/credentials.json'), 'utf8'));
  const api = auth.apiBaseUrl.replace(/\/$/, '');
  ensure(local ? /^http:\/\/127\.0\.0\.1:\d+$/.test(api) : api === 'https://api.tracelab.aquex.ai', 'Unexpected credential scope');
  const headers = local ? { Authorization: `Bearer ${auth.token}` } : { 'X-API-Key': auth.key };
  async function get(route) { const response = await fetch(api + '/api/v1' + route, { headers }); ensure(response.ok, `API ${route.split('?')[0]} ${response.status}`); return response.json(); }
  const [me, stats, missions] = await Promise.all([get('/auth/me'), get('/admin/stats'), get('/missions?page_size=1')]);
  ensure(['admin','owner'].includes(me.role), 'Admin principal required');
  ensure(stats.missions.total === missions.pagination.total, 'Admin mission count differs from list total');
  ensure(Object.values(stats.missions.by_status).reduce((a,b) => a+b, 0) === stats.missions.total, 'Mission status counts do not sum to total');
  ensure(!('complete' in stats.missions.by_status), 'Legacy complete status appeared');
  for (const [status,count] of Object.entries(stats.missions.by_status)) {
    ensure((await get('/missions?page_size=1&status='+status)).pagination.total === count, 'Status count differs from list');
  }
  await fs.mkdir(out, { recursive: true });
  browser = await chromium.launch({ headless: true });
  const results = [];
  for (const theme of ['light', 'dark']) for (const width of [390, 820, 1440]) {
    const context = await browser.newContext({ viewport: { width, height: 1000 }, colorScheme: theme });
    const transportErrors = []; const pageErrors = [];
    await context.route(/https?:\/\/(api\.tracelab\.aquex\.ai|localhost:8000|127\.0\.0\.1:8103)\/.*/, async route => {
      const incoming = new URL(route.request().url());
      try {
        if (route.request().method() === 'OPTIONS') { await route.fulfill({ status: 204, headers: { 'access-control-allow-origin': base, 'access-control-allow-headers': 'authorization,content-type,x-api-key', 'access-control-allow-methods': 'GET,OPTIONS' } }); return; }
        ensure(route.request().method() === 'GET', 'Smoke must remain read-only');
        const response = await fetch(api + incoming.pathname + incoming.search, { headers });
        if (!response.ok) transportErrors.push({ path: incoming.pathname, status: response.status });
        await route.fulfill({ status: response.status, body: await response.text(), headers: { 'content-type': 'application/json', 'access-control-allow-origin': base } });
      } catch { transportErrors.push({ path: incoming.pathname, error: 'API transport failed' }); await route.abort().catch(() => {}); }
    });
    await context.addInitScript(({ me, theme }) => { localStorage.setItem('tracelab.auth.v2', JSON.stringify({ token: 'smoke-placeholder', user_id: me.user_id, email: me.email, display_name: 'Evidence reviewer' })); localStorage.setItem('tracelab.theme.v1:' + me.user_id, theme); }, { me, theme });
    const page = await context.newPage();
    page.on('pageerror', () => pageErrors.push('Client error; details suppressed'));
    async function measure(name) {
      await page.addScriptTag({ path: require.resolve('axe-core/axe.min.js') });
      const measured = await page.evaluate(async () => ({ scrollWidth: document.documentElement.scrollWidth, theme: document.documentElement.dataset.theme, violations: (await window.axe.run(document, { resultTypes: ['violations'] })).violations.filter(v => ['critical', 'serious'].includes(v.impact)).map(v => ({ id: v.id, targets: v.nodes.map(n => n.target) })) }));
      const screenshot = `${theme}-${width}-${name}.png`;
      await page.screenshot({ path: path.join(out, screenshot), fullPage: true });
      results.push({ name, theme, width, ...measured, transportErrors: [...transportErrors], pageErrors: [...pageErrors], screenshot });
      await fs.writeFile(path.join(out, 'results.json'), JSON.stringify(results, null, 2));
    }
    // The /console aliases were retired in Sprint 54 (ALIAS-1); these pages are reached
    // directly now, and route-migration.spec.ts asserts the old URLs return 404.
    for (const route of ['/admin/observability', '/admin/corrections']) {
      stage = `${theme}-${width}-${route}`;
      await page.goto(base+route, { waitUntil: 'networkidle' });
      if (route === '/admin/observability') {
        ensure(new URL(page.url()).pathname === '/admin/observability', 'Observability did not load');
        await page.getByRole('region', { name: 'Mission statuses' }).waitFor();
        await page.getByText(stats.missions.total.toLocaleString(), { exact: true }).first().waitFor();
        await page.getByRole('button', { name: 'Refresh', exact: true }).click();
        await page.getByRole('button', { name: 'Refresh', exact: true }).waitFor();
        await measure('observability');
      } else {
        ensure(new URL(page.url()).pathname === '/admin/corrections', 'Corrections did not load');
        await page.getByRole('button', { name: 'Telemetry', exact: true }).waitFor();
        await measure('correction-queue');
        await page.getByRole('button', { name: 'Telemetry', exact: true }).click();
        await measure('correction-telemetry');
        await page.getByRole('button', { name: /Dead Letter/ }).click();
        ensure(await page.getByRole('button', { name: 'Clear All', exact: true }).count() === 0, 'Fake dead letter clear action remains');
        await measure('correction-dead-letter');
      }
    }
    await context.close();
  }
  const failures = results.filter(r => r.scrollWidth > r.width || r.theme !== r.screenshot.split('-')[0] || r.violations.length || r.transportErrors.length || r.pageErrors.length);
  const summary = { checked_at: new Date().toISOString(), base, api, fixture: local, checks: results.length, failures: failures.length, mission_total: stats.missions.total, mission_statuses: stats.missions.by_status, projects: stats.projects, documents: stats.documents, chunks: stats.chunks, worker_status: stats.worker?.status, write_requests: 0 };
  await fs.writeFile(path.join(out, 'summary.json'), JSON.stringify(summary, null, 2));
  console.log(JSON.stringify(summary)); if (failures.length) process.exitCode = 1;
} catch (error) { console.error(`Admin smoke failed during ${stage}: ${error instanceof Error ? error.message.split('\n')[0].replace(/https?:\/\/\S+/g, '[URL]') : 'unknown error'}`); process.exitCode = 1; }
finally { await browser?.close(); }
