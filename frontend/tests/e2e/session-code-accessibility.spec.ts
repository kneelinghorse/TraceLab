import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

async function audit(page: Page) {
  await page.addScriptTag({ path: path.resolve("node_modules/axe-core/axe.min.js") });
  const result = await page.evaluate(async () => {
    const axe = (window as unknown as { axe: { run: (node: Document) => Promise<{ violations: { id: string; impact: string }[] }> } }).axe;
    return { overflow: document.documentElement.scrollWidth > innerWidth, violations: (await axe.run(document)).violations.filter(v => ["serious", "critical"].includes(v.impact)) };
  });
  expect(result).toEqual({ overflow: false, violations: [] });
}

for (const transport of ["json", "download"]) for (const theme of ["light", "dark"] as const) for (const width of [390, 820, 1440]) {
  test(`disabled session and scrollable code ${transport} ${theme} ${width}`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.emulateMedia({ colorScheme: theme });
    await page.addInitScript(({ theme }) => {
      if (!sessionStorage.getItem("fixture-initialized")) {
        localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "dedicated-disabled-fixture", user_id: "fixture-member", email: "fixture@example.test", display_name: "Private fixture member" }));
        localStorage.setItem("tracelab.theme.v1:fixture-member", theme);
        sessionStorage.setItem("fixture-initialized", "true");
      }
      Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: async (text: string) => { (window as unknown as { copied: string }).copied = text; } } });
    }, { theme });
    const line = 'const measurement = "' + "preserve_whitespace_and_content_".repeat(20) + '";';
    const columns = Array.from({ length: 12 }, (_, index) => `MeasurementColumn${index}`);
    const content = `Private fixture research.\n\n\`\`\`js\n${line}\n\`\`\`\n\n| ${columns.join(" | ")} |\n| ${columns.map(() => "---").join(" | ")} |\n| ${columns.map(() => "MeasuredValue").join(" | ")} |`;
    const report = { id: "fixture", title: "Keyboard research fixture", content, status: "draft", report_type: "summary", tokens_used: 50, chunk_count: 0, sources: [], citations: [], citation_status: "unavailable", created_at: "2026-09-29T00:00:00Z", updated_at: "2026-09-29T00:00:00Z" };
    let rejection: "none" | "ordinary" | "disabled" = "none";
    await page.route("**/api/v1/**", async route => {
      const endpoint = new URL(route.request().url()).pathname;
      const target = transport === "json" ? "/reports/fixture" : "/reports/fixture/export";
      if (endpoint.endsWith(target) && rejection !== "none") return route.fulfill({ status: 403, json: { detail: rejection === "disabled" ? "Account is disabled" : "Project access denied" } });
      let json: unknown = {};
      if (endpoint.endsWith("/auth/me")) json = { user_id: "fixture-member", email: "fixture@example.test", role: "member" };
      else if (endpoint.endsWith("/reports/fixture")) json = report;
      else if (endpoint.endsWith("/evidence")) json = { entries: [], notes: [], entry_total: 0, note_total: 0, page: 1, page_size: 20 };
      await route.fulfill({ json });
    });
    await page.goto("/reports/fixture");
    await expect(page.getByRole("heading", { name: report.title })).toBeVisible();
    for (const label of ["Scrollable code block", "Scrollable table"]) {
      const region = page.getByRole("region", { name: label });
      for (let index = 0; index < 60 && !(await region.evaluate(element => element === document.activeElement)); index++) await page.keyboard.press("Tab");
      await expect(region).toBeFocused();
      expect(await region.evaluate(element => element.scrollWidth > element.clientWidth)).toBe(true);
      expect(await region.evaluate(element => getComputedStyle(element).outlineStyle !== "none" && parseFloat(getComputedStyle(element).outlineWidth) >= 2)).toBe(true);
      await page.keyboard.press("ArrowRight");
      await expect.poll(() => region.evaluate(element => element.scrollLeft)).toBeGreaterThan(0);
    }
    expect(await page.locator("pre code").textContent()).toBe(line + "\n");
    await page.getByRole("button", { name: "Copy", exact: true }).click();
    expect(await page.evaluate(() => (window as unknown as { copied: string }).copied)).toBe(content);
    await audit(page);
    await page.screenshot({ path: info.outputPath("code-table.png"), fullPage: true });

    async function exportReport() {
      await page.getByRole("button", { name: "Export ▾", exact: true }).click();
      await page.getByRole("button", { name: "Markdown (.md)", exact: true }).click();
    }
    rejection = "ordinary";
    if (transport === "json") await page.reload(); else await exportReport();
    if (transport === "json") await expect(page.getByText("Report could not be loaded.")).toBeVisible();
    else await expect(page.getByRole("alert").filter({ hasText: "Project access denied" })).toBeVisible();
    expect(await page.evaluate(() => localStorage.getItem("tracelab.auth.v2"))).not.toBeNull();
    await expect(page.getByRole("heading", { name: "Sign in", exact: true })).toHaveCount(0);

    rejection = "disabled";
    if (transport === "json") await page.getByRole("button", { name: "Retry", exact: true }).click(); else await exportReport();
    await expect(page.getByRole("heading", { name: "Sign in", exact: true })).toBeVisible();
    expect(await page.evaluate(() => localStorage.getItem("tracelab.auth.v2"))).toBeNull();
    await expect(page.getByText("Private fixture research.")).toHaveCount(0);
    await expect(page.locator(".app-workspace")).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Forgot password?", exact: true })).toBeVisible();
    await audit(page);
    await page.screenshot({ path: info.outputPath("signed-out.png"), fullPage: true });
    await page.reload();
    await expect(page.getByRole("heading", { name: "Sign in", exact: true })).toBeVisible();
    await page.getByRole("link", { name: "Forgot password?", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Forgot password?", exact: true })).toBeVisible();
    await audit(page);
  });
}
