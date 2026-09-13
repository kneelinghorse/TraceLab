// Built-app and post-deploy Evidence checks. Production credentials stay in Node;
// the browser receives a placeholder token and only read-only API requests run.
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(new URL('../package.json', import.meta.url));
const { chromium } = require('playwright');
const base = process.env.UI_BASE || 'https://tracelab.aquex.ai';
const out = process.env.UI_OUT || path.join(os.tmpdir(), 'tracelab-evidence-smoke');
let browser;
let stage = 'preflight';
function ensure(value, message) { if (!value) throw new Error(message); }
try {
  const local = Boolean(process.env.EVIDENCE_SMOKE_AUTH_FILE);
  const auth = JSON.parse(await fs.readFile(process.env.EVIDENCE_SMOKE_AUTH_FILE || path.join(os.homedir(), '.config/tracelab-mcp/credentials.json'), 'utf8'));
  const api = auth.apiBaseUrl.replace(/\/$/, '');
  ensure(local ? /^http:\/\/127\.0\.0\.1:\d+$/.test(api) : api === 'https://api.tracelab.aquex.ai', 'Unexpected credential scope');
  const headers = local ? { Authorization: `Bearer ${auth.token}` } : { 'X-API-Key': auth.key };
  async function get(route) { const response = await fetch(api + '/api/v1' + route, { headers }); ensure(response.ok, `API ${route.split('?')[0]} ${response.status}`); return response.json(); }
  const ids = auth.ids || { project: '0afcc588-e722-45bd-8320-f486601b877c', mission: '7b847edd-5433-4237-a899-57b47e6edf0a', report: 'f4d46a82-2e25-4f5c-a2f8-68d565ad51be', document: 'e51e0fe0-9a08-4ed0-83ad-041a7396472d', session: 'deepsearch:64ff9dac-d043-4f74-8645-612cecc58d79' };
  const scope = new URLSearchParams({ project_id: ids.project, session_key: ids.session });
  const [me, ledger, supporting, background, reportEntries, documentEntries] = await Promise.all([
    get('/auth/me'), get('/evidence?' + scope), get('/evidence?' + scope + '&disposition=supporting'), get('/evidence?' + scope + '&disposition=background'),
    get(`/evidence?project_id=${ids.project}&report_id=${ids.report}`), get(`/evidence?project_id=${ids.project}&document_id=${ids.document}`),
  ]);
  ensure(ledger.entry_total > 0 && reportEntries.entry_total > 0 && documentEntries.entry_total > 0, 'Missing output evidence');
  const first = ledger.entries[0];
  const detail = await get('/evidence/' + first.id);
  ensure(detail.entry.id === first.id, 'Wrong entry detail');
  const searched = await get('/evidence/search?' + scope + '&q=' + encodeURIComponent(first.claim.split(/\s+/).find(word => word.length > 4) || 'research'));
  ensure(searched.total > 0, 'Expected search hit missing');
  if (local) ensure(ledger.entry_total === 50 && supporting.entry_total === 44 && background.entry_total === 6, 'Fixture counts changed');
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
    stage = `${theme}-${width}-list`;
    await page.goto(base + '/evidence?' + scope, { waitUntil: 'networkidle' });
    await page.getByText(`${ledger.entry_total} evidence entries`, { exact: true }).waitFor();
    await page.getByLabel('Disposition', { exact: true }).selectOption('supporting');
    await page.getByRole('button', { name: 'Apply filters' }).click();
    await page.getByText(`${supporting.entry_total} evidence entries`, { exact: true }).waitFor();
    await page.getByLabel('Disposition', { exact: true }).selectOption('background');
    await page.getByRole('button', { name: 'Apply filters' }).click();
    await page.getByText(`${background.entry_total} evidence entries`, { exact: true }).waitFor();
    await measure('list');
    await page.getByRole('button', { name: 'Promote session' }).click();
    await page.getByRole('dialog', { name: 'Promote evidence session' }).waitFor();
    await measure('promotion-dialog');
    await page.keyboard.press('Escape');
    ensure(await page.getByRole('button', { name: 'Promote session' }).evaluate(e => e === document.activeElement), 'Dialog did not restore focus');
    stage = `${theme}-${width}-detail`;
    await page.goto(base + '/evidence/' + first.id, { waitUntil: 'networkidle' });
    await page.getByRole('heading', { level: 1, name: first.claim, exact: true }).waitFor();
    await measure('detail');
    for (const kind of ['report', 'document', 'mission']) {
      stage = `${theme}-${width}-${kind}`;
      await page.goto(`${base}/${kind}s/${ids[kind]}`, { waitUntil: 'networkidle' });
      if (kind === 'mission') await page.getByRole('tab', { name: 'Evidence', exact: true }).click();
      const panel = page.getByRole('region', { name: 'Related evidence' });
      const browse = panel.getByRole('link', { name: /Browse evidence/ });
      await browse.waitFor();
      await measure(kind);
      await browse.click();
      await page.getByRole('heading', { level: 1, name: 'Evidence', exact: true }).waitFor();
      ensure(new URL(page.url()).searchParams.get(kind + '_id') === ids[kind], 'Output link lost scope');
    }
    await context.close();
  }
  const failures = results.filter(r => r.scrollWidth > r.width || r.theme !== r.screenshot.split('-')[0] || r.violations.length || r.transportErrors.length || r.pageErrors.length);
  const summary = { checked_at: new Date().toISOString(), base, api, fixture: local, checks: results.length, failures: failures.length, ledger_total: ledger.entry_total, supporting: supporting.entry_total, background: background.entry_total, search_total: searched.total, report_evidence: reportEntries.entry_total, document_evidence: documentEntries.entry_total, ids };
  await fs.writeFile(path.join(out, 'summary.json'), JSON.stringify(summary, null, 2));
  console.log(JSON.stringify(summary)); if (failures.length) process.exitCode = 1;
} catch (error) { console.error(`Evidence smoke failed during ${stage}: ${error instanceof Error ? error.message.split('\n')[0].replace(/https?:\/\/\S+/g, '[URL]') : 'unknown error'}`); process.exitCode = 1; }
finally { await browser?.close(); }
