#!/usr/bin/env node
// Argument-level MCP parity (next-step #307).
//
// The cluster audit proves an ACTION NAME exists. That is a transport count: it says
// nothing about whether the arguments a client is told to send are the arguments the
// handler actually accepts.
//
// Two schemas describe every tool and they can disagree silently:
//   * inputSchema.properties  — advertised to MCP clients, drives their call shape
//   * the Zod schema the handler .parse()s — the runtime contract
// Zod strips unknown keys by default, so a property advertised but absent from the Zod
// schema is accepted, ignored and never reported. This is the input-side twin of the
// two-serializers bug in cmos/contracts/mission-authoring-contract.md.
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(ROOT, 'packages/tracelab-mcp/package.json'));
const ts = require('typescript');

function walk(node, visit) { visit(node); ts.forEachChild(node, child => walk(child, visit)); }

/** Map a Zod call chain back to its base type, e.g. z.string().min(1).optional() -> string. */
function zodBaseType(node) {
  let current = node;
  while (current && ts.isCallExpression(current)) {
    const target = current.expression;
    if (ts.isPropertyAccessExpression(target)) {
      const name = target.name.text;
      if (ts.isIdentifier(target.expression) && target.expression.text === 'z') return name;
      current = target.expression;
      continue;
    }
    break;
  }
  if (current && ts.isPropertyAccessExpression(current) && ts.isIdentifier(current.expression) && current.expression.text === 'z') {
    return current.name.text;
  }
  return null;
}

/** JSON Schema type names for the Zod base types this package uses. */
const ZOD_TO_JSON = {
  string: 'string', number: 'number', boolean: 'boolean', array: 'array',
  object: 'object', enum: 'string', literal: 'string', record: 'object',
  union: null, any: null, unknown: null, coerce: null, nativeEnum: 'string',
};

export function parse(root = ROOT) {
  const file = path.join(root, 'packages/tracelab-mcp/src/index.ts');
  const source = ts.createSourceFile('index.ts', fs.readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true);
  const consts = new Map();
  const functions = new Map();
  walk(source, node => {
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.initializer) consts.set(node.name.text, node.initializer);
    if (ts.isFunctionDeclaration(node) && node.name) functions.set(node.name.text, node);
  });
  const unwrap = node => {
    let current = node;
    while (current && (ts.isAsExpression(current) || ts.isParenthesizedExpression(current))) current = current.expression;
    if (current && ts.isIdentifier(current) && consts.has(current.text)) return unwrap(consts.get(current.text));
    return current;
  };

  // 1. Advertised arguments, per tool, from inputSchema.properties.
  const advertised = new Map();
  walk(source, node => {
    if (!ts.isObjectLiteralExpression(node)) return;
    const nameProp = node.properties.find(p => p.name?.getText() === 'name' && ts.isPropertyAssignment(p));
    const schemaProp = node.properties.find(p => p.name?.getText() === 'inputSchema' && ts.isPropertyAssignment(p));
    if (!nameProp || !schemaProp || !ts.isStringLiteral(nameProp.initializer)) return;
    const properties = unwrap(schemaProp.initializer).properties?.find(p => p.name?.getText() === 'properties');
    if (!properties || !ts.isPropertyAssignment(properties)) return;
    const fields = new Map();
    for (const property of unwrap(properties.initializer).properties ?? []) {
      if (!property.name) continue;
      const typeProp = unwrap(property.initializer)?.properties?.find(p => p.name?.getText() === 'type');
      const declared = typeProp && ts.isPropertyAssignment(typeProp) && ts.isStringLiteral(typeProp.initializer) ? typeProp.initializer.text : null;
      fields.set(property.name.getText().replace(/['"]/g, ''), declared);
    }
    advertised.set(nameProp.initializer.text, fields);
  });

  // 2. Accepted arguments, per Zod schema, following spreads into shared field objects.
  // Zod schemas compose: z.object({...}).refine(...), Base.extend({...}), A.merge(B),
  // .superRefine/.partial/.strict. Resolving only the outermost call makes a composed
  // schema look like it accepts nothing, which then reports every one of its arguments as
  // advertised-but-never-accepted. That false positive is worse than no check at all, so
  // the chain is walked and the field maps are unioned.
  const literalFields = literal => {
    const fields = new Map();
    for (const property of literal.properties ?? []) {
      if (ts.isSpreadAssignment(property)) {
        const spread = unwrap(property.expression);
        if (spread && ts.isObjectLiteralExpression(spread)) {
          for (const [key, value] of literalFields(spread)) fields.set(key, value);
        } else if (ts.isIdentifier(property.expression)) {
          for (const [key, value] of (collect(property.expression) ?? new Map())) fields.set(key, value);
        }
        continue;
      }
      if (property.name) fields.set(property.name.getText().replace(/['"]/g, ''), zodBaseType(unwrap(property.initializer)));
    }
    return fields;
  };
  const seen = new Set();
  function collect(node) {
    let current = unwrap(node);
    if (!current) return null;
    if (ts.isIdentifier(current)) {
      if (seen.has(current.text)) return new Map();
      seen.add(current.text);
      const resolved = consts.get(current.text);
      return resolved ? collect(resolved) : null;
    }
    if (ts.isObjectLiteralExpression(current)) return literalFields(current);
    if (!ts.isCallExpression(current)) return null;
    const target = current.expression;
    if (!ts.isPropertyAccessExpression(target)) return null;
    const method = target.name.text;
    if (ts.isIdentifier(target.expression) && target.expression.text === 'z') {
      if (method !== 'object') return null;
      const literal = current.arguments?.[0] ? unwrap(current.arguments[0]) : null;
      return literal && ts.isObjectLiteralExpression(literal) ? literalFields(literal) : null;
    }
    const base = collect(target.expression) ?? new Map();
    if (method === 'extend' || method === 'merge') {
      const argument = current.arguments?.[0] ? unwrap(current.arguments[0]) : null;
      const extra = argument ? (ts.isObjectLiteralExpression(argument) ? literalFields(argument) : collect(argument)) : null;
      for (const [key, value] of (extra ?? new Map())) base.set(key, value);
    }
    // refine / superRefine / partial / strict / optional / transform keep the field set.
    return base;
  }
  const zodFields = name => { seen.clear(); return collect(consts.get(name) ? ts.factory.createIdentifier(name) && consts.get(name) : null); };

  // 3. tool -> actions -> handler -> Zod schema.
  const clusters = unwrap(consts.get('CLUSTER_HANDLERS'));
  const tools = new Map();
  for (const property of clusters?.properties ?? []) {
    if (!property.name || !ts.isPropertyAssignment(property)) continue;
    const tool = property.name.getText().replace(/['"]/g, '');
    const clusterFn = functions.get(property.initializer.getText());
    if (!clusterFn) continue;
    const actions = new Map();
    walk(clusterFn, node => {
      if (!ts.isCaseClause(node) || !ts.isStringLiteral(node.expression)) return;
      const action = node.expression.text;
      let handler = null;
      walk(node, inner => {
        if (!handler && ts.isCallExpression(inner) && ts.isIdentifier(inner.expression) && /^handle/.test(inner.expression.text)) handler = inner.expression.text;
      });
      if (!handler) return;
      const target = functions.get(handler);
      let schema = null;
      if (target) walk(target, inner => {
        if (!schema && ts.isCallExpression(inner) && ts.isPropertyAccessExpression(inner.expression)
          && ['parse', 'safeParse'].includes(inner.expression.name.text) && ts.isIdentifier(inner.expression.expression)) {
          schema = inner.expression.expression.text;
        }
      });
      actions.set(action, { handler, schema, fields: schema ? zodFields(schema) : null });
    });
    tools.set(tool, actions);
  }
  return { advertised, tools };
}

/** Arguments every action tolerates because the cluster reads them before dispatch. */
const CLUSTER_LEVEL = new Set(['action']);

export function check(parsed) {
  const gaps = [];
  for (const [tool, actions] of parsed.tools) {
    const declared = parsed.advertised.get(tool);
    if (!declared) { gaps.push({ tool, kind: 'tool-not-advertised', detail: 'CLUSTER_HANDLERS entry has no tool definition' }); continue; }
    const accepted = new Map();
    for (const [action, info] of actions) {
      if (!info.fields) { gaps.push({ tool, action, kind: 'handler-schema-unresolved', detail: `${info.handler} has no resolvable Zod input schema` }); continue; }
      for (const [field, type] of info.fields) if (!accepted.has(field)) accepted.set(field, type);
    }
    for (const [field, type] of declared) {
      if (CLUSTER_LEVEL.has(field)) continue;
      if (!accepted.has(field)) {
        gaps.push({ tool, argument: field, kind: 'advertised-but-never-accepted', detail: 'declared in inputSchema; no action’s Zod schema accepts it, so Zod strips it silently' });
        continue;
      }
      const zod = accepted.get(field);
      const expected = zod === null || zod === undefined ? null : ZOD_TO_JSON[zod];
      if (type && expected && type !== expected && !(type === 'integer' && expected === 'number')) {
        gaps.push({ tool, argument: field, kind: 'type-mismatch', detail: `inputSchema says ${type}; Zod says ${zod}` });
      }
    }
    for (const field of accepted.keys()) {
      if (CLUSTER_LEVEL.has(field) || declared.has(field)) continue;
      gaps.push({ tool, argument: field, kind: 'accepted-but-not-advertised', detail: 'a handler accepts it but no client can discover it from inputSchema' });
    }
  }
  return gaps;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const parsed = parse();
  const gaps = check(parsed);
  const report = {
    tools: parsed.tools.size,
    actions: [...parsed.tools.values()].reduce((total, actions) => total + actions.size, 0),
    advertised_arguments: [...parsed.advertised.values()].reduce((total, fields) => total + fields.size, 0),
    gaps,
  };
  console.log(JSON.stringify(report, null, 2));
  if (gaps.length) process.exitCode = 1;
}
