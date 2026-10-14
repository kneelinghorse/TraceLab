import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

const stamp = "2026-10-13T12:00:00Z";
const project = { id: "project", name: "Navigation research", status: "active", created_at: stamp, updated_at: stamp };
const sourceId = "4a329716-7f08-4da1-a0e0-8e87d5fc91e0";
const origins = ["written", "librarian", "agent_brief", "mission"] as const;
const labels = {
  written: "Written from collection Reviewed sources",
  librarian: "Written by the Librarian from Navigation research",
  agent_brief: "Evidence brief from an agent's research session",
  mission: "Results of mission Compare navigation findings",
};
const hrefs = { written: "/collections/collection", librarian: "/projects/project", agent_brief: "/evidence?project_id=project&session_key=research", mission: "/missions/mission?tab=results" };
const reports = origins.map(origin => ({
  id: origin, origin, origin_label: labels[origin], origin_href: hrefs[origin], project_id: project.id, project_name: project.name,
  title: `${origin} findings`, content: "# Research findings\n\nThe reviewed sources support a clear navigation path [1].", status: origin === "librarian" ? "final" : "draft",
  prompt: origin === "mission" ? "Auto-generated from mission UX-1 [tracelab-auto-report:v2]" : "Retain competing claims.",
  report_type: "markdown", tokens_used: 0, chunk_count: 2, created_at: stamp, updated_at: stamp,
  citation_status: "validated", citations: [{ marker: 1, available: true, href: "/documents/document?chunk=chunk&index=0", excerpt: "Source navigation was difficult.", chunk_id: "chunk", document_id: "document" }],
  sources: [
    { id: "source-collection", report_id: origin, source_id: sourceId, source_type: "collection", name: "Reviewed sources", href: "/collections/collection", added_at: stamp },
    { id: "source-document", report_id: origin, source_id: sourceId, source_type: "chunk", name: "Navigation interviews", href: "/documents/document?chunk=chunk&index=0", added_at: stamp },
    { id: "unavailable", report_id: origin, source_id: null, source_type: "chunk", name: "Source unavailable", href: null, added_at: stamp },
  ],
}));
const orphan = { ...reports[3], id: "orphan", title: "Retained orphan result", origin_label: "Mission results", origin_href: null };

async function fixtures(page: Page, theme: "light" | "dark", width: number) {
  await page.setViewportSize({ width, height: 900 });
  await page.emulateMedia({ colorScheme: theme });
  await page.addInitScript(theme => {
    localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "fixture", user_id: "reader", email: "reader@example.test" }));
    localStorage.setItem("tracelab.theme.v1:reader", theme);
  }, theme);
  await page.route("**/api/v1/**", async route => {
    const url = new URL(route.request().url());
    const endpoint = url.pathname;
    let json: unknown = {};
    if (endpoint.endsWith("/auth/me")) json = { user_id: "reader", email: "reader@example.test", role: "admin" };
    else if (endpoint.endsWith("/activity/summary")) json = { completed_missions_new: 0, new_total: 0, by_type: { mission: 0, report: 0, evidence: 0 } };
    else if (endpoint.endsWith("/projects/project/stats")) json = { report_count: 2, document_count: 0, chunk_count: 0, total_tokens: 0 };
    else if (endpoint.endsWith("/projects/project")) json = project;
    else if (endpoint.endsWith("/projects")) json = { data: [project], pagination: { total: 1, page: 1, pages: 1 } };
    else if (endpoint.endsWith("/home/favorites")) json = { items: [], total: 0 };
    else if (endpoint.endsWith("/reports")) {
      const requested = url.searchParams.getAll("origin");
      const items = [...reports, orphan].filter(report => !requested.length || requested.includes(report.origin));
      json = { items, total: items.length, page: 1, page_size: 20 };
    } else if (/\/reports\/[^/]+$/.test(endpoint)) json = reports.find(report => endpoint.endsWith(`/reports/${report.id}`));
    else if (endpoint.endsWith("/evidence/entry")) json = {
      entry: { id: "entry", project_id: "project", source_id: "source", source_url: "https://example.test/source", claim: "Navigation finding", disposition: "supporting", session_key: "research", origin: "deepsearch-worker", tags: [], created_at: stamp },
      links: [{ id: "mission", kind: "report", title: "Mission results", href: hrefs.mission, mission_result: true }],
    };
    else if (endpoint.endsWith("/evidence")) json = { entries: [], notes: [], entry_total: 0, note_total: 0, page: 1, page_size: 20 };
    await route.fulfill({ json });
  });
}

async function accessible(page: Page) {
  await page.addScriptTag({ path: path.resolve("node_modules/axe-core/axe.min.js") });
  const result = await page.evaluate(async () => {
    const axe = (window as unknown as { axe: { run: (node: Document) => Promise<{ violations: { id: string; impact: string }[] }> } }).axe;
    return { overflow: document.documentElement.scrollWidth > innerWidth, violations: (await axe.run(document)).violations.filter(v => ["serious", "critical"].includes(v.impact)) };
  });
  expect(result).toEqual({ overflow: false, violations: [] });
}

for (const theme of ["light", "dark"] as const) for (const width of [390, 1440]) {
  for (const origin of origins) test(`${origin} report reads as a document in ${theme} at ${width}`, async ({ page }, info) => {
    await fixtures(page, theme, width);
    await page.goto(`/reports/${origin}`);
    await expect(page.getByRole("heading", { name: `${origin} findings`, exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: labels[origin], exact: true })).toHaveAttribute("href", hrefs[origin]);
    await expect(page.locator("main")).not.toContainText(/Tokens:|Type:|Chunks:|Auto-generated from mission|tracelab-auto-report|Custom Prompt|\bmarkdown\b|4a329716/);
    expect(await page.getByRole("heading", { level: 2 }).allTextContents()).toEqual(expect.arrayContaining(["Content", "Source citations"]));
    const headings = (await page.getByRole("heading", { level: 2 }).allTextContents()).map(s => s.trim());
    expect(headings[0]).toBe("Content");
    expect(headings[1]).toMatch(/^Evidence citations/);
    await expect(page.getByText("Instructions", { exact: true })).toHaveCount(origin === "written" || origin === "librarian" ? 1 : 0);
    await expect(page.getByText("Final", { exact: true })).toHaveCount(origin === "librarian" ? 1 : 0);
    await expect(page.getByText("Draft", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Navigation interviews", exact: true })).toHaveAttribute("href", "/documents/document?chunk=chunk&index=0");
    await expect(page.getByText("Source unavailable", { exact: true })).toBeVisible();
    await accessible(page);
    await page.screenshot({ path: info.outputPath("report.png"), fullPage: true });
  });

  test(`document defaults, separate result filters and evidence destination in ${theme} at ${width}`, async ({ page }, info) => {
    await fixtures(page, theme, width);
    await page.goto("/reports");
    await expect(page.getByRole("link", { name: "written findings", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "librarian findings", exact: true })).toBeVisible();
    await expect(page.getByText("mission findings", { exact: true })).toHaveCount(0);
    await expect(page.getByText("agent_brief findings", { exact: true })).toHaveCount(0);
    await accessible(page);
    await page.screenshot({ path: info.outputPath("reports-default.png"), fullPage: true });
    await page.getByRole("button", { name: "Evidence briefs", exact: true }).click();
    await expect(page.getByRole("link", { name: "agent_brief findings", exact: true })).toBeVisible();
    await expect(page.getByText("written findings", { exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: "Mission results", exact: true }).click();
    await expect(page.getByRole("link", { name: "mission findings", exact: true })).toHaveAttribute("href", hrefs.mission);
    await expect(page.getByText("Retained orphan result", { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Retained orphan result", exact: true })).toHaveCount(0);
    await accessible(page);
    await page.screenshot({ path: info.outputPath("mission-results.png"), fullPage: true });
    await page.goto("/projects/project?tab=reports");
    await page.getByRole("tab", { name: "Reports", exact: true }).click();
    await expect(page.getByRole("link", { name: "written findings", exact: true })).toBeVisible();
    await expect(page.getByText("mission findings", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("link", { name: labels.written, exact: true })).toBeVisible();
    await page.goto("/evidence/entry");
    await expect(page.getByRole("link", { name: "Open report", exact: true })).toHaveAttribute("href", hrefs.mission);
  });
}
