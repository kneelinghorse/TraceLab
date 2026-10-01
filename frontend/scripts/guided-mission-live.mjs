// S62-ENTRY: real local API + invited member accounts, scripted model only.
// Started by tests/e2e/guided_mission_fixture.py against a production UI build.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
const require = createRequire(import.meta.url);
const {chromium} = require('playwright');
const {expect} = require('@playwright/test');
const base = process.env.UI_BASE;
const api = process.env.GUIDED_API;
for (const origin of [base, api]) assert(['localhost', '127.0.0.1'].includes(new URL(origin).hostname));
const users = JSON.parse(await fs.readFile(process.env.GUIDED_AUTH_FILE, 'utf8'));
const out = process.env.UI_OUT || '/tmp/s62-entry-browser';
await fs.mkdir(out, {recursive: true});
const results = [];
const browser = await chromium.launch();
try {
  for (const entry of ['/', '/missions']) for (const theme of ['light', 'dark']) for (const width of [390, 820, 1440]) {
    const user = users[results.length];
    const context = await browser.newContext({viewport: {width, height: 1000}, colorScheme: theme});
    // Set once: reload must restore the actual persisted conversation/draft.
    await context.addInitScript(({user, theme}) => {
      localStorage.setItem('tracelab.auth.v2', JSON.stringify(user));
      localStorage.setItem('tracelab.theme.v1:' + user.user_id, theme);
    }, {user, theme});
    const writes = [], errors = [], failed = [];
    let initialProjectsVerified = false;
    await context.route('**/api/v1/**', async route => {
      const request = route.request(), url = new URL(request.url());
      assert(['localhost', '127.0.0.1', 'api.tracelab.aquex.ai'].includes(url.hostname));
      if (request.method() !== 'GET') writes.push(url.pathname);
      assert(!url.pathname.endsWith('/submit'), 'Creating a draft must never execute research');
      try {
        const response = await route.fetch({url: api + url.pathname + url.search, timeout: 10000});
        if (response.status() >= 400) failed.push({path: url.pathname, status: response.status()});
        if (request.method() === 'GET' && url.pathname.endsWith('/projects') && !writes.some(p => p.endsWith('/projects'))) {
          assert.equal((await response.json()).pagination.total, 0, 'Other members projects must remain inaccessible');
          initialProjectsVerified = true;
        }
        await route.fulfill({response});
      } catch (error) {
        const errorKind = /Timeout|timed out/i.test(String(error)) ? 'timeout' : /disposed|closed|cancel|abort/i.test(String(error)) ? 'cancelled' : 'other';
        failed.push({path: url.pathname, status: 'transport-error', errorKind});
        await route.abort().catch(() => {});
      }
    });
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(base + entry);
    await page.waitForLoadState('networkidle');
    const plan = page.getByRole('link', {name: 'Plan a mission', exact: true});
    await expect(plan).toHaveAttribute('href', '/librarian?intent=mission');
    await plan.focus(); await page.keyboard.press('Enter');
    await expect(page.getByRole('heading', {name: 'Plan a mission', exact: true})).toBeVisible();
    await expect(page.getByRole('button', {name: 'Draft a mission', exact: true})).toBeDisabled();
    await expect.poll(() => initialProjectsVerified).toBe(true);
    assert.equal(writes.filter(p => !p.includes('/activity/viewed')).length, 0);
    await expect(page.getByRole('link', {name: 'Create manually'})).toHaveAttribute('href', '/missions/new');
    await expect(page.getByRole('radiogroup', {name: 'How the Librarian replies'})).toHaveCount(0);
    await page.getByLabel('Message the Librarian').fill('Help me compare onboarding needs for new research teams.');
    await page.keyboard.press('Enter');
    await expect(page.getByRole('log')).toContainText('Who is the audience');
    const transcript = page.getByRole('log', {name: 'Transcript'});
    assert(await transcript.evaluate(el => el.scrollHeight > el.clientHeight), 'The fixture must exercise a genuinely overflowing transcript');
    await page.getByRole('button', {name: 'Start over', exact: true}).focus();
    await page.keyboard.press('Tab');
    await expect(transcript).toBeFocused();
    const scrollBefore = await transcript.evaluate(el => el.scrollTop);
    await page.keyboard.press('ArrowUp');
    await expect.poll(() => transcript.evaluate(el => el.scrollTop)).toBeLessThan(scrollBefore);
    const focusRing = await transcript.evaluate(el => getComputedStyle(el).boxShadow);
    assert.notEqual(focusRing, 'none', 'Keyboard users must see the transcript focus target');
    await expect(page.getByRole('button', {name: 'Draft a mission', exact: true})).toBeDisabled();
    await page.getByLabel('New project', {exact: true}).fill('Guided planning ' + results.length);
    await page.getByRole('button', {name: 'Create', exact: true}).click();
    await expect(page.getByRole('button', {name: 'Draft a mission', exact: true})).toBeEnabled();
    await page.getByRole('button', {name: 'Draft a mission', exact: true}).click();
    const draft = page.getByRole('region', {name: 'Mission draft', exact: true});
    await expect(draft).toBeFocused();
    for (const text of ['Objective', 'Success criteria', 'Constraints', 'Deliverables', '300 and 500 words', 'A short evidence-backed comparison']) await expect(draft).toContainText(text);
    const project = await page.getByRole('combobox', {name: 'Project', exact: true}).inputValue();
    await page.reload();
    await expect(draft).toBeVisible();
    await expect(page.getByRole('combobox', {name: 'Project', exact: true})).toHaveValue(project);
    await expect(page.getByRole('log')).toContainText('Help me compare onboarding');
    await page.addScriptTag({path: require.resolve('axe-core/axe.min.js')});
    const layout = await page.evaluate(async () => ({overflow: document.documentElement.scrollWidth > innerWidth, theme: document.documentElement.dataset.theme, violations: (await window.axe.run(document)).violations.filter(v => ['critical', 'serious'].includes(v.impact)).map(v => ({id: v.id, targets: v.nodes.map(n => n.target)}))}));
    assert.deepEqual(layout, {overflow: false, theme, violations: []});
    const screenshot = `${entry === '/' ? 'home' : 'missions'}-${theme}-${width}.png`;
    await page.screenshot({path: path.join(out, screenshot), fullPage: true});
    // Real duplicate click; the disabled control and server idempotency both apply.
    await page.getByRole('button', {name: 'Create draft mission', exact: true}).dblclick();
    await expect(page).toHaveURL(/\/missions\/[0-9a-f-]+\?from=librarian$/);
    await expect(page.getByRole('button', {name: 'Submit to DeepSearch', exact: true})).toBeVisible();
    assert.equal(writes.filter(p => p.endsWith('/projects')).length, 1);
    assert.equal(writes.filter(p => p.endsWith('/librarian/drafts')).length, 1);
    assert.equal(writes.filter(p => p.endsWith('/librarian/missions')).length, 1);
    await page.waitForLoadState('networkidle', {timeout: 15000});
    await context.unrouteAll({behavior: 'ignoreErrors'});
    assert.deepEqual(errors, []); assert.deepEqual(failed, []);
    results.push({entry, theme, width, role: 'member', initialProjects: 0, destination: 'personal-space', savedStatus: 'draft', executed: false, transcriptKeyboardScroll: true, transcriptFocusVisible: true, ...layout, screenshot});
    await fs.writeFile(path.join(out, 'results.json'), JSON.stringify(results, null, 2));
    console.log(JSON.stringify({entry, theme, width, passed: true}));
    await context.close();
  }
} finally { await browser.close(); }
