import { readdir, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

// Color choices must follow the user's theme on every rendered surface.
const source = process.argv[2] ? path.resolve(process.argv[2]) : fileURLToPath(new URL("../src", import.meta.url));
const palette = /\b(?:bg|text|border|ring|outline|divide|fill|stroke|from|via|to|placeholder|shadow)-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}\b|\b(?:bg|text|border)-(?:white|black)\b|(?:bg|text|border)-\[(?:#|rgb|hsl|oklch)/g;
const failures = [];
// data-theme selects the semantic token values. Theme-specific utilities
// create a second palette layer and must never be reintroduced.
const darkUtilities = /\bdark:[\w:[\]/.%-]+/g;
async function scan(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const file = path.join(dir, entry.name);
    if (entry.isDirectory()) await scan(file);
    else if (/\.(?:[jt]sx?|css)$/.test(file) && !/\.test\./.test(file)) {
      const lines = (await readFile(file, "utf8")).split("\n");
      lines.forEach((line, index) => {
        const matches = [...line.matchAll(palette), ...line.matchAll(darkUtilities)].map(match => match[0]);
        if (matches.length) failures.push(`${path.relative(source, file)}:${index + 1}: ${matches.join(", ")}`);
      });
    }
  }
}
await scan(source);
if (failures.length) {
  console.error("Use semantic OODS colors without fixed palettes or dark variants:\n" + failures.join("\n"));
  process.exitCode = 1;
} else console.log("OODS color gate passed: no fixed palette colors or dark variants in rendered source.");
