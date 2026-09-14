import fs from "node:fs";
import path from "node:path";
import { expect, it } from "vitest";

import config from "../../next.config";
import migrations from "./route-migrations.json";

it("keeps every maintained roadmap row in the executable migration map", () => {
  const roadmap = fs.readFileSync(path.resolve(process.cwd(), "../cmos/foundational-docs/roadmap-sprints-50-53-ux-overhaul.md"), "utf8");
  const table = roadmap.split("## Route Migration Map")[1].split("\n---")[0];
  const rows = table.split("\n").filter(line => line.startsWith("| `/"));
  expect(rows).toHaveLength(migrations.length);
  for (const migration of migrations) {
    const source = migration.source.replace(":id", "{id}");
    const destination = migration.destination.replace(":id", "{id}");
    const row = rows.find(line => line.split("|")[1].trim() === `\`${source}\``);
    expect(row, `Roadmap must describe ${source} independently`).toBeDefined();
    expect(row!.split("|")[2].trim()).toBe(`\`${destination}\``);
    expect(row!.split("|")[3].trim()).toBe(migration.sprint);
  }
});

it("keeps permanent redirects for all aliases without redirecting canonical Home to itself", async () => {
  const redirects = await config.redirects!();
  const aliases = migrations.filter(row => row.kind === "redirect");
  expect(new Set(migrations.map(row => row.source)).size).toBe(migrations.length);
  expect(aliases).toHaveLength(7);
  expect(redirects).toHaveLength(aliases.length);
  for (const row of aliases) {
    expect(redirects).toContainEqual({ source: row.source, destination: row.destination, permanent: true });
    const target = new URL(row.destination, "https://tracelab.aquex.ai").pathname;
    expect(aliases.some(alias => alias.source === target)).toBe(false);
  }
  expect(migrations.find(row => row.source === "/")).toMatchObject({ destination: "/", kind: "page" });
  expect(redirects.some(row => row.source === "/")).toBe(false);
});
