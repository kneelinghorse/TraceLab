import { expect, test } from "@playwright/test";
import path from "node:path";

const tools = [
  ["describe", "Describe this project", "Project description"],
  ["duplicates", "Find duplicates", "Duplicate review"],
  ["collections", "Suggest collections", "Organise research"],
  ["report", "Write a report", "Draft a report"],
] as const;

for (const theme of ["light", "dark"]) for (const width of [390, 1440]) {
  test(`conversation and tool navigation ${theme} ${width}`, async ({ page }, info) => {
    test.setTimeout(60_000);
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(theme => {
      localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "fixture", user_id: "reader", email: "reader@example.test" }));
      localStorage.setItem("tracelab.theme.v1:reader", theme);
    }, theme);
    const project = { id: "project", name: "Onboarding study", description: "Research onboarding friction.", status: "active", created_at: "2026-10-01T00:00:00Z" };
    const errors: string[] = [], writes: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.route("**/api/v1/**", async route => {
      const request = route.request(), endpoint = new URL(request.url()).pathname;
      let json: unknown = {};
      if (endpoint.endsWith("/auth/me")) json = { user_id: "reader", email: "reader@example.test", role: "member" };
      else if (endpoint.endsWith("/projects")) json = { data: [project], pagination: { total: 1, pages: 1, page: 1 } };
      else if (endpoint.endsWith("/projects/project")) json = project;
      else if (endpoint.endsWith("/projects/project/stats")) json = { project_id: "project", name: project.name, document_count: 2, chunk_count: 4, report_count: 0, total_tokens: 800 };
      else if (endpoint.endsWith("/favorites")) json = { total: 0, items: [] };
      else if (endpoint.endsWith("/spaces")) json = [{ id: "space", name: "Personal", personal_owner_id: "reader" }];
      else if (endpoint.endsWith("/descriptions/project")) json = { project_id: "project", description: project.description, revision: 0, provenance: null, can_restore: false };
      else if (endpoint.endsWith("/librarian/turns")) json = { segments: [{ kind: "prose", text: "Start with who abandons and when.", citations: [] }], suggested_action: null, evidence: [], withheld_count: 0, usage: null, model: "fixture" };
      if (!["GET", "HEAD", "OPTIONS"].includes(request.method())) writes.push(endpoint);
      await route.fulfill({ json });
    });
    const composer = page.getByRole("textbox", { name: "Message the Librarian", exact: true });
    async function composerAboveFold() {
      await expect(composer).toBeVisible();
      const box = await composer.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.y).toBeGreaterThanOrEqual(0);
      expect(box!.y + box!.height).toBeLessThanOrEqual(900);
      expect(await page.evaluate(() => scrollY)).toBe(0);
    }
    async function capture(name: string) {
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.addScriptTag({ path: path.resolve("node_modules/axe-core/axe.min.js") });
      const audit = await page.evaluate(async () => {
        const axe = (window as unknown as { axe: { run: (node: Document) => Promise<{ violations: { id: string; impact: string }[] }> } }).axe;
        return { overflow: document.documentElement.scrollWidth > innerWidth, violations: (await axe.run(document)).violations.filter(v => ["serious", "critical"].includes(v.impact)) };
      });
      expect(audit).toEqual({ overflow: false, violations: [] });
      await page.screenshot({ path: info.outputPath(`${name}.png`), fullPage: true });
    }
    await page.goto("/librarian");
    await expect(page.getByRole("button", { name: "No project chosen" })).toBeVisible();
    await expect(page.getByText("More with this project", { exact: true })).toHaveCount(0);
    await composerAboveFold();
    await capture("no-project");
    await page.goto("/projects/project");
    await expect(page.getByRole("link", { name: "Review description and its drafting history" })).toHaveAttribute("href", "/librarian?project=project&tool=describe");
    await page.getByRole("link", { name: "Ask the Librarian" }).click();
    await expect(page.getByRole("button", { name: "About: Onboarding study" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Where you are" })).toHaveCount(0);
    for (const [, , region] of tools) await expect(page.getByRole("region", { name: region, exact: true })).toHaveCount(0);
    await composerAboveFold();
    await capture("conversation-empty");
    await composer.fill("Why do users leave onboarding?");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(page.getByRole("log")).toContainText("Start with who abandons and when.");
    await composer.fill("An unfinished follow-up");
    await page.evaluate(() => window.scrollTo(0, 0));
    await composerAboveFold();
    await capture("conversation-restored");
    for (const [tool, label, region] of tools) {
      const chooser = page.getByText("More with this project", { exact: true });
      await chooser.focus(); await page.keyboard.press("Enter");
      if (tool === "describe") await capture("chooser");
      await page.getByRole("link", { name: new RegExp(`^${label}`) }).click();
      await expect(page).toHaveURL(new RegExp(`tool=${tool}$`));
      await expect(page.getByRole("region", { name: region, exact: true })).toBeVisible();
      await expect(page.getByRole("region", { name: "Conversation with the Librarian" })).toHaveCount(0);
      for (const [other, , otherRegion] of tools) if (other !== tool) await expect(page.getByRole("region", { name: otherRegion, exact: true })).toHaveCount(0);
      await capture(tool);
      await page.goBack();
      await expect(composer).toHaveValue("An unfinished follow-up");
      await expect(page.getByRole("log")).toContainText("Start with who abandons and when.");
      await page.goForward();
      await expect(page.getByRole("region", { name: region, exact: true })).toBeVisible();
      await page.getByRole("link", { name: "Back to conversation" }).click();
      await expect(composer).toHaveValue("An unfinished follow-up");
    }
    expect(errors).toEqual([]);
    expect(writes).toEqual(["/api/v1/librarian/turns"]);
  });
}
