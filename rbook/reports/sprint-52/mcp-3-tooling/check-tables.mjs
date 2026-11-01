// Assert the README and docs/mcp-tools.md tool tables match CLUSTER_ACTIONS exactly (order included).
import fs from 'node:fs';
import path from 'node:path';
process.env.VITEST = '1'; // keep the entrypoint from starting a stdio server on import
const REPO = '/Users/systemsystems/portfolio/TraceLab';
const { CLUSTER_ACTIONS } = await import(path.join(REPO, 'packages/tracelab-mcp/dist/index.js'));
const expected = Object.fromEntries(Object.entries(CLUSTER_ACTIONS).map(([tool, actions]) => [tool, [...actions]]));
const report = { tools: Object.keys(expected).length, actions: Object.values(expected).flat().length, files: {} };
let failed = false;
for (const file of ['packages/tracelab-mcp/README.md', 'docs/mcp-tools.md']) {
  const text = fs.readFileSync(path.join(REPO, file), 'utf8');
  const rows = {};
  for (const line of text.split('\n')) {
    const match = /^\| `(tracelab_[a-z_]+)` \| (.+?) \|/.exec(line);
    if (match) rows[match[1]] = [...match[2].matchAll(/`([a-z_]+)`/g)].map(m => m[1]);
  }
  const mismatches = Object.entries(expected).filter(([tool, actions]) => JSON.stringify(rows[tool]) !== JSON.stringify(actions)).map(([tool]) => ({ tool, table: rows[tool], registry: expected[tool] }));
  const extra = Object.keys(rows).filter(tool => !(tool in expected));
  report.files[file] = { rows: Object.keys(rows).length, mismatches, extra };
  if (mismatches.length || extra.length || Object.keys(rows).length !== report.tools) failed = true;
}
console.log(JSON.stringify(report, null, 2));
if (failed) process.exit(1);
