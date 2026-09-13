import { expect, test, type Page } from "@playwright/test";
import path from "node:path";
import { readFile } from "node:fs/promises";

async function accessible(page: Page) {
  await page.addScriptTag({ path: path.resolve("node_modules/axe-core/axe.min.js") });
  const result = await page.evaluate(async () => {
    const axe = (window as unknown as { axe: { run: (node: Document) => Promise<{ violations: { id: string; impact: string }[] }> } }).axe;
    return { overflow: document.documentElement.scrollWidth > innerWidth, violations: (await axe.run(document)).violations.filter(v => ["critical", "serious"].includes(v.impact)) };
  });
  expect(result).toEqual({ overflow: false, violations: [] });
}
const project = "10000000-0000-4000-8000-000000000001";
for (const theme of ["light", "dark"] as const) for (const width of [390, 820, 1440]) {
  test(`collection context, reviewed seed and evidence citations in ${theme} at ${width}`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.emulateMedia({ colorScheme: theme });
    await page.addInitScript(({ theme }) => {
      localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "fixture", user_id: "reader", email: "reader@example.test" }));
      localStorage.setItem("tracelab.theme.v1:reader", theme);
    }, { theme });
    const stamp = "2026-09-13T00:00:00Z";
    const collection = { id: "collection", name: "Research context", description: "Primary documents and competing claims", instructions: "Preserve contradictions and cite primary sources.", item_count: 1, items: [{ id: "item", collection_id: "collection", chunk_id: "chunk", document_id: "document", notes: "A primary excerpt", chunk_content: "The research starts with evidence.", added_at: stamp }], created_at: stamp, updated_at: stamp };
    const documents = Array.from({ length: 123 }, (_, i) => ({ id: `document-${i}`, name: `Source ${i + 1}`, project_id: project, file_type: "txt", processed: false, chunked: false, embedded: false }));
    const references = documents.map(doc => ({ title: doc.name, document_id: doc.id, href: `/documents/${doc.id}` }));
    const context = { collection_id: collection.id, document_ids: documents.map(doc => doc.id) };
    const report = { id: "report", project_id: project, title: "Auditable findings", content: "# Findings\n\nA primary finding.", status: "final", report_type: "report", tokens_used: 24, chunk_count: 1, citations: [], sources: [{ id: "raw", source_type: "ledger_entry", source_id: "inaccessible", added_at: stamp }], created_at: stamp, updated_at: stamp };
    const entry = { id: "entry", project_id: project, mission_id: null, session_key: "research", origin: "mcp-agent", claim: "An authorized, sourced finding", source_url: "https://example.test/primary", disposition: "supporting", tags: [], created_at: stamp, updated_at: stamp, snippet: "A primary passage", source_sighting_count: 1 };
    const mission = { id: "seeded", mission_id: "", title: "", objective: "", success_criteria: [], project_id: project, status: "draft", context: {}, tags: [], deliverables: [], metadata: {}, research_phases: {}, execution_metadata: {}, created_at: stamp, updated_at: stamp };
    let submitted = 0;
    let created = 0;
    let releaseProjects!: () => void;
    const projectsReady = new Promise<void>(resolve => { releaseProjects = resolve; });
    await page.route("**/api/v1/**", async route => {
      const request = route.request(); const url = new URL(request.url()); const endpoint = url.pathname; const method = request.method();
      const body = method === "GET" ? null : request.postDataJSON();
      let result: unknown = {};
      if (endpoint.endsWith("/auth/me")) result = { user_id: "reader", email: "reader@example.test", role: "admin" };
      else if (endpoint.endsWith("/home")) result = { missions: { total: 0 }, attention: { total: 0 } };
      else if (endpoint.endsWith("/projects")) { await projectsReady; result = { data: [{ id: project, name: "Research" }], pagination: { page: 1, pages: 1, total: 1 } }; }
      else if (endpoint.endsWith("/mission-seed")) result = { collection_id: collection.id, title: `Research: ${collection.name}`, project_id: project, background: collection.instructions, references, context };
      else if (endpoint.endsWith("/collections/collection/documents")) { const current = Number(url.searchParams.get("page") || 1); result = { items: documents.slice((current - 1) * 20, current * 20), total: 123, page: current, page_size: 20 }; }
      else if (endpoint.endsWith("/collections/collection")) { if (method === "PUT") Object.assign(collection, body); result = collection; }
      else if (endpoint.endsWith("/collections")) result = { data: [collection], total: 121 };
      else if (endpoint.endsWith("/reports/report/export")) { const format = url.searchParams.get("format"); await route.fulfill({ body: `original ${format} bytes\n`, contentType: "text/plain" }); return; }
      else if (endpoint.endsWith("/reports/report")) result = report;
      else if (endpoint.endsWith("/reports")) result = { items: [report], total: 481, page: Number(url.searchParams.get("page") || 1), page_size: 20 };
      else if (endpoint.endsWith("/evidence/entry")) result = { entry, links: [] };
      else if (endpoint.endsWith("/evidence")) result = { entries: [entry], notes: [], entry_total: 21, note_total: 0, page: Number(url.searchParams.get("page") || 1), page_size: 20 };
      else if (endpoint.endsWith("/contract-preview")) result = { mission_id: mission.mission_id, mission_uuid: mission.id, contract_version: "1.0", compiler_revision: "seed-contract", fidelity: "structural_only", named_entities: [], objectives: [], evidence_slots: [], acceptance_checks: [], deliverable_schemas: [], coverage_thresholds: {}, validation_thresholds: {} };
      else if (endpoint.endsWith("/submit")) { submitted++; mission.status = "queued"; result = { status: "queued", uuid: mission.id }; }
      else if (endpoint.endsWith("/missions/seeded")) result = mission;
      else if (endpoint.endsWith("/missions") && method === "POST") { created++; expect(body.references).toEqual(references); expect(body.context).toEqual(context); expect(body.background).toBe(collection.instructions); Object.assign(mission, body); result = mission; }
      else if (endpoint.endsWith("/logs") || endpoint.endsWith("/events/recent")) result = [];
      await route.fulfill({ json: result });
    });
    await page.goto("/collections");
    await expect(page.getByText("121 collections", { exact: true })).toBeVisible();
    await accessible(page); await page.screenshot({ path: info.outputPath("collections.png"), fullPage: true });
    await page.getByRole("button", { name: "Next", exact: true }).click();
    await expect(page.getByText("Page 2 of 7 (121 total)")).toBeVisible();
    await page.getByRole("link", { name: collection.name, exact: true }).click();
    await expect(page.getByText("Documents (123)", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Edit", exact: true }).click();
    await page.getByRole("textbox", { name: "Instructions", exact: true }).fill("Compare primary evidence and preserve competing claims.");
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page.getByText("Compare primary evidence and preserve competing claims.", { exact: true })).toBeVisible();
    await page.getByRole("navigation", { name: "Collection document pages" }).getByRole("button", { name: "Next" }).click();
    await expect(page.getByRole("link", { name: "Source 21", exact: true })).toBeVisible();
    const opener = page.getByRole("button", { name: "Create Report", exact: true });
    await opener.click();
    await expect(page.getByRole("dialog", { name: "Create Report" })).toBeVisible();
    await accessible(page);
    await page.keyboard.press("Escape");
    await expect(opener).toBeFocused();
    await accessible(page); await page.screenshot({ path: info.outputPath("collection-context.png"), fullPage: true });
    await page.getByRole("link", { name: "Seed mission" }).click();
    await expect(page.getByText("Review 123 source documents", { exact: true })).toBeVisible();
    await expect(page.getByLabel("Project", { exact: false })).toBeVisible();
    releaseProjects();
    await expect(page.getByLabel("Project", { exact: false })).toHaveValue(project);
    expect(created).toBe(0); expect(submitted).toBe(0);
    await page.getByLabel("Objective", { exact: false }).fill("Compare the evidence for the stated research question.");
    await page.getByRole("textbox", { name: "Success Criteria 1", exact: true }).fill("Cite a primary source and preserve competing claims.");
    await page.getByRole("button", { name: "Save and preview", exact: true }).click();
    await expect(page.getByText("seed-contract", { exact: true })).toBeVisible();
    await accessible(page);
    await page.getByRole("button", { name: "Submit to DeepSearch", exact: true }).click();
    await expect(page).toHaveURL(/\/missions\/seeded$/); expect(created).toBe(1); expect(submitted).toBe(1);
    await page.goto("/reports"); await expect(page.getByText("481 reports", { exact: true })).toBeVisible();
    await accessible(page); await page.screenshot({ path: info.outputPath("reports.png"), fullPage: true });
    await page.getByRole("link", { name: report.title, exact: true }).click();
    await expect(page.getByRole("link", { name: entry.claim, exact: true })).toHaveAttribute("href", "/evidence/entry");
    await expect(page.locator('a[href="/evidence/inaccessible"]')).toHaveCount(0);
    await page.getByRole("navigation", { name: "Citation pages" }).getByRole("button", { name: "Next" }).click();
    await expect(page.getByText("Page 2 of 2 (21 total)")).toBeVisible();
    await accessible(page); await page.screenshot({ path: info.outputPath("report-citations.png"), fullPage: true });
    for (const [format, label] of [["md", "Markdown (.md)"], ["json", "JSON (.json)"], ["txt", "Plain text (.txt)"]]) {
      await page.getByRole("button", { name: "Export ▾", exact: true }).click();
      const download = page.waitForEvent("download");
      await page.getByRole("button", { name: label, exact: true }).click();
      expect(await readFile((await (await download).path())!, "utf8")).toBe(`original ${format} bytes\n`);
    }
    await page.getByRole("link", { name: entry.claim, exact: true }).click();
    await expect(page).toHaveURL(/\/evidence\/entry$/);
    await expect(page.getByText(entry.snippet, { exact: true })).toBeVisible();
  });
}
