#!/usr/bin/env node
// Inventory actual frontend transports and trace symbol references back to page entrypoints.
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(ROOT, 'packages/tracelab-mcp/package.json'));
const ts = require('typescript');
const methods = new Set(['get', 'post', 'put', 'patch', 'delete', 'head', 'options']);
const classifications = new Set(['covered', 'partial', 'closed-MCP-1', 'closed-MCP-2', 'rest-only-by-design', 'deferred-MCP-2', 'needs-derek', 'dead-client-code']);

function filesUnder(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const filename = path.join(directory, entry.name);
    return entry.isDirectory() ? filesUnder(filename) : /\.(ts|tsx)$/.test(entry.name) && !/\.(test|spec)\./.test(entry.name) ? [filename] : [];
  });
}
function walk(node, visit) { visit(node); ts.forEachChild(node, child => walk(child, visit)); }
function functionNode(node) { return ts.isFunctionDeclaration(node) || ts.isFunctionExpression(node) || ts.isArrowFunction(node) || ts.isMethodDeclaration(node); }

export function inventory(root = ROOT) {
  const frontend = path.join(root, 'frontend');
  const files = filesUnder(path.join(frontend, 'src'));
  const program = ts.createProgram(files, {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext,
    moduleResolution: ts.ModuleResolutionKind.Bundler, jsx: ts.JsxEmit.Preserve,
    baseUrl: frontend, paths: { '@/*': ['src/*'] }, skipLibCheck: true,
  });
  const checker = program.getTypeChecker();
  const sources = files.map(filename => program.getSourceFile(filename));
  const units = new Set(sources);
  for (const source of sources) walk(source, node => { if (functionNode(node)) units.add(node); });
  const owner = node => { while (node && !units.has(node)) node = node.parent; return node; };
  const symbol = node => {
    let result = checker.getSymbolAtLocation(node);
    if (result?.flags & ts.SymbolFlags.Alias) result = checker.getAliasedSymbol(result);
    return result;
  };
  const declaration = node => symbol(node)?.valueDeclaration;
  const target = node => {
    let declared = declaration(node);
    if (!declared) return undefined;
    if ((ts.isVariableDeclaration(declared) || ts.isPropertyAssignment(declared)) && declared.initializer && functionNode(declared.initializer)) declared = declared.initializer;
    return units.has(declared) ? declared : undefined;
  };
  const edges = new Map([...units].map(unit => [unit, new Set()]));
  for (const source of sources) walk(source, node => {
    if (ts.isIdentifier(node) && !ts.isImportSpecifier(node.parent) && !ts.isImportClause(node.parent)) {
      const from = owner(node), to = target(node);
      if (from && to && from !== to) edges.get(from).add(to);
    }
    // Callback bodies are reached when their enclosing operation supplies them.
    if (functionNode(node) && (ts.isCallExpression(node.parent) || ts.isNewExpression(node.parent) || ts.isJsxExpression(node.parent))) {
      edges.get(owner(node.parent))?.add(node);
    }
  });
  const roots = sources.filter(source => source.fileName.includes('/src/pages/'));
  for (const source of roots) {
    for (const statement of source.statements) {
      if (statement.modifiers?.some(modifier => modifier.kind === ts.SyntaxKind.ExportKeyword)) {
        if (functionNode(statement)) edges.get(source).add(statement);
        if (ts.isVariableStatement(statement)) for (const d of statement.declarationList.declarations) {
          if (d.initializer && functionNode(d.initializer)) edges.get(source).add(d.initializer);
        }
      }
    }
  }
  const live = new Set();
  function reach(unit) { if (!unit || live.has(unit)) return; live.add(unit); for (const next of edges.get(unit)) reach(next); }
  roots.forEach(reach);
  const reverse = new Map([...units].map(unit => [unit, new Set()]));
  for (const [from, tos] of edges) for (const to of tos) reverse.get(to).add(from);
  function consumers(unit) {
    const seen = new Set();
    function visit(current) { if (seen.has(current) || !live.has(current)) return; seen.add(current); for (const parent of reverse.get(current)) visit(parent); }
    for (const from of reverse.get(unit)) visit(from);
    if (unit.getSourceFile().fileName.includes('/src/components/')) visit(unit);
    return [...new Set([...seen].map(n => path.relative(root, n.getSourceFile().fileName)).filter(f => /\/src\/(pages|components|features|contexts)\//.test(f)))].sort();
  }
  function expression(node, seen = new Set()) {
    if (ts.isStringLiteralLike(node)) return node.text;
    if (ts.isTemplateExpression(node)) return node.head.text + node.templateSpans.map(span => expression(span.expression, seen) + span.literal.text).join('');
    if (ts.isIdentifier(node)) {
      const declared = declaration(node);
      if (declared && ts.isVariableDeclaration(declared) && declared.initializer && !seen.has(declared)) return expression(declared.initializer, new Set([...seen, declared]));
      return `{${node.text}}`;
    }
    if (ts.isCallExpression(node) && ['buildApiUrl', 'encodeURIComponent'].includes(node.expression.getText())) return expression(node.arguments[0], seen);
    if (ts.isParenthesizedExpression(node)) return expression(node.expression, seen);
    if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.PlusToken) return expression(node.left, seen) + expression(node.right, seen);
    return `{${node.getText()}}`;
  }
  function operationName(unit) {
    if (unit.name) {
      const object = unit.parent;
      const parent = object?.parent;
      return (ts.isObjectLiteralExpression(object) && ts.isVariableDeclaration(parent) ? parent.name.getText() + '.' : '') + unit.name.getText();
    }
    if (ts.isPropertyAssignment(unit.parent)) {
      const object = unit.parent.parent;
      return (ts.isVariableDeclaration(object.parent) ? object.parent.name.getText() + '.' : '') + unit.parent.name.getText();
    }
    if (ts.isVariableDeclaration(unit.parent)) return unit.parent.name.getText();
    return operationName(owner(unit.parent));
  }
  const operations = [];
  for (const source of sources) {
    const relative = path.relative(root, source.fileName);
    if (!relative.startsWith('frontend/src/lib/api/') && relative !== 'frontend/src/components/missions/MissionRunActivity.tsx') continue;
    if (relative.endsWith('/http.ts')) continue; // Generic transport, not a UI operation.
    walk(source, node => {
      if (!ts.isCallExpression(node)) return;
      let method, route;
      const called = node.expression;
      if (ts.isPropertyAccessExpression(called) && symbol(called.expression)?.getName() === 'httpClient') {
        method = called.name.text.toUpperCase(); route = node.arguments[0];
      } else if (ts.isIdentifier(called) && ['fetch', 'apiRequest'].includes(symbol(called)?.getName() ?? called.text)) {
        const options = node.arguments[1];
        const setting = options && ts.isObjectLiteralExpression(options) ? options.properties.find(p => p.name?.getText() === 'method') : undefined;
        method = setting && ts.isPropertyAssignment(setting) ? expression(setting.initializer) : 'GET'; route = node.arguments[0];
      } else if (ts.isPropertyAccessExpression(called) && called.name.text === 'open') {
        const receiver = declaration(called.expression);
        if (receiver && ts.isVariableDeclaration(receiver) && receiver.initializer && ts.isNewExpression(receiver.initializer) && receiver.initializer.expression.getText() === 'XMLHttpRequest') {
          method = expression(node.arguments[0]); route = node.arguments[1];
        }
      }
      if (!method) return;
      if (!methods.has(method.toLowerCase()) || !route) throw new Error(`Unsupported transport in ${relative}:${source.getLineAndCharacterOfPosition(node.getStart()).line + 1}`);
      const routePath = expression(route);
      if (!routePath.startsWith('/')) throw new Error(`Unresolved API path ${relative}: ${routePath}`);
      const unit = owner(node);
      const name = operationName(unit);
      operations.push({
        id: `${relative}#${name}:${method}:${routePath}`,
        api_file: relative, operation: name,
        source_line: source.getLineAndCharacterOfPosition(node.getStart()).line + 1,
        method, path: `/api/v1${routePath}`, live: live.has(unit), ui_consumers: consumers(unit),
      });
    });
  }
  return operations.sort((a, b) => a.id.localeCompare(b.id));
}

export function clusterActions(root = ROOT) {
  const source = ts.createSourceFile('index.ts', fs.readFileSync(path.join(root, 'packages/tracelab-mcp/src/index.ts'), 'utf8'), ts.ScriptTarget.Latest, true);
  const values = new Map();
  walk(source, node => { if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name)) values.set(node.name.text, node.initializer); });
  function unwrap(node) { return ts.isAsExpression(node) ? unwrap(node.expression) : ts.isIdentifier(node) ? unwrap(values.get(node.text)) : node; }
  const registry = unwrap(values.get('CLUSTER_ACTIONS'));
  if (!ts.isObjectLiteralExpression(registry)) throw new Error('CLUSTER_ACTIONS must resolve to an object');
  return Object.fromEntries(registry.properties.map(property => [property.name.getText(), unwrap(property.initializer).elements.map(action => action.text)]));
}

export function audit(operations, manifest, actions) {
  const errors = [];
  const rows = new Map();
  for (const row of manifest.operations) {
    if (rows.has(row.id)) errors.push(`Duplicate manifest operation: ${row.id}`);
    rows.set(row.id, row);
  }
  for (const operation of operations) {
    const row = rows.get(operation.id);
    if (!row) { errors.push(`Unclassified operation: ${operation.id}`); continue; }
    rows.delete(operation.id);
    if (!classifications.has(row.classification) || !row.rationale?.trim()) errors.push(`Invalid classification/rationale: ${operation.id}`);
    if (row.method !== operation.method || row.path !== operation.path || JSON.stringify(row.ui_consumers) !== JSON.stringify(operation.ui_consumers)) errors.push(`Stale route/consumer inventory: ${operation.id}`);
    if ((row.classification === 'dead-client-code') === operation.live) errors.push(`Incorrect live/dead classification: ${operation.id}`);
    if (typeof row.mcp === 'string') {
      const separator = row.mcp.lastIndexOf('.');
      const tool = row.mcp.slice(0, separator), action = row.mcp.slice(separator + 1);
      if (!actions[tool]?.includes(action)) errors.push(`Missing CLUSTER_ACTIONS action ${row.mcp}: ${operation.id}`);
    } else if (row.mcp !== null || ['covered', 'partial', 'closed-MCP-1', 'closed-MCP-2'].includes(row.classification)) errors.push(`Invalid or missing MCP mapping: ${operation.id}`);
  }
  for (const id of rows.keys()) errors.push(`Stale manifest operation: ${id}`);
  return errors;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const operations = inventory();
  const actions = clusterActions();
  const inventoryOnly = process.argv.includes('--inventory');
  const manifest = inventoryOnly ? undefined : JSON.parse(fs.readFileSync(path.join(ROOT, 'cmos/contracts/mcp-parity-manifest.json'), 'utf8'));
  const errors = manifest ? audit(operations, manifest, actions) : [];
  const classified = operations.map(operation => ({ ...(manifest?.operations.find(row => row.id === operation.id) ?? {}), ...operation }));
  const totals = { operations: operations.length, live: operations.filter(op => op.live).length, dead: operations.filter(op => !op.live).length, tools: Object.keys(actions).length, actions: Object.values(actions).flat().length, classifications: Object.fromEntries([...classifications].map(kind => [kind, classified.filter(row => row.classification === kind).length])) };
  const report = { totals, errors, reconciliation: manifest?.reconciliation, operations: classified };
  const outputIndex = process.argv.indexOf('--output');
  if (outputIndex !== -1) fs.writeFileSync(process.argv[outputIndex + 1], JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify(outputIndex === -1 && inventoryOnly ? report : { totals, errors }, null, 2));
  if (errors.length) process.exitCode = 1;
}
