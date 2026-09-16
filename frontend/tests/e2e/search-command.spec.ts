import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

test.use({ timezoneId: "America/Chicago" });

const projectId = "00000000-0000-4000-8000-000000000001";
const documentId = "00000000-0000-4000-8000-000000000002";
const chunkIds = ["00000000-0000-4000-8000-000000000003", "00000000-0000-4000-8000-000000000004"];
const kinds = ["project", "document", "mission", "report", "collection", "evidence"];
const entityPath = (kind: string) => `/${kind === "evidence" ? "evidence" : `${kind}s`}/${projectId}`;
const results = chunkIds.map((chunk_id, index) => ({ chunk_id, document_id: documentId, project_id: projectId, content: `Authorized result ${index + 1}`, source_type: "transcript", rrf_score: 0.1 - index * 0.01, score: 0.1, chunk_index: index }));
const rag = { answer: "An answer supported by the authorized results. https://example.test/evidence/" + "provenance".repeat(15), citations: [{ chunk_id: chunkIds[0], document_id: documentId, snippet: "Authorized support for research workflows and preservation of provenance. ".repeat(5), score: 0.1 }], sources: [], latency_ms: 12, quality: { composite_score: 0.9, threshold: 0.8 }, routing: { selected_model: "test-model" }, cache: { hit: false } };
const entry = { id: projectId, name: "Saved scope", query_text: "saved scope", filters: { project_id: projectId, source_type: "transcript" }, top_k: 7, search_mode: "semantic", owner: "member", use_count: 0, created_at: "2026-09-13T00:00:00Z", updated_at: "2026-09-13T00:00:00Z" };

async function fixture(page: Page) {
  const requests: { pathname: string; body: Record<string, unknown> | null }[] = [];
  let saved = [entry];
  await page.addInitScript(() => localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "search-test", user_id: "member", email: "member@example.test", display_name: "Member" })));
  await page.route("**/api/v1/**", async route => {
    const url = new URL(route.request().url());
    const pathname = url.pathname;
    const body = route.request().postDataJSON() as Record<string, unknown> | null;
    requests.push({ pathname, body });
    let response: unknown;
    if (pathname.endsWith("/auth/me")) response = { user_id: "member", email: "member@example.test", display_name: "Member", role: "member" };
    else if (pathname.endsWith("/projects")) response = { data: [{ id: projectId, name: "Accessible project" }], pagination: { page: 1, page_size: 100, total: 1, pages: 1 } };
    // The first document page intentionally lacks the returned document and its source type.
    else if (pathname.endsWith("/documents")) response = { data: [], pagination: { page: 1, page_size: 100, total: 117, pages: 2 } };
    else if (pathname.endsWith("/facets")) response = { source_types: [{ value: "transcript", count: 117 }], projects: [], document_types: [], tags: [], date_range: { min: null, max: null } };
    else if (pathname.endsWith("/search/history")) response = { entries: [{ ...entry, query_text: "Recent scope" }] };
    else if (pathname.endsWith("/activity/summary")) response = { generated_at: "2026-09-13T00:00:00Z", new_total: 0, by_type: { mission: 0, report: 0, evidence: 0 } };
    else if (pathname.endsWith("/saved-searches")) {
      if (route.request().method() === "POST") { const created = { ...entry, ...body, id: documentId }; saved = [...saved, created]; response = created; }
      else response = { items: saved, limit_per_user: 50 };
    } else if (pathname.endsWith("/navigation/search")) {
      const query = url.searchParams.get("q") ?? "";
      const selected = url.searchParams.get("entity_type");
      const pageNumber = Number(url.searchParams.get("page") ?? 1);
      const matches = kinds.filter(kind => (!selected || selected === kind) && (query === "all" || query === kind));
      response = { query, groups: matches.map(kind => ({ entity_type: kind, total: kind === "collection" && query === "all" ? 113 : 1, page: pageNumber, page_size: 5, items: [{ id: projectId, title: `${kind} named result${pageNumber > 1 ? ` page ${pageNumber}` : ""}`, href: entityPath(kind) }] })) };
    } else if (pathname.includes("/search/replay/")) response = { entry: { ...entry, query_text: "Recent scope" }, semantic: { results: [results[1]] }, rag };
    else if (pathname.endsWith("/execute")) response = { saved_search: saved.find(item => pathname.includes(item.id)) ?? entry, semantic: { results: [results[1]] }, rag };
    else if (pathname.endsWith("/pedr/search")) response = { results, metadata: null };
    else if (pathname.endsWith("/search")) response = rag;
    else if (pathname.endsWith("/collections")) response = { collections: [], total: 0 };
    else { await route.fulfill({ status: 404, json: { detail: "Fixture object not found" } }); return; }
    await route.fulfill({ json: response });
  });
  return requests;
}

async function audit(page: Page, name: string) {
  await page.addScriptTag({ path: path.resolve("node_modules/axe-core/axe.min.js") });
  const result = await page.evaluate(async () => {
    const axe = (window as unknown as { axe: { run: (node: Document) => Promise<{ violations: { id: string; impact: string }[] }> } }).axe;
    return { overflow: document.documentElement.scrollWidth > innerWidth, violations: (await axe.run(document)).violations.filter(item => ["serious", "critical"].includes(item.impact)) };
  });
  expect(result, name).toEqual({ overflow: false, violations: [] });
  if (process.env.UX9_SCREENSHOT_DIR) await page.screenshot({ path: path.join(process.env.UX9_SCREENSHOT_DIR, `${name}.png`), fullPage: true });
}

for (const theme of ["light", "dark"] as const) {
  for (const width of [390, 820, 1440]) {
    test(`palette keyboard reach, paging and focus in ${theme} at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 1000 });
      await page.emulateMedia({ colorScheme: theme });
      await fixture(page);
      await page.goto("/search");
      const opener = page.getByRole("textbox", { name: "Search query", exact: true });
      await opener.focus();
      await page.keyboard.press("Control+k");
      const dialog = page.getByRole("dialog", { name: "Search and navigation" });
      const query = dialog.getByRole("textbox");
      await expect(query).toBeFocused();
      await expect(dialog.getByRole("button", { name: "New mission", exact: true })).toBeVisible();
      await expect(dialog.getByRole("button", { name: "Upload documents", exact: true })).toBeVisible();
      await expect(dialog.getByRole("button", { name: "Users", exact: true })).toHaveCount(0);
      await query.fill("all");
      await expect(dialog.getByRole("region", { name: "Collections (113)" })).toBeVisible();
      for (let i = 0; i < 15; i++) { await page.keyboard.press("Tab"); expect(await dialog.evaluate(node => node.contains(document.activeElement))).toBe(true); }
      const pages = dialog.getByRole("navigation", { name: "Collections pages" });
      await pages.getByRole("button", { name: "Next" }).focus();
      await page.keyboard.press("Enter");
      await expect(dialog.getByRole("button", { name: "collection named result page 2" })).toBeVisible();
      await query.focus();
      await query.press("ArrowDown");
      await expect(dialog.getByRole("button", { name: "project named result", exact: true })).toBeFocused();
      await page.keyboard.press("End");
      await expect(dialog.getByRole("button", { name: "evidence named result", exact: true })).toBeFocused();
      await page.keyboard.press("Home");
      await expect(dialog.getByRole("button", { name: "project named result", exact: true })).toBeFocused();
      await page.keyboard.press("End");
      await page.keyboard.press("Tab");
      await expect(dialog.getByText("Keyboard help", { exact: true })).toBeFocused();
      await page.keyboard.press("Enter");
      await expect(dialog.getByText(/Escape closes this dialog and restores focus/)).toBeVisible();
      await audit(page, `palette-${theme}-${width}`);
      await page.keyboard.press("Escape");
      await expect(opener).toBeFocused();
      for (const kind of kinds) {
        await page.keyboard.press("Meta+k");
        await expect(query).toBeFocused();
        await query.fill(kind);
        await expect(dialog.getByRole("button", { name: `${kind} named result`, exact: true })).toBeVisible();
        await query.press("ArrowDown");
        await expect(dialog.getByRole("button", { name: `${kind} named result`, exact: true })).toBeFocused();
        await page.keyboard.press("Enter");
        await expect(page).toHaveURL(new RegExp(`${entityPath(kind)}$`));
        await expect(dialog).not.toBeVisible();
      }
    });

    test(`search preserves API results, filters and saved replay in ${theme} at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 1000 });
      await page.emulateMedia({ colorScheme: theme });
      const requests = await fixture(page);
      await page.goto("/search");
      await expect(page.getByText("Start with a question", { exact: true })).toBeVisible();
      await page.getByRole("textbox", { name: "Search query", exact: true }).fill("scope & provenance");
      await page.getByLabel("Project", { exact: true }).selectOption(projectId);
      await page.getByLabel("Source type", { exact: true }).selectOption("transcript");
      await page.getByLabel("Collected from").fill("2026-01-01");
      await page.getByLabel("Collected until").fill("2026-09-13");
      await page.getByRole("textbox", { name: "Search query", exact: true }).press("Enter");
      const region = page.getByRole("region", { name: "Search results", exact: true });
      await expect(region.locator("code")).toHaveText(chunkIds);
      expect(requests.find(item => item.pathname.endsWith("/pedr/search"))?.body).toMatchObject({ query: "scope & provenance", project_id: projectId, source_type: "transcript", date_from: "2026-01-01", date_to: "2026-09-13" });
      await expect(page.getByText(rag.answer, { exact: true })).toBeVisible();
      expect(requests.find(item => item.pathname === "/api/v1/search")?.body).toMatchObject({ source_type: "transcript", date_from: "2026-01-01", date_to: "2026-09-13" });
      const answerPanel = page.locator("section").filter({ has: page.getByRole("heading", { name: "Synthesized response with citations", exact: true }) });
      expect(await answerPanel.evaluate(node => node.getBoundingClientRect().bottom - node.lastElementChild!.getBoundingClientRect().bottom), "The answer panel fits its content so history and mobile stats follow in document order").toBeLessThan(40);
      const focusResult = page.getByRole("button", { name: "Focus result", exact: true });
      const focusSize = await focusResult.evaluate(node => ({ width: node.getBoundingClientRect().width, height: node.getBoundingClientRect().height }));
      expect(focusSize.width, "Long citations must not squeeze the action into a vertical label").toBeGreaterThan(60);
      expect(focusSize.height).toBeLessThan(30);
      await audit(page, `search-results-${theme}-${width}`);
      await page.getByRole("button", { name: "Focus result", exact: true }).click();
      await page.getByRole("button", { name: "Save current search", exact: true }).click();
      await page.getByLabel("Name", { exact: true }).fill("Saved browser round trip");
      await page.getByRole("button", { name: "Save search", exact: true }).click();
      await expect(page.getByRole("button", { name: "Saved browser round trip", exact: true })).toBeVisible();
      expect(requests.find(item => item.pathname.endsWith("/saved-searches") && item.body)?.body).toMatchObject({ query_text: "scope & provenance", filters: { project_id: projectId, source_type: "transcript", date_from: "2026-01-01", date_to: "2026-09-13" } });
      await page.goto("/saved-searches");
      const saved = page.getByRole("article").filter({ has: page.getByRole("button", { name: "Saved browser round trip", exact: true }) });
      await saved.getByRole("button", { name: "Run now", exact: true }).click();
      await expect(page).toHaveURL(new RegExp(`/search\\?saved=${documentId}$`));
      await expect(region.locator("code")).toHaveText([chunkIds[1]]);
      await page.keyboard.press("Control+k");
      const dialog = page.getByRole("dialog", { name: "Search and navigation" });
      await dialog.getByRole("button", { name: "Recent scope", exact: true }).focus();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`/search\\?history=${projectId}$`));
      await expect(page.getByRole("textbox", { name: "Search query", exact: true })).toHaveValue("Recent scope");
      await expect(page.getByLabel("Chunks", { exact: true })).toHaveValue("7");
      await expect(region.locator("code")).toHaveText([chunkIds[1]]);
    });
  }
}

test("recent and saved search times use UTC even outside the UTC timezone", async ({ page }) => {
  await fixture(page);
  await page.clock.setFixedTime("2026-09-14T01:44:00Z");
  const timestamp = "2026-09-14T01:43:00";
  await page.route("**/api/v1/search/history*", route => route.fulfill({ json: { entries: [{ ...entry, created_at: timestamp }] } }));
  await page.route("**/api/v1/saved-searches", route => route.fulfill({ json: { items: [{ ...entry, last_used_at: timestamp }], limit_per_user: 50 } }));
  await page.goto("/search");
  await expect.soft(page.getByText("1 minute ago", { exact: true })).toBeVisible();
  await expect.soft(page.getByText("Last run 1 minute ago", { exact: true })).toBeVisible();
});

test("the retired /search/results alias is gone rather than silently redirecting", async ({ request }) => {
  // Retired in Sprint 54 (ALIAS-1). route-migration.spec.ts asserts this from the migration
  // map too; this keeps the search suite honest about its own former alias.
  const response = await request.get("/search/results?q=scope%20%26%20provenance", { maxRedirects: 0 });
  expect(response.status()).toBe(404);
});

test("loading, no matches, service failure and missing saved search stay distinct", async ({ page }) => {
  await fixture(page);
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/v1/pedr/search", async route => { await pending; await route.fulfill({ json: { results: [], metadata: null } }); });
  await page.goto("/search?q=empty");
  await expect(page.getByText("Searching your research…", { exact: true })).toBeVisible();
  release();
  await expect(page.getByText("No matching results", { exact: true })).toBeVisible();
  await page.route("**/api/v1/pedr/search", route => route.fulfill({ status: 503, json: { detail: "Unavailable" } }));
  await page.route("**/api/v1/retrieval/search", route => route.fulfill({ status: 503, json: { detail: "Unavailable" } }));
  await page.getByRole("textbox", { name: "Search query", exact: true }).fill("failure");
  await page.getByRole("textbox", { name: "Search query", exact: true }).press("Enter");
  await expect(page.getByText("Search unavailable", { exact: true })).toBeVisible();
  await expect(page.getByText("No matching results", { exact: true })).toHaveCount(0);
  await page.route("**/api/v1/saved-searches/*/execute", route => route.fulfill({ status: 404, json: { detail: "Not found" } }));
  await page.goto(`/search?saved=${projectId}`);
  await expect(page.getByText("Search not found", { exact: true })).toBeVisible();
});
