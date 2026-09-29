import { expect, test } from "@playwright/test";
import path from "node:path";

for (const theme of ["light", "dark"]) for (const width of [390, 820, 1440]) {
  test(`reviewed project description ${theme} ${width}`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.addInitScript(({ theme }) => {
      localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "fixture", user_id: "reader", email: "reader@example.test" }));
      localStorage.setItem("tracelab.theme.v1:reader", theme);
    }, { theme });
    await page.emulateMedia({ colorScheme: theme as "light" | "dark" });
    let generations = 0;
    let acceptances = 0;
    const original = "Original human description";
    let current = original;
    let provenance: Record<string, unknown> | null = null;
    const citations = [{ marker: 1, available: true, href: "/documents/source?chunk=chunk&index=0", excerpt: "Interviews show confusing onboarding steps." }];
    await page.route("**/api/v1/**", async route => {
      const endpoint = new URL(route.request().url()).pathname;
      let json: unknown = {};
      if (endpoint.endsWith("/auth/me")) json = { user_id: "reader", email: "reader@example.test", role: "admin" };
      else if (endpoint.endsWith("/projects")) json = { data: [{ id: "project", name: "Onboarding study", description: current }], pagination: { total: 1, pages: 1, page: 1 } };
      else if (endpoint.endsWith("/spaces")) json = [{ id: "space", name: "Personal", personal_owner_id: "reader" }];
      else if (endpoint.endsWith("/descriptions/draft")) {
        generations++;
        json = { project_id: "project", proposal_token: "fixture", description: "This project investigates confusing onboarding steps [1].", current_description: current, prompt: "Describe the onboarding study", basis: "corpus", model: "fixture", citations, coverage: { readable_chunks: 20, used_chunks: 12, excluded_chunks: 0, eligible_chunks: 20, limited: true, chunk_limit: 12, character_limit: 24000 } };
      } else if (endpoint.includes("/descriptions/")) {
        if (endpoint.endsWith("/accept")) {
          acceptances++;
          current = route.request().postDataJSON().description;
          provenance = { proposal_id: "proposal", current: true, edited: false, model: "fixture", accepted_at: "2026-09-29T00:00:00Z", previous_value: original, prompt: "Describe the onboarding study", citations };
        } else if (endpoint.endsWith("/restore")) { current = original; provenance = null; }
        json = { project_id: "project", description: current, revision: acceptances, provenance, can_restore: Boolean(provenance) };
      }
      await route.fulfill({ json });
    });
    await page.goto("/librarian?project=project");
    await expect(page.getByText(original)).toBeVisible();
    expect(generations).toBe(0);
    await page.getByLabel("What should the description explain?").fill("Describe the onboarding study");
    await page.getByRole("button", { name: "Draft description", exact: true }).click();
    await expect(page.getByRole("region", { name: "Review description" })).toBeFocused();
    await page.reload();
    await expect(page.getByLabel("Proposed description (editable)")).toHaveValue(/onboarding steps/);
    expect(generations).toBe(1);
    expect(acceptances).toBe(0);
    await page.addScriptTag({ path: path.resolve("node_modules/axe-core/axe.min.js") });
    const audit = await page.evaluate(async () => {
      const axe = (window as unknown as { axe: { run: (node: Document) => Promise<{ violations: { id: string; impact: string }[] }> } }).axe;
      return { overflow: document.documentElement.scrollWidth > innerWidth, violations: (await axe.run(document)).violations.filter(v => ["serious", "critical"].includes(v.impact)) };
    });
    expect(audit).toEqual({ overflow: false, violations: [] });
    await page.screenshot({ path: info.outputPath("description-review.png"), fullPage: true });
    const accept = page.getByRole("button", { name: "Accept description" });
    await accept.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByText(/Machine drafted · Human accepted/)).toBeVisible();
    expect(acceptances).toBe(1);
    expect(generations).toBe(1);
    await page.getByRole("button", { name: "Restore previous description" }).click();
    await expect(page.getByText(original)).toBeVisible();
    expect(generations).toBe(1);
  });
}
