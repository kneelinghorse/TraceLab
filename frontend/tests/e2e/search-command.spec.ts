import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

test.use({ timezoneId: "America/Chicago" });

const projectId = "00000000-0000-4000-8000-000000000001";
const documentId = "00000000-0000-4000-8000-000000000002";
const chunkIds = ["00000000-0000-4000-8000-000000000003", "00000000-0000-4000-8000-000000000004"];
const kinds = ["project", "document", "mission", "report", "collection", "evidence"];
const entityPath = (kind: string) => `/${kind === "evidence" ? "evidence" : `${kind}s`}/${projectId}`;
const collectionId = "00000000-0000-4000-8000-000000000005";
const results = chunkIds.map((chunk_id, index) => ({ chunk_id, document_id: documentId, project_id: projectId, content: `Authorized result ${index + 1}`, source_type: "transcript", rrf_score: 0.1 - index * 0.01, rrf_rank: index + 1, score: 0.1, chunk_index: index, layer_ranks: {}, layer_scores: {}, confidence: 0.5, criticality: 0.5, quality_score: 1, quality_gates_passed: 0, contributing_layers: ["lexical"] }));
// A saved run returns an answer too; the Librarian's list must not show it (decision #545).
const rag = { answer: "An answer the chunk list never shows.", citations: [], sources: [], latency_ms: 12, quality: { composite_score: 0.9, threshold: 0.8 }, routing: { selected_model: "test-model" }, cache: { hit: false } };
const entry = { id: projectId, name: "Saved scope", query_text: "saved scope", filters: { project_id: projectId, source_type: "transcript" }, top_k: 7, search_mode: "semantic", owner: "member", use_count: 0, created_at: "2026-09-13T00:00:00Z", updated_at: "2026-09-13T00:00:00Z" };

async function fixture(page: Page) {
  const requests: { method: string; pathname: string; body: Record<string, unknown> | null }[] = [];
  let saved = [entry];
  await page.addInitScript(() => localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "search-test", user_id: "member", email: "member@example.test", display_name: "Member" })));
  await page.route("**/api/v1/**", async route => {
    const url = new URL(route.request().url());
    const pathname = url.pathname;
    const method = route.request().method();
    const body = route.request().postDataJSON() as Record<string, unknown> | null;
    requests.push({ method, pathname, body });
    let response: unknown;
    if (pathname.endsWith("/auth/me")) response = { user_id: "member", email: "member@example.test", display_name: "Member", role: "member" };
    else if (pathname.endsWith("/projects")) response = { data: [{ id: projectId, name: "Accessible project" }], pagination: { page: 1, page_size: 100, total: 1, pages: 1 } };
    else if (pathname.endsWith("/spaces")) response = [{ id: "space-mine", name: "Member's Space", created_at: "2026-09-13T00:00:00Z", personal_owner_id: "member" }];
    else if (pathname.endsWith(`/documents/${documentId}`)) response = { id: documentId, name: "Field notes.md", project_id: projectId };
    else if (pathname.endsWith("/activity/summary")) response = { generated_at: "2026-09-13T00:00:00Z", new_total: 0, by_type: { mission: 0, report: 0, evidence: 0 } };
    else if (pathname.endsWith("/saved-searches")) {
      if (method === "POST") { const created = { ...entry, ...body, id: documentId }; saved = [...saved, created]; response = created; }
      else response = { items: saved, limit_per_user: 50 };
    } else if (pathname.endsWith("/navigation/search")) {
      const query = url.searchParams.get("q") ?? "";
      const selected = url.searchParams.get("entity_type");
      const pageNumber = Number(url.searchParams.get("page") ?? 1);
      const matches = kinds.filter(kind => (!selected || selected === kind) && (query === "all" || query === kind));
      response = { query, groups: matches.map(kind => ({ entity_type: kind, total: kind === "collection" && query === "all" ? 113 : 1, page: pageNumber, page_size: 5, items: [{ id: projectId, title: `${kind} named result${pageNumber > 1 ? ` page ${pageNumber}` : ""}`, href: entityPath(kind) }] })) };
    } else if (pathname.endsWith("/execute")) response = { saved_search: saved.find(item => pathname.includes(item.id)) ?? entry, semantic: { results: [results[1]] }, rag };
    else if (pathname.endsWith("/pedr/search")) response = { results, metadata: null };
    else if (pathname.endsWith("/collections") && method === "POST") response = { id: collectionId, name: body?.name, description: null, created_at: "2026-09-13T00:00:00Z", updated_at: "2026-09-13T00:00:00Z", item_count: 0 };
    else if (pathname.endsWith(`/collections/${collectionId}/chunks`)) response = { id: `item-${requests.length}`, collection_id: collectionId, chunk_id: body?.chunk_id, notes: null, added_at: "2026-09-13T00:00:00Z", chunk_content: null, document_id: documentId };
    else if (pathname.endsWith("/collections")) response = { data: [], total: 0 };
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
      await page.goto("/librarian");
      const opener = page.getByRole("textbox", { name: "Message the Librarian", exact: true });
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

    test(`the Librarian lists what /search found, keeps it as a collection and reruns a saved search in ${theme} at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 1000 });
      await page.emulateMedia({ colorScheme: theme });
      const requests = await fixture(page);
      // The retired Search page's URL lands on the Librarian with its query (QA-2).
      await page.goto("/search?q=scope%20%26%20provenance");
      await expect(page).toHaveURL(/\/librarian\?q=scope(\+|%20)%26(\+|%20)provenance$/);
      await expect(page.getByRole("radio", { name: "List the chunks" })).toBeChecked();
      const list = page.getByRole("region", { name: "Matching chunks", exact: true });
      await expect(list.getByRole("heading", { name: "2 chunks match “scope & provenance”" })).toBeVisible();
      expect(requests.find(item => item.pathname.endsWith("/pedr/search"))?.body).toEqual({ query: "scope & provenance", top_k: 20 });
      expect(requests.some(item => item.pathname === "/api/v1/search"), "Listing chunks must not ask the answer route").toBe(false);
      await expect(list.getByRole("link", { name: "Field notes.md #0" })).toHaveAttribute("href", `/documents/${documentId}?chunk=${chunkIds[0]}&index=0`);
      await expect(list.getByRole("link", { name: "Field notes.md #1" })).toHaveAttribute("href", `/documents/${documentId}?chunk=${chunkIds[1]}&index=1`);
      await audit(page, `librarian-chunks-${theme}-${width}`);

      await list.getByRole("button", { name: "Save 2 chunks as a collection", exact: true }).click();
      await expect(list.getByRole("link", { name: "scope & provenance", exact: true })).toHaveAttribute("href", `/collections/${collectionId}`);
      expect(requests.filter(item => item.pathname.endsWith(`/collections/${collectionId}/chunks`)).map(item => item.body?.chunk_id)).toEqual(chunkIds);

      await list.getByRole("button", { name: "Save current search", exact: true }).click();
      await page.getByLabel("Name", { exact: true }).fill("Saved browser round trip");
      await page.getByRole("button", { name: "Save search", exact: true }).click();
      await expect(list.getByText(/^Search saved\./)).toBeVisible();
      expect(requests.find(item => item.method === "POST" && item.pathname.endsWith("/saved-searches"))?.body).toMatchObject({ query_text: "scope & provenance", top_k: 20, filters: {} });

      await page.goto("/saved-searches");
      const saved = page.getByRole("article").filter({ has: page.getByRole("button", { name: "Saved browser round trip", exact: true }) });
      await saved.getByRole("button", { name: "Run now", exact: true }).click();
      await expect(page).toHaveURL(new RegExp(`/librarian\\?saved=${documentId}$`));
      await expect(list.getByRole("heading", { name: "Saved search “Saved browser round trip”: 1 chunk matches" })).toBeVisible();
      await expect(list.getByRole("link", { name: "Field notes.md #1" })).toBeVisible();
      await expect(page.getByText(rag.answer, { exact: true })).toHaveCount(0);

      await page.keyboard.press("Control+k");
      const dialog = page.getByRole("dialog", { name: "Search and navigation" });
      await expect(dialog.getByRole("region", { name: "Recent searches" })).toHaveCount(0);
      await dialog.getByRole("button", { name: "Saved scope", exact: true }).focus();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`/librarian\\?saved=${projectId}$`));
      await expect(list.getByRole("heading", { name: "Saved search “Saved scope”: 1 chunk matches" })).toBeVisible();
    });
  }
}

test("saved search times use UTC even outside the UTC timezone", async ({ page }) => {
  await fixture(page);
  await page.clock.setFixedTime("2026-09-14T01:44:00Z");
  const timestamp = "2026-09-14T01:43:00";
  await page.route("**/api/v1/saved-searches", route => route.fulfill({ json: { items: [{ ...entry, last_used_at: timestamp }], limit_per_user: 50 } }));
  await page.goto("/saved-searches");
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
  await page.goto("/librarian?q=empty");
  await expect(page.getByText("Searching the documents…", { exact: true })).toBeVisible();
  release();
  await expect(page.getByText("No chunks match", { exact: true })).toBeVisible();
  await page.route("**/api/v1/pedr/search", route => route.fulfill({ status: 503, json: { detail: "Unavailable" } }));
  await page.getByRole("textbox", { name: "Message the Librarian", exact: true }).fill("failure");
  await page.getByRole("textbox", { name: "Message the Librarian", exact: true }).press("Enter");
  await expect(page.getByText("The chunks could not be listed", { exact: true })).toBeVisible();
  await expect(page.getByText("No chunks match", { exact: true })).toHaveCount(0);
  await page.route("**/api/v1/saved-searches/*/execute", route => route.fulfill({ status: 404, json: { detail: "Not found" } }));
  await page.goto(`/librarian?saved=${projectId}`);
  await expect(page.getByText("This saved search no longer exists", { exact: true })).toBeVisible();
});
