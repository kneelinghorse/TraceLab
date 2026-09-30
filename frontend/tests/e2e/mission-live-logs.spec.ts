import { expect, test } from "@playwright/test";
import path from "node:path";

for (const theme of ["light", "dark"] as const) for (const width of [390, 820, 1440]) {
  test(`owned run observations ${theme} ${width}`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.emulateMedia({ colorScheme: theme });
    await page.addInitScript(theme => {
      localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "fixture", user_id: "reader", email: "reader@example.test", display_name: "Researcher" }));
      localStorage.setItem("tracelab.theme.v1:reader", theme);
    }, theme);
    const state = { id: "live-1", mission_id: "LOG2-FIXTURE", title: "Observed research", objective: "Inspect safe runner observations", success_criteria: ["Cite primary evidence"], project_id: null, status: "in_progress", tags: [], deliverables: [], context: {}, metadata: {}, research_phases: {}, execution_metadata: {}, result_protocol: {}, result_document_ids: [], result_report_id: null, result_markdown: null, created_at: new Date().toISOString(), updated_at: new Date().toISOString() };
    const logs: { id: string; message: string; level: string; logged_at: string; created_at: string; attempt_count: number }[] = [];
    let failure = 0;
    await page.route("**/api/v1/**", async route => {
      const endpoint = new URL(route.request().url()).pathname;
      if (endpoint.includes("/missions/")) expect(route.request().method()).toBe("GET");
      if (endpoint.endsWith("/auth/me")) return route.fulfill({ json: { user_id: "reader", email: "reader@example.test", role: "admin" } });
      if (endpoint.endsWith("/missions/live-1")) return route.fulfill({ json: state });
      if (endpoint.endsWith("/logs")) return route.fulfill({ status: failure || 200, json: failure ? { detail: "fixture outage" } : logs });
      if (endpoint.endsWith("/missions/events/recent")) return route.fulfill({ json: [] });
      return route.fulfill({ json: {} });
    });
    await page.clock.install();
    await page.goto("/missions/live-1");
    await expect(page.getByText("Waiting for the first runner observation.")).toBeVisible();
    for (let i = 0; i < 24; i++) logs.push({ id: `event-${i}`, message: i === 23 ? "Future worker observation remains readable" : JSON.stringify({ phase: "running", event: "mission_progress", count: i }), level: "INFO", logged_at: new Date().toISOString(), created_at: new Date().toISOString(), attempt_count: i < 2 ? 1 : 2 });
    await page.clock.runFor(5100);
    await expect(page.getByText("Receiving runner observations.")).toBeVisible();
    const region = page.getByRole("region", { name: "Recorded log lines" });
    await expect(region.getByText("Attempt 1", { exact: true })).toBeVisible();
    await expect(region.getByText("Attempt 2", { exact: true })).toBeVisible();
    await expect(region).toContainText("Future worker observation remains readable");
    await expect(page.getByRole("progressbar")).toHaveCount(0);
    await region.focus();
    await expect(region).toBeFocused();
    await page.keyboard.press("End");
    await expect.poll(() => region.evaluate(node => node.scrollTop)).toBeGreaterThan(0);
    await page.addScriptTag({ path: path.resolve("node_modules/axe-core/axe.min.js") });
    const audit = await page.evaluate(async () => {
      const axe = (window as unknown as { axe: { run: (node: Document) => Promise<{ violations: { id: string; impact: string }[] }> } }).axe;
      return { overflow: document.documentElement.scrollWidth > innerWidth, violations: (await axe.run(document)).violations.filter(v => ["critical", "serious"].includes(v.impact)) };
    });
    expect(audit).toEqual({ overflow: false, violations: [] });
    await page.evaluate(() => { window.scrollTo({ top: 0, behavior: "instant" }); });
    await page.screenshot({ path: info.outputPath(`live-logs-${theme}-${width}.png`), fullPage: true });
    await page.clock.runFor(35000);
    await expect(page.getByText(/runner may be working quietly/)).toBeVisible();
    failure = 503;
    await page.getByRole("button", { name: "Refresh logs" }).click();
    await expect(page.getByText(/Log refresh failed/)).toBeVisible();
    await expect(region).toContainText("Future worker observation remains readable");
    failure = 403;
    await page.getByRole("button", { name: "Refresh logs" }).click();
    await expect(page.getByText(/Run activity is unavailable for this account/)).toBeVisible();
    await expect(region).toHaveCount(0);
  });
}
