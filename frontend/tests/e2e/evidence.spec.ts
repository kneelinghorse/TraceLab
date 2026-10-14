import { expect, test } from "@playwright/test";
import claimFixtures from "../../../tests/fixtures/evidence_display_claims.json";

for (const theme of ["light", "dark"] as const) for (const width of [390, 1440]) {
  test(`evidence promotion traps keyboard focus and cancels without writing in ${theme} at ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.emulateMedia({ colorScheme: theme });
    await page.addInitScript(({ theme }) => {
      localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "fixture", user_id: "reader", email: "reader@example.test" }));
      localStorage.setItem("tracelab.theme.v1:reader", theme);
    }, { theme });
    let writes = 0;
    await page.route("**/api/v1/**", async route => {
      const path = new URL(route.request().url()).pathname;
      if (route.request().method() !== "GET") writes++;
      const body = path.endsWith("/auth/me") ? { user_id: "reader", email: "reader@example.test", role: "member" }
        : path.endsWith("/projects") ? { data: [{ id: "project", name: "Research" }], pagination: { pages: 1 } }
        : { entries: [], notes: [], entry_total: 0, note_total: 0, page: 1, page_size: 20 };
      await route.fulfill({ json: body });
    });
    await page.goto("/evidence?project_id=project&session_key=research-session");
    const trigger = page.getByRole("button", { name: "Promote session" });
    await trigger.click();
    const dialog = page.getByRole("dialog", { name: "Promote evidence session" });
    await expect(dialog).toBeVisible();
    for (const key of ["Tab", "Shift+Tab"]) for (let count = 0; count < 8; count++) {
      await page.keyboard.press(key);
      expect(await dialog.evaluate(node => node.contains(document.activeElement))).toBe(true);
    }
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
    await expect(trigger).toBeFocused();
    expect(writes).toBe(0);
  });
}

for (const theme of ["light", "dark"] as const) for (const width of [390, 1440]) {
  test(`table claims read as prose on cards, detail and briefs in ${theme} at ${width}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ colorScheme: theme });
    await page.addInitScript(({ theme }) => {
      localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "fixture", user_id: "reader", email: "reader@example.test" }));
      localStorage.setItem("tracelab.theme.v1:reader", theme);
    }, { theme });
    const fixture = claimFixtures.cases[9];
    const entry = { id: "entry", project_id: "project", mission_id: null, claim: fixture.claim, summary: null, snippet: fixture.claim, query: null, tags: [], source_url: fixture.source_url, source_id: "source", source_sighting_count: 1, session_key: "claim-display", origin: "deepsearch-worker", disposition: "supporting", created_at: "2026-10-14T00:00:00Z", updated_at: "2026-10-14T00:00:00Z" };
    const writes: string[] = [];
    await page.route("**/api/v1/**", async route => {
      const path = new URL(route.request().url()).pathname;
      const method = route.request().method();
      if (method !== "GET" && !path.startsWith("/api/v1/activity/")) writes.push(`${method} ${path}`);
      const body = path.endsWith("/auth/me") ? { user_id: "reader", email: "reader@example.test", role: "member" }
        : path.endsWith("/projects") ? { data: [{ id: "project", name: "Research" }], pagination: { pages: 1 } }
        : path.endsWith("/evidence/entry") ? { entry, links: [] }
        : path.endsWith("/reports/brief") ? { id: "brief", project_id: "project", title: "Readable evidence brief", content: claimFixtures.brief.markdown, origin: "agent_brief", origin_label: "Evidence brief", status: "final", report_type: "markdown", sources: [], citations: [], chunk_count: 0, tokens_used: 0, created_at: entry.created_at, updated_at: entry.updated_at }
        : path.startsWith("/api/v1/activity/") ? { viewed: 1, new_total: 0, by_type: {}, items: [] }
        : { entries: [entry], notes: [], entry_total: 1, note_total: 0, page: 1, page_size: 20 };
      await route.fulfill({ json: body });
    });
    async function capture(name: string) {
      await page.evaluate(() => document.fonts.ready);
      await page.addScriptTag({ path: require.resolve("axe-core/axe.min.js") });
      const audit = await page.evaluate(async () => ({
        overflow: document.documentElement.scrollWidth > innerWidth,
        violations: (await (window as unknown as { axe: { run: (node: Document) => Promise<{ violations: { impact: string }[] }> } }).axe.run(document)).violations.filter(v => ["serious", "critical"].includes(v.impact)),
      }));
      expect(audit.overflow).toBe(false);
      expect(audit.violations).toEqual([]);
      await page.screenshot({ path: testInfo.outputPath(`claims-${name}-${theme}-${width}.png`), fullPage: true });
    }
    await page.goto("/evidence?project_id=project");
    const link = page.getByRole("link", { name: fixture.display, exact: true });
    await expect(link).toBeVisible();
    await capture("card");
    await link.click();
    await expect(page.getByRole("heading", { level: 1, name: fixture.display })).toBeVisible();
    await expect(page.getByRole("blockquote")).toHaveText(fixture.claim);
    await capture("detail");
    await page.goto("/reports/brief");
    await expect(page.getByText("Claim: a · b; c · d", { exact: false })).toBeVisible();
    await expect(page.locator("table")).toHaveCount(0);
    await expect(page.getByRole("region", { name: "Evidence citations", exact: true }).getByRole("link", { name: fixture.display, exact: true })).toBeVisible();
    await capture("brief");
    expect(writes).toEqual([]);
  });
}
