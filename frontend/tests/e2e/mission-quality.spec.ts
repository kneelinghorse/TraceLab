import { expect, test } from "@playwright/test";
import path from "node:path";
import fixtures from "../fixtures/mission-quality.json";

for (const theme of ["light", "dark"]) for (const width of [390, 1440]) {
  test(`research quality remains readable and honest in ${theme} at ${width}`, async ({ page }, info) => {
    test.setTimeout(60_000);
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(theme => {
      localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "fixture", user_id: "reader", email: "reader@example.test", display_name: "Researcher" }));
      localStorage.setItem("tracelab.theme.v1:reader", theme);
    }, theme);
    const base = { id: "quality", mission_id: "QUALITY-FIXTURE", title: "Research with recorded quality", objective: "Understand the evidence", success_criteria: [], project_id: null, project_name: null, tags: [], deliverables: [], context: {}, metadata: {}, research_phases: {}, result_document_ids: [], result_report_id: null, created_at: "2026-10-08T00:00:00Z", updated_at: "2026-10-08T01:00:00Z" };
    let current: Record<string, unknown> = {};
    await page.route("**/api/v1/**", async route => {
      const endpoint = new URL(route.request().url()).pathname;
      let json: unknown = {};
      if (endpoint.endsWith("/auth/me")) json = { user_id: "reader", email: "reader@example.test", role: "member" };
      else if (endpoint.endsWith("/missions/quality")) json = current;
      else if (endpoint.endsWith("/logs") || endpoint.endsWith("/events/recent")) json = [];
      await route.fulfill({ json });
    });
    for (const [name, fixture] of Object.entries(fixtures)) {
      if (name === "provenance") continue;
      current = { ...base, ...fixture };
      await page.goto("/missions/quality?tab=results");
      const quality = page.getByRole("region", { name: "Research quality", exact: true });
      await expect(quality).toBeVisible();
      await expect(quality).not.toContainText(/%|percent/);
      await expect(page.getByRole("heading", { name: "Retained result" })).toBeVisible();
      if (name === "supported_sample") {
        await expect(quality).toContainText("No detected material issue");
        await expect(quality).toContainText("Sampled verification; report-wide accuracy unknown");
      } else if (name === "legacy_uncertainty") await expect(quality).toContainText("Quality not assessed for this run");
      else if (name === "live_warning") await expect(quality).toContainText("3 claims were not assessed.");
      else if (name === "missing_cited_body") await expect(quality).toContainText("1 cited source has no readable body.");
      else if (name === "failed_retained_memory") {
        const failure = page.getByRole("region", { name: "Provider failure details", exact: true });
        await expect(failure).toContainText("Provider failed again during retained-memory finalization.");
        await expect(failure).toContainText("Invalid message structure");
        await expect(failure).toContainText("Provider message pattern");
        await expect(failure).toContainText("Request shape available.");
      } else if (name === "legacy_schema5_unknown") await expect(quality).toContainText("Verification scope unknown; report-wide accuracy unknown");
      await page.addScriptTag({ path: path.resolve("node_modules/axe-core/axe.min.js") });
      const audit = await page.evaluate(async () => {
        const axe = (window as unknown as { axe: { run: (node: Document) => Promise<{ violations: { impact: string }[] }> } }).axe;
        return { overflow: document.documentElement.scrollWidth > innerWidth, violations: (await axe.run(document)).violations.filter(v => ["critical", "serious"].includes(v.impact)) };
      });
      expect(audit).toEqual({ overflow: false, violations: [] });
      await page.screenshot({ path: info.outputPath(`${name}-results.png`), fullPage: true });
      await page.getByRole("tab", { name: "Details", exact: true }).click();
      const raw = page.locator("details").filter({ has: page.getByText("Raw quality data", { exact: true }) });
      await expect(raw).not.toHaveAttribute("open");
      await raw.locator("summary").focus();
      await page.keyboard.press("Enter");
      await expect(raw).toHaveAttribute("open", "");
      await expect(raw.locator("pre")).toContainText("quality_record");
      await page.keyboard.press("Tab");
      await expect(raw.locator("pre")).toBeFocused();
      const detailsAudit = await page.evaluate(async () => {
        const axe = (window as unknown as { axe: { run: (node: Document) => Promise<{ violations: { impact: string }[] }> } }).axe;
        return { overflow: document.documentElement.scrollWidth > innerWidth, violations: (await axe.run(document)).violations.filter(v => ["critical", "serious"].includes(v.impact)) };
      });
      expect(detailsAudit).toEqual({ overflow: false, violations: [] });
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: info.outputPath(`${name}-raw.png`), fullPage: true });
    }
  });
}
