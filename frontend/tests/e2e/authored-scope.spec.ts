import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import path from "node:path";

const fixture = path.resolve("../tests/fixtures/authored_scope_v1");
const read = (name: string) => readFileSync(path.join(fixture, name), "utf8");
const manifest = JSON.parse(read("manifest.json"));
const contract = JSON.parse(read("canonical-contract.json"));
const project = "10000000-0000-4000-8000-000000000001";
async function accessible(page: Page) {
  await page.addScriptTag({ path: path.resolve("node_modules/axe-core/axe.min.js") });
  const audit = await page.evaluate(async () => {
    const axe = (window as unknown as { axe: { run: (node: Document) => Promise<{ violations: { id: string; impact: string }[] }> } }).axe;
    return { overflow: document.documentElement.scrollWidth > innerWidth, violations: (await axe.run(document)).violations.filter(v => ["critical", "serious"].includes(v.impact)) };
  });
  expect(audit).toEqual({ overflow: false, violations: [] });
}
for (const theme of ["light", "dark"]) for (const width of [390, 820, 1440]) {
  test(`authored scope four outcomes, preview and retained exports ${theme} ${width}`, async ({ page }, info) => {
    test.setTimeout(90000);
    page.on("pageerror", error => console.error("Browser error:", error.message, error.stack));
    await page.setViewportSize({ width, height: 1000 });
    await page.emulateMedia({ colorScheme: theme as "light" | "dark" });
    await page.addInitScript(theme => {
      localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "fixture", user_id: "reader", email: "reader@example.test" }));
      localStorage.setItem("tracelab.theme.v1:reader", theme);
    }, theme);
    let current: Record<string, unknown> = {};
    let previewFails = true;
    const writes: string[] = [];
    const preview = { ...contract, compiler_revision: "79ef84842fb84259bafe59924b21fe2f5ad05d7d", compiler_semantic_revision: 3, fidelity: "structural_only", canonical_contract_id: contract.contract_id, mission_uuid: "scope" };
    await page.route("**/api/v1/**", async route => {
      const request = route.request(), endpoint = new URL(request.url()).pathname;
      // Viewing a mission records activity, but may never dispatch research.
      if (request.method() === "PUT" && endpoint === "/api/v1/activity/viewed") return route.fulfill({ json: { viewed: 0, new_total: 0 } });
      if (!["GET", "HEAD", "OPTIONS"].includes(request.method())) writes.push(endpoint);
      if (endpoint.endsWith("/auth/me")) return route.fulfill({ json: { user_id: "reader", email: "reader@example.test", role: "member" } });
      if (endpoint.endsWith("/contract-preview")) {
        if (previewFails) { previewFails = false; return route.fulfill({ status: 503, json: { detail: "Preview temporarily unavailable" } }); }
        return route.fulfill({ json: preview });
      }
      if (endpoint.endsWith("/missions/scope")) return route.fulfill({ json: current });
      if (endpoint.endsWith("/logs") || endpoint.endsWith("/events/recent")) return route.fulfill({ json: [] });
      return route.fulfill({ json: {} });
    });
    for (const output of manifest.outputs) {
      const audit = JSON.parse(read(output.expected));
      const markdown = read(output.persisted);
      const protocol = { report_metadata: { references: 2, forensic: { authored_scope: { policy: contract.authored_scope, policy_sha256: audit.policy_sha256 }, authored_scope_validation: audit, original_synthesis: { ...audit.pre_render, text: read(output.pre_render) } } } };
      current = { id: "scope", mission_id: "S64-FIXTURE", title: "Authored scope acceptance", objective: contract.objective, success_criteria: contract.success_criteria, project_id: project, status: output.mission_outcome === "complete" ? "completed" : "validation_failed", tags: [], deliverables: [], context: {}, metadata: {}, research_phases: {}, execution_metadata: { quality_record: { report_word_count: 9999 }, final_outcome: { authored_scope_validation: audit, delivery_quality: output.delivery_quality, quality_gate_failures: ["independent_quality_warning"] } }, result_protocol: protocol, result_markdown: markdown, result_document_ids: [], result_report_id: null, created_at: "2026-10-01T00:00:00Z", updated_at: "2026-10-01T00:00:00Z" };
      await page.goto("/missions/scope");
      const panel = page.getByRole("region", { name: "Scope outcome" });
      await expect(panel.getByText(`${audit.persisted.words} words · 300–500 words requested`)).toBeVisible();
      await expect(panel.getByText(`${audit.consulted_count} · maximum 2`)).toBeVisible();
      await expect(panel.getByText(/Independent research quality warning/)).toBeVisible();
      if (output.name === "partial") await expect(panel.getByText("timeout")).toBeVisible();
      if (audit.verdict === "violated") await expect(panel.getByRole("heading", { name: "Scope validation failed" })).toBeVisible();
      await panel.getByText("Count provenance", { exact: true }).focus();
      await page.keyboard.press("Enter");
      await expect(panel.getByText(/unicode-whitespace-v1/)).toBeVisible();
      await page.getByRole("tab", { name: "Results", exact: true }).click();
      const download = page.waitForEvent("download");
      await page.getByRole("button", { name: "Export as .md", exact: true }).click();
      const saved = await (await download).path();
      expect(createHash("sha256").update(readFileSync(saved!)).digest("hex")).toBe(audit.persisted.sha256);
      const protocolDownload = page.waitForEvent("download");
      await page.getByRole("button", { name: "Export full protocol", exact: true }).click();
      const protocolFile = await (await protocolDownload).path();
      expect(JSON.parse(readFileSync(protocolFile!, "utf8"))).toEqual(protocol);
      await accessible(page);
      await page.screenshot({ path: info.outputPath(`${output.name}.png`), fullPage: true });
    }
    await page.getByRole("tab", { name: "Run", exact: true }).click();
    await page.getByRole("button", { name: "Preview contract", exact: true }).click();
    await expect(page.getByText(/Preview temporarily unavailable/)).toBeVisible();
    await page.getByRole("button", { name: "Preview contract", exact: true }).click();
    const plan = page.getByRole("region", { name: "Planned scope" });
    await expect(plan.getByText(/300–500 words/)).toBeVisible();
    // Stress URL wrapping without modifying the canonical fixture bytes.
    preview.authored_scope = { ...contract.authored_scope, allowed_urls: ["https://example.test/" + "long".repeat(300)] };
    await page.getByRole("button", { name: "Refresh preview", exact: true }).click();
    await expect(plan.getByText(/https:\/\/example.test/)).toBeVisible();
    await accessible(page);
    await page.screenshot({ path: info.outputPath("planned-long-url.png"), fullPage: true });
    expect(writes).toEqual([]);
  });
}

for (const theme of ["light", "dark"]) for (const width of [390, 820, 1440]) {
  test(`reviewed Librarian scope save, retry and manual edit ${theme} ${width}`, async ({ page }, info) => {
    page.on("pageerror", error => console.error("Browser error:", error.message, error.stack));
    await page.setViewportSize({ width, height: 1000 });
    await page.addInitScript(theme => {
      localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "fixture", user_id: "reader", email: "reader@example.test" }));
      localStorage.setItem("tracelab.theme.v1:reader", theme);
    }, theme);
    const draft = { mission_id: "S64-REVIEW", title: "Reviewed exact pages", objective: contract.objective, success_criteria: contract.success_criteria, deliverables: [], tags: [], references: contract.authored_scope.reference_urls.map((url: string) => ({ url })), context: { authored_scope: contract.authored_scope, keep: "reviewed" } };
    const preview = { ...contract, compiler_revision: "79ef848", fidelity: "structural_only", mission_uuid: "saved" };
    const mission = { ...draft, id: "saved", project_id: project, status: "draft", metadata: {}, research_phases: {}, execution_metadata: {}, result_document_ids: [], result_report_id: null, created_at: "2026-10-01T00:00:00Z", updated_at: "2026-10-01T00:00:00Z" };
    let saves = 0, edits = 0;
    const unexpected: string[] = [];
    await page.route("**/api/v1/**", async route => {
      const request = route.request(), endpoint = new URL(request.url()).pathname;
      let json: unknown = {};
      if (request.method() === "PUT" && endpoint === "/api/v1/activity/viewed") return route.fulfill({ json: { viewed: 0, new_total: 0 } });
      if (endpoint.endsWith("/auth/me")) json = { user_id: "reader", email: "reader@example.test", role: "member" };
      else if (endpoint.endsWith("/spaces")) json = [];
      else if (endpoint.endsWith("/projects")) json = { data: [{ id: project, name: "Scope project" }], pagination: { total: 1, pages: 1, page: 1 } };
      else if (endpoint.endsWith("/librarian/turns")) json = { segments: [{ kind: "prose", text: "Ready to review the exact pages.", citations: [] }], suggested_action: "draft_mission", evidence: [], chunks: [], no_evidence: false, withheld_count: 0, usage: null, model: "scripted" };
      else if (endpoint.endsWith("/librarian/drafts")) json = { draft, preview, preview_error: null, lint_errors: [], lint_warnings: [], notes: [], model: "scripted" };
      else if (endpoint.endsWith("/librarian/missions")) {
        saves++;
        expect(request.postDataJSON().draft.context).toEqual(draft.context);
        expect(request.postDataJSON().draft.references).toEqual(draft.references);
        if (saves === 1) return route.fulfill({ status: 503, json: { detail: "Temporary save outage" } });
        json = { mission, created: true };
      } else if (endpoint.endsWith("/missions/saved")) {
        if (request.method() === "PATCH") {
          edits++;
          const body = request.postDataJSON();
          expect(body.context).toEqual(draft.context);
          expect(body.references).toEqual(draft.references);
          expect(body).not.toHaveProperty("execution_metadata");
          Object.assign(mission, body);
        }
        json = mission;
      } else if (endpoint.endsWith("/contract-preview")) json = preview;
      else if (endpoint.endsWith("/logs") || endpoint.endsWith("/events/recent")) json = [];
      else if (!["GET", "HEAD", "OPTIONS"].includes(request.method())) unexpected.push(endpoint);
      await route.fulfill({ json });
    });
    await page.goto(`/librarian?intent=mission&project=${project}`);
    await page.getByLabel("Message the Librarian").fill("Review these two exact pages in 300–500 words.");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await page.getByRole("button", { name: "Draft a mission", exact: true }).click();
    const draftPanel = page.getByRole("region", { name: "Mission draft" });
    await expect(draftPanel).toBeFocused();
    await expect(draftPanel.getByText(/300–500 words/)).toBeVisible();
    expect(saves).toBe(0);
    await accessible(page);
    await page.screenshot({ path: info.outputPath("librarian-review.png"), fullPage: true });
    await page.getByRole("button", { name: "Create draft mission", exact: true }).click();
    await expect(page.getByText(/Temporary save outage/)).toBeVisible();
    await page.getByRole("button", { name: "Create draft mission", exact: true }).click();
    await expect(page).toHaveURL(/\/missions\/saved/);
    await page.getByRole("button", { name: "Edit Mission", exact: true }).click();
    await page.getByLabel("Title", { exact: false }).fill("Refined exact page review");
    await page.getByRole("button", { name: "Save and preview", exact: true }).click();
    await expect(page.getByRole("region", { name: "Planned scope" }).first()).toBeVisible();
    await accessible(page);
    await page.screenshot({ path: info.outputPath("manual-review.png"), fullPage: true });
    expect(saves).toBe(2); expect(edits).toBe(1); expect(unexpected).toEqual([]);
  });
}
