import { expect, it } from "vitest";
import migrations from "./route-migrations.json";
import { inspectInternalLinks } from "../../scripts/route-migration-links.mjs";

it("finds every internal alias, including a dynamic mission and trailing slash", () => {
  const aliases = migrations.filter(row => row.kind === "redirect");
  const result = inspectInternalLinks(aliases.map(row => `${row.source.replace(":id", "MISSION-1")}/?q=scope#result`), "https://tracelab.aquex.ai/");
  expect(result.legacyInternalLinks.map(row => row.alias).sort()).toEqual(aliases.map(row => row.source).sort());
});

it("preserves canonical and external source links while keeping credentials out of receipts", () => {
  const result = inspectInternalLinks([
    "/", "/missions/MISSION-1", "/search?q=/console", "/settings?invite=secret#invites",
    "https://example.test/console", "/projects/project-1", "/projects/project-1?tab=reports",
  ], "https://tracelab.aquex.ai/");
  expect(result.legacyInternalLinks).toEqual([]);
  expect(result.internalLinks).toEqual(["/", "/missions/MISSION-1", "/projects/project-1", "/search", "/settings"]);
  expect(JSON.stringify(result)).not.toContain("secret");
});
