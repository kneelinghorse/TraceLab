// Read-only Home smoke. Defaults to production; a local auth file permits an
// isolated fixture API without copying any real credential into browser logs.
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(new URL('../package.json', import.meta.url));
const { chromium } = require('playwright');
const base = process.env.UI_BASE || 'https://tracelab.aquex.ai';
const out = process.env.UI_OUT || path.join(os.tmpdir(), 'tracelab-home-smoke');
let browser;
let stage = 'preflight';
function ensure(condition, message) { if (!condition) throw new Error(message); }
try {
  const local = Boolean(process.env.HOME_SMOKE_AUTH_FILE);
  const credentials = JSON.parse(await fs.readFile(process.env.HOME_SMOKE_AUTH_FILE || path.join(os.homedir(), '.config/tracelab-mcp/credentials.json'), 'utf8'));
  const api = credentials.apiBaseUrl.replace(/\/$/, '');
  ensure(local ? /^http:\/\/127\.0\.0\.1:\d+$/.test(api) : api === 'https://api.tracelab.aquex.ai', 'Unexpected credential scope');
  const headers = local ? { Authorization: `Bearer ${credentials.token}` } : { 'X-API-Key': credentials.key };
  async function get(route) {
    const response = await fetch(api + '/api/v1' + route, { headers });
    ensure(response.ok, 'API preflight failed');
    return response.json();
  }
  const [me, home, missions, projects, reports] = await Promise.all(['/auth/me', '/home', '/missions?page_size=1', '/projects?page_size=1', '/reports?page_size=1'].map(get));
  ensure(home.missions.total === missions.pagination.total, 'Mission total mismatch');
  ensure(home.recent_projects.total === projects.pagination.total, 'Project total mismatch');
  ensure(home.recent_reports.total === reports.total, 'Report total mismatch');
  for (const [status, count] of Object.entries(home.missions.by_status)) {
    const filtered = await get(`/missions?page_size=1&status=${encodeURIComponent(status)}`);
    ensure(count === filtered.pagination.total, 'Mission status total mismatch');
  }
  await fs.mkdir(out, { recursive: true });
  browser = await chromium.launch({ headless: true });
  const results = [];
  for (const theme of ['light', 'dark']) for (const width of [390, 820, 1440]) {
    stage = `${theme}-${width}`;
    const context = await browser.newContext({ viewport: { width, height: 1000 }, colorScheme: theme });
    const transportErrors = [];
    const pageErrors = [];
    await context.route(/https?:\/\/(api\.tracelab\.aquex\.ai|localhost:8000|127\.0\.0\.1:8102)\/.*/, async route => {
      const incoming = new URL(route.request().url());
      try {
        if (route.request().method() === 'OPTIONS') {
          await route.fulfill({ status: 204, headers: { 'access-control-allow-origin': base, 'access-control-allow-headers': 'authorization,content-type,x-api-key', 'access-control-allow-methods': 'GET,OPTIONS' } });
          return;
        }
        ensure(route.request().method() === 'GET', 'Smoke must remain read-only');
        const response = await fetch(api + incoming.pathname + incoming.search, { headers });
        if (!response.ok) transportErrors.push({ path: incoming.pathname, status: response.status });
        await route.fulfill({ status: response.status, body: await response.text(), headers: { 'content-type': response.headers.get('content-type') || 'application/json', 'access-control-allow-origin': base } });
      } catch {
        transportErrors.push({ path: incoming.pathname, error: 'API transport failed' });
        await route.abort().catch(() => {});
      }
    });
    await context.addInitScript(({ me, theme }) => {
      localStorage.setItem('tracelab.auth.v2', JSON.stringify({ token: 'smoke-placeholder', user_id: me.user_id, email: me.email, display_name: 'Home reviewer' }));
      localStorage.setItem('tracelab.theme.v1:' + me.user_id, theme);
    }, { me, theme });
    const page = await context.newPage();
    page.on('pageerror', () => pageErrors.push('Client error; details suppressed'));
    const response = await page.goto(base, { waitUntil: 'networkidle', timeout: 45000 });
    ensure(response.status() === 200 && new URL(page.url()).pathname === '/', 'Home redirected or failed');
    await page.getByRole('heading', { name: 'Home', exact: true }).waitFor();
    await page.getByRole('link', { name: `${home.missions.total.toLocaleString()} missions`, exact: true }).waitFor();
    await page.getByRole('button', { name: /Search research or jump to a section/ }).click();
    ensure(await page.getByRole('dialog', { name: 'Search and navigation' }).isVisible(), 'Search did not open');
    await page.keyboard.press('Escape');
    await page.addScriptTag({ path: require.resolve('axe-core/axe.min.js') });
    const measured = await page.evaluate(async () => {
      const axe = await window.axe.run(document, { resultTypes: ['violations'] });
      return { scrollWidth: document.documentElement.scrollWidth, theme: document.documentElement.dataset.theme, mainCount: document.querySelectorAll('main').length,
        violations: axe.violations.filter(v => ['critical', 'serious'].includes(v.impact)).map(v => ({ id: v.id, impact: v.impact, nodes: v.nodes.map(n => n.target) })) };
    });
    const screenshot = `${theme}-${width}-home.png`;
    await page.screenshot({ path: path.join(out, screenshot), fullPage: true });
    const evidence = home.attention.items.find(m => m.evidence_href);
    let evidenceLinkPassed = null;
    if (evidence) {
      await page.getByRole('link', { name: `Evidence (${evidence.evidence_count.toLocaleString()})`, exact: true }).first().click();
      await page.getByText(`${evidence.evidence_count} evidence entries`, { exact: true }).waitFor();
      evidenceLinkPassed = new URL(page.url()).searchParams.get('mission_id') === evidence.id;
      const evidenceAxe = await page.evaluate(async () => (await window.axe.run(document, { resultTypes: ['violations'] })).violations.filter(v => ['critical', 'serious'].includes(v.impact)).map(v => v.id));
      measured.evidenceViolations = evidenceAxe;
      measured.evidenceScrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      await page.screenshot({ path: path.join(out, `${theme}-${width}-evidence.png`), fullPage: true });
    }
    results.push({ themeRequested: theme, width, ...measured, pageErrors, transportErrors, evidenceLinkPassed, screenshot });
    await fs.writeFile(path.join(out, 'results.json'), JSON.stringify(results, null, 2));
    await context.close();
  }
  const failures = results.filter(r => r.scrollWidth > r.width || r.theme !== r.themeRequested || r.mainCount !== 1 || r.violations.length || r.pageErrors.length || r.transportErrors.length || r.evidenceLinkPassed === false || r.evidenceViolations?.length || r.evidenceScrollWidth > r.width);
  await fs.writeFile(path.join(out, 'summary.json'), JSON.stringify({ checked_at: new Date().toISOString(), base, api, fixture: local, viewport_checks: results.length, failures: failures.length, mission_total: home.missions.total, project_total: home.recent_projects.total, report_total: home.recent_reports.total, all_status_totals_match: true }, null, 2));
  console.log(JSON.stringify({ checks: results.length, failures: failures.length, missionTotal: home.missions.total, fixture: local }));
  if (failures.length) process.exitCode = 1;
} catch {
  console.error(`Home smoke failed during ${stage}. Request details suppressed to protect credentials.`);
  process.exitCode = 1;
} finally { await browser?.close(); }
