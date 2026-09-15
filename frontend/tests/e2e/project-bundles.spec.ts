import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

async function accessible(page: Page) {
  await page.addScriptTag({ path: path.resolve("node_modules/axe-core/axe.min.js") });
  const result = await page.evaluate(async () => {
    const axe = (window as unknown as { axe: { run: (node: Document) => Promise<{ violations: { id: string; impact: string }[] }> } }).axe;
    return { overflow: document.documentElement.scrollWidth > innerWidth, violations: (await axe.run(document)).violations.filter(v => ["critical", "serious"].includes(v.impact)) };
  });
  expect(result).toEqual({ overflow: false, violations: [] });
}

for (const theme of ["light", "dark"] as const) for (const width of [390, 820, 1440]) {
  test(`project tabs, independent uploads, chunks and personal favorites in ${theme} at ${width}`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.emulateMedia({ colorScheme: theme });
    await page.addInitScript(({ theme }) => {
      const actor = localStorage.getItem("fixture-actor") || "reader-a";
      localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "fixture", user_id: actor, email: `${actor}@example.test`, display_name: "Researcher" }));
      localStorage.setItem("tracelab.theme.v1:" + actor, theme);
    }, { theme });
    const project = { id: "project", name: "Auditable source bundle", description: "Sources, context and results", status: "active", created_at: "2026-09-13T00:00:00Z", updated_at: "2026-09-13T01:00:00Z" };
    const doc = { id: "document", project_id: "project", name: "Primary source.txt", file_type: "notes", processed: true, chunked: true, embedded: true, chunk_count: 123, total_tokens: 246, uploaded_at: project.created_at };
    const entry = { id: "entry", project_id: "project", mission_id: null, session_key: "sources", origin: "mcp-agent", claim: "A finding tied to its source document", source_url: "https://example.test/source", source_id: "source", source_sighting_count: 1, disposition: "supporting", tags: [], created_at: project.created_at, updated_at: project.updated_at };
    const favorites = new Set<string>();
    let actor = "reader-a";
    let uploads = 0;
    await page.route("**/api/v1/**", async route => {
      const request = route.request();
      const url = new URL(request.url());
      const endpoint = url.pathname;
      let result: unknown = {};
      if (endpoint.endsWith("/auth/me")) result = { user_id: actor, email: `${actor}@example.test`, role: "admin" };
      else if (endpoint.endsWith("/home/favorites/projects/project")) { favorites.add(actor); await route.fulfill({ status: 204 }); return; }
      else if (endpoint.endsWith("/home/favorites")) result = { total: favorites.has(actor) ? 1 : 0, items: favorites.has(actor) ? [{ id: project.id, title: project.name, href: "/projects/project" }] : [] };
      else if (endpoint.endsWith("/home")) result = { generated_at: project.updated_at, refresh_seconds: 30, missions: { total: 0, by_status: { completed: 0 } }, activity: { generated_at: project.updated_at, refresh_seconds: 30, page: 1, page_size: 10, total: 0, new_total: 0, items: [] }, active_runs: { total: 0, items: [] }, recent_reports: { total: 0, items: [] }, recent_projects: { total: 1, items: [] }, evidence_activity: { total: 0, items: [] }, favorites: { total: favorites.has(actor) ? 1 : 0, items: favorites.has(actor) ? [{ id: project.id, title: project.name, href: "/projects/project" }] : [] } };
      else if (endpoint.endsWith("/projects/project/stats")) result = { project_id: project.id, name: project.name, document_count: 123, chunk_count: 246, report_count: 23, total_tokens: 1722 };
      else if (endpoint.endsWith("/projects/project")) result = project;
      else if (endpoint.endsWith("/projects")) result = { data: [project], pagination: { total: 51, page: 1, page_size: 100, pages: 1 } };
      else if (endpoint.endsWith("/documents/upload")) {
        uploads++;
        if (request.postData()?.includes("rejected.bin")) { await route.fulfill({ status: 400, json: { detail: "Unsupported file format: .bin" } }); return; }
        result = { id: "uploaded", name: "Accepted.txt", processed: false };
      } else if (endpoint.endsWith("/process")) result = { status: "completed" };
      else if (endpoint.endsWith("/documents/document/chunks")) result = { data: [{ id: "chunk", chunk_index: 0, content: "An original source excerpt", token_count: 12, start_char: 0, end_char: 26 }], pagination: { total: 123, page: 1, pages: 13 } };
      else if (endpoint.endsWith("/documents/document")) result = doc;
      else if (endpoint.endsWith("/documents")) { expect(url.searchParams.get("project_id")).toBe("project"); result = { data: [doc], pagination: { total: 123, page: Number(url.searchParams.get("page") || 1), pages: 7 } }; }
      else if (endpoint.endsWith("/collections")) result = { total: 23, data: [{ id: "collection", name: "Source context", item_count: 1, updated_at: project.updated_at }] };
      else if (endpoint.endsWith("/missions")) result = { data: [{ id: "mission", title: "Source research", status: "completed" }], pagination: { total: 33, pages: 2 } };
      else if (endpoint.endsWith("/reports")) result = { items: [{ id: "report", title: "Research result", status: "final" }], total: 23, page: 1, page_size: 20 };
      else if (endpoint.endsWith("/evidence")) result = { entries: [entry], notes: [], entry_total: 43, note_total: 0, page: 1, page_size: 20 };
      await route.fulfill({ json: result });
    });
    await page.goto("/projects/project");
    await expect(page.getByRole("heading", { name: project.name })).toBeVisible();
    await expect(page.getByText("123", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Favorite project", exact: true }).click();
    await expect(page.getByRole("button", { name: "Unfavorite project", exact: true })).toBeVisible();
    await accessible(page);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: info.outputPath("project-overview.png"), fullPage: true });
    await page.getByRole("tab", { name: "Overview", exact: true }).focus();
    await page.keyboard.press("ArrowRight");
    await expect(page.getByRole("tab", { name: "Documents", exact: true })).toBeFocused();
    await expect(page.getByText("123 documents", { exact: true })).toBeVisible();
    await page.getByLabel("Choose files").setInputFiles([{ name: "rejected.bin", mimeType: "application/octet-stream", buffer: Buffer.from("Reject this file") }, { name: "Accepted.txt", mimeType: "text/plain", buffer: Buffer.from("A primary source") }]);
    await page.getByRole("button", { name: "Upload files", exact: true }).click();
    await expect(page.getByText("Unsupported file format: .bin", { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Open Accepted.txt", exact: true })).toBeVisible();
    expect(uploads).toBe(2);
    await accessible(page);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: info.outputPath("project-uploads.png"), fullPage: true });
    for (const tab of ["Evidence", "Collections", "Missions", "Reports"]) {
      await page.getByRole("tab", { name: tab, exact: true }).click();
      await expect(page.getByRole("tabpanel")).toContainText(`${tab === "Evidence" ? 43 : tab === "Missions" ? 33 : 23} ${tab.toLowerCase()}`);
      await accessible(page);
    }
    await page.goto("/documents/document");
    await page.getByRole("tab", { name: "Chunks", exact: true }).click();
    await page.getByRole("button", { name: /#0/ }).click();
    await expect(page.getByText("An original source excerpt", { exact: true })).toBeVisible();
    await accessible(page);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: info.outputPath("document-chunks.png"), fullPage: true });
    await page.getByRole("tab", { name: "Evidence", exact: true }).click();
    await expect(page.getByRole("link", { name: entry.claim, exact: true })).toHaveAttribute("href", "/evidence/entry");
    await page.goto("/");
    await expect(page.getByRole("region", { name: "Favorite projects", exact: true }).getByRole("link", { name: project.name })).toBeVisible();
    await accessible(page);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: info.outputPath("home-favorites.png"), fullPage: true });
    actor = "reader-b";
    await page.evaluate(() => localStorage.setItem("fixture-actor", "reader-b"));
    await page.reload();
    await expect(page.getByRole("region", { name: "Favorite projects", exact: true })).toContainText("Favorite a project");
    await expect(page.getByRole("region", { name: "Favorite projects", exact: true }).getByRole("link", { name: project.name })).toHaveCount(0);
  });
}
