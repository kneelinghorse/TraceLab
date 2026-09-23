// QA-2 production check: the retired Search page, the ALIAS-1 trap, and the chunk list's links.
// Read-only. The API key rides only to the TraceLab API and is never printed or stored.
// Run from the repository root after both Railway services serve the merge:
//   EXPECT_SHA=<merge sha> node cmos/reports/sprint-59/QA-2/production_check.mjs
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.resolve(here, '../../../../frontend/package.json'));
const { chromium } = require('playwright');

const base = 'https://tracelab.aquex.ai';
const api = 'https://api.tracelab.aquex.ai';
const project = '0afcc588-e722-45bd-8320-f486601b877c'; // TraceLab Research
const expectSha = process.env.EXPECT_SHA;
if (!expectSha) throw Error('Set EXPECT_SHA to the merge commit');
const out = path.join(here, 'production');
await fs.mkdir(out, { recursive: true });
const checks = [];
const record = (name, passed, detail) => { checks.push({ name, passed, ...detail }); console.log(JSON.stringify({ name, passed })); };

function servedPage(html) {
  const match = html.match(/<script id="__NEXT_DATA__" type="application\/json">(.*?)<\/script>/s);
  return match ? JSON.parse(match[1]) : null;
}

// 1. The deployed frontend is the merge.
const version = await (await fetch(`${base}/api/version`, { cache: 'no-store' })).json();
record('frontend serves the merge commit', version.commit === expectSha, { served: version.commit, expected: expectSha });

// 2. The ALIAS-1 trap: /search must redirect, and nothing under it may answer 200 with a page.
const probes = [
  { path: '/search', status: 308, location: '/librarian' },
  { path: '/search?q=scope%20%26%20provenance', status: 308, location: '/librarian?q=scope%20%26%20provenance' },
  { path: `/search?q=Qdrant&project=${project}`, status: 308, location: `/librarian?q=Qdrant&project=${project}` },
  { path: '/search?saved=00000000-0000-4000-8000-000000000000', status: 308, location: '/librarian?saved=00000000-0000-4000-8000-000000000000' },
  { path: '/search/results?q=scope', status: 404 },
  { path: '/search/anything', status: 404 },
  { path: '/search/index', status: 404 },
  { path: '/features/search', status: 404 },
];
for (const probe of probes) {
  const response = await fetch(base + probe.path, { redirect: 'manual' });
  const header = response.headers.get('location');
  const location = header ? (url => url.origin === base ? url.pathname + url.search : url.href)(new URL(header, base)) : null;
  const html = response.status === 200 || response.status === 404 ? await response.text() : '';
  const page = servedPage(html)?.page ?? null;
  const passed = response.status === probe.status && (probe.location ? location === probe.location : page !== '/search');
  record(`GET ${probe.path}`, passed, { status: response.status, location, servedPage: page, expected: probe });
}

// 3. The deployed build has no /search page at all, and does have the Librarian.
const librarianHtml = await (await fetch(`${base}/librarian?q=Qdrant&project=${project}`)).text();
const data = servedPage(librarianHtml);
record('/librarian?q= is served by the Librarian page', data?.page === '/librarian', { servedPage: data?.page ?? null });
const manifest = await (await fetch(`${base}/_next/static/${data.buildId}/_buildManifest.js`)).text();
const pages = [...manifest.matchAll(/"(\/[^"]*)":\s*\[/g)].map(match => match[1]);
record('build manifest lists /librarian and no /search page', pages.includes('/librarian') && !pages.some(page => page === '/search' || page.startsWith('/search/')), { buildId: data.buildId, searchPages: pages.filter(page => page.includes('search')) });

// 4. Signed in, read-only: /search?q= lands on the list, and a chunk link opens that chunk in its document.
const creds = JSON.parse(await fs.readFile(path.join(os.homedir(), '.config/tracelab-mcp/credentials.json'), 'utf8'));
const me = await (await fetch(`${api}/api/v1/auth/me`, { headers: { 'X-API-Key': creds.key } })).json();
const browser = await chromium.launch({ headless: true });
const blocked = [];
try {
  const context = await browser.newContext({ timezoneId: 'America/Chicago', viewport: { width: 1440, height: 1000 } });
  await context.route(url => url.origin === api, async route => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    if (request.method() === 'OPTIONS') { await route.continue(); return; }
    const read = request.method() === 'GET' || (request.method() === 'POST' && pathname === '/api/v1/pedr/search');
    if (!read) { blocked.push({ method: request.method(), path: pathname }); await route.abort(); return; }
    const headers = { ...request.headers(), 'x-api-key': creds.key };
    delete headers.authorization;
    await route.continue({ headers });
  });
  await context.addInitScript(user => localStorage.setItem('tracelab.auth.v2', JSON.stringify({ token: 'qa2-check-placeholder', user_id: user.user_id, email: user.email, display_name: 'QA-2 check' })), me);
  const page = await context.newPage();
  const searched = page.waitForResponse(response => response.url() === `${api}/api/v1/pedr/search`);
  await page.goto(`${base}/search?q=Qdrant&project=${project}`, { waitUntil: 'domcontentloaded' });
  const body = (await searched).request().postDataJSON();
  const list = page.getByRole('region', { name: 'Matching chunks' });
  await list.getByRole('heading', { name: /chunks? match/ }).waitFor();
  const heading = await list.getByRole('heading').first().textContent();
  const rows = list.locator('ol > li');
  // Document names arrive after the list; the placeholder label is "Document #n".
  await rows.first().getByRole('link').filter({ hasNotText: /^Document #/ }).waitFor();
  const count = await rows.count();
  const named = await rows.getByRole('link').evaluateAll(links => links.filter(link => !/^Document #/.test(link.textContent)).length);
  record('/search?q= lands on the Librarian list of the project', page.url() === `${base}/librarian?q=Qdrant&project=${project}` && body.top_k === 20 && body.project_id === project && count === 20 && named === count, { url: page.url(), request: body, heading, rows: count, rowsWithDocumentName: named });
  await list.screenshot({ path: path.join(out, 'librarian-list-1440.png') });
  const link = rows.first().getByRole('link');
  const href = await link.getAttribute('href');
  const label = await link.textContent();
  const [, documentId, chunkId, index] = href.match(/^\/documents\/([^?]+)\?chunk=([^&]+)&index=(\d+)$/) ?? [];
  await link.click();
  await page.waitForURL(`${base}${href}`);
  const cited = page.locator('[data-cited="true"]');
  await cited.waitFor();
  const citedText = await cited.locator('button').first().textContent();
  await page.screenshot({ path: path.join(out, 'chunk-opened-1440.png'), fullPage: false });
  record('the first chunk link opens that chunk, marked, in its document', Boolean(documentId && chunkId) && citedText.includes(`#${index}`), { label, href, marked: citedText.trim().replace(/\s+/g, ' ') });
} catch (error) {
  record('signed-in list and chunk link', false, { error: error.message.split('\n')[0] });
} finally {
  await browser.close();
}
record('no write left the browser', blocked.length === 0, { blocked });

const passed = checks.every(check => check.passed);
await fs.writeFile(path.join(out, 'check.json'), JSON.stringify({ checkedAt: new Date().toISOString(), base, expectSha, passed, checks }, null, 2) + '\n');
process.exitCode = passed ? 0 : 1;
