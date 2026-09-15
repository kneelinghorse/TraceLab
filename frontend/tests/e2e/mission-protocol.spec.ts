import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

async function accessible(page: Page) {
  await page.addScriptTag({ path: path.resolve("node_modules/axe-core/axe.min.js") });
  const result = await page.evaluate(async () => {
    const axe = (window as unknown as { axe: { run: (node: Document) => Promise<{ violations: { id: string; impact: string; nodes: { target: string[] }[] }[] }> } }).axe;
    return { overflow: document.documentElement.scrollWidth > innerWidth, violations: (await axe.run(document)).violations.filter(v => ["critical", "serious"].includes(v.impact)) };
  });
  expect(result).toEqual({ overflow: false, violations: [] });
}
const project = "10000000-0000-4000-8000-000000000001";
for (const theme of ["light", "dark"] as const) for (const width of [390, 820, 1440]) {
  test(`author, inspect, audit and prepare a new run in ${theme} at ${width}`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.emulateMedia({ colorScheme: theme });
    await page.addInitScript(({ theme }) => {
      localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "fixture", user_id: "reader", email: "reader@example.test", display_name: "Researcher" }));
      localStorage.setItem("tracelab.theme.v1:reader", theme);
    }, { theme });
    const state = { id: "run-1", mission_id: "UX6-TEST", title: "Inspectable research", objective: "Find primary evidence for the research question", success_criteria: ["Cite primary sources"], project_id: project, project_name: "Research", status: "draft", tags: [], deliverables: [], context: {}, metadata: {}, research_phases: {}, execution_metadata: {} as Record<string, unknown>, result_protocol: {}, result_document_ids: [], result_report_id: null, result_markdown: null as string | null, created_at: "2026-09-13T00:00:00Z", updated_at: "2026-09-13T01:00:00Z", queued_at: null as string | null, started_at: null as string | null, completed_at: null as string | null };
    const entry = { id: "evidence-1", project_id: project, mission_id: "run-1", session_key: "run-1", origin: "deepsearch-worker", claim: "A measured finding with a primary source", source_url: "https://example.test/source", source_id: "source-1", source_sighting_count: 1, disposition: "supporting", tags: [], created_at: state.created_at, updated_at: state.updated_at, snippet: "Observed research evidence" };
    const writes: { method: string; path: string; body: Record<string, unknown> | null }[] = [];
    await page.route("**/api/v1/**", async route => {
      const url = new URL(route.request().url());
      const endpoint = url.pathname;
      const method = route.request().method();
      const body = method === "GET" ? null : route.request().postDataJSON();
      if (method !== "GET") writes.push({ method, path: endpoint, body });
      let response: unknown = {};
      if (endpoint.endsWith("/auth/me")) response = { user_id: "reader", email: "reader@example.test", role: "admin" };
      else if (endpoint.endsWith("/home")) response = { missions: { total: 143 }, active_runs: { total: 1 } };
      else if (endpoint.endsWith("/projects")) response = { data: [{ id: project, name: "Research" }], pagination: { page: 1, pages: 1, total: 1 } };
      else if (endpoint.endsWith("/missions/events/recent")) { expect(url.searchParams.get("mission_id")).toBe("run-1"); response = []; }
      else if (endpoint.endsWith("/logs")) response = [];
      else if (endpoint.endsWith("/contract-preview")) response = { mission_id: state.mission_id, mission_uuid: state.id, contract_version: "1.0", compiler_revision: "24e8810-fixture", fidelity: "structural_only", named_entities: [], objectives: [], evidence_slots: [], acceptance_checks: [], deliverable_schemas: [], coverage_thresholds: {}, validation_thresholds: {} };
      else if (endpoint.endsWith("/submit")) { expect(state.status).toBe("draft"); state.status = "queued"; state.queued_at = state.updated_at; response = { status: "queued", uuid: state.id }; }
      else if (endpoint.endsWith("/missions/run-1")) {
        if (method === "PATCH") { expect(body.status).toBeUndefined(); Object.assign(state, body); }
        response = state;
      } else if (endpoint.endsWith("/missions")) {
        if (method === "POST") { expect(body.status).toBe("draft"); Object.assign(state, body); response = state; }
        else response = { data: [state], pagination: { page: 1, page_size: 20, total: 143, pages: 8 } };
      } else if (endpoint.endsWith("/evidence/evidence-1")) response = { entry, links: [{ kind: "mission", id: state.id, title: state.title, href: "/missions/run-1", relationship: "produced by" }] };
      else if (endpoint.endsWith("/evidence")) response = { entries: [entry], notes: [], entry_total: 1, note_total: 0, page: 1, page_size: 20 };
      await route.fulfill({ json: response });
    });
    await page.goto("/missions");
    await expect(page.getByText("143 matching missions")).toBeVisible();
    await accessible(page);
    await page.screenshot({ path: info.outputPath("list.png"), fullPage: true });
    await page.getByRole("link", { name: "Create Mission" }).click();
    await page.getByLabel("Mission ID", { exact: false }).fill("UX6-TEST");
    await page.getByLabel("Title", { exact: false }).fill(state.title);
    await page.getByLabel("Objective", { exact: false }).fill(state.objective);
    await page.getByLabel("Project", { exact: false }).selectOption(project);
    await page.getByRole("textbox", { name: "Success Criteria 1", exact: true }).fill("Cite primary sources");
    await page.getByRole("button", { name: "Save and preview", exact: true }).click();
    await expect(page.getByText("24e8810-fixture", { exact: true })).toBeVisible();
    await accessible(page);
    await page.screenshot({ path: info.outputPath("authoring.png"), fullPage: true });
    await page.getByRole("button", { name: "Submit to DeepSearch", exact: true }).click();
    await expect(page).toHaveURL(/\/missions\/run-1$/);
    await expect(page.getByText(/Logs unavailable/)).toBeVisible();
    await expect(page.getByText("Step progress unknown")).toBeVisible();
    state.status = "in_progress"; state.started_at = state.updated_at;
    state.execution_metadata = { current_phase: "synthesis", current_step: 2, total_steps: 3, progress_percent: 65 };
    await page.getByRole("button", { name: "Refresh", exact: true }).click();
    await expect(page.getByText("Step 2 of 3")).toBeVisible();
    await accessible(page);
    await page.screenshot({ path: info.outputPath("run.png"), fullPage: true });
    state.status = "completed"; state.completed_at = state.updated_at; state.result_markdown = "# Research result\nA measured finding with a primary source.";
    await page.getByRole("button", { name: "Refresh", exact: true }).click();
    await expect(page.getByRole("button", { name: "Re-run", exact: true })).toBeVisible();
    await page.getByRole("tab", { name: "Results", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Research result", exact: true })).toBeVisible();
    await accessible(page);
    await page.getByRole("tab", { name: "Evidence", exact: true }).click();
    await page.getByRole("link", { name: entry.claim, exact: true }).click();
    await expect(page).toHaveURL(/\/evidence\/evidence-1$/);
    await expect(page.getByRole("heading", { name: entry.claim, level: 1 })).toBeVisible();
    await page.goto("/missions/run-1");
    await page.getByRole("button", { name: "Re-run", exact: true }).click();
    await accessible(page);
    await page.getByRole("button", { name: "Continue", exact: true }).click();
    await expect(page).toHaveURL(/\/missions\/new\?from=run-1$/);
    await expect(page.getByLabel("Mission ID", { exact: false })).not.toHaveValue("UX6-TEST");
    await expect(page.getByLabel("Objective", { exact: false })).toHaveValue(state.objective);
    expect(writes.filter(write => write.method === "POST" && write.path.endsWith("/missions"))).toHaveLength(1);
    expect(writes.filter(write => write.path.endsWith("/submit"))).toHaveLength(1);
    expect(writes.some(write => write.body?.status === "completed")).toBe(false);
  });
}
test("queue bookmark permanently redirects and retains filters", async ({ request }) => {
  const response = await request.get("/missions/queue?project_id=scope", { maxRedirects: 0 });
  expect(response.status()).toBe(308);
  const target = new URL(response.headers().location, response.url());
  expect(target.pathname).toBe("/missions");
  expect(target.searchParams.get("view")).toBe("queue");
  expect(target.searchParams.get("project_id")).toBe("scope");
});
