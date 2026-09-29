import { expect, test } from "@playwright/test";
import path from "node:path";

for (const theme of ["light", "dark"]) for (const width of [390, 820, 1440]) {
  test(`duplicate review ${theme} ${width}`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.addInitScript(({ theme }) => {
      localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "fixture", user_id: "reader", email: "reader@example.test" }));
      localStorage.setItem("tracelab.theme.v1:reader", theme);
    }, { theme });
    await page.emulateMedia({ colorScheme: theme as "light" | "dark" });
    let scans = 0;
    let comparisons = 0;
    const corpusWrites: string[] = [];
    const pair = { candidate_id: "pair", kind: "probable_overlap", score: 0.92,
      documents: [{ id: "a", name: "Onboarding interviews — original", href: "/documents/a" }, { id: "b", name: "Onboarding interviews — edited", href: "/documents/b" }],
      basis: "92% five-word phrase overlap across two distinct passages.",
      evidence: [{ left_excerpt: "Researchers found the first upload difficult to discover. They wanted a visible destination and confirmation.", right_excerpt: "Researchers found the initial upload difficult to discover. They wanted a visible destination and confirmation." }],
      recommendation: "Compare source dates and annotations. Keep both if either adds useful context. This review changes neither document.",
    };
    await page.route("**/api/v1/**", async route => {
      const request = route.request();
      const endpoint = new URL(request.url()).pathname;
      let json: unknown = {};
      if (!["GET", "HEAD", "OPTIONS"].includes(request.method()) && !endpoint.includes("/duplicates/")) corpusWrites.push(endpoint);
      if (endpoint.endsWith("/auth/me")) json = { user_id: "reader", email: "reader@example.test", role: "admin" };
      else if (endpoint.endsWith("/projects")) json = { data: [{ id: "project", name: "Onboarding study" }], pagination: { total: 1, pages: 1, page: 1 } };
      else if (endpoint.endsWith("/spaces")) json = [{ id: "space", name: "Personal", personal_owner_id: "reader" }];
      else if (endpoint.endsWith("/descriptions/project")) json = { project_id: "project", description: "A study of onboarding.", revision: 0, provenance: null, can_restore: false };
      else if (endpoint.endsWith("/duplicates/scan")) {
        scans++;
        json = { project_id: "project", method: "fixture", scanned_at: "2026-09-29T00:00:00Z", candidates: [pair], coverage: { readable_documents: 120, scanned_documents: 100, examined_documents: 90, empty_documents: 8, overlong_documents: 2, exact_only_documents: 4, limited: true, document_limit: 100, character_limit: 20000, candidate_count: 1, candidates_limited: false, pair_limit: 20 } };
      } else if (endpoint.endsWith("/duplicates/compare")) {
        comparisons++;
        json = { candidate: pair, documents: pair.documents.map(doc => ({ ...doc, content: "Current extracted text. Researchers want a clear upload destination and explicit acceptance before changing their library.\n\nThey also want to keep source links visible while reviewing a collection." })) };
      }
      await route.fulfill({ json });
    });
    await page.goto("/librarian?project=project");
    await page.getByRole("button", { name: "Find possible duplicates" }).waitFor();
    expect(scans).toBe(0);
    await page.getByRole("button", { name: "Find possible duplicates" }).click();
    await expect(page.getByRole("region", { name: "Duplicate results" })).toBeFocused();
    await page.reload();
    await expect(page.getByText("Probable text overlap", { exact: true })).toBeVisible();
    expect(scans).toBe(1);
    const compare = page.getByRole("button", { name: "Compare sources" });
    await compare.focus(); await page.keyboard.press("Enter");
    await expect(page.getByRole("region", { name: "Compare documents" })).toBeFocused();
    expect(comparisons).toBe(1);
    await page.addScriptTag({ path: path.resolve("node_modules/axe-core/axe.min.js") });
    const audit = await page.evaluate(async () => {
      const axe = (window as unknown as { axe: { run: (node: Document) => Promise<{ violations: { id: string; impact: string }[] }> } }).axe;
      return { overflow: document.documentElement.scrollWidth > innerWidth, violations: (await axe.run(document)).violations.filter(v => ["serious", "critical"].includes(v.impact)) };
    });
    expect(audit).toEqual({ overflow: false, violations: [] });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: info.outputPath("duplicate-comparison.png"), fullPage: true });
    await page.getByRole("button", { name: "Close comparison" }).click();
    await expect(compare).toBeFocused();
    await page.getByRole("button", { name: "Keep both", exact: true }).click();
    await page.reload();
    await expect(page.getByText(/1 pairs reviewed/)).toBeVisible();
    expect(scans).toBe(1); expect(comparisons).toBe(1); expect(corpusWrites).toEqual([]);
  });
}
