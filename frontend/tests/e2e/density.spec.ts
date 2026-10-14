import { test, expect } from "@playwright/test";
import path from "node:path";
import baseline from "../fixtures/density-baseline.json";
import { writeFile } from "node:fs/promises";

const stamp = "2026-10-13T12:00:00Z";
const project = { id: "density-project", name: "Research workspace", description: "Sources and findings for the research team.", status: "active", created_at: stamp, updated_at: stamp };
const collection = { id: "density-collection", name: "Primary sources", description: "Evidence for the next research question.", instructions: "Cite primary sources and retain competing claims.", item_count: 1, created_at: stamp, updated_at: stamp, items: [{ id: "item", chunk_id: "chunk", document_id: "document", chunk_content: "A source passage for comparison.", added_at: stamp }] };
const mission = { id: "density-mission", mission_id: "DENSITY-01", title: "Compare primary findings", objective: "Review the available evidence and preserve its sources.", status: "completed", project_id: project.id, project_name: project.name, created_at: stamp, updated_at: stamp };
const report = { id: "density-report", title: "Research findings", report_type: "report", status: "final", tokens_used: 800, chunk_count: 3, created_at: stamp };
const entry = { id: "density-entry", project_id: project.id, session_key: "research-session", source_id: "source", source_url: "https://example.test/source", claim: "A finding supported by primary evidence.", disposition: "supporting", tags: [], created_at: stamp };
const surfaces = [
  { name: "home", url: "/", row: 'ol[aria-label="Activity items"] > li' },
  { name: "librarian", url: `/librarian?project=${project.id}`, row: 'section[aria-label="Project"]' },
  { name: "projects", url: "/projects", row: `main a.group[href="/projects/${project.id}"]` },
  { name: "project", url: `/projects/${project.id}`, row: '#project-panel section' },
  { name: "missions", url: "/missions", row: 'section[aria-label="Mission list"] li' },
  { name: "evidence", url: `/evidence?project_id=${project.id}`, row: 'section[aria-label="Evidence entries"] article' },
  { name: "reports", url: "/reports", row: 'main li.panel' },
  { name: "collections", url: "/collections", row: 'main .grid > .bg-surface' },
  { name: "collection", url: `/collections/${collection.id}`, row: 'section[aria-label="Collection documents"] li' },
];

for (const theme of ["light", "dark"] as const) for (const width of [1440, 390]) for (const surface of surfaces) {
  test(`${surface.name} density in ${theme} at ${width}`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 900 });
    await page.clock.setFixedTime(new Date("2026-10-13T18:00:00Z"));
    await page.emulateMedia({ colorScheme: theme });
    await page.addInitScript(t => {
      localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "fixture", user_id: "density-reader", email: "reader@example.test", display_name: "Researcher" }));
      localStorage.setItem("tracelab.theme.v1:density-reader", t);
    }, theme);
    await page.route("**/api/v1/**", async route => {
      const endpoint = new URL(route.request().url()).pathname;
      let body: unknown = {};
      if (endpoint.endsWith("/auth/me")) body = { user_id: "density-reader", email: "reader@example.test", display_name: "Researcher", role: "admin" };
      else if (endpoint.endsWith("/activity/summary")) body = { new_total: 0, by_type: { mission: 0, report: 0, evidence: 0 } };
      else if (endpoint.endsWith("/home/favorites")) body = { total: 0, items: [] };
      else if (endpoint.endsWith("/home")) body = {
        generated_at: stamp, refresh_seconds: 30, missions: { total: 20, by_status: { completed: 20 } },
        favorites: { total: 0, items: [] },
        activity: { total: 20, new_total: 0, page: 1, page_size: 20, items: Array.from({ length: 20 }, (_, i) => ({ type: "mission", id: `activity-${i}`, title: `Research result ${i + 1}`, subtitle: "Research workspace", status: "completed", href: `/missions/activity-${i}`, occurred_at: stamp, new: false })) },
        active_runs: { total: 0, items: [] }, recent_reports: { total: 0, items: [] }, recent_projects: { total: 0, items: [] }, evidence_activity: { total: 0, items: [] },
      };
      else if (endpoint.endsWith(`/projects/${project.id}/stats`)) body = { document_count: 12, chunk_count: 36, report_count: 4, total_tokens: 2400 };
      else if (endpoint.endsWith(`/projects/${project.id}`)) body = project;
      else if (endpoint.endsWith("/projects")) body = { data: [project], pagination: { page: 1, pages: 1, total: 1 } };
      else if (endpoint.endsWith("/missions")) body = { data: [mission], pagination: { page: 1, pages: 1, total: 1 } };
      else if (endpoint.endsWith("/reports")) body = { items: [report], total: 1, page: 1, page_size: 20 };
      else if (endpoint.endsWith("/evidence")) body = { entries: [entry], entry_total: 1, notes: [], note_total: 0, page: 1, page_size: 20 };
      else if (endpoint.endsWith(`/collections/${collection.id}/documents`)) body = { items: [{ id: "document", name: "Primary source", file_type: "markdown", embedded: true }], total: 1, page: 1, page_size: 20 };
      else if (endpoint.endsWith(`/collections/${collection.id}`)) body = collection;
      else if (endpoint.endsWith("/collections")) body = { data: [collection], total: 1 };
      else if (endpoint.endsWith("/spaces")) body = [];
      await route.fulfill({ json: body });
    });
    await page.goto(surface.url);
    const row = page.locator(surface.row).first();
    await expect(row).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    await page.addScriptTag({ path: path.resolve("node_modules/axe-core/axe.min.js") });
    const result = await page.evaluate(async selector => {
      const axe = (window as unknown as { axe: { run: (node: Document) => Promise<{ violations: { id: string; impact: string }[] }> } }).axe;
      return {
        bodyFontSize: parseFloat(getComputedStyle(document.body).fontSize),
        descriptionWidth: document.querySelector('main header p')!.getBoundingClientRect().width,
        headingFontSize: parseFloat(getComputedStyle(document.querySelector('main h1')!).fontSize),
        smallText: [...document.querySelectorAll('main .text-xs, main .form-label')].filter(el => el.getClientRects().length && !el.closest('.sr-only')).map(el => parseFloat(getComputedStyle(el).fontSize)),
        firstRowTop: document.querySelector(selector)!.getBoundingClientRect().top,
        visibleActivityRows: [...document.querySelectorAll('ol[aria-label="Activity items"] > li')].filter(el => el.getBoundingClientRect().bottom <= innerHeight).length,
        overflow: document.documentElement.scrollWidth > innerWidth,
        violations: (await axe.run(document)).violations.filter(v => ["serious", "critical"].includes(v.impact)),
      };
    }, surface.row);
    await writeFile(info.outputPath("measurement.json"), JSON.stringify({ surface: surface.name, theme, width, selector: surface.row, ...result }, null, 2));
    await page.screenshot({ path: info.outputPath("page.png"), fullPage: true });
    if (width === 1440) {
      const before = baseline.surfaces[surface.name as keyof typeof baseline.surfaces];
      // More research must be visible without scrolling; spacing class names alone cannot prove it.
      expect(before.firstRowTop - result.firstRowTop).toBeGreaterThanOrEqual(40);
      if (surface.name === "home") expect(result.visibleActivityRows - before.visibleActivityRows).toBeGreaterThanOrEqual(3);
    }
    // Actions must wrap below the copy on phones, never squeeze it into a word-wide column.
    if (width === 390) expect(result.descriptionWidth).toBeGreaterThanOrEqual(width - 120);
    expect(result.bodyFontSize).toBe(16);
    expect(result.headingFontSize).toBe(24);
    expect(result.smallText.every(size => size >= 14)).toBe(true);
    expect(result.overflow).toBe(false);
    expect(result.violations).toEqual([]);
  });
}
