// QA-1 production acceptance: ask the deployed Librarian real questions about TraceLab
// Research, open every citation link, and refuse the question the project cannot answer.
//
// Run from the repository root after the QA-1 merge has deployed:
//
//     node cmos/reports/sprint-59/QA-1/production_acceptance.mjs
//
// It drives https://tracelab.aquex.ai as Derek through his MCP credential
// (~/.config/tracelab-mcp/credentials.json), sent only to the production API as
// X-API-Key and never printed or written. The only write it allows is POST
// /librarian/turns (the question itself: a model call and a usage row); every other
// non-GET request is refused. First, POST /pedr/search (read-only, no model call)
// records each question's semantic similarities, so the receipt shows the answering
// chunk reaching the floor and the unsupported question staying under it.
// Output: <QA1_OUT, default production>/results.json and *.png, clock America/Chicago.
//
//     node cmos/reports/sprint-59/QA-1/production_acceptance.mjs --recheck <results.json>
//
// re-applies the checks to a recorded run and writes <results>-recheck.json, sending
// nothing: a question already asked would only come back from a cache.
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';

const require = createRequire(new URL('../../../../frontend/package.json', import.meta.url));
const {chromium} = require('playwright');

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(HERE, process.env.QA1_OUT || 'production');
const WEB = 'https://tracelab.aquex.ai';
const API = 'https://api.tracelab.aquex.ai';
const TIMEZONE = 'America/Chicago';
const PROJECT = '0afcc588-e722-45bd-8320-f486601b877c'; // TraceLab Research
const TRACE_SHARE_58 = '04ffc800-85cf-4a49-bcec-a856644796a8';
const FLOOR = 0.4; // settings.rag_context_threshold, unset on Railway

const QUESTIONS = [
  {
    id: 'Q1-miro-highest-access',
    budget: 'Short answer',
    maxTokens: 600,
    question: 'When a Miro board is shared at more than one level at the same time, which access level does a user actually get?',
    answering: {document_id: TRACE_SHARE_58, chunk_indexes: [6]},
    facts: [/(high(er|est)[\s\u2010-\u2015-]*access|more permissive)/i],
    expect: 'answered',
  },
  {
    id: 'Q2-sharing-options-synthesis',
    budget: 'Full synthesis',
    maxTokens: 2000,
    // A first wording ("What sharing model options does the TRACE-SHARE-58 report lay out ...")
    // was dropped before any model call: its answering chunks ranked 6th and 15th, behind
    // the report's reference list, so top_k 5 would not have reached them.
    question: 'Compare the workspace-inheritance and project-level sharing archetypes from the research, and explain which option it recommends for TraceLab and why.',
    // Chunk 9 holds "Option 1 — Hybrid, project-bounded (recommended)"; chunk 10 the runner-up and Option 4.
    answering: {document_id: TRACE_SHARE_58, chunk_indexes: [9, 10]},
    facts: [/hybrid/i, /(option\s*1|project[\s‐-―-]*bounded)/i],
    expect: 'answered',
  },
  {
    // Added for the second run: a fresh question, so the final build answers through the model.
    id: 'Q3-airtable-toggle-default',
    budget: 'Short answer',
    maxTokens: 600,
    question: "Out of the box, does Airtable's workspace setting that restricts adding new collaborators start switched on or off?",
    // Chunk 5 ("defaults to *off*") and chunk 10 ("which defaults to off").
    answering: {document_id: TRACE_SHARE_58, chunk_indexes: [5, 10]},
    facts: [/\boff\b/i],
    expect: 'answered',
  },
  {
    id: 'R1-kubernetes-autoscaling',
    budget: 'Short answer',
    maxTokens: 600,
    // RAG-4's X3 wording: 0.374 at most on production, below the floor.
    question: 'How should Kubernetes horizontal pod autoscaling be tuned for bursty GPU inference traffic?',
    expect: 'refused',
  },
];

// Questions this run expects the semantic cache to answer (no model call): the second
// run asks Q1 and Q2 again so the fixed build renders the first run's exact answers.
const CACHED = new Set((process.env.QA1_CACHED_IDS || '').split(',').filter(Boolean));

// Every check reads the recorded entry, so --recheck can apply them to an earlier run.
function checksFor(question, entry) {
  const segments = entry.response.segments ?? [];
  const chunks = entry.response.chunks ?? [];
  const answerText = segments.map((segment) => segment.text).join('\n\n');
  // The fact must be stated where it is cited, not only in uncited prose.
  const citedText = segments.filter((segment) => segment.citations.length).map((segment) => segment.text).join('\n\n');
  const cited = new Set(segments.flatMap((segment) => segment.citations));
  const checks = {
    status_200: entry.status === 200,
    budget_sent: entry.request.mode === 'answer' && entry.request.max_tokens === question.maxTokens,
    // usage is null exactly when no model was paid: a cached answer, or a refusal before the model.
    served_as_expected: question.expect === 'refused' ? true : (CACHED.has(question.id) ? entry.response.usage === null : entry.response.usage !== null),
    no_page_errors: entry.ui.page_errors.length === 0,
    no_other_writes: entry.ui.blocked_writes.length === 0,
    no_horizontal_overflow: entry.screenshots.every((shot) => !shot.horizontal_overflow),
    no_raw_citation_labels: !/\[Document:/i.test(answerText),
  };
  if (question.expect === 'answered') {
    const answeringIds = new Set(chunks.filter((chunk) => chunk.document_id === question.answering.document_id && question.answering.chunk_indexes.includes(chunk.chunk_index)).map((chunk) => chunk.id));
    Object.assign(checks, {
      not_refused: entry.response.no_evidence === false,
      cited_passage_states_the_fact: question.facts.every((pattern) => pattern.test(citedText)),
      cites_an_answering_chunk: [...answeringIds].some((id) => cited.has(id)),
      every_citation_listed: [...cited].every((id) => chunks.some((chunk) => chunk.id === id)),
      ui_links_match_response: JSON.stringify(entry.ui.citation_links.map((link) => link.href).sort()) === JSON.stringify(segments.flatMap((segment) => segment.citations.map((id) => chunks.find((chunk) => chunk.id === id)?.href)).sort()),
      every_link_opens_its_chunk: entry.links.length > 0 && entry.links.every((link) => link.api_chunk_at_index && link.chunks_tab_selected && link.marked_cited && link.expanded_text_is_the_chunk && link.snippet_in_expanded_text),
      answering_chunk_at_the_floor: (entry.similarity.answering ?? []).some((item) => typeof item.found === 'object' && item.found.semantic_cosine >= FLOOR),
    });
  } else {
    Object.assign(checks, {
      refused: entry.response.no_evidence === true,
      refusal_text: answerText === 'Nothing in this project answers that question.',
      asserts_nothing: cited.size === 0 && chunks.length === 0 && entry.ui.corpus_claims === 0 && entry.ui.citation_links.length === 0,
      ui_shows_refusal_note: entry.ui.refusal_note === 'Nothing in this project answers that question.',
      below_the_floor: entry.similarity.reaches_floor === false,
      no_model_call: entry.response.usage === null,
    });
  }
  return checks;
}

if (process.argv[2] === '--recheck') {
  const file = path.resolve(process.argv[3]);
  const recorded = JSON.parse(await fs.readFile(file, 'utf8'));
  for (const entry of recorded.questions) {
    entry.checks_as_run = entry.checks;
    entry.checks = checksFor(QUESTIONS.find((question) => question.id === entry.id), entry);
    entry.met = Object.values(entry.checks).every(Boolean);
    console.log(entry.id, entry.met ? 'MET' : 'NOT MET', JSON.stringify(entry.checks));
  }
  recorded.all_met = recorded.questions.every((entry) => entry.met);
  recorded.rechecked_at_utc = new Date().toISOString();
  await fs.writeFile(file.replace(/\.json$/, '-recheck.json'), JSON.stringify(recorded, null, 2) + '\n');
  console.log('all_met:', recorded.all_met);
  process.exit(0);
}

const creds = JSON.parse(await fs.readFile(path.join(os.homedir(), '.config/tracelab-mcp/credentials.json'), 'utf8'));
if (creds.apiBaseUrl.replace(/\/$/, '') !== API) throw Error('Unexpected credential scope');

async function api(method, route, body) {
  const response = await fetch(API + '/api/v1' + route, {
    method,
    headers: {'X-API-Key': creds.key, 'Content-Type': 'application/json'},
    ...(body ? {body: JSON.stringify(body)} : {}),
  });
  const text = await response.text();
  let json = null;
  try { json = JSON.parse(text); } catch { json = text.slice(0, 500); }
  return {status: response.status, json};
}

async function documentChunks(documentId) {
  const found = {};
  for (let page = 1; ; page += 1) {
    const {status, json} = await api('GET', `/documents/${documentId}/chunks?page=${page}&page_size=100`);
    if (status !== 200) return found;
    for (const chunk of json.data) found[chunk.id] = {chunk_index: chunk.chunk_index, content: chunk.content};
    if (page >= json.pagination.pages) return found;
  }
}

async function similarity(question) {
  const {status, json} = await api('POST', '/pedr/search', {query: question.question, project_id: PROJECT, top_k: 30, enable_graph: false});
  if (status !== 200) return {status, error: json};
  const rows = json.results.map((result, index) => ({
    rank: index + 1,
    document_id: result.document_id,
    chunk_index: result.chunk_index,
    semantic_cosine: result.layer_scores?.semantic ?? null,
  }));
  const cosines = rows.map((row) => row.semantic_cosine).filter((value) => value != null);
  return {
    status,
    cosine_max: Math.max(...cosines),
    cosine_top5: cosines.slice(0, 5),
    reaches_floor: cosines.some((value) => value >= FLOOR),
    answering: question.answering?.chunk_indexes.map((index) => ({
      chunk_index: index,
      found: rows.find((row) => row.document_id === question.answering.document_id && row.chunk_index === index) ?? 'not in top 30',
    })),
  };
}

const normalize = (text) => (text ?? '').replace(/\s+/g, ' ').trim();

await fs.mkdir(OUT, {recursive: true});
const me = (await api('GET', '/auth/me')).json;
const health = (await api('GET', '/health')).json;
const results = {
  web: WEB,
  timezone: TIMEZONE,
  started_at_utc: new Date().toISOString(),
  health_commit: health?.commit ?? health?.version ?? health,
  role: me.role,
  project: PROJECT,
  floor: FLOOR,
  questions: [],
};

const browser = await chromium.launch({headless: true});
try {
  for (const question of QUESTIONS) {
    const entry = {id: question.id, budget: question.budget, question: question.question, expect: question.expect};
    entry.similarity = await similarity(question);

    const context = await browser.newContext({timezoneId: TIMEZONE, viewport: {width: 1440, height: 1000}, colorScheme: 'light'});
    const writes = [];
    await context.route(/https:\/\/api\.tracelab\.aquex\.ai\/.*/, async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const method = request.method();
      if (method === 'OPTIONS') { await route.continue(); return; }
      if (method === 'PUT' && url.pathname === '/api/v1/activity/viewed') {
        await route.fulfill({status: 200, json: {viewed: 0, new_total: 0}, headers: {'access-control-allow-origin': WEB, 'access-control-allow-credentials': 'true'}});
        return;
      }
      const allowed = method === 'GET' || (method === 'POST' && ['/api/v1/facets', '/api/v1/librarian/turns'].includes(url.pathname));
      if (!allowed) { writes.push({method, path: url.pathname}); await route.abort(); return; }
      const headers = {...request.headers(), 'x-api-key': creds.key};
      delete headers.authorization;
      await route.continue({headers});
    });
    await context.addInitScript((user) => {
      localStorage.setItem('tracelab.auth.v2', JSON.stringify({token: 'qa-1-acceptance-placeholder', user_id: user.user_id, email: user.email, display_name: 'QA-1 acceptance'}));
      localStorage.setItem('tracelab.librarian.orientation.v1:' + user.user_id, 'dismissed');
    }, me);
    const page = await context.newPage();
    const pageErrors = [];
    page.on('pageerror', () => pageErrors.push('Client-side exception (detail suppressed)'));

    await page.goto(WEB + '/librarian', {waitUntil: 'networkidle', timeout: 60000});
    await page.locator(`#librarian-project option[value="${PROJECT}"]`).waitFor({state: 'attached', timeout: 30000});
    await page.getByRole('combobox', {name: 'Project', exact: true}).selectOption(PROJECT);
    await page.getByRole('radio', {name: 'Ask the documents'}).check();
    await page.getByRole('radio', {name: question.budget}).check();
    await page.getByLabel('Message the Librarian').fill(question.question);
    const turn = page.waitForResponse((response) => response.url() === API + '/api/v1/librarian/turns' && response.request().method() === 'POST', {timeout: 180000});
    entry.sent_at_utc = new Date().toISOString();
    await page.getByRole('button', {name: 'Ask', exact: true}).click();
    const response = await turn;
    entry.request = JSON.parse(response.request().postData());
    entry.status = response.status();
    entry.response = await response.json();
    await page.getByRole('article', {name: 'Librarian'}).first().waitFor({timeout: 30000});
    await page.waitForTimeout(500);

    const log = page.getByRole('log');
    entry.ui = {
      corpus_claims: await log.locator("[data-kind='corpus_claim']").count(),
      refusal_note: (await log.locator("[data-kind='refusal']").count()) ? normalize(await log.locator("[data-kind='refusal']").innerText()) : null,
      citation_links: await log.locator("[aria-label='Citations'] a").evaluateAll((links) => links.map((link) => ({text: link.textContent.trim(), href: link.getAttribute('href')}))),
      page_errors: pageErrors,
      blocked_writes: writes,
    };

    // The answer on screen, in both themes and at both widths (the conversation persists per user).
    entry.screenshots = [];
    for (const theme of ['light', 'dark']) {
      for (const width of [1440, 390]) {
        await page.evaluate(({user, theme}) => localStorage.setItem('tracelab.theme.v1:' + user, theme), {user: me.user_id, theme});
        await page.emulateMedia({colorScheme: theme});
        await page.setViewportSize({width, height: 1000});
        await page.reload({waitUntil: 'networkidle'});
        await page.getByRole('article', {name: 'Librarian'}).first().waitFor({timeout: 30000});
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
        const file = `${question.id}-${theme}-${width}.png`;
        await page.screenshot({path: path.join(OUT, file), fullPage: true});
        entry.screenshots.push({file, theme, width, horizontal_overflow: overflow});
      }
    }

    // Every citation: resolves through the API, and its link opens the cited chunk.
    const chunks = entry.response.chunks ?? [];
    entry.links = [];
    for (const chunk of chunks) {
      const inDocument = await documentChunks(chunk.document_id);
      const linkPage = await context.newPage();
      await linkPage.setViewportSize({width: 1440, height: 1000});
      await linkPage.goto(WEB + chunk.href, {waitUntil: 'networkidle', timeout: 60000});
      const cited = linkPage.locator('[data-cited="true"]');
      await cited.waitFor({timeout: 30000}).catch(() => {});
      const expanded = linkPage.locator(`[id="chunk-${chunk.id}"]`);
      const expandedText = (await expanded.count()) ? normalize(await expanded.innerText()) : '';
      const file = `${question.id}-link-${chunk.chunk_index}.png`;
      await linkPage.screenshot({path: path.join(OUT, file), fullPage: false});
      entry.links.push({
        href: chunk.href,
        chunk_id: chunk.id,
        document_id: chunk.document_id,
        document_name: chunk.document_name,
        chunk_index: chunk.chunk_index,
        api_chunk_at_index: inDocument[chunk.id]?.chunk_index === chunk.chunk_index,
        chunks_tab_selected: (await linkPage.getByRole('tab', {name: 'Chunks'}).getAttribute('aria-selected')) === 'true',
        marked_cited: await cited.count() === 1,
        cited_label: (await cited.count()) ? normalize(await cited.locator('button').first().innerText()) : null,
        expanded_text_is_the_chunk: expandedText.includes(normalize(inDocument[chunk.id]?.content).slice(0, 200)),
        snippet_in_expanded_text: expandedText.includes(normalize(chunk.snippet).slice(0, 120)),
        screenshot: file,
      });
      await linkPage.close();
    }
    await context.close();

    entry.checks = checksFor(question, entry);
    entry.met = Object.values(entry.checks).every(Boolean);
    results.questions.push(entry);
    console.log(question.id, entry.met ? 'MET' : 'NOT MET', JSON.stringify(entry.checks));
  }
} finally {
  await browser.close();
}
results.finished_at_utc = new Date().toISOString();
results.all_met = results.questions.every((entry) => entry.met);
await fs.writeFile(path.join(OUT, 'results.json'), JSON.stringify(results, null, 2) + '\n');
console.log('all_met:', results.all_met);
process.exit(results.all_met ? 0 : 1);
