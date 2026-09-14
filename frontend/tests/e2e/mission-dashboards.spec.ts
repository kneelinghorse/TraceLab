import { expect, test, type Page, type TestInfo } from "@playwright/test";
import path from "node:path";

test.use({ timezoneId: "America/Chicago" });
// Each workflow includes three full-page axe/screenshot audits as well as CRUD and navigation.
test.setTimeout(60_000);
const generated = "2026-09-14T00:00:00";
const project = "00000000-0000-4000-8000-000000000001";
const savedId = "00000000-0000-4000-8000-000000000002";
type View = { id: string; name: string; filters: { view: string; reason?: string[]; project_id?: string }; total: number };
async function fixture(page: Page, options: { failure?: boolean; gate?: Promise<void> } = {}) {
  let views: View[] = [];
  const writes: { method: string; body: Record<string, unknown> | null }[] = [];
  await page.addInitScript(() => localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "dashboard-test", user_id: "reader", email: "reader@example.test", display_name: "Reader" })));
  await page.route("**/api/v1/**", async route => {
    const url = new URL(route.request().url());
    const method = route.request().method();
    let data: unknown;
    if (url.pathname.endsWith("/auth/me")) data = { user_id: "reader", role: "member", email: "reader@example.test", display_name: "Reader" };
    else if (url.pathname.endsWith("/projects")) data = { data: [{ id: project, name: "A research project" }], pagination: { total: 1, page: 1, pages: 1, page_size: 100 } };
    else if (url.pathname.endsWith("/home/attention")) {
      await options.gate;
      if (options.failure) { await route.fulfill({ status: 500, json: { detail: "Unavailable" } }); return; }
      data = { generated_at: generated, total: 143, stalled_after_seconds: 3600, by_reason: { validation_failed: 10, blocked: 13, stalled: 20, unreviewed: 100 }, dashboards: [{ key: "at_risk", total: 43 }, { key: "unreviewed", total: 100 }] };
    } else if (url.pathname.endsWith("/home")) data = { generated_at: generated, refresh_seconds: 30, stalled_after_seconds: 3600, missions: { total: 543, by_status: { completed: 500 } }, attention: { total: 143, items: [] }, active_runs: { total: 1, items: [] }, favorites: { total: 0, items: [] }, recent_projects: { total: 0, items: [] }, recent_reports: { total: 0, items: [] }, evidence_activity: { total: 0, items: [] } };
    else if (url.pathname.includes("/mission-views")) {
      if (method !== "GET") writes.push({ method, body: route.request().postDataJSON() as Record<string, unknown> | null });
      if (method === "POST") { const body = route.request().postDataJSON(); const view = { id: savedId, ...body, total: 100 }; views = [view]; data = view; }
      else if (method === "PUT") { const body = route.request().postDataJSON(); views[0].name = body.name; data = views[0]; }
      else if (method === "DELETE") { views = []; await route.fulfill({ status: 204 }); return; }
      else data = { items: views };
    } else if (url.pathname.endsWith("/missions")) {
      const reasons = url.searchParams.getAll("reason");
      const counts: Record<string, number> = { validation_failed: 10, blocked: 13, stalled: 20, unreviewed: 100 };
      const total = reasons.length ? reasons.reduce((sum, reason) => sum + counts[reason], 0) : 543;
      data = { data: [{ id: savedId, mission_id: "REVIEW-1", title: "Inspect the research result", objective: "Review supporting evidence", status: reasons.includes("unreviewed") ? "completed" : "blocked", project_id: project, project_name: "A research project", updated_at: generated }], pagination: { total, pages: Math.ceil(total / 20), page: Number(url.searchParams.get("page") ?? 1), page_size: 20 } };
    } else if (url.pathname.endsWith("/search/history")) data = { entries: [] };
    else if (url.pathname.endsWith("/saved-searches")) data = { items: [] };
    else if (url.pathname.endsWith("/navigation/search")) data = { groups: [] };
    else { await route.fulfill({ status: 404, json: { detail: "Fixture not found" } }); return; }
    await route.fulfill({ json: data });
  });
  return writes;
}
async function audit(page: Page, info: TestInfo, name: string) {
  await page.addScriptTag({ path: path.resolve("node_modules/axe-core/axe.min.js") });
  const result = await page.evaluate(async () => {
    const axe = (window as unknown as { axe: { run: (root: Document) => Promise<{ violations: { id: string; impact: string }[] }> } }).axe;
    return { overflow: document.documentElement.scrollWidth > innerWidth, violations: (await axe.run(document)).violations.filter(item => ["critical", "serious"].includes(item.impact)) };
  });
  expect(result).toEqual({ overflow: false, violations: [] });
  await page.screenshot({ path: info.outputPath(`${name}.png`), fullPage: true });
}
for (const theme of ["light", "dark"] as const) for (const width of [1440, 390]) test(`dashboards and personal view workflow in ${theme} at ${width}px`, async ({ page }, info) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  const writes = await fixture(page);
  await page.setViewportSize({ width, height: 1000 });
  await page.emulateMedia({ colorScheme: theme });
  await page.goto("/missions");
  await expect(page.getByRole("link", { name: "At risk missions 43" })).toBeVisible();
  await expect(page.locator("time")).toHaveText("9/13/2026, 7:00:00 PM");
  await page.getByRole("link", { name: "Unreviewed completions 100" }).click();
  await expect(page.getByText("100 matching missions", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Unreviewed completion", { exact: true })).toBeChecked();
  await audit(page, info, "dashboards");
  const opener = page.getByRole("button", { name: "Save view", exact: true });
  await opener.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Save view", exact: true });
  await expect(dialog.getByLabel("View name")).toBeFocused();
  await page.keyboard.type("Completions to review");
  await page.keyboard.press("Shift+Tab");
  await expect(dialog.getByRole("button", { name: "Save", exact: true })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(dialog.getByLabel("View name")).toBeFocused();
  await audit(page, info, "save-dialog");
  await page.keyboard.press("Escape");
  await expect(opener).toBeFocused();
  expect(writes).toHaveLength(0);
  await opener.click();
  await dialog.getByLabel("View name").fill("Completions to review");
  await dialog.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("link", { name: "Completions to review (100)" })).toBeVisible();
  expect(writes[0]).toEqual({ method: "POST", body: { name: "Completions to review", filters: { view: "attention", reason: ["unreviewed"] } } });
  await page.getByRole("button", { name: "Rename Completions to review" }).click();
  await page.getByLabel("View name").fill("Review next");
  await page.getByRole("dialog").getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("link", { name: "Review next (100)" })).toBeVisible();
  await page.keyboard.press("Control+k");
  await page.getByRole("button", { name: "Review next (100)" }).click();
  await expect(page).toHaveURL(/view=attention&reason=unreviewed/);
  await page.getByRole("button", { name: "Delete Review next" }).click();
  expect(writes.filter(item => item.method === "DELETE")).toHaveLength(0);
  await page.getByRole("button", { name: "Delete view", exact: true }).click();
  await expect(page.getByText("No saved views yet.")).toBeVisible();
  await page.getByRole("link", { name: "At risk missions 43" }).click();
  await expect(page.getByText("43 matching missions", { exact: true })).toBeVisible();
  await page.goBack();
  await expect(page.getByLabel("Unreviewed completion", { exact: true })).toBeChecked();
  await page.goto("/");
  await expect(page.getByRole("navigation", { name: "Attention dashboards" }).getByRole("link", { name: "Unreviewed completions" })).toHaveAttribute("href", "/missions?view=attention&reason=unreviewed");
  await audit(page, info, "home");
  expect(errors).toEqual([]);
});

test("loading and failed dashboard counts never render as zero", async ({ page }) => {
  let release!: () => void;
  await fixture(page, { failure: true, gate: new Promise<void>(resolve => { release = resolve; }) });
  await page.goto("/missions");
  await expect(page.getByText("Loading dashboards…")).toBeVisible();
  await expect(page.getByRole("link", { name: /At risk missions/ })).toHaveCount(0);
  release();
  await expect(page.getByText("Dashboard totals unavailable.")).toBeVisible();
  await expect(page.getByRole("link", { name: /At risk missions/ })).toHaveCount(0);
});
