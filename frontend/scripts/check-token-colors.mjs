import { readdir, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

// Color choices must follow the user's theme on every rendered surface.
const source = fileURLToPath(new URL("../src", import.meta.url));
const palette = /\b(?:bg|text|border|ring|outline|divide|fill|stroke|from|via|to|placeholder|shadow)-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}\b|\b(?:bg|text|border)-(?:white|black)\b|(?:bg|text|border)-\[(?:#|rgb|hsl|oklch)/g;
const failures = [];
async function scan(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const file = path.join(dir, entry.name);
    if (entry.isDirectory()) await scan(file);
    else if (/\.[jt]sx?$/.test(file) && !/\.test\./.test(file)) {
      const lines = (await readFile(file, "utf8")).split("\n");
      lines.forEach((line, index) => {
        const matches = line.match(palette);
        if (matches) failures.push(`${path.relative(source, file)}:${index + 1}: ${matches.join(", ")}`);
      });
    }
  }
}
await scan(source);
if (failures.length) {
  console.error("Use semantic OODS colors instead of a fixed palette:\n" + failures.join("\n"));
  process.exitCode = 1;
} else console.log("OODS color gate passed: no fixed palette colors in rendered source.");
