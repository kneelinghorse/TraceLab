import { expect, test, type Locator, type Page, type TestInfo } from "@playwright/test";
import path from "node:path";

test.use({ timezoneId: "America/Chicago" });
const kinds = ["project", "document", "mission", "report", "collection", "evidence"] as const;
type Kind = typeof kinds[number];
const id = (index: number) => `00000000-0000-4000-8000-${String(index).padStart(12, "0")}`;
const nodes = kinds.map((type, index) => ({ type, id: id(index + 1), key: `${type}:${id(index + 1)}`,
  title: type === "document" ? "A complete source title with enough detail to require clamping in the diagram but remain readable in the list" : `${type} research`,
  href: `/${type === "evidence" ? type : type + "s"}/${id(index + 1)}`,
  attributes: { updated_at: "2026-09-14T18:00:00+00:00", ...(type === "document" ? { chunk_count: 117 } : {}) },
}));
const byType = Object.fromEntries(nodes.map(node => [node.type, node])) as Record<Kind, typeof nodes[number]>;
const relations: Record<Kind, [string, Kind, number][]> = {
  project: [["documents", "document", 53], ["missions", "mission", 3], ["reports", "report", 3], ["evidence", "evidence", 547]],
  document: [["source_mission", "mission", 1], ["source_report", "report", 1], ["evidence", "evidence", 47]],
  mission: [["result_documents", "document", 12], ["result_report", "report", 1], ["evidence", "evidence", 15]],
  report: [["collections", "collection", 1], ["source_documents", "document", 2], ["evidence", "evidence", 27]],
  collection: [["documents", "document", 8]], evidence: [["mission", "mission", 1]],
};
function neighborhood(kind: Kind, depth: number, empty = false) {
  const root = byType[kind];
  const shown = new Map([[root.key, root]]);
  const edges: { from: string; to: string; relation: string; basis: string }[] = [];
  const groups: { from_key: string; relation: string; target_type: Kind; total: number; shown: number }[] = [];
  let frontier = [root];
  if (!empty) for (let hop = 0; hop < depth; hop++) {
    const next: typeof nodes = [];
    for (const from of frontier) for (const [relation, target, total] of relations[from.type]) {
      const node = byType[target];
      edges.push({ from: from.key, to: node.key, relation, basis: "persisted fixture relationship" });
      groups.push({ from_key: from.key, relation, target_type: target, total, shown: 1 });
      if (!shown.has(node.key)) { next.push(node); shown.set(node.key, node); }
    }
    frontier = next;
  }
  return { root, nodes: [...shown.values()], edges, groups, truncated: groups.some(group => group.total > group.shown) };
}

async function fixture(page: Page, options: { status?: number; empty?: boolean; gate?: Promise<void> } = {}) {
  const requests: { method: string; root: string | null; depth: string | null }[] = [];
  await page.addInitScript(() => localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "graph-test", user_id: "member", email: "member@example.test", display_name: "Graph reader" })));
  await page.route("**/api/v1/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/auth/me")) { await route.fulfill({ json: { user_id: "member", email: "member@example.test", display_name: "Graph reader", role: "member" } }); return; }
    if (url.pathname.endsWith("/navigation/search")) {
      await route.fulfill({ json: { query: url.searchParams.get("q"), groups: nodes.map(node => ({ entity_type: node.type, total: 31, page: 1, page_size: 5, items: [node] })) } }); return;
    }
    if (url.pathname.endsWith("/graph/neighborhood")) {
      requests.push({ method: route.request().method(), root: url.searchParams.get("root_type"), depth: url.searchParams.get("depth") });
      await options.gate;
      if (options.status && options.status !== 200) { await route.fulfill({ status: options.status, json: { detail: "Fixture root unavailable" } }); return; }
      await route.fulfill({ json: neighborhood(url.searchParams.get("root_type") as Kind, Number(url.searchParams.get("depth")), options.empty) }); return;
    }
    if (url.pathname.endsWith("/inbox/summary")) { await route.fulfill({ json: { generated_at: "2026-09-13T00:00:00", refresh_seconds: 30, seen_through: "2026-09-13T00:00:00", default_lookback_seconds: 604800, unread: { failures: 0, completions: 0, evidence: 0, total: 0 } } }); return; }
    await route.fulfill({ status: 404, json: { detail: "No fixture for this route" } });
  });
  return requests;
}

async function tabTo(page: Page, target: Locator) {
  for (let step = 0; step < 160; step++) {
    if (await target.evaluate(node => node === document.activeElement)) return;
    await page.keyboard.press("Tab");
  }
  await expect(target).toBeFocused();
}
async function audit(page: Page, info: TestInfo, name: string) {
  await page.addScriptTag({ path: path.resolve("node_modules/axe-core/axe.min.js") });
  const result = await page.evaluate(async () => {
    const axe = (window as unknown as { axe: { run: (node: Document) => Promise<{ violations: { id: string; impact: string }[] }> } }).axe;
    return { overflow: document.documentElement.scrollWidth > innerWidth,
      violations: (await axe.run(document)).violations.filter(v => ["critical", "serious"].includes(v.impact)),
      mainCount: document.querySelectorAll("main").length };
  });
  expect(result).toEqual({ overflow: false, violations: [], mainCount: 1 });
  await page.screenshot({ path: info.outputPath(`${name}.png`), fullPage: true });
}

test("keyboard root selection, depth, every list control and browser Back preserve the neighborhood", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 1000 });
  const requests = await fixture(page);
  await page.goto("/graph");
  const input = page.getByRole("textbox", { name: "Find an object" });
  await tabTo(page, input);
  await page.keyboard.type("research");
  await page.keyboard.press("Enter");
  const choice = page.getByRole("button", { name: "Center on project research" });
  await choice.waitFor();
  await tabTo(page, choice);
  await page.keyboard.press("Enter");
  await expect(page.locator("[data-neighborhood-root]")).toHaveAttribute("data-neighborhood-root", byType.project.key);
  await tabTo(page, page.getByRole("button", { name: "Depth 2", exact: true }));
  await page.keyboard.press("Space");
  await expect(page).toHaveURL(/depth=2/);
  await expect(page.locator(`[data-list-node-key="${byType.collection.key}"]`)).toBeVisible();
  const center = page.getByRole("region", { name: "Relationship list" }).getByRole("button", { name: `Center here: ${byType.document.title}`, exact: true }).first();
  await tabTo(page, center);
  await page.keyboard.press("Enter");
  await expect(page.locator("[data-neighborhood-root]")).toHaveAttribute("data-neighborhood-root", byType.document.key);
  await page.goBack();
  await expect(page.locator("[data-neighborhood-root]")).toHaveAttribute("data-neighborhood-root", byType.project.key);
  await expect(page.getByRole("button", { name: "Depth 2", exact: true })).toHaveAttribute("aria-pressed", "true");
  const controls = page.locator("[data-list-node-key] a,[data-list-node-key] button");
  await tabTo(page, controls.first());
  for (let index = 0; index < await controls.count(); index++) {
    await expect(controls.nth(index)).toBeFocused();
    await page.keyboard.press("Tab");
  }
  expect(await page.getByRole("region", { name: "Relationship list" }).evaluate(node => node.contains(document.activeElement))).toBe(false);
  await expect(page.locator('svg[role="img"] a,svg[role="img"] button,svg[role="img"] [tabindex]')).toHaveCount(0);
  expect(requests.some(request => request.root === "document" && request.depth === "2")).toBe(true);
  expect(requests.every(request => request.method === "GET")).toBe(true);
});

for (const theme of ["light", "dark"] as const) for (const width of [1440, 390]) {
  test(`the complete ${theme} graph and root picker remain accessible at ${width}px`, async ({ page }, info) => {
    await fixture(page);
    await page.setViewportSize({ width, height: 1000 });
    await page.emulateMedia({ colorScheme: theme });
    await page.goto("/graph");
    await page.getByText("Choose an object to explore", { exact: true }).waitFor();
    await audit(page, info, "root-picker");
    await page.goto(`/graph?root=${byType.project.key}&depth=2`);
    await page.getByRole("region", { name: "Relationship list" }).waitFor();
    if (width === 390) await page.getByRole("button", { name: "Open navigation" }).click();
    await expect(page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Relationships" }).first()).toHaveAttribute("aria-current", "page");
    if (width === 390) await page.keyboard.press("Escape");
    const keys = await page.evaluate(() => ({
      diagram: [...document.querySelectorAll("[data-graph-node-key]")].map(n => n.getAttribute("data-graph-node-key")),
      list: [...document.querySelectorAll("[data-list-node-key]")].map(n => n.getAttribute("data-list-node-key")),
    }));
    expect(new Set(keys.diagram)).toEqual(new Set(keys.list));
    await expect(page.locator(`[data-relation-group="${byType.project.key}:documents"]`).getByText("1 of 53 shown")).toBeVisible();
    await expect(page.locator(`[data-relation-group="${byType.project.key}:evidence"]`).getByText("1 of 547 shown")).toBeVisible();
    await expect(page.getByRole("link", { name: byType.document.title, exact: true }).first()).toBeVisible();
    expect(await page.locator("time").first().textContent()).toContain("1:00:00 PM");
    await audit(page, info, "neighborhood");
    if (width === 390) {
      await page.getByText("Show relationship diagram", { exact: true }).click();
      await expect(page.getByRole("img", { name: /Relationship diagram/ })).toBeVisible();
      await audit(page, info, "mobile-diagram");
    }
  });
}

test("all six URL root types reach the same graph endpoint and canonical object link", async ({ page }) => {
  const requests = await fixture(page);
  for (const kind of kinds) {
    await page.goto(`/graph?root=${byType[kind].key}`);
    const root = page.getByRole("region", { name: "Root object", exact: true });
    await expect(root.getByRole("link", { name: byType[kind].title })).toHaveAttribute("href", byType[kind].href);
  }
  expect(new Set(requests.map(request => request.root))).toEqual(new Set(kinds));
});

test("loading, empty, forbidden, missing and retriable failures have distinct states", async ({ page }, info) => {
  let release!: () => void;
  const options = { status: 200, empty: true, gate: new Promise<void>(resolve => { release = resolve; }) };
  await fixture(page, options);
  await page.goto(`/graph?root=${byType.project.key}`);
  await expect(page.getByText("Loading relationships…", { exact: true })).toBeVisible();
  release();
  await expect(page.getByText("No accessible relationships are recorded", { exact: true })).toBeVisible();
  await audit(page, info, "empty");
  for (const [status, title] of [[403, "Access to this object is restricted"], [404, "Root object not found"], [500, "Relationships could not load"]] as const) {
    options.status = status;
    await page.reload();
    await expect(page.getByText(title, { exact: true })).toBeVisible();
    await audit(page, info, `state-${status}`);
  }
  options.status = 200;
  options.empty = false;
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(page.getByRole("region", { name: "Relationship list" })).toBeVisible();
});
