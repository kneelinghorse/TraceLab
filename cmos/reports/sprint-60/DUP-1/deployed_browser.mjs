// Real deployed responses; comparisons and local review must not change research.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
const out = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.resolve(out, '../../../../frontend/package.json'));
const { chromium } = require('@playwright/test');
const credentials = JSON.parse(await fs.readFile(path.join(os.homedir(), '.config/tracelab-mcp/credentials.json'), 'utf8'));
const api = 'https://api.tracelab.aquex.ai';
const web = 'https://tracelab.aquex.ai';
assert.equal(credentials.apiBaseUrl.replace(/\/$/, ''), api);
const receipt = JSON.parse(await fs.readFile(path.join(out, 'deployed-acceptance.json'), 'utf8'));
const me = await (await fetch(api + '/api/v1/auth/me', { headers: { 'X-API-Key': credentials.key } })).json();
const browser = await chromium.launch();
const results = [];
try {
  for (const [theme, width] of [['light', 390], ['dark', 1440]]) {
    const context = await browser.newContext({ viewport: { width, height: 1000 }, colorScheme: theme });
    await context.route(api + '/**', async route => {
      const headers = { ...route.request().headers(), 'x-api-key': credentials.key };
      delete headers.authorization;
      await route.continue({ headers });
    });
    await context.addInitScript(({ user, theme }) => {
      localStorage.setItem('tracelab.auth.v2', JSON.stringify({ token: 'browser-auth-via-header', ...user }));
      localStorage.setItem(`tracelab.theme.v1:${user.user_id}`, theme);
    }, { user: me, theme });
    const page = await context.newPage();
    let scans = 0;
    let comparisons = 0;
    const writes = [];
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {
      if (!request.url().startsWith(api + '/') || ['GET', 'HEAD', 'OPTIONS'].includes(request.method())) return;
      const pathname = new URL(request.url()).pathname;
      if (pathname.endsWith('/duplicates/scan')) scans++;
      else if (pathname.endsWith('/duplicates/compare')) comparisons++;
      else writes.push({ method: request.method(), path: pathname });
    });
    const librarian = web + '/librarian?project=' + receipt.project_id;
    await page.goto(librarian);
    await page.getByRole('button', { name: 'Find possible duplicates' }).waitFor();
    assert.equal(scans, 0);
    await page.getByRole('button', { name: 'Find possible duplicates' }).click();
    await page.getByRole('region', { name: 'Duplicate results' }).waitFor();
    await page.reload();
    await page.getByText('Exact normalized text', { exact: true }).waitFor();
    assert.equal(scans, 1);
    let sourceLinks = 0;
    for (const pair of receipt.candidates) {
      for (const source of pair.documents) {
        const card = page.locator('article').filter({ hasText: pair.documents[0].name }).filter({ hasText: pair.documents[1].name });
        await card.getByRole('button', { name: 'Compare sources' }).focus();
        await page.keyboard.press('Enter');
        const comparison = page.getByRole('region', { name: 'Compare documents', exact: true });
        await comparison.waitFor();
        const link = comparison.locator(`a[href="${source.href}"]`);
        await link.focus(); await page.keyboard.press('Enter');
        await page.waitForURL(web + source.href);
        await page.getByRole('heading', { level: 1, name: source.name, exact: true }).waitFor();
        sourceLinks++;
        await page.goto(librarian);
        await page.getByText('Exact normalized text', { exact: true }).waitFor();
      }
    }
    const firstCard = page.locator('article').first();
    await firstCard.getByRole('button', { name: 'Compare sources' }).click();
    await page.getByRole('region', { name: 'Compare documents', exact: true }).waitFor();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: path.join(out, `deployed-${theme}-${width}.png`), fullPage: true, mask: [page.getByText(me.email, { exact: true })] });
    await page.getByRole('button', { name: 'Close comparison' }).click();
    await firstCard.getByRole('button', { name: 'Keep both', exact: true }).click();
    await page.locator('article').first().getByRole('button', { name: 'Dismiss pair' }).click();
    await page.reload();
    await page.getByText('2 pairs reviewed in your browser. No documents were changed.', { exact: true }).waitFor();
    assert.equal(scans, 1);
    assert.deepEqual(writes, []); assert.deepEqual(errors, []);
    results.push({ theme, width, scans, comparisons, source_links_opened: sourceLinks, keep_both_and_dismiss_persisted: true, corpus_write_requests: writes, page_errors: errors, overflow: false });
    await context.close();
  }
} finally { await browser.close(); }
await fs.writeFile(path.join(out, 'deployed-browser.json'), JSON.stringify({ verified_at: new Date().toISOString(), serving_commit: receipt.serving_commit, project_id: receipt.project_id, results, mocked_responses: false, personal_user_acceptance: false }, null, 2) + '\n');
console.log(JSON.stringify({ scenarios: results.length, source_links_opened: results.reduce((n, r) => n + r.source_links_opened, 0), corpus_writes: 0 }));
