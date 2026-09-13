import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";

function check(classes: string) {
  const source = mkdtempSync(path.join(tmpdir(), "tracelab-colors-"));
  try {
    writeFileSync(path.join(source, "Surface.tsx"), `<div className="${classes}" />`);
    return spawnSync(process.execPath, ["scripts/check-token-colors.mjs", source], { encoding: "utf8" });
  } finally {
    rmSync(source, { recursive: true, force: true });
  }
}

describe("one semantic palette on every surface", () => {
  it.each(["dark:bg-surface", "dark:hover:text-muted", "dark:prose-invert", "hover:dark:bg-surface", "text-gray-500"])("rejects a new competing palette utility: %s", (classes) => {
    const result = check(classes);
    expect(result.status).toBe(1);
    expect(result.stderr).toContain("Surface.tsx:1");
  });
  it("accepts token colors that adapt to every theme", () => {
    expect(check("bg-surface text-foreground hover:bg-surface-alt").status).toBe(0);
  });
});
