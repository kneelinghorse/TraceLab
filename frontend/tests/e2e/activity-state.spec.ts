import { test, expect, type Page } from "@playwright/test";
import path from "node:path";

const stamp = "2026-10-14T12:00:00";
const states = ["new", "unseen", "seen"] as const;
const missions = states.map(state => ({
  id: `mission-${state}`, mission_id: `RUN-${state}`, title: `${state} mission`, objective: "A sourced research result",
  status: "completed", success_criteria: ["Cite evidence"], tags: [], deliverables: [], project_id: null,
  research_phases: {}, metadata: {}, context: {}, execution_metadata: {}, result_protocol: {},
  result_document_ids: [], result_report_id: null, result_markdown: "A sourced result", created_at: stamp, updated_at: stamp,
  completed_at: stamp, queued_at: null, started_at: null,
}));
const reports = states.map(state => ({
  id: `report-${state}`, title: `${state} report`, origin: "written", origin_label: "Written from 2 excerpts", origin_href: null,
  status: "draft", project_id: null, project_name: null, created_at: stamp, updated_at: stamp,
}));

async function fixtures(page: Page, theme: "light" | "dark", width: number) {
  const viewed = new Set(["mission-seen", "report-seen"]);
  const batches: { type: string; id: string }[][] = [];
  const writes: string[] = [];
  await page.setViewportSize({ width, height: 900 });
  await page.emulateMedia({ colorScheme: theme });
  await page.addInitScript(theme => {
    localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "fixture", user_id: "reader", email: "reader@example.test" }));
    localStorage.setItem("tracelab.theme.v1:reader", theme);
  }, theme);
  const stateFor = (id: string) => ({ viewed: viewed.has(id), new: id.endsWith("-new") && !viewed.has(id) });
  await page.route("**/api/v1/**", async route => {
    const url = new URL(route.request().url());
    const endpoint = url.pathname;
    let json: unknown = {};
    if (endpoint.endsWith("/auth/me")) json = { user_id: "reader", email: "reader@example.test", role: "admin" };
    else if (endpoint.endsWith("/activity/summary")) json = { generated_at: stamp, completed_missions_new: viewed.has("mission-new") ? 0 : 1, new_total: 2, by_type: { mission: 1, report: 1, evidence: 0 } };
    else if (endpoint.endsWith("/activity/state")) {
      expect(route.request().method()).toBe("POST");
      const { items } = route.request().postDataJSON(); batches.push(items);
      json = { items: items.map((item: { type: string; id: string }) => ({ ...item, ...stateFor(item.id) })) };
    } else if (endpoint.endsWith("/activity/viewed")) {
      expect(route.request().method()).toBe("PUT");
      for (const item of route.request().postDataJSON().items) { viewed.add(item.id); writes.push(item.id); }
      json = { viewed: 1, new_total: 0 };
    } else if (endpoint.endsWith("/home")) json = {
      generated_at: stamp, refresh_seconds: 30, missions: { total: 3, by_status: { completed: 3 } },
      activity: { generated_at: stamp, refresh_seconds: 30, page: 1, page_size: 10, total: 3, new_total: viewed.has("mission-new") ? 0 : 1,
        items: missions.map(mission => ({ type: "mission", id: mission.id, title: mission.title, status: mission.status, subtitle: mission.mission_id, occurred_at: stamp, href: `/missions/${mission.id}`, ...stateFor(mission.id) })) },
      active_runs: { total: 0, items: [] }, recent_reports: { total: 0, items: [] }, recent_projects: { total: 0, items: [] }, favorites: { total: 0, items: [] }, evidence_activity: { total: 0, items: [] },
    };
    else if (endpoint.endsWith("/missions")) json = { data: missions, pagination: { page: 1, page_size: 20, total: 3, pages: 1 } };
    else if (endpoint.endsWith("/reports")) json = { items: reports, page: 1, page_size: 20, total: 3 };
    else if (endpoint.endsWith("/projects")) json = { data: [], pagination: { total: 0, page: 1, pages: 1 } };
    else if (endpoint.endsWith("/home/favorites")) json = { items: [], total: 0 };
    await route.fulfill({ json });
  });
  return { batches, writes };
}

async function checkRows(page: Page, kind: "mission" | "report", surface: "home" | "list") {
  for (const state of states) {
    const title = surface === "list" && kind === "mission"
      ? page.getByRole("heading", { name: `${state} ${kind}`, exact: true })
      : page.locator("main").getByRole("link", { name: `${state} ${kind}`, exact: true });
    const row = title.locator("xpath=ancestor::li[1]");
    await expect(row).toHaveAttribute("data-viewed", String(state === "seen"));
    await expect(title).toHaveCSS("font-weight", state === "seen" ? "400" : "600");
    await expect(row.getByTestId("new-activity-dot")).toHaveCount(state === "new" ? 1 : 0);
  }
}

async function capture(page: Page, file: string) {
  await page.addScriptTag({ path: path.resolve("node_modules/axe-core/axe.min.js") });
  const result = await page.evaluate(async () => {
    const axe = (window as unknown as { axe: { run: (node: Document) => Promise<{ violations: { id: string; impact: string }[] }> } }).axe;
    return { overflow: document.documentElement.scrollWidth > innerWidth, violations: (await axe.run(document)).violations.filter(v => ["serious", "critical"].includes(v.impact)).map(v => v.id) };
  });
  expect(result).toEqual({ overflow: false, violations: [] });
  await page.screenshot({ path: file, fullPage: true });
}

for (const theme of ["light", "dark"] as const) for (const width of [390, 1440]) {
  test(`three row states and a clearable Missions dot in ${theme} at ${width}`, async ({ page }, info) => {
    const { batches, writes } = await fixtures(page, theme, width);
    await page.goto("/");
    await checkRows(page, "mission", "home");
    await expect(page.getByRole("region", { name: "Active missions" })).toHaveCount(0);
    const activity = page.getByRole("region", { name: "Recent activity" });
    expect((await activity.boundingBox())!.width).toBeGreaterThan((await page.locator("main").boundingBox())!.width * 0.85);
    await capture(page, info.outputPath("home-activity.png"));
    if (width === 390) await page.getByRole("button", { name: "Open navigation" }).click();
    const nav = page.getByRole("navigation", { name: "Main navigation" });
    await expect(nav.getByRole("link", { name: "Missions, new results", exact: true })).toBeVisible();
    await expect(nav).not.toContainText(/\d/);
    await expect(nav.getByTestId("new-results-dot")).toHaveCount(1);
    await expect(nav.getByRole("link", { name: "Evidence", exact: true })).toBeVisible();
    await expect(nav.getByRole("link", { name: "Reports", exact: true })).toBeVisible();
    await capture(page, info.outputPath("home-new.png"));
    if (width === 390) await page.keyboard.press("Escape");
    for (const kind of ["mission", "report"] as const) {
      await page.goto(`/${kind}s`);
      await checkRows(page, kind, "list");
      expect(batches).toContainEqual(states.map(state => ({ type: kind, id: `${kind}-${state}` })));
      await capture(page, info.outputPath(`${kind}s.png`));
    }
    expect(writes).toEqual([]);
    await page.goto("/");
    const newRow = page.locator('li[data-new="true"]');
    await newRow.getByRole("button", { name: "Mark viewed" }).click();
    await expect(page.locator("main").getByRole("link", { name: "new mission", exact: true })).toHaveCSS("font-weight", "400");
    if (width === 390) await page.getByRole("button", { name: "Open navigation" }).click();
    await expect(page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Missions", exact: true })).toBeVisible();
    await expect(page.getByTestId("new-results-dot")).toHaveCount(0);
    await capture(page, info.outputPath("home-seen.png"));
    expect(writes).toEqual(["mission-new"]);
  });
}
