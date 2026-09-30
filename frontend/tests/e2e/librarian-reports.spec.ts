import { expect, test } from "@playwright/test";
import path from "node:path";

for (const theme of ["light", "dark"]) for (const width of [390, 820, 1440]) {
  test(`reviewed report ${theme} ${width}`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.addInitScript(({ theme }) => {
      localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "fixture", user_id: "reader", email: "reader@example.test" }));
      localStorage.setItem("tracelab.theme.v1:reader", theme);
    }, { theme });
    await page.emulateMedia({ colorScheme: theme as "light" | "dark" });
    let drafts = 0;
    const accepts: unknown[] = [], otherWrites: string[] = [], errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    const members = [1, 2].map(marker => ({ marker, chunk_id: `chunk-${marker}`, document_name: `Interview ${marker}`, characters: 100,
      text: "Researchers want to know the destination project before saving and return to the exact excerpt after reviewing.", href: `/documents/doc-${marker}?chunk=chunk-${marker}&index=0` }));
    await page.route("**/api/v1/**", async route => {
      const request = route.request(), endpoint = new URL(request.url()).pathname;
      let json: unknown = {}, status = 200;
      if (!["GET", "HEAD", "OPTIONS"].includes(request.method()) && !endpoint.includes("/librarian/reports/")) otherWrites.push(endpoint);
      if (endpoint.endsWith("/auth/me")) json = { user_id: "reader", email: "reader@example.test", role: "member" };
      else if (endpoint.endsWith("/projects")) json = { data: [{ id: "project", name: "Onboarding study" }], pagination: { total: 1, pages: 1, page: 1 } };
      else if (endpoint.endsWith("/spaces")) json = [{ id: "space", name: "Personal", personal_owner_id: "reader" }];
      else if (endpoint.endsWith("/descriptions/project")) json = { project_id: "project", description: "Onboarding study.", revision: 0, provenance: null, can_restore: false };
      else if (endpoint.endsWith("/collections")) json = { data: [{ id: "collection", name: "Reviewed feedback", item_count: 2 }], total: 1 };
      else if (endpoint.endsWith("/librarian/reports/sources")) json = {
        project_id: "project", collection_id: "collection", collection_name: "Reviewed feedback", source_token: "reviewed-inputs", members,
        coverage: { readable_chunks: 2, eligible_chunks: 2, excluded_chunks: 0, other_project_chunks: 1, listed_chunks: 2, limited: false, candidate_limit: 100, chunk_limit: 12, character_limit: 24000 },
      };
      else if (endpoint.endsWith("/librarian/reports/draft")) {
        drafts++;
        const input = request.postDataJSON();
        expect(input.reviewed_sources).toBe(true);
        expect(input.chunk_ids).toEqual(["chunk-2"]);
        json = { project_id: "project", report_id: "report", title: input.title, prompt: input.prompt, format: input.format, model: "fixture", generated_at: "2026-09-30T00:00:00Z",
          proposal_token: `signed-preview-${drafts}`, content: "# Feedback\n\nThe source describes navigation uncertainty [2].", input_chunk_ids: input.chunk_ids, input_characters: 100,
          citations: [{ marker: 2, available: true, href: members[1].href }] };
      } else if (endpoint.endsWith("/librarian/reports/accept")) {
        accepts.push(request.postDataJSON());
        if (accepts.length === 1) { status = 503; json = { detail: "Connection interrupted. Retry the same reviewed preview." }; }
        else json = { report_id: "report", title: "Reviewed navigation report", href: "/reports/report" };
      }
      await route.fulfill({ status, json });
    });
    await page.goto("/librarian?project=project");
    const panel = page.getByRole("region", { name: "Draft a report", exact: true });
    await panel.getByLabel("Report title", { exact: true }).fill("Navigation report");
    await panel.getByLabel("What should the report explain?").fill("Summarise navigation feedback");
    await panel.getByRole("button", { name: "Browse collections" }).click();
    await panel.getByLabel("Report source set").selectOption("collection");
    await panel.getByRole("button", { name: "Load excerpts for review" }).click();
    await expect(panel.getByText(/1 readable excerpts from other projects excluded/)).toBeVisible();
    expect(drafts).toBe(0); expect(accepts).toEqual([]);
    await panel.getByRole("checkbox", { name: "Use report excerpt 2" }).check();
    await expect(panel.getByRole("button", { name: "Draft cited report" })).toBeDisabled();
    await panel.getByRole("checkbox", { name: "I reviewed the selected excerpts from Onboarding study." }).check();
    await panel.getByRole("button", { name: "Draft cited report" }).focus(); await page.keyboard.press("Enter");
    const preview = panel.getByRole("region", { name: "Review report draft", exact: true });
    await expect(preview).toBeFocused();
    await panel.getByLabel("Report title", { exact: true }).fill("Reviewed navigation report");
    await expect(panel.getByRole("button", { name: "Save reviewed report" })).toBeDisabled();
    await panel.getByRole("button", { name: "Draft report again" }).click();
    await expect(preview.getByRole("heading", { name: "Reviewed navigation report" })).toBeVisible();
    await page.reload();
    await expect(preview.getByRole("heading", { name: "Reviewed navigation report" })).toBeVisible();
    expect(drafts).toBe(2); expect(accepts).toEqual([]);
    await preview.getByRole("link", { name: "[2] Open report source excerpt" }).focus();
    await expect(preview.getByRole("link", { name: "[2] Open report source excerpt" })).toHaveAttribute("href", members[1].href);
    await preview.getByRole("button", { name: "Save reviewed report" }).focus(); await page.keyboard.press("Enter");
    await expect(panel.getByRole("alert")).toContainText("Retry the same reviewed preview");
    await page.reload();
    await preview.getByRole("button", { name: "Save reviewed report" }).click();
    await expect(preview.getByRole("link", { name: "Reviewed navigation report" })).toHaveAttribute("href", "/reports/report");
    expect(accepts).toEqual([{ project_id: "project", proposal_token: "signed-preview-2" }, { project_id: "project", proposal_token: "signed-preview-2" }]);
    expect(drafts).toBe(2); expect(otherWrites).toEqual([]); expect(errors).toEqual([]);
    await page.addScriptTag({ path: path.resolve("node_modules/axe-core/axe.min.js") });
    const audit = await page.evaluate(async () => {
      const axe = (window as unknown as { axe: { run: (node: Document) => Promise<{ violations: { id: string; impact: string }[] }> } }).axe;
      return { overflow: document.documentElement.scrollWidth > innerWidth, violations: (await axe.run(document)).violations.filter(v => ["serious", "critical"].includes(v.impact)) };
    });
    expect(audit).toEqual({ overflow: false, violations: [] });
    await preview.scrollIntoViewIfNeeded();
    await page.screenshot({ path: info.outputPath("reviewed-report.png") });
  });
}
