#!/usr/bin/env bash
# Exercise the distributed ESM entrypoint from an isolated npm installation.
set -euo pipefail
cd "$(dirname "$0")/.."
package_test_dir=$(mktemp -d)
trap 'rm -rf "$package_test_dir"' EXIT
npm run build
# Audit matches remain visible. device-code.ts intentionally defines a local
# __dirname from import.meta.url; the installed-entrypoint test covers ESM startup.
if command -v rg > /dev/null 2>&1; then
  rg -n '\b(__dirname|__filename)\b|\brequire\(' src --glob '*.ts' --glob '!*.test.ts' || [[ $? == 1 ]]
else
  grep -REn '(__dirname|__filename)|require\(' src --include='*.ts' --exclude='*.test.ts' || [[ $? == 1 ]]
fi
npm pack --json --pack-destination "$package_test_dir" > "$package_test_dir/pack.json"
package_archive=$(node -e 'const fs = require("node:fs"); console.log(JSON.parse(fs.readFileSync(process.argv[1], "utf8"))[0].filename)' "$package_test_dir/pack.json")
npm install --prefix "$package_test_dir/install" --no-audit --no-fund "$package_test_dir/$package_archive"
node scripts/check-canonical-links.mjs "$package_test_dir/install/node_modules/@aquex/tracelab-mcp/dist/index.js"
