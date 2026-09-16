import { expect, test } from "@playwright/test";
import fs from "node:fs/promises";
import migrations from "../../src/lib/route-migrations.json";

test("every maintained migration preserves its destination and query parameters", async ({ request, baseURL }, testInfo) => {
  const id = "00000000-0000-4000-8000-000000000001";
  const query = "?q=scope%20%26%20provenance&tag=first&tag=second&view=all";
  const checks: Record<string, unknown>[] = [];
  try {
    for (const row of migrations) for (const suffix of ["", query]) {
      const source = row.source.replace(":id", id) + suffix;
      const expected = new URL(row.destination.replace(":id", id), baseURL);
      const destinationKeys = new Set(expected.searchParams.keys());
      for (const [key, value] of new URL(source, baseURL).searchParams) {
        if (!destinationKeys.has(key)) expected.searchParams.append(key, value);
      }
      const response = await request.get(source, { maxRedirects: 0 });
      // A retired alias must be GONE, not quietly still redirecting. Asserting 404 here is
      // what stops a retirement from being cosmetic (ALIAS-1).
      if (row.kind === "retired") {
        const passed = response.status() === 404;
        checks.push({ source: row.source, requested: source, status: response.status(), actual: null, expected: 404, passed });
        expect.soft(passed, `${source}: retired alias should be 404, got ${response.status()}`).toBe(true);
        continue;
      }
      const actual = new URL(row.kind === "redirect" ? response.headers().location ?? "" : response.url(), baseURL);
      const actualQuery = [...actual.searchParams].sort(([a], [b]) => a.localeCompare(b));
      const expectedQuery = [...expected.searchParams].sort(([a], [b]) => a.localeCompare(b));
      const passed = response.status() === (row.kind === "redirect" ? 308 : 200)
        && actual.origin === expected.origin && actual.pathname === expected.pathname
        && actual.hash === expected.hash && JSON.stringify(actualQuery) === JSON.stringify(expectedQuery);
      checks.push({ source: row.source, requested: source, status: response.status(), actual: actual.href, expected: expected.href, passed });
      expect.soft(passed, `${source}: ${response.status()} → ${actual.href}; expected ${expected.href}`).toBe(true);
    }
  } finally {
    const coverage = { baseURL, checkedAt: new Date().toISOString(), mapRows: migrations.length, coveredRows: new Set(checks.map(row => row.source)).size, checks: checks.length, passed: checks.filter(row => row.passed).length, results: checks };
    console.log(JSON.stringify({ routeMigration: { mapRows: coverage.mapRows, coveredRows: coverage.coveredRows, checks: coverage.checks, passed: coverage.passed } }));
    const output = testInfo.outputPath("route-migration-coverage.json");
    await fs.writeFile(output, JSON.stringify(coverage, null, 2));
    await testInfo.attach("route-migration-coverage", { path: output, contentType: "application/json" });
  }
  expect(checks).toHaveLength(migrations.length * 2);
});
