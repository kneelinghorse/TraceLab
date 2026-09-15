import { expect, test, type Page, type TestInfo } from "@playwright/test";
import path from "node:path";

test.use({ timezoneId: "America/Chicago" });
// Each workflow includes axe/screenshot audits of the inbox and the shell badge in both drawer and toolbar.
test.setTimeout(60_000);
const generated = "2026-09-14T00:00:00.123456";
const doneId = "00000000-0000-4000-8000-000000000001";
const failId = "00000000-0000-4000-8000-000000000002";
const projectId = "00000000-0000-4000-8000-000000000003";
type Write = { method: string; pathname: string; body: Record<string, unknown> | null };
async function fixture(page: Page, options: { failing?: boolean } = {}) {
  const writes: Write[] = [];
  let seen = "2026-09-13T00:00:00";
  let reviewed = false;
  const counts = () => ({ failures: seen < "2026-09-13T22:00:00" ? 1 : 0, completions: !reviewed && seen < "2026-09-13T21:30:00" ? 1 : 0, evidence: seen < "2026-09-13T23:00:00" ? 1 : 0 });
  const blank = { reviewed: null, entry_count: null, project_id: null, mission_id: null, session_key: null, origin: null };
  await page.addInitScript(() => localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "inbox-test", user_id: "reader", email: "reader@example.test", display_name: "Reader" })));
  await page.route("**/api/v1/**", async route => {
    const url = new URL(route.request().url());
    const method = route.request().method();
    let data: unknown;
    if (url.pathname.endsWith("/auth/me")) data = { user_id: "reader", role: "member", email: "reader@example.test", display_name: "Reader" };
    else if (url.pathname.endsWith("/inbox/summary")) {
      if (options.failing) { await route.fulfill({ status: 500, json: { detail: "Unavailable" } }); return; }
      const unread = counts();
      data = { generated_at: generated, refresh_seconds: 30, seen_through: seen, default_lookback_seconds: 604800, unread: { ...unread, total: unread.failures + unread.completions + unread.evidence } };
    } else if (url.pathname.endsWith("/inbox/seen")) {
      const body = route.request().postDataJSON() as { seen_through: string };
      writes.push({ method, pathname: url.pathname, body });
      if (body.seen_through > seen) seen = body.seen_through;
      data = { seen_through: seen };
    } else if (url.pathname.endsWith("/inbox")) {
      const section = url.searchParams.get("section");
      const items = section === "failures" ? [{ ...blank, section, id: failId, title: "Validate the sources", label: "RESEARCH-9", status: "validation_failed", occurred_at: "2026-09-13T22:00:00", updated_at: "2026-09-13T22:00:00", unread: seen < "2026-09-13T22:00:00", href: `/missions/${failId}` }]
        : section === "completions" ? [{ ...blank, section, id: doneId, title: "Summarize the evidence", label: "RESEARCH-10", status: "completed", occurred_at: "2026-09-13T21:30:00", updated_at: "2026-09-13T21:30:00", unread: !reviewed && seen < "2026-09-13T21:30:00", href: `/missions/${doneId}`, reviewed }]
        : section === "evidence" ? [{ ...blank, section, id: `${projectId}:${doneId}:worker-run:deepsearch-worker`, title: "worker-run", label: "deepsearch-worker", status: null, occurred_at: "2026-09-13T23:00:00", updated_at: null, unread: seen < "2026-09-13T23:00:00", href: `/evidence?project_id=${projectId}&mission_id=${doneId}&session_key=worker-run`, entry_count: 12, project_id: projectId, mission_id: doneId, session_key: "worker-run", origin: "deepsearch-worker" }]
        : null;
      if (!items) { await route.fulfill({ status: 422, json: { detail: "Unknown section" } }); return; }
      data = { section, generated_at: generated, seen_through: seen, total: items.length, items };
    } else if (url.pathname.includes("/home/missions/") && url.pathname.endsWith("/review")) {
      writes.push({ method, pathname: url.pathname, body: route.request().postDataJSON() as Record<string, unknown> });
      reviewed = true;
      await route.fulfill({ status: 204 });
      return;
    } else if (url.pathname.endsWith("/home")) data = { generated_at: generated, refresh_seconds: 30, stalled_after_seconds: 3600, missions: { total: 2, by_status: { completed: 1 } }, attention: { total: 0, items: [] }, active_runs: { total: 0, items: [] }, favorites: { total: 0, items: [] }, recent_projects: { total: 0, items: [] }, recent_reports: { total: 0, items: [] }, evidence_activity: { total: 0, items: [] } };
    else if (url.pathname.endsWith("/search/history")) data = { entries: [] };
    else if (url.pathname.endsWith("/saved-searches")) data = { items: [] };
    else if (url.pathname.endsWith("/mission-views")) data = { items: [] };
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
for (const theme of ["light", "dark"] as const) for (const width of [1440, 390]) test(`priority inbox workflow in ${theme} at ${width}px`, async ({ page }, info) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  const writes = await fixture(page);
  await page.setViewportSize({ width, height: 1000 });
  await page.emulateMedia({ colorScheme: theme });
  await page.goto("/inbox");
  await expect(page.getByRole("heading", { name: "Inbox", exact: true, level: 1 })).toBeVisible();
  const banner = page.getByRole("banner");
  await expect(banner.getByRole("link", { name: "Inbox, 3 unread" })).toBeVisible();
  if (width < 900) {
    await page.getByRole("button", { name: "Open navigation" }).click();
    await expect(page.getByRole("dialog", { name: "Navigation" }).getByRole("link", { name: "Inbox, 3 unread" })).toBeVisible();
    await audit(page, info, "drawer");
    await page.getByRole("button", { name: "Close navigation" }).click();
  } else {
    await expect(page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Inbox, 3 unread" })).toHaveAttribute("aria-current", "page");
  }
  const headings = page.getByRole("heading", { level: 2 });
  await expect(headings).toHaveText([/Agent failures/, /Mission completions/, /New evidence/]);
  await expect(page.getByRole("link", { name: "12 evidence entries" })).toHaveAttribute("href", `/evidence?project_id=${projectId}&mission_id=${doneId}&session_key=worker-run`);
  await expect(page.getByRole("listitem").filter({ hasText: "Validate the sources" }).locator("time")).toHaveText("Sep 13, 5:00 PM");
  await expect(page.getByText("Unread", { exact: true })).toHaveCount(3);
  await audit(page, info, "inbox");
  await page.getByRole("button", { name: "Mark reviewed" }).click();
  await expect(page.getByText("Reviewed", { exact: true })).toBeVisible();
  expect(writes[0]).toEqual({ method: "PUT", pathname: `/api/v1/home/missions/${doneId}/review`, body: { updated_at: "2026-09-13T21:30:00" } });
  await expect(banner.getByRole("link", { name: "Inbox, 2 unread" })).toBeVisible();
  await page.getByRole("button", { name: "Mark all as seen" }).click();
  await expect(banner.getByRole("link", { name: "Inbox", exact: true })).toBeVisible();
  expect(writes[1]).toEqual({ method: "PUT", pathname: "/api/v1/inbox/seen", body: { seen_through: generated } });
  await expect(page.getByText("0 unread")).toBeVisible();
  await expect(page.getByText("Unread", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Mark all as seen" })).toBeDisabled();
  await audit(page, info, "inbox-seen");
  await page.goto("/inbox?section=bogus");
  await expect(page.getByText("Inbox section not found")).toBeVisible();
  await page.goto("/inbox?section=failures");
  await expect(headings).toHaveText([/Agent failures/]);
  expect(errors).toEqual([]);
});

test("failed unread counts never render as zero", async ({ page }) => {
  await fixture(page, { failing: true });
  await page.goto("/inbox");
  await expect(page.getByText("Unread counts could not load.")).toBeVisible();
  await expect(page.getByRole("banner").getByRole("link", { name: "Inbox", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mark all as seen" })).toBeDisabled();
});
