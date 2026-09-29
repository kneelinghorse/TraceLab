import { expect, test } from "@playwright/test";
import path from "node:path";

for (const theme of ["light", "dark"]) for (const width of [390, 820, 1440]) {
  test(`durable report citations ${theme} ${width}`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.addInitScript(({ theme }) => {
      localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "fixture", user_id: "reader", email: "reader@example.test" }));
      localStorage.setItem("tracelab.theme.v1:reader", theme);
    }, { theme });
    await page.emulateMedia({ colorScheme: theme as "light" | "dark" });
    const stamp = "2026-09-29T00:00:00Z";
    const report = { id: "report", title: "A report with durable citations", content: "# Findings\n\nThe first source records a useful finding [1]. The third source has become unavailable [3].", status: "draft", report_type: "summary", tokens_used: 50, chunk_count: 3, sources: [], created_at: stamp, updated_at: stamp, citation_status: "validated", citations: [
      { marker: 1, available: true, chunk_id: "chunk", document_id: "doc", href: "/documents/doc?chunk=chunk&index=0", excerpt: "A useful finding retained from the reviewed source." },
      { marker: 3, available: false, chunk_id: null, document_id: null, href: null, excerpt: "" },
    ] };
    await page.route("**/api/v1/**", async route => {
      const endpoint = new URL(route.request().url()).pathname;
      let json: unknown = {};
      if (endpoint.endsWith("/auth/me")) json = { user_id: "reader", email: "reader@example.test", role: "admin" };
      else if (endpoint.endsWith("/reports/report")) json = report;
      else if (endpoint.endsWith("/evidence")) json = { entries: [], notes: [], entry_total: 0, note_total: 0, page: 1, page_size: 20 };
      await route.fulfill({ json });
    });
    await page.goto("/reports/report");
    const source = page.getByRole("link", { name: "[1] Open source excerpt" });
    await expect(source).toHaveAttribute("href", "/documents/doc?chunk=chunk&index=0");
    await expect(page.getByText(/\[3\] Source unavailable/)).toBeVisible();
    await expect(page.getByRole("link", { name: /\[3\]/ })).toHaveCount(0);
    // Reach the citation using keyboard navigation, not a pointer-only path.
    for (let i = 0; i < 40 && !(await source.evaluate(el => el === document.activeElement)); i++) await page.keyboard.press("Tab");
    await expect(source).toBeFocused();
    await page.addScriptTag({ path: path.resolve("node_modules/axe-core/axe.min.js") });
    const audit = await page.evaluate(async () => {
      const axe = (window as unknown as { axe: { run: (node: Document) => Promise<{ violations: { id: string; impact: string }[] }> } }).axe;
      return { overflow: document.documentElement.scrollWidth > innerWidth, violations: (await axe.run(document)).violations.filter(v => ["serious", "critical"].includes(v.impact)) };
    });
    expect(audit).toEqual({ overflow: false, violations: [] });
    await page.screenshot({ path: info.outputPath("report-citations.png"), fullPage: true });
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/documents\/doc\?chunk=chunk&index=0$/);
  });
}
