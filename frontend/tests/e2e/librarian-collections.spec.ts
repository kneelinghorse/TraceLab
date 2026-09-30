import { expect, test } from "@playwright/test";
import path from "node:path";

for (const theme of ["light", "dark"]) for (const width of [390, 820, 1440]) {
  test(`reviewed collections ${theme} ${width}`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.addInitScript(({ theme }) => {
      localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "fixture", user_id: "reader", email: "reader@example.test" }));
      localStorage.setItem("tracelab.theme.v1:reader", theme);
    }, { theme });
    await page.emulateMedia({ colorScheme: theme as "light" | "dark" });
    let drafts = 0;
    const accepts: { name: string; member_ids: string[]; proposal_token: string }[] = [];
    const otherWrites: string[] = [];
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    const destination = { owner_id: "reader", workspace_id: "space", space_name: "Default Workspace" };
    const members = [2, 1].map(marker => ({ marker, available: true, chunk_id: `chunk-${marker}`, document_id: `doc-${marker}`, document_name: `Onboarding interview ${marker}`, excerpt: "Researchers want to see the destination before saving and return to the exact source excerpt after reviewing a group.", href: `/documents/doc-${marker}?chunk=chunk-${marker}&index=0` }));
    await page.route("**/api/v1/**", async route => {
      const request = route.request(); const endpoint = new URL(request.url()).pathname;
      let json: unknown = {};
      if (!["GET", "HEAD", "OPTIONS"].includes(request.method()) && !endpoint.includes("/librarian/collections/")) otherWrites.push(endpoint);
      if (endpoint.endsWith("/auth/me")) json = { user_id: "reader", email: "reader@example.test", role: "member" };
      else if (endpoint.endsWith("/projects")) json = { data: [{ id: "project", name: "Onboarding study" }], pagination: { total: 1, pages: 1, page: 1 } };
      else if (endpoint.endsWith("/spaces")) json = [{ id: "space", name: "Personal", personal_owner_id: "reader" }];
      else if (endpoint.endsWith("/descriptions/project")) json = { project_id: "project", description: "Onboarding study.", revision: 0, provenance: null, can_restore: false };
      else if (endpoint.endsWith("/librarian/collections/draft")) {
        drafts++;
        json = { project_id: "project", prompt: "Group feedback by pain point", model: "fixture-model", destination,
          coverage: { readable_documents: 12, documents_with_eligible_chunks: 8, used_documents: 2, readable_chunks: 50, eligible_chunks: 48, used_chunks: 20, excluded_chunks: 2, limited: true, chunk_limit: 20, character_limit: 24000 },
          groups: [{ group_id: "one", proposal_token: "signed-one", name: "Source navigation", description: "Feedback about finding and keeping source context", rationale: "These excerpts discuss source navigation [2] [1].", members }, { group_id: "two", proposal_token: "signed-two", name: "Optional follow-up", description: "Another grouping to review", rationale: "A navigation example [1].", members: [members[1]] }],
        };
      } else if (endpoint.endsWith("/librarian/collections/accept")) {
        const body = request.postDataJSON(); accepts.push(body);
        json = { collection_id: "one", name: body.name, href: "/collections/one", state: accepts.length === 1 ? "partial" : "saved", completed_member_ids: accepts.length === 1 ? [] : body.member_ids, missing_member_ids: accepts.length === 1 ? body.member_ids : [], destination };
      }
      await route.fulfill({ json });
    });
    await page.goto("/librarian?project=project");
    await page.getByLabel("How should the research be organised?").fill("Group feedback by pain point");
    expect(drafts).toBe(0); expect(accepts).toEqual([]);
    await page.getByRole("button", { name: "Suggest collections" }).click();
    await expect(page.getByRole("region", { name: "Review suggested collections", exact: true })).toBeFocused();
    const first = page.getByRole("article", { name: "Suggested collection 1" });
    const second = page.getByRole("article", { name: "Suggested collection 2" });
    await page.getByLabel("Collection name 1", { exact: true }).fill("Reviewed onboarding feedback");
    await page.getByRole("checkbox", { name: "Include excerpt 2 in collection 1", exact: true }).uncheck();
    await second.getByRole("button", { name: "Dismiss group" }).click();
    expect(accepts).toEqual([]);
    await page.reload();
    await expect(page.getByLabel("Collection name 1", { exact: true })).toHaveValue("Reviewed onboarding feedback");
    expect(drafts).toBe(1);
    await first.getByRole("link", { name: "Open excerpt [1]" }).focus();
    await expect(first.getByRole("link", { name: "Open excerpt [1]" })).toHaveAttribute("href", "/documents/doc-1?chunk=chunk-1&index=0");
    await first.getByRole("button", { name: "Accept this collection" }).focus(); await page.keyboard.press("Enter");
    await expect(first.getByRole("button", { name: "Retry 1 missing excerpts" })).toBeVisible();
    await page.reload();
    await first.getByRole("button", { name: "Retry 1 missing excerpts" }).click();
    await expect(page.getByText("Reviewed collection saved.", { exact: true })).toBeVisible();
    expect(accepts).toHaveLength(2);
    expect(accepts[0]).toEqual(accepts[1]);
    expect(accepts[0]).toMatchObject({ name: "Reviewed onboarding feedback", member_ids: ["chunk-1"], proposal_token: "signed-one" });
    await expect(first.getByRole("link", { name: "Reviewed onboarding feedback" })).toHaveAttribute("href", "/collections/one");
    await page.addScriptTag({ path: path.resolve("node_modules/axe-core/axe.min.js") });
    const audit = await page.evaluate(async () => {
      const axe = (window as unknown as { axe: { run: (node: Document) => Promise<{ violations: { id: string; impact: string }[] }> } }).axe;
      return { overflow: document.documentElement.scrollWidth > innerWidth, violations: (await axe.run(document)).violations.filter(v => ["serious", "critical"].includes(v.impact)) };
    });
    expect(audit).toEqual({ overflow: false, violations: [] });
    await page.getByRole("region", { name: "Organise research", exact: true }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: info.outputPath("reviewed-collection.png") });
    expect(drafts).toBe(1); expect(otherWrites).toEqual([]); expect(errors).toEqual([]);
  });
}
