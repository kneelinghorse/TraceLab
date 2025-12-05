/**
 * Relational Core v0.1.0
 * Typed graph registry for Nodes (entities) and Edges (relationships).
 * Sits alongside SemanticCore/TemporalCore/PragmaticCore.
 *
 * Features
 *  - Register/validate nodes & edges with type compatibility and required metadata per edge kind
 *  - Referential integrity (source/target must exist)
 *  - Discovery via dot-path equality queries (subset match for objects)
 *  - Neighbor queries (in/out/both) with optional filters
 *  - Shortest path (BFS) with edge-type filter and direction
 *  - Simple import/export of graph JSON
 */

class RelationalCore {
  constructor() {
    this.version = "0.1.0";

    /** @type {Map<string, RelNode>} */
    this.nodes = new Map();
    /** @type {Map<string, RelEdge>} */
    this.edges = new Map(); // key = edge.id || `${source}~${type}~${target}`

    /** @type {Map<string, Set<string>>} */
    this.adjacencyOut = new Map(); // nodeId -> Set(edgeId)
    /** @type {Map<string, Set<string>>} */
    this.adjacencyIn  = new Map(); // nodeId -> Set(edgeId)

    this.NodeKind = new Set([
      "ui.component", "service", "api.endpoint", "db.table", "dataset",
      "team", "repo", "pipeline.job", "queue.topic", "infra.resource"
    ]);

    this.EdgeKind = new Set([
      "CALLS", "READS_FROM", "WRITES_TO", "EMITS_EVENT", "SUBSCRIBES_TO",
      "PRODUCES", "CONSUMES", "AUTHENTICATES_WITH", "AUTHORIZES_VIA",
      "CACHES", "RATE_LIMITED_BY", "MONITORED_BY", "OWNED_BY", "MAINTAINED_BY",
      "DEPLOYED_ON", "BACKED_BY", "DOCUMENTED_BY", "ALIASED_TO", "VERSION_OF",
      "DEPRECATES", "REPLACES", "MEASURES"
    ]);

    // Compatibility matrix (allowed [sourceKinds] -> [targetKinds])
    this.compat = new Map(Object.entries({
      CALLS:            { src: ["ui.component","service"],                 dst: ["api.endpoint","service"] },
      READS_FROM:       { src: ["service","pipeline.job","ui.component"], dst: ["db.table","dataset","queue.topic"] },
      WRITES_TO:        { src: ["service","pipeline.job","ui.component"], dst: ["db.table","dataset","queue.topic"] },
      EMITS_EVENT:      { src: ["service","pipeline.job","ui.component"], dst: ["queue.topic"] },
      SUBSCRIBES_TO:    { src: ["service","pipeline.job","ui.component"], dst: ["queue.topic"] },
      PRODUCES:         { src: ["service","pipeline.job"],                dst: ["dataset"] },
      CONSUMES:         { src: ["service","pipeline.job"],                dst: ["dataset"] },
      AUTHENTICATES_WITH:{src: ["ui.component","service","api.endpoint"], dst: ["service","infra.resource"] },
      AUTHORIZES_VIA:   { src: ["ui.component","service","api.endpoint"], dst: ["service","infra.resource"] },
      CACHES:           { src: ["service","api.endpoint"],                dst: ["infra.resource"] },
      RATE_LIMITED_BY:  { src: ["service","api.endpoint"],                dst: ["service","infra.resource"] },
      MONITORED_BY:     { src: ["service","api.endpoint","pipeline.job","queue.topic","db.table","dataset"], dst: ["service","infra.resource","team"] },
      OWNED_BY:         { src: ["ui.component","service","api.endpoint","db.table","dataset","repo","pipeline.job","queue.topic","infra.resource"], dst: ["team"] },
      MAINTAINED_BY:    { src: ["ui.component","service","api.endpoint","db.table","dataset","repo","pipeline.job","queue.topic","infra.resource"], dst: ["team"] },
      DEPLOYED_ON:      { src: ["service","api.endpoint","pipeline.job"], dst: ["infra.resource"] },
      BACKED_BY:        { src: ["service","api.endpoint"],                dst: ["infra.resource","db.table"] },
      DOCUMENTED_BY:    { src: ["service","api.endpoint","pipeline.job","dataset"], dst: ["repo"] },
      ALIASED_TO:       { src: ["service","api.endpoint","db.table","dataset","queue.topic","repo"], dst: ["service","api.endpoint","db.table","dataset","queue.topic","repo"] },
      VERSION_OF:       { src: ["service","api.endpoint","db.table","dataset","repo"], dst: ["service","api.endpoint","db.table","dataset","repo"] },
      DEPRECATES:       { src: ["service","api.endpoint","db.table","dataset","repo"], dst: ["service","api.endpoint","db.table","dataset","repo"] },
      REPLACES:         { src: ["service","api.endpoint","db.table","dataset","repo"], dst: ["service","api.endpoint","db.table","dataset","repo"] },
      MEASURES:         { src: ["infra.resource"],                        dst: ["infra.resource"] }
    }))
  }

  // ------------------------- Public API -------------------------

  /** @param {RelNode} n */
  registerNode(n) {
    const node = { id: n.id || this._randId("node"), kind: n.kind, name: n.name || null, refs: n.refs || {}, metadata: n.metadata || {} };
    const { valid, errors } = this.validateNode(node);
    if (!valid) throw new Error(`Invalid node(${node.id}): ${errors.join(", ")}`);
    this.nodes.set(node.id, node);
    if (!this.adjacencyOut.has(node.id)) this.adjacencyOut.set(node.id, new Set());
    if (!this.adjacencyIn.has(node.id))  this.adjacencyIn.set(node.id, new Set());
    return node.id;
  }

  /** @param {RelEdge} e */
  registerEdge(e) {
    const edge = {
      id: e.id || `${e.source}~${e.type}~${e.target}`,
      source: e.source,
      target: e.target,
      type: e.type,
      metadata: e.metadata || {}
    };
    const { valid, errors } = this.validateEdge(edge);
    if (!valid) throw new Error(`Invalid edge(${edge.id}): ${errors.join(", ")}`);

    this.edges.set(edge.id, edge);
    if (!this.adjacencyOut.has(edge.source)) this.adjacencyOut.set(edge.source, new Set());
    if (!this.adjacencyIn.has(edge.target))  this.adjacencyIn.set(edge.target,  new Set());
    this.adjacencyOut.get(edge.source).add(edge.id);
    this.adjacencyIn.get(edge.target).add(edge.id);
    return edge.id;
  }

  /** Remove edge by id */
  removeEdge(edgeId) {
    const e = this.edges.get(edgeId);
    if (!e) return false;
    this.edges.delete(edgeId);
    this.adjacencyOut.get(e.source)?.delete(edgeId);
    this.adjacencyIn.get(e.target)?.delete(edgeId);
    return true;
  }

  /** Remove node and all incident edges */
  removeNode(nodeId) {
    if (!this.nodes.has(nodeId)) return false;
    for (const eid of Array.from(this.adjacencyOut.get(nodeId) || [])) this.removeEdge(eid);
    for (const eid of Array.from(this.adjacencyIn.get(nodeId)  || [])) this.removeEdge(eid);
    this.adjacencyOut.delete(nodeId);
    this.adjacencyIn.delete(nodeId);
    this.nodes.delete(nodeId);
    return true;
  }

  /** @returns {{valid:boolean, errors:string[]}} */
  validateNode(n) {
    const errors = [];
    if (!n.id) errors.push("missing id");
    if (!n.kind || !this.NodeKind.has(n.kind)) errors.push(`invalid kind '${n.kind}'`);
    return { valid: errors.length === 0, errors };
  }

  /** @returns {{valid:boolean, errors:string[]}} */
  validateEdge(e) {
    const errors = [];
    if (!e.source) errors.push("missing source");
    if (!e.target) errors.push("missing target");
    if (!e.type || !this.EdgeKind.has(e.type)) errors.push(`invalid type '${e.type}'`);

    // Referential integrity
    const src = this.nodes.get(e.source);
    const dst = this.nodes.get(e.target);
    if (!src) errors.push(`unknown source node '${e.source}'`);
    if (!dst) errors.push(`unknown target node '${e.target}'`);

    if (src && dst) {
      // Compatibility
      const rule = this.compat.get(e.type);
      if (rule) {
        if (!rule.src.includes(src.kind)) errors.push(`type '${e.type}' not allowed from '${src.kind}'`);
        if (!rule.dst.includes(dst.kind)) errors.push(`type '${e.type}' not allowed to '${dst.kind}'`);
      }

      // Required metadata by edge type
      const md = e.metadata || {};
      if (e.type === "CALLS") {
        if (!md.protocol) errors.push("CALLS.metadata.protocol is required (e.g., 'https', 'grpc')");
        if (dst.kind === "api.endpoint" && !md.method) errors.push("CALLS to api.endpoint requires metadata.method (GET/POST/...)");
      }
      if (e.type === "READS_FROM" || e.type === "WRITES_TO") {
        const dc = md.data_contract || {};
        if (!dc.schema_id && !dc.url) errors.push(`${e.type} requires metadata.data_contract.{schema_id|url}`);
      }
      if (e.type === "OWNED_BY") {
        if (dst.kind !== "team") errors.push("OWNED_BY target must be kind 'team'");
        if (!md.contact && !md.oncall) errors.push("OWNED_BY requires metadata.contact or metadata.oncall");
      }
    }

    return { valid: errors.length === 0, errors };
  }

  /** Exact-match discovery on dot-paths; subset match for object expected values */
  discoverNodes(query = {}) {
    const out = [];
    for (const [, n] of this.nodes) if (this._matchesQuery(n, query)) out.push(n);
    return out;
  }

  discoverEdges(query = {}) {
    const out = [];
    for (const [, e] of this.edges) if (this._matchesQuery(e, query)) out.push(e);
    return out;
  }

  /** List neighbor nodes for a given node */
  neighbors(nodeId, dir = "out", filter = {}) {
    const eids = new Set();
    if (dir === "out" || dir === "both") for (const id of this.adjacencyOut.get(nodeId) || []) eids.add(id);
    if (dir === "in"  || dir === "both") for (const id of this.adjacencyIn.get(nodeId)  || []) eids.add(id);

    const result = [];
    for (const eid of eids) {
      const e = this.edges.get(eid);
      if (!e) continue;
      if (filter.type && e.type !== filter.type) continue;
      const neighborId = (e.source === nodeId) ? e.target : e.source;
      const n = this.nodes.get(neighborId);
      if (!n) continue;
      if (filter.nodeKind && n.kind !== filter.nodeKind) continue;
      result.push(n);
    }
    return result;
  }

  /** Shortest path (BFS) between two nodes; filter by allowed edge types and direction */
  path(sourceId, targetId, maxDepth = 6, allowTypes = null, direction = "out") {
    if (sourceId === targetId) return [sourceId];
    const q = [sourceId];
    const prev = new Map();
    const seen = new Set([sourceId]);

    const getEdges = (nid) => {
      const ids = [];
      if (direction === "out" || direction === "both") ids.push(...(this.adjacencyOut.get(nid) || []));
      if (direction === "in"  || direction === "both") ids.push(...(this.adjacencyIn.get(nid)  || []));
      return ids;
    };

    let depth = 0; let layerCount = 1; let nextCount = 0;
    while (q.length && depth <= maxDepth) {
      const cur = q.shift();
      const edgeIds = getEdges(cur);
      for (const eid of edgeIds) {
        const e = this.edges.get(eid); if (!e) continue;
        if (allowTypes && !allowTypes.includes(e.type)) continue;
        const nb = (e.source === cur) ? e.target : e.source;
        if (seen.has(nb)) continue;
        seen.add(nb); prev.set(nb, cur); q.push(nb); nextCount++;
        if (nb === targetId) return this._reconstructPath(prev, sourceId, targetId);
      }
      layerCount--;
      if (layerCount === 0) { depth++; layerCount = nextCount; nextCount = 0; }
    }
    return null;
  }

  // ------------------------- Import / Export -------------------------

  /** Load a graph JSON: { nodes: RelNode[], edges: RelEdge[] } */
  importGraph(graph) {
    const added = { nodes: 0, edges: 0 };
    for (const n of graph.nodes || []) { this.registerNode(n); added.nodes++; }
    for (const e of graph.edges || []) { this.registerEdge(e); added.edges++; }
    return added;
  }

  /** Export current graph to { nodes, edges } */
  exportGraph() {
    return {
      nodes: Array.from(this.nodes.values()),
      edges: Array.from(this.edges.values())
    };
  }

  // ------------------------- Internals -------------------------

  _reconstructPath(prev, start, end) {
    const path = [end];
    let cur = end;
    while (cur !== start) { cur = prev.get(cur); if (!cur) return null; path.push(cur); }
    return path.reverse();
  }

  _matchesQuery(obj, query) {
    for (const [path, expected] of Object.entries(query)) {
      const got = this._getPath(path, obj);
      if (Array.isArray(got)) {
        if (!got.includes(expected)) return false;
      } else if (expected && typeof expected === "object" && !Array.isArray(expected)) {
        if (!got || typeof got !== "object") return false;
        for (const [k, v] of Object.entries(expected)) if (got[k] !== v) return false;
      } else {
        if (got !== expected) return false;
      }
    }
    return true;
  }

  _getPath(path, obj) {
    const parts = String(path).split(".");
    let cur = obj;
    for (const p of parts) { if (cur == null) return undefined; cur = cur[p]; }
    return cur;
  }

  _randId(prefix) { return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2,8)}`; }
}

// JSDoc typedefs for editor help (optional)
/**
 * @typedef {Object} RelNode
 * @property {string} id
 * @property {string} kind
 * @property {string=} name
 * @property {{ semantic_id?: string, repo?: string, url?: string }=} refs
 * @property {Object<string, any>=} metadata
 */

/**
 * @typedef {Object} RelEdge
 * @property {string=} id
 * @property {string} source
 * @property {string} target
 * @property {string} type
 * @property {{ protocol?: string, method?: string, authentication?: string, authorization?: string, sla?: Object, data_contract?: { schema_id?: string, url?: string, version?: string, pii?: string[] }, notes?: string, tags?: string[] }=} metadata
 */

// UMD export
if (typeof module !== "undefined" && module.exports) {
  module.exports = RelationalCore;
} else if (typeof window !== "undefined") {
  window.RelationalCore = RelationalCore;
}

/* ------------------------------- Example -------------------------------
const rc = new RelationalCore();
rc.registerNode({ id: 'sem_payment_form_submit_button', kind: 'ui.component', refs: { semantic_id: 'sem_payment_form_submit_button' } });
rc.registerNode({ id: 'api:/v3/charge#POST', kind: 'api.endpoint', metadata: { service: 'payments' } });
rc.registerNode({ id: 'team:payments-platform', kind: 'team', metadata: { contact: 'oncall-payments@example.com' } });

rc.registerEdge({
  source: 'sem_payment_form_submit_button',
  target: 'api:/v3/charge#POST',
  type: 'CALLS',
  metadata: { protocol: 'https', method: 'POST', authentication: 'jwt', data_contract: { schema_id: 'charge_request_v3.2.json' } }
});

rc.registerEdge({ source: 'api:/v3/charge#POST', target: 'team:payments-platform', type: 'OWNED_BY', metadata: { contact: 'oncall-payments@example.com' } });

console.log('Neighbors OUT of button:', rc.neighbors('sem_payment_form_submit_button', 'out').map(n => n.id));
console.log('Path button → team:', rc.path('sem_payment_form_submit_button', 'team:payments-platform'));
*/
