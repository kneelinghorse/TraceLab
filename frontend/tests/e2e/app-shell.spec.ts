import { test, expect } from "@playwright/test";
import path from "node:path";

// Browser-level focus, hydration, and command integration. API responses are
// deterministic here; scripts/ui-shell-smoke.mjs covers real deployed data.
test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.addInitScript(() => {
    localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "shell-test", user_id: "alice", email: "alice@example.test", display_name: "Alice" }));
  });
  await page.route("**/api/v1/**", async route => {
    const pathname = new URL(route.request().url()).pathname;
    let body: unknown = {};
    if (pathname.endsWith("/auth/me")) body = { user_id: "alice", email: "alice@example.test", display_name: "Alice", role: "admin" };
    else if (pathname.endsWith("/home")) body = {
      generated_at: "2026-09-13T00:00:00Z", refresh_seconds: 30, stalled_after_seconds: 3600,
      missions: { total: 433, by_status: { completed: 424 } },
      attention: { total: 0, items: [] }, active_runs: { total: 0, items: [] },
      recent_reports: { total: 0, items: [] }, recent_projects: { total: 0, items: [] },
      evidence_activity: { total: 0, items: [] },
    };
    else if (pathname.endsWith("/home/attention")) body = { generated_at: "2026-09-13T00:00:00Z", total: 0, stalled_after_seconds: 3600, by_reason: { validation_failed: 0, blocked: 0, stalled: 0, unreviewed: 0 }, dashboards: [{ key: "at_risk", total: 0 }, { key: "unreviewed", total: 0 }] };
    else if (pathname.endsWith("/mission-views")) body = { items: [] };
    else if (pathname.endsWith("/inbox/summary")) body = { generated_at: "2026-09-13T00:00:00", refresh_seconds: 30, seen_through: "2026-09-13T00:00:00", default_lookback_seconds: 604800, unread: { failures: 0, completions: 0, evidence: 0, total: 0 } };
    else if (pathname.endsWith("/projects") || pathname.endsWith("/missions") || pathname.endsWith("/documents")) body = { data: [], pagination: { page: 1, page_size: 20, total: 0, pages: 1 } };
    else if (pathname.endsWith("/search/history")) body = { entries: [] };
    else if (pathname.endsWith("/saved-searches")) body = { items: [] };
    else if (pathname.endsWith("/navigation/search")) body = { query: new URL(route.request().url()).searchParams.get("q"), groups: [] };
    else if (pathname.endsWith("/facets")) body = { source_types: [], projects: [], document_types: [], tags: [], date_range: { min: null, max: null } };
    else if (pathname.endsWith("/pedr/search")) body = { results: [], metadata: null };
    else if (pathname.endsWith("/search")) body = { answer: "No matching sources", citations: [], sources: [], latency_ms: 12, quality: { composite_score: 0.9, threshold: 0.8 }, routing: { selected_model: "test" }, cache: { hit: false } };
    await route.fulfill({ json: body });
  });
});

test("Home stays at the root and its search opens the shell palette", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Home", exact: true })).toBeVisible();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("link", { name: "433 missions" })).toBeVisible();
  await expect(page.getByText("You’re up to date.")).toBeVisible();
  const search = page.getByRole("button", { name: /Search research or jump to a section/ });
  await search.click();
  await expect(page.getByRole("textbox", { name: "Search research or find a section" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(search).toBeFocused();
  await expect(page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Missions", exact: true })).toHaveAttribute("href", "/missions");
});

test("theme persists through hydration and OS changes without a wrong-color frame", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.addInitScript(() => {
    (window as unknown as { paintedThemes: string[] }).paintedThemes = [];
    function sample() {
      if (document.body?.innerText) (window as unknown as { paintedThemes: string[] }).paintedThemes.push(document.documentElement.dataset.theme || "missing");
      if (performance.now() < 3000) requestAnimationFrame(sample);
    }
    requestAnimationFrame(sample);
  });
  await page.goto("/missions");
  await expect(page.getByRole("heading", { name: "Missions", exact: true })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  const paints = await page.evaluate(() => (window as unknown as { paintedThemes: string[] }).paintedThemes);
  expect(paints.length).toBeGreaterThan(0);
  expect(paints.every(theme => theme === "dark")).toBe(true);
  await expect(page.getByRole("combobox", { name: "Color theme" }).locator("option:checked")).toHaveText("System (Dark)");
  const darkBackground = await page.locator("body").evaluate(node => getComputedStyle(node).backgroundColor);
  await page.getByRole("combobox", { name: "Color theme" }).selectOption("light");
  await page.reload();
  await expect(page.getByRole("combobox", { name: "Color theme" })).toHaveValue("light");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.getByRole("combobox", { name: "Color theme" }).selectOption("system");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await expect(page.getByRole("combobox", { name: "Color theme" }).locator("option:checked")).toHaveText("System (Light)");
  expect(await page.locator("body").evaluate(node => getComputedStyle(node).backgroundColor)).not.toBe(darkBackground);
  expect(errors).toEqual([]);
});

for (const storedChoice of ["system", "hc"]) {
  test(`the head bootstrap resolves stored ${storedChoice} to System dark before delayed hydration`, async ({ page }) => {
    await page.addInitScript(choice => localStorage.setItem("tracelab.theme.v1:alice", choice), storedChoice);
    let releaseHydration!: () => void;
    const hydration = new Promise<void>(resolve => { releaseHydration = resolve; });
    await page.route("**/_next/**/*.js", async route => { await hydration; await route.continue(); });
    try {
      await page.goto("/missions", { waitUntil: "commit" });
      await expect(page.getByText("Loading workspace…")).toBeVisible();
      await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
      expect(await page.locator("body").evaluate(node => getComputedStyle(node).backgroundColor)).not.toBe("rgba(0, 0, 0, 0)");
    } finally {
      releaseHydration();
    }
    await expect(page.getByRole("heading", { name: "Missions", exact: true })).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await expect(page.getByRole("combobox", { name: "Color theme" })).toHaveValue("system");
    await expect(page.getByRole("option", { name: "High contrast" })).toHaveCount(0);
  });
}

test("Light persists across reload and OS changes with native keyboard focus", async ({ page }) => {
  await page.goto("/missions");
  const selector = page.getByRole("combobox", { name: "Color theme" });
  await selector.focus();
  // Native type-ahead selects Light, then Enter commits it.
  await selector.press("l");
  await selector.press("Enter");
  await expect(selector).toHaveValue("light");
  await expect(selector).toBeFocused();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.reload();
  await expect(selector).toHaveValue("light");
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  expect(await page.locator("html").evaluate(node => ({ dark: node.classList.contains("dark"), scheme: node.style.colorScheme }))).toEqual({ dark: false, scheme: "light" });
});

test("mobile drawer traps focus, closes with Escape, and returns focus to its trigger", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/missions");
  const trigger = page.getByRole("button", { name: "Open navigation" });
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "Navigation", exact: true });
  await expect(dialog).toBeVisible();
  for (let i = 0; i < 22; i++) {
    await page.keyboard.press("Tab");
    expect(await dialog.evaluate(node => node.contains(document.activeElement))).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(trigger).toBeFocused();
  await trigger.click();
  await dialog.getByRole("link", { name: "Saved searches" }).click();
  await expect(page).toHaveURL(/saved-searches/);
  await expect(dialog).not.toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("command palette submits a real search request and supports keyboard dismissal", async ({ page }) => {
  await page.goto("/missions");
  await page.getByRole("heading", { name: "Missions", exact: true }).waitFor();
  await page.keyboard.press("Control+k");
  const query = page.getByRole("textbox", { name: "Search research or find a section" });
  await expect(query).toBeFocused();
  await query.fill("source & provenance");
  const request = page.waitForRequest(r => r.url().endsWith("/pedr/search") && r.method() === "POST");
  await query.press("Enter");
  expect((await request).postDataJSON().query).toBe("source & provenance");
  await expect(page).toHaveURL(/search\?q=source%20%26%20provenance/);
  await expect(page.getByText("No matching sources", { exact: true })).toBeVisible();
  for (const theme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: theme });
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    await page.addScriptTag({ path: path.resolve("node_modules/axe-core/axe.min.js") });
    const violations = await page.evaluate(async () => {
      const axe = (window as unknown as { axe: { run: (node: Document) => Promise<{ violations: { id: string; impact: string }[] }> } }).axe;
      return (await axe.run(document)).violations.filter(v => ["critical", "serious"].includes(v.impact));
    });
    expect(violations).toEqual([]);
  }
  await page.keyboard.press("Meta+k");
  await expect(query).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Search and navigation" })).not.toBeVisible();
});

test("open modal surfaces meet the same axe severity and landmark gates", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/missions");
  for (const name of ["Open navigation", "Search"]) {
    await page.getByRole("button", { name, exact: true }).click();
    await page.addScriptTag({ path: path.resolve("node_modules/axe-core/axe.min.js") });
    const violations = await page.evaluate(async () => {
      const axe = (window as unknown as { axe: { run: (node: Document) => Promise<{ violations: { id: string; impact: string }[] }> } }).axe;
      return (await axe.run(document)).violations.filter(v => ["critical", "serious"].includes(v.impact) || ["html-has-lang", "region", "landmark-one-main", "landmark-no-duplicate-banner"].includes(v.id));
    });
    expect(violations).toEqual([]);
    await page.keyboard.press("Escape");
  }
});

for (const theme of ["light", "dark"] as const) {
  for (const width of [390, 1440]) {
    test(`login and registration share accessible ${theme} surfaces at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 1000 });
      await page.emulateMedia({ colorScheme: theme });
      await page.goto("/missions");
      await page.getByRole("heading", { name: "Missions", exact: true }).waitFor();
      await page.evaluate(() => window.dispatchEvent(new Event("tracelab:auth-expired")));
      await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeVisible();
      for (const view of ["login", "register"]) {
        if (view === "register") await page.getByRole("button", { name: "Create one" }).click();
        await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
        await expect(page.getByRole("main")).toHaveCount(1);
        await page.addScriptTag({ path: path.resolve("node_modules/axe-core/axe.min.js") });
        const result = await page.evaluate(async () => {
          const axe = (window as unknown as { axe: { run: (node: Document) => Promise<{ violations: { id: string; impact: string }[] }> } }).axe;
          return { overflow: document.documentElement.scrollWidth > innerWidth, violations: (await axe.run(document)).violations.filter(v => ["critical", "serious"].includes(v.impact)) };
        });
        expect(result).toEqual({ overflow: false, violations: [] });
      }
    });
  }
}
