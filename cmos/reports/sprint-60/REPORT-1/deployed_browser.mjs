// Visit the real report and every exact chunk destination with existing human auth.
// No fake responses and no suppression of product writes; credentials are never recorded.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
const out = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(out, '../../../..');
const require = createRequire(path.join(root, 'frontend/package.json'));
const { chromium } = require('playwright');
const { expect } = require('@playwright/test');
const api = 'https://api.tracelab.aquex.ai';
const web = 'https://tracelab.aquex.ai';
const receipt = JSON.parse(await fs.readFile(path.join(out, 'deployed-mcp.json'), 'utf8'));
const creds = JSON.parse(await fs.readFile(path.join(os.homedir(), '.config/tracelab-mcp/credentials.json'), 'utf8'));
assert.equal(creds.apiBaseUrl.replace(/\/$/, ''), api);
const meResponse = await fetch(api + '/api/v1/auth/me', { headers: { 'X-API-Key': creds.key } });
assert.equal(meResponse.status, 200);
const me = await meResponse.json();
const browser = await chromium.launch();
const checks = [];
try {
  for (const [theme, width] of [['light', 390], ['dark', 1440]]) {
    const context = await browser.newContext({ viewport: { width, height: 1000 }, colorScheme: theme });
    await context.addInitScript(({ user, theme }) => {
      localStorage.setItem('tracelab.auth.v2', JSON.stringify({ token: 'report1-browser-api-key-session', ...user }));
      localStorage.setItem('tracelab.theme.v1:' + user.user_id, theme);
    }, { user: me, theme });
    await context.route(api + '/**', async route => {
      const headers = { ...route.request().headers(), 'x-api-key': creds.key };
      delete headers.authorization;
      await route.continue({ headers });
    });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(receipt.report_url);
    await expect(page.getByRole('heading', { name: 'REPORT-1 acceptance — durable source citations' })).toBeVisible();
    await expect(page.getByText('Review not recorded', { exact: false })).toBeVisible();
    for (const citation of receipt.citations) await expect(page.getByRole('link', { name: `[${citation.marker}] Open source excerpt` })).toHaveAttribute('href', citation.href);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.screenshot({ path: path.join(out, `deployed-report-${theme}-${width}.png`), fullPage: true, mask: [page.getByText(me.email, { exact: true })] });
    for (const citation of receipt.citations) {
      await page.goto(web + citation.href);
      await expect(page.locator('[data-cited="true"]')).toBeVisible();
      await expect(page.locator(`[id="chunk-${citation.chunk_id}"]`)).toBeVisible();
      await expect(page.locator('[data-cited="true"] button[aria-expanded="true"]')).toBeVisible();
      checks.push({ theme, width, marker: citation.marker, exact_chunk_opened: true });
    }
    assert.deepEqual(errors, []);
    await context.close();
  }
} finally { await browser.close(); }
await fs.writeFile(path.join(out, 'deployed-browser.json'), JSON.stringify({ verified_at: new Date().toISOString(), serving_commit: receipt.serving_commit, report_id: receipt.report_id, checks, mocked_responses: false, personal_user_acceptance: false }, null, 2) + '\n');
console.log(JSON.stringify(checks));
