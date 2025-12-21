/*
 * Semantic Protocol — v3.3.0 (Graph-Ready)
 * Optimized for: cataloging, deterministic indexing, and graph-based search.
 *
 * Key upgrades vs v3.2.x:
 * - Deterministic vector hashing (no string % number bug)
 * - Rich graph edges (relationships.edges) + export helpers
 * - Practical query language (arrays, exists, in, regex, comparisons, AND/OR)
 * - Catalog search that blends lexical + vector + graph-proximity scoring
 *
 * Zero dependencies. Works in Node or modern browsers (BigInt required).
 */

// ————————————————————————————————————————————————————————————————
// Tiny shared utils (zero deps)
// ————————————————————————————————————————————————————————————————
const clone = x => JSON.parse(JSON.stringify(x));

function jsonCanon(v){
  if (v === null || typeof v !== 'object') return JSON.stringify(v);
  if (Array.isArray(v)) return '[' + v.map(jsonCanon).join(',') + ']';
  const k = Object.keys(v).sort();
  return '{' + k.map(x => JSON.stringify(x) + ':' + jsonCanon(v[x])).join(',') + '}';
}

// FNV-1a 64-bit over string → BigInt
function fnv1a64BigInt(str){
  const s = String(str ?? '');
  let h = BigInt('0xcbf29ce484222325');
  const p = BigInt('0x100000001b3');
  for (let i = 0; i < s.length; i++){
    h ^= BigInt(s.charCodeAt(i));
    h = (h * p) & BigInt('0xFFFFFFFFFFFFFFFF');
  }
  return h;
}

// Hash any JSON-serializable value → "fnv1a64-<16hex>"
function hash(value){
  const bi = fnv1a64BigInt(jsonCanon(value));
  return 'fnv1a64-' + bi.toString(16).padStart(16, '0');
}

function hashToBigInt(h){
  const m = /fnv1a64-([0-9a-fA-F]{16})/.exec(String(h || ''));
  if (!m) return BigInt(0);
  try { return BigInt('0x' + m[1]); } catch { return BigInt(0); }
}

function dget(obj, path){
  if (!path) return obj;
  const p = String(path).replace(/\[(\d+)\]/g, '.$1').split('.');
  let cur = obj;
  for (const k of p){ if (cur == null) return undefined; cur = cur[k]; }
  return cur;
}

function dset(obj, path, val){
  const parts = String(path).split('.');
  let cur = obj;
  while (parts.length > 1){
    const k = parts.shift();
    if (!(k in cur) || typeof cur[k] !== 'object') cur[k] = {};
    cur = cur[k];
  }
  cur[parts[0]] = val;
}

function safeParseRhs(rhs){
  const s = String(rhs ?? '');
  // Allow JSON values for richer queries: numbers, booleans, arrays, objects
  if (/^\s*(\{|\[|true\b|false\b|null\b|-?\d+(\.\d+)?\s*)/i.test(s)){
    try { return JSON.parse(s); } catch { /* fallthrough */ }
  }
  return s;
}

function isAnyUrn(u){
  // General URN acceptance (lets you link external systems too)
  return typeof u === 'string' && /^urn:[a-zA-Z0-9][a-zA-Z0-9:+.\-_/]*$/.test(u);
}

function isProtoUrn(u){
  // Suite URNs (kept compatible with your family)
  return typeof u === 'string' &&
    /^urn:proto:(api|api\.endpoint|data|event|ui|workflow|infra|device|ai|iam|metric|integration|testing|docs|obs|config|release|agent|semantic):[A-Za-z0-9_.\/-]+(@[\d.]+)?(#[^#\s]+)?$/.test(u);
}

// Tokenize text for lexical search (simple + deterministic)
function tokenize(text){
  const t = String(text ?? '').toLowerCase();
  const tokens = t.match(/[a-z0-9]+/g) || [];
  // de-dupe while preserving some order
  const seen = new Set();
  const out = [];
  for (const tok of tokens){
    if (tok.length < 2) continue;
    if (seen.has(tok)) continue;
    seen.add(tok);
    out.push(tok);
  }
  return out;
}

function l2Normalize(vec){
  const mag = Math.sqrt(vec.reduce((s, v) => s + (v * v), 0));
  if (!mag) return vec;
  return vec.map(v => v / mag);
}

function cosineSimilarity(a, b){
  if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return 0;
  let dot = 0, magA = 0, magB = 0;
  for (let i = 0; i < a.length; i++){
    const x = a[i] || 0, y = b[i] || 0;
    dot += x * y;
    magA += x * x;
    magB += y * y;
  }
  if (!magA || !magB) return 0;
  return dot / (Math.sqrt(magA) * Math.sqrt(magB));
}

// Deterministic fallback vectorizer: hashed bag-of-words
function vectorizeDeterministic(text, dims = 128, seed = ''){
  const toks = tokenize(text);
  const v = new Array(dims).fill(0);
  for (const tok of toks){
    const idx = Number(fnv1a64BigInt(seed + '|' + tok) % BigInt(dims));
    v[idx] += 1;
  }
  return l2Normalize(v);
}

function stableSlug(s){
  return String(s ?? '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80) || 'item';
}

function sortEdges(edges){
  const arr = (edges || []).slice();
  arr.sort((a, b) => {
    const ak = `${a?.type||''}|${a?.from||''}|${a?.to||''}|${a?.direction||''}`;
    const bk = `${b?.type||''}|${b?.from||''}|${b?.to||''}|${b?.direction||''}`;
    return ak.localeCompare(bk);
  });
  return arr;
}

// ————————————————————————————————————————————————————————————————
// Semantic Protocol Engine
// ————————————————————————————————————————————————————————————————
class SemanticProtocolV33 {
  constructor(options = {}){
    this.options = {
      version: '3.3.0',
      defaultVectorDims: 128,
      // Optional injection point: (manifest) => { model, dims, vector }
      vectorizer: null,
      ...options
    };

    this._validators = new Map();
    this._registerBuiltIns();
  }

  registerValidator(name, fn){ this._validators.set(name, fn); }

  validate(manifest, selected = []){
    const names = selected.length ? selected : Array.from(this._validators.keys());
    const results = names.map(n => ({ name: n, ...(this._validators.get(n)?.(manifest) || { ok: true }) }));
    return { ok: results.every(r => r.ok), results };
  }

  // Practical query language:
  // - Supports AND: "a:=:x && b:contains:y"
  // - Supports OR:  "a:=:x || b:=:y"
  // Operators:
  //   :=: equals (deep-ish)
  //   contains: substring OR array-any substring
  //   has: array includes exact (or object has key)
  //   in: lhs is in rhs-list (rhs is JSON array or comma list)
  //   exists: path exists / truthy-ish
  //   regex: rhs is /pattern/i or plain pattern (case-insensitive)
  //   > < >= <= numeric comparisons
  query(manifest, expr){
    const s = String(expr ?? '').trim();
    if (!s) return false;

    // OR
    if (s.includes('||')){
      return s.split('||').some(part => this.query(manifest, part.trim()));
    }
    // AND
    if (s.includes('&&')){
      return s.split('&&').every(part => this.query(manifest, part.trim()));
    }

    const [rawPath, op, ...rest] = s.split(':');
    const rhsRaw = rest.join(':');
    const path = rawPath?.trim();
    const oper = op?.trim();
    const rhsVal = safeParseRhs(rhsRaw.trim());
    if (!path || !oper) return false;

    const lhs = dget(manifest, path.replace(/\[(\d+)\]/g, '.$1'));

    const deepEq = (a, b) => jsonCanon(a) === jsonCanon(b);

    switch (oper){
      case ':=:':
        return deepEq(lhs, rhsVal);

      case 'exists':
        return lhs !== undefined && lhs !== null;

      case 'contains': {
        if (Array.isArray(lhs)) return lhs.some(x => String(x ?? '').includes(String(rhsVal)));
        return String(lhs ?? '').includes(String(rhsVal));
      }

      case 'has': {
        if (Array.isArray(lhs)) return lhs.includes(rhsVal);
        if (lhs && typeof lhs === 'object') return Object.prototype.hasOwnProperty.call(lhs, String(rhsVal));
        return false;
      }

      case 'in': {
        let list = rhsVal;
        if (!Array.isArray(list)){
          list = String(rhsRaw ?? '').split(',').map(x => x.trim()).filter(Boolean);
        }
        return list.some(x => deepEq(lhs, x) || String(lhs) === String(x));
      }

      case 'regex': {
        const raw = String(rhsRaw ?? '').trim();
        let re = null;
        const m = raw.match(/^\/(.+)\/([gimsuy]*)$/);
        if (m) {
          try { re = new RegExp(m[1], m[2]); } catch { re = null; }
        } else {
          try { re = new RegExp(raw, 'i'); } catch { re = null; }
        }
        if (!re) return false;
        if (Array.isArray(lhs)) return lhs.some(x => re.test(String(x ?? '')));
        return re.test(String(lhs ?? ''));
      }

      case '>':  return Number(lhs) >  Number(rhsVal);
      case '<':  return Number(lhs) <  Number(rhsVal);
      case '>=': return Number(lhs) >= Number(rhsVal);
      case '<=': return Number(lhs) <= Number(rhsVal);

      default:
        return false;
    }
  }

  // Semantic intent inference (light heuristic)
  _resolveIntent(m){
    const purpose = String(m?.semantics?.purpose || '').toLowerCase();
    const verbMap = [
      ['Create',  ['create','add','submit','generate','compose']],
      ['Read',    ['read','get','view','display','list','browse','search','discover']],
      ['Update',  ['update','edit','save','modify','patch']],
      ['Delete',  ['delete','remove','archive']],
      ['Execute', ['execute','trigger','run','publish','emit','dispatch']],
    ];
    for (const [intent, keys] of verbMap){
      if (keys.some(k => purpose.includes(k))) return intent;
    }
    return 'Generic';
  }

  _calculateCriticality(m){
    const gov = m?.governance || {};
    const impact = Number(gov.businessImpact ?? 5);
    const visibility = Number(gov.userVisibility ?? 0.5);
    const pii = gov.piiHandling ? 1.0 : 0.0;

    const edgeCount = (m?.relationships?.edges || []).length;
    const blastRadius = Math.log1p(edgeCount);

    const score = (impact * 0.4) + (visibility * 0.2) + (pii * 0.3) + (blastRadius * 0.1);
    return Math.round(Math.min(10, score) * 10) / 10; // 0.0..10.0 step 0.1
  }

  _calculateConfidence(m){
    // Simple evidence-weighted confidence (0..1)
    let logOdds = Math.log(0.4 / 0.6); // prior
    const evidence = [
      { present: !!m?.semantics?.purpose,          likelihood: 1.6 },
      { present: !!m?.context?.domain,            likelihood: 1.2 },
      { present: !!m?.context?.flow,              likelihood: 1.15 },
      { present: !!m?.context?.step,              likelihood: 1.15 },
      { present: !!m?.governance?.owner,          likelihood: 1.1 },
      { present: (m?.relationships?.edges||[]).length > 0, likelihood: 1.2 },
    ];
    for (const e of evidence){
      if (e.present) logOdds += Math.log(e.likelihood);
    }
    return 1 / (1 + Math.exp(-logOdds));
  }

  _normalizeBindings(bindings = {}){
    const norm = {};
    // Include known keys + any extra keys caller provides
    const keys = new Set([
      'api','event','workflow','data','ui','docs','metric','obs','integration','testing','config','release','infra','device','ai','iam',
      ...Object.keys(bindings || {})
    ]);
    for (const key of Array.from(keys)){
      const arr = (bindings[key] || []);
      norm[key] = arr
        .map(b => ({
          urn: b?.urn,
          purpose: b?.purpose || undefined,
          requires: b?.requires || undefined,
          provides: b?.provides || undefined
        }))
        .filter(b => isAnyUrn(b.urn));
    }
    return norm;
  }

  // Canonical embeddable text for vector search
  _toEmbeddingText(m){
    const parts = [
      m?.urn,
      m?.element?.type,
      m?.element?.role,
      m?.element?.name,
      m?.semantics?.purpose,
      m?.metadata?.description,
      ...(m?.semantics?.tags || []),
      ...(m?.semantics?.synonyms || []),
      ...(m?.semantics?.keywords || []),
      m?.context?.domain,
      m?.context?.flow,
      m?.context?.step
    ].filter(Boolean);
    return parts.join(' | ');
  }

  // Build deterministic URN if missing
  _ensureUrn(m){
    const version = this.options.version;
    m.version = m.version || version;

    // Prefer explicit id, else deterministic fallback
    if (!m.id){
      const basis = {
        type: m?.element?.type || 'semantic',
        name: m?.element?.name || m?.element?.role || m?.semantics?.purpose || 'item',
        domain: m?.context?.domain || ''
      };
      m.id = stableSlug(basis.type + '-' + basis.name) + '-' + hash(basis).slice(-8);
    }

    if (!m.urn){
      m.urn = `urn:proto:semantic:${m.id}@${m.version}`;
    }
    return m;
  }

  // Normalize + enrich manifest deterministically
  createManifest(input = {}){
    const m = clone(input);

    this._ensureUrn(m);

    // Governance defaults (kept stable)
    m.governance = {
      owner: m?.governance?.owner,
      piiHandling: false,
      classification: m?.governance?.classification || (m?.governance?.piiHandling ? 'pii' : 'internal'),
      businessImpact: 5,
      userVisibility: 0.5,
      ...m.governance,
    };

    // Core semantic fields
    m.element = m.element || {};
    m.element.type = m.element.type || 'semantic';
    m.element.intent = m.element.intent || this._resolveIntent(m);
    m.element.criticality = (m.element.criticality != null) ? m.element.criticality : this._calculateCriticality(m);

    m.semantics = m.semantics || {};
    m.semantics.purpose = m.semantics.purpose || '';
    m.semantics.tags = Array.isArray(m.semantics.tags) ? m.semantics.tags : [];
    m.semantics.synonyms = Array.isArray(m.semantics.synonyms) ? m.semantics.synonyms : [];
    m.semantics.keywords = Array.isArray(m.semantics.keywords) ? m.semantics.keywords : [];

    m.semantics.precision = m.semantics.precision || {};
    m.semantics.precision.confidence =
      (m.semantics.precision.confidence != null) ? m.semantics.precision.confidence : this._calculateConfidence(m);

    // Context + bindings
    m.context = m.context || {};
    m.context.protocolBindings = this._normalizeBindings(m.context.protocolBindings || {});

    // Relationships / edges (graph-ready)
    m.relationships = m.relationships || {};
    m.relationships.edges = Array.isArray(m.relationships.edges) ? m.relationships.edges : [];

    // Fold protocol bindings into edges (optional but very useful for graph search)
    const bindingEdges = [];
    for (const [k, arr] of Object.entries(m.context.protocolBindings || {})){
      for (const b of (arr || [])){
        if (!isAnyUrn(b.urn)) continue;
        bindingEdges.push({
          type: 'binds_to',
          via: k,                 // binding category (api/ui/data/...)
          from: m.urn,
          to: b.urn,
          direction: 'out',
          weight: 0.6,
          reason: b.purpose || `protocolBinding:${k}`
        });
      }
    }

    // Normalize + merge edges deterministically
    const merged = [
      ...m.relationships.edges.map(e => ({
        type: e?.type || 'related_to',
        from: e?.from || m.urn,
        to: e?.to,
        direction: e?.direction || 'out',
        weight: (e?.weight != null) ? Number(e.weight) : 0.5,
        reason: e?.reason,
        evidence: e?.evidence,
        via: e?.via
      })),
      ...bindingEdges
    ].filter(e => isAnyUrn(e.from) && isAnyUrn(e.to));

    // De-dupe edges by stable key
    const edgeMap = new Map();
    for (const e of merged){
      const key = `${e.type}|${e.from}|${e.to}|${e.direction}`;
      if (!edgeMap.has(key)) edgeMap.set(key, e);
    }
    m.relationships.edges = sortEdges(Array.from(edgeMap.values()));

    // Embedding/vector
    const text = this._toEmbeddingText(m);
    m.__text = text;

    // If caller provided real embeddings, keep them.
    // Otherwise:
    //  1) if vectorizer injected, use it
    //  2) else use deterministic fallback vector
    m.semantics.embedding = m.semantics.embedding || null;
    m.semantics.features = m.semantics.features || {};

    if (!m.semantics.embedding?.vector && typeof this.options.vectorizer === 'function'){
      const emb = this.options.vectorizer(m);
      if (emb && Array.isArray(emb.vector) && Number(emb.dims || emb.vector.length) === emb.vector.length){
        m.semantics.embedding = { model: emb.model || 'external', dims: emb.dims || emb.vector.length, vector: emb.vector };
      }
    }

    if (!m.semantics.embedding?.vector){
      const dims = Number(m?.semantics?.features?.dims || this.options.defaultVectorDims);
      m.semantics.features.dims = dims;
      m.semantics.features.vector = Array.isArray(m.semantics.features.vector)
        ? m.semantics.features.vector
        : vectorizeDeterministic(text, dims, m.urn);
    }

    // Deterministic hashes/signatures (exclude timestamps/ephemera by design)
    m.__hashes = this._hashes(m);

    return m;
  }

  _hashes(m){
    const nodeShape = {
      urn: m?.urn,
      version: m?.version,
      element: {
        type: m?.element?.type,
        role: m?.element?.role,
        name: m?.element?.name,
        intent: m?.element?.intent,
        criticality: m?.element?.criticality
      },
      semantics: {
        purpose: m?.semantics?.purpose,
        tags: (m?.semantics?.tags || []).slice().sort(),
        synonyms: (m?.semantics?.synonyms || []).slice().sort(),
        keywords: (m?.semantics?.keywords || []).slice().sort(),
      },
      context: {
        domain: m?.context?.domain,
        flow: m?.context?.flow,
        step: m?.context?.step
      },
      governance: {
        owner: m?.governance?.owner,
        piiHandling: !!m?.governance?.piiHandling,
        classification: m?.governance?.classification,
        businessImpact: m?.governance?.businessImpact,
        userVisibility: m?.governance?.userVisibility
      }
    };

    const edgesShape = (m?.relationships?.edges || []).map(e => ({
      type: e.type,
      from: e.from,
      to: e.to,
      direction: e.direction,
      weight: e.weight,
      via: e.via
    }));

    const embeddingShape = m?.semantics?.embedding?.vector
      ? { model: m.semantics.embedding.model, dims: m.semantics.embedding.dims, vector: m.semantics.embedding.vector }
      : { dims: m?.semantics?.features?.dims, vector: m?.semantics?.features?.vector };

    return {
      node_hash: hash(nodeShape),
      graph_hash: hash(sortEdges(edgesShape)),
      text_hash: hash(m.__text || ''),
      vector_hash: hash(embeddingShape),
      sig_hash: hash({ node: hash(nodeShape), graph: hash(edgesShape) })
    };
  }

  diff(a, b){
    const A = a?.__hashes || this._hashes(a);
    const B = b?.__hashes || this._hashes(b);

    const changes = [];
    const significant = [];
    const breaking = [];

    if (A.node_hash !== B.node_hash){
      significant.push({ path: 'node', reason: 'node fields changed', from: A.node_hash, to: B.node_hash });
    }
    if (A.graph_hash !== B.graph_hash){
      significant.push({ path: 'relationships.edges', reason: 'graph edges changed', from: A.graph_hash, to: B.graph_hash });
    }
    if (A.vector_hash !== B.vector_hash){
      significant.push({ path: 'semantics.embedding/features.vector', reason: 'vector changed', from: A.vector_hash, to: B.vector_hash });
    }

    // Breaking heuristics
    if (String(a?.urn) !== String(b?.urn)){
      breaking.push({ path: 'urn', reason: 'identity changed', from: a?.urn, to: b?.urn });
    }
    if (String(a?.element?.type) !== String(b?.element?.type)){
      breaking.push({ path: 'element.type', reason: 'node type changed', from: a?.element?.type, to: b?.element?.type });
    }

    if (breaking.length || significant.length){
      changes.push({ path: '*', from: A, to: B });
    }

    return { changes, breaking, significant };
  }

  generateDocs(m){
    const lines = [];
    lines.push(`# ${m?.urn}`);
    lines.push(`**Type**: \`${m?.element?.type}\``);
    lines.push(`**Intent**: \`${m?.element?.intent}\``);
    lines.push(`**Criticality**: \`${m?.element?.criticality}\``);
    lines.push(`\n## Purpose\n${m?.semantics?.purpose || '—'}`);
    lines.push(`\n## Tags\n${(m?.semantics?.tags||[]).length ? (m.semantics.tags.map(t=>`- ${t}`).join('\n')) : '- (none)'}`);
    lines.push(`\n## Governance\n- Owner: ${m?.governance?.owner || '—'}\n- Classification: ${m?.governance?.classification || '—'}\n- PII Handling: ${!!m?.governance?.piiHandling}`);
    lines.push(`\n## Graph Edges (${(m?.relationships?.edges||[]).length})`);
    if (!(m?.relationships?.edges||[]).length) lines.push('- (none)');
    for (const e of (m?.relationships?.edges||[])){
      lines.push(`- \`${e.type}\` ${e.from} -> ${e.to} (w=${e.weight})${e.via?` via=${e.via}`:''}`);
    }
    return lines.join('\n');
  }

  // Export graph records for ingestion
  toGraph(m, { includeExternalNodes = true } = {}){
    const nodes = [];
    const edges = [];

    const baseNode = {
      id: m.urn,
      label: m?.element?.type || 'semantic',
      properties: {
        urn: m.urn,
        id: m.id,
        version: m.version,
        intent: m?.element?.intent,
        criticality: m?.element?.criticality,
        purpose: m?.semantics?.purpose,
        tags: m?.semantics?.tags || [],
        domain: m?.context?.domain,
        owner: m?.governance?.owner,
        classification: m?.governance?.classification,
      }
    };
    nodes.push(baseNode);

    for (const e of (m?.relationships?.edges || [])){
      edges.push({
        type: e.type,
        from: e.from,
        to: e.to,
        direction: e.direction || 'out',
        weight: e.weight ?? 0.5,
        via: e.via,
        reason: e.reason
      });
      if (includeExternalNodes && e.to && e.to !== m.urn){
        nodes.push({ id: e.to, label: 'external', properties: { urn: e.to } });
      }
    }

    // De-dupe nodes by id
    const byId = new Map();
    for (const n of nodes){
      if (!byId.has(n.id)) byId.set(n.id, n);
    }

    return { nodes: Array.from(byId.values()), edges };
  }

  _registerBuiltIns(){
    this.registerValidator('core.shape', (m)=>{
      const issues = [];
      if (!isAnyUrn(m?.urn)) issues.push({ path: 'urn', msg: 'urn required and must be a URN', level: 'error' });
      if (!m?.element?.type) issues.push({ path: 'element.type', msg: 'element.type required', level: 'error' });
      return { ok: issues.length === 0, issues };
    });

    this.registerValidator('bindings.urns', (m)=>{
      const issues = [];
      const pb = m?.context?.protocolBindings || {};
      for (const [k, arr] of Object.entries(pb)){
        for (const [i, b] of (arr || []).entries()){
          if (!isAnyUrn(b?.urn)) issues.push({ path: `context.protocolBindings.${k}[${i}].urn`, msg: 'invalid URN', level: 'error' });
        }
      }
      return { ok: issues.length === 0, issues };
    });

    this.registerValidator('graph.edges', (m)=>{
      const issues = [];
      for (const [i, e] of (m?.relationships?.edges || []).entries()){
        if (!e?.type) issues.push({ path: `relationships.edges[${i}].type`, msg: 'edge type required', level: 'error' });
        if (!isAnyUrn(e?.from)) issues.push({ path: `relationships.edges[${i}].from`, msg: 'edge.from must be URN', level: 'error' });
        if (!isAnyUrn(e?.to)) issues.push({ path: `relationships.edges[${i}].to`, msg: 'edge.to must be URN', level: 'error' });
        if (e?.from === e?.to) issues.push({ path: `relationships.edges[${i}]`, msg: 'self-loop edge (from==to)', level: 'warn' });
      }
      return { ok: issues.filter(x => x.level === 'error').length === 0, issues };
    });

    this.registerValidator('vector.shape', (m)=>{
      const issues = [];
      const emb = m?.semantics?.embedding;
      const feat = m?.semantics?.features;

      if (emb?.vector){
        if (!Array.isArray(emb.vector)) issues.push({ path:'semantics.embedding.vector', msg:'must be number[]', level:'error' });
        if (Number(emb.dims || emb.vector.length) !== emb.vector.length) issues.push({ path:'semantics.embedding.dims', msg:'dims must match vector length', level:'error' });
      } else if (feat?.vector){
        if (!Array.isArray(feat.vector)) issues.push({ path:'semantics.features.vector', msg:'must be number[]', level:'error' });
        if (Number(feat.dims || feat.vector.length) !== feat.vector.length) issues.push({ path:'semantics.features.dims', msg:'dims must match vector length', level:'error' });
      } else {
        issues.push({ path:'semantics.embedding/features', msg:'a vector must exist (embedding or features)', level:'error' });
      }
      return { ok: issues.filter(x => x.level === 'error').length === 0, issues };
    });
  }
}

// ————————————————————————————————————————————————————————————————
// Suite-style factory wrapper
// ————————————————————————————————————————————————————————————————
function createSemanticProtocol(manifestInput = {}, options = {}){
  const sp = new SemanticProtocolV33(options);
  const manifest = sp.createManifest(manifestInput);
  return Object.freeze({
    manifest: () => clone(manifest),
    validate: (names=[]) => sp.validate(manifest, names),
    match: (expr) => sp.query(manifest, expr),
    query: (expr) => sp.query(manifest, expr),
    diff: (other) => sp.diff(manifest, other?.manifest ? other.manifest() : other),
    generateDocs: () => sp.generateDocs(manifest),
    toGraph: (opts) => sp.toGraph(manifest, opts),
    set: (path, value) => { const m = clone(manifest); dset(m, path, value); return createSemanticProtocol(m, options); }
  });
}

// ————————————————————————————————————————————————————————————————
// Catalog: lexical + vector + graph-aware search
// ————————————————————————————————————————————————————————————————
function createSemanticCatalog(items = [], options = {}){
  const opts = {
    weights: { text: 0.35, vector: 0.55, graph: 0.10 },
    maxResults: 25,
    ...options
  };

  const manifests = items.map(x => x?.manifest ? x.manifest() : x);
  const byUrn = new Map(manifests.map(m => [m.urn, m]));

  // Precompute tokens + vectors + adjacency
  const tokenIndex = new Map(); // token -> Set(urn)
  const tokensByUrn = new Map();
  const vectorByUrn = new Map();

  const outAdj = new Map(); // urn -> edges[]
  const inAdj  = new Map();

  function addToIndex(urn, tokens){
    for (const t of tokens){
      if (!tokenIndex.has(t)) tokenIndex.set(t, new Set());
      tokenIndex.get(t).add(urn);
    }
  }

  function getVector(m){
    if (m?.semantics?.embedding?.vector) return m.semantics.embedding.vector;
    return m?.semantics?.features?.vector || null;
  }

  for (const m of manifests){
    const text = m.__text || [
      m.urn, m.element?.type, m.element?.name, m.element?.role,
      m.semantics?.purpose, m.metadata?.description,
      ...(m.semantics?.tags||[]), ...(m.semantics?.synonyms||[]), ...(m.semantics?.keywords||[])
    ].filter(Boolean).join(' | ');

    const toks = tokenize(text);
    tokensByUrn.set(m.urn, toks);
    addToIndex(m.urn, toks);

    const vec = getVector(m);
    if (Array.isArray(vec)) vectorByUrn.set(m.urn, vec);

    const edges = (m.relationships?.edges || []);
    for (const e of edges){
      if (!outAdj.has(e.from)) outAdj.set(e.from, []);
      outAdj.get(e.from).push(e);
      if (!inAdj.has(e.to)) inAdj.set(e.to, []);
      inAdj.get(e.to).push(e);
    }
  }

  function neighbors(urn, { direction='out', types=null } = {}){
    const edges = direction === 'in' ? (inAdj.get(urn) || []) : (outAdj.get(urn) || []);
    const filtered = types ? edges.filter(e => types.includes(e.type)) : edges;
    return filtered.map(e => direction === 'in' ? e.from : e.to);
  }

  function traverse(starts, { depth=2, direction='out', types=null } = {}){
    const startUrns = Array.isArray(starts) ? starts : [starts];
    const visited = new Set(startUrns);
    const frontier = startUrns.map(u => ({ u, d: 0 }));
    const edgesOut = [];

    while (frontier.length){
      const { u, d } = frontier.shift();
      if (d >= depth) continue;
      const edges = direction === 'in' ? (inAdj.get(u) || []) : (outAdj.get(u) || []);
      for (const e of edges){
        if (types && !types.includes(e.type)) continue;
        const v = direction === 'in' ? e.from : e.to;
        edgesOut.push(e);
        if (!visited.has(v)){
          visited.add(v);
          frontier.push({ u: v, d: d + 1 });
        }
      }
    }

    return { nodes: Array.from(visited).map(u => byUrn.get(u) || { urn: u }), edges: edgesOut };
  }

  function shortestPath(from, to, { direction='out', types=null, maxDepth=6 } = {}){
    if (from === to) return [from];
    const q = [{ u: from, path: [from] }];
    const seen = new Set([from]);

    while (q.length){
      const cur = q.shift();
      if (cur.path.length > maxDepth + 1) continue;

      const edges = direction === 'in' ? (inAdj.get(cur.u) || []) : (outAdj.get(cur.u) || []);
      for (const e of edges){
        if (types && !types.includes(e.type)) continue;
        const v = direction === 'in' ? e.from : e.to;
        if (seen.has(v)) continue;
        const nextPath = cur.path.concat([v]);
        if (v === to) return nextPath;
        seen.add(v);
        q.push({ u: v, path: nextPath });
      }
    }
    return null;
  }

  // Main blended search
  function search({ text=null, vector=null, filters=null, graph=null, limit=null } = {}){
    const L = limit ?? opts.maxResults;

    // Candidate set: from tokens, else all nodes
    let candidates = new Set(byUrn.keys());

    const qTokens = text ? tokenize(text) : [];
    if (qTokens.length){
      candidates = new Set();
      for (const t of qTokens){
        const hit = tokenIndex.get(t);
        if (hit) hit.forEach(u => candidates.add(u));
      }
      // fallback to all if token index yields nothing
      if (candidates.size === 0) candidates = new Set(byUrn.keys());
    }

    // Optional filter expression(s)
    const passesFilter = (m) => {
      if (!filters) return true;
      if (typeof filters === 'function') return !!filters(m);
      if (typeof filters === 'string'){
        // reuse protocol-style query syntax: supports && and ||
        // keep a very small evaluator here
        const sp = new SemanticProtocolV33();
        return sp.query(m, filters);
      }
      return true;
    };

    // Graph proximity boost
    const graphBoost = new Map(); // urn -> boost
    if (graph?.seeds?.length){
      const depth = graph.depth ?? 2;
      const direction = graph.direction ?? 'out';
      const types = graph.types ?? null;
      const boost = Number(graph.boost ?? 0.25);

      // BFS from seeds, assign boost by distance
      const visited = new Set();
      const frontier = [];
      for (const s of graph.seeds){
        frontier.push({ u: s, d: 0 });
        visited.add(s);
        graphBoost.set(s, boost);
      }
      while (frontier.length){
        const { u, d } = frontier.shift();
        if (d >= depth) continue;
        const nexts = neighbors(u, { direction, types });
        for (const v of nexts){
          if (visited.has(v)) continue;
          visited.add(v);
          const b = boost / (d + 2); // distance decay
          graphBoost.set(v, Math.max(graphBoost.get(v) || 0, b));
          frontier.push({ u: v, d: d + 1 });
        }
      }
    }

    // If no explicit vector provided, derive a deterministic one from text (optional)
    let qVec = vector;
    if (!qVec && text){
      qVec = vectorizeDeterministic(text, 128, 'query');
    }

    const results = [];
    for (const urn of candidates){
      const m = byUrn.get(urn);
      if (!m) continue;
      if (!passesFilter(m)) continue;

      // lexical score
      let sText = 0;
      if (qTokens.length){
        const docTokens = tokensByUrn.get(urn) || [];
        const docSet = new Set(docTokens);
        let hit = 0;
        for (const t of qTokens) if (docSet.has(t)) hit++;
        sText = qTokens.length ? (hit / qTokens.length) : 0;
      }

      // vector score
      let sVec = 0;
      const dVec = vectorByUrn.get(urn);
      if (Array.isArray(qVec) && Array.isArray(dVec) && qVec.length === dVec.length){
        sVec = cosineSimilarity(qVec, dVec);
      }

      // graph score
      const sGraph = graphBoost.get(urn) || 0;

      const score =
        (opts.weights.text * sText) +
        (opts.weights.vector * sVec) +
        (opts.weights.graph * sGraph);

      results.push({
        urn,
        score,
        breakdown: { text: sText, vector: sVec, graph: sGraph },
        item: m
      });
    }

    results.sort((a, b) => b.score - a.score);
    return results.slice(0, L);
  }

  // Export graph (all nodes + edges)
  function exportGraph(){
    const nodes = manifests.map(m => ({
      id: m.urn,
      label: m?.element?.type || 'semantic',
      properties: {
        urn: m.urn,
        id: m.id,
        version: m.version,
        intent: m?.element?.intent,
        criticality: m?.element?.criticality,
        purpose: m?.semantics?.purpose,
        tags: m?.semantics?.tags || [],
        domain: m?.context?.domain,
        owner: m?.governance?.owner
      }
    }));

    const edges = [];
    for (const m of manifests){
      for (const e of (m.relationships?.edges || [])){
        edges.push({
          type: e.type,
          from: e.from,
          to: e.to,
          direction: e.direction || 'out',
          weight: e.weight ?? 0.5,
          via: e.via,
          reason: e.reason
        });
      }
    }
    return { nodes, edges };
  }

  return Object.freeze({
    items: () => clone(manifests),
    get: (urn) => clone(byUrn.get(urn)),
    find: (predicateOrExpr) => {
      if (typeof predicateOrExpr === 'function') return manifests.filter(predicateOrExpr).map(clone);
      if (typeof predicateOrExpr === 'string'){
        const sp = new SemanticProtocolV33();
        return manifests.filter(m => sp.query(m, predicateOrExpr)).map(clone);
      }
      return [];
    },
    search,
    neighbors,
    traverse,
    shortestPath,
    exportGraph
  });
}

// ————————————————————————————————————————————————————————————————
// Exports
// ————————————————————————————————————————————————————————————————
module.exports = {
  createSemanticProtocol,
  createSemanticCatalog,
  SemanticProtocolV33
};
