// Read-only browser follow-up: prior acceptance/restore receipt and exact source links.
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
const writes = [];
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
    page.on('request', request => {
      if (request.url().startsWith(api + '/') && !['GET', 'HEAD', 'OPTIONS'].includes(request.method())) {
        writes.push({ method: request.method(), path: new URL(request.url()).pathname });
      }
    });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    for (const project of receipt.receipts) {
      await page.goto(web + '/librarian?project=' + project.project_id);
      await page.getByText('Previous description restored.', { exact: true }).waitFor();
      await page.getByText('Last accepted draft and sources', { exact: true }).click();
      assert.equal(await page.getByRole('button', { name: 'Restore previous description' }).count(), 0);
      for (const citation of project.source_links) {
        const link = page.locator(`a[href="${citation.href}"]`);
        await link.focus();
        await page.keyboard.press('Enter');
        await page.waitForURL(web + citation.href);
        await page.locator(`[id="chunk-${citation.chunk_id}"]`).waitFor();
        await page.goto(web + '/librarian?project=' + project.project_id);
        await page.getByText('Last accepted draft and sources', { exact: true }).click();
      }
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
      assert.equal(overflow, false);
      await page.screenshot({ path: path.join(out, `deployed-${project.basis}-${theme}-${width}.png`), fullPage: true, mask: [page.getByText(me.email, { exact: true })] });
      results.push({ theme, width, project_id: project.project_id, prior_acceptance_visible: true, guarded_restore_complete: true, source_links_opened: project.source_links.length, overflow });
    }
    assert.deepEqual(errors, []);
    await context.close();
  }
} finally { await browser.close(); }
await fs.writeFile(path.join(out, 'deployed-browser.json'), JSON.stringify({ verified_at: new Date().toISOString(), serving_commit: receipt.serving_commit, results, page_errors: 0, observed_write_requests: writes, mocked_responses: false, personal_user_acceptance: false }, null, 2) + '\n');
console.log(JSON.stringify({ scenarios: results.length, source_links_opened: results.reduce((n, r) => n + r.source_links_opened, 0), page_errors: 0 }));
