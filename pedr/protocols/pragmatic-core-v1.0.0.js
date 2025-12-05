/**
 * Pragmatic Core v1.0.0
 * Decision/Use layer for the Protocol Family
 *
 * Purpose
 *  - Consume signals (esp. TemporalCore findings) and *decide what to do*.
 *  - Unify: goal → trigger → context/guards → policy/conflict-resolution → action → audit/effects.
 *  - Mirrors style of SemanticProtocol & TemporalCore (registry, manifests, validators, discovery).
 *
 * Key Concepts
 *  - Directive: a pragmatic rule describing when & how to act.
 *  - Trigger: event that proposes action (temporal_finding | event | schedule | state_change).
 *  - Guards: preconditions checked against an evaluation context.
 *  - Policy: cooldown/rate-limit/exclusivity/conflicts/rollout.
 *  - Action: typed effector (ui_intervention | api_call | message | navigation | state_mutation | policy_update).
 *
 * Minimal Integration
 *  - Call pragmatic.evaluate({ findings, events, state }, ctx) with TemporalCore findings array.
 *  - Provide ctx.subject (ids), ctx.effectors (map action.type → function), and optional ctx.options.
 */

class PragmaticCore {
  constructor() {
    this.version = "1.0.0";
    this.directives = new Map(); // id -> directive

    // Runtime policy state
    this.cooldowns = new Map();      // key: `${dirId}|${subjectKey}` -> lastExecTs
    this.rateBuckets = new Map();    // key: `${dirId}|${rateKey}|${bucketStart}` -> count
    this.execCache = new Set();      // idempotency cache of `${dirId}|${subjectKey}|${actionHash}`
  }

  /** Register a directive */
  registerDirective(d) {
    const dir = this._normalizeDirective(d);
    const { valid, errors } = this.validateDirective(dir);
    if (!valid) throw new Error(`Invalid PragmaticDirective(${dir.id}): ${errors.join(", ")}`);
    this.directives.set(dir.id, dir);
    return dir.id;
  }

  /** Enable/disable or update an existing directive */
  updateDirective(id, patch) {
    const cur = this.directives.get(id);
    if (!cur) throw new Error(`Unknown directive id ${id}`);
    const next = this._normalizeDirective({ ...cur, ...patch, id });
    const { valid, errors } = this.validateDirective(next);
    if (!valid) throw new Error(`Invalid PragmaticDirective(${id}) after update: ${errors.join(", ")}`);
    this.directives.set(id, next);
    return next;
  }

  /** Validate directive shape (non-exhaustive but practical) */
  validateDirective(dir) {
    const errors = [];
    if (!dir.id) errors.push("missing id");
    if (!dir.protocol?.startsWith("pragmatic/core/")) errors.push("invalid protocol");
    if (typeof dir.enabled !== "boolean") errors.push("enabled must be boolean");
    if (!Number.isFinite(dir.priority)) errors.push("priority must be a number");
    if (!dir.scope) errors.push("scope required");
    if (!dir.trigger?.type) errors.push("trigger.type required");
    if (!dir.action?.type) errors.push("action.type required");

    // Recognized action types
    const allowedActions = new Set(["ui_intervention","api_call","message","navigation","state_mutation","policy_update"]);
    if (!allowedActions.has(dir.action.type)) errors.push(`unsupported action.type '${dir.action.type}'`);

    // RateLimit shape check
    const rl = dir.trigger.rateLimit;
    if (rl && (!rl.key || !Number.isFinite(rl.max) || !rl.window)) errors.push("invalid rateLimit");

    // Hints only; guards/selector validated at runtime
    return { valid: errors.length === 0, errors };
  }

  /** Discover directives by simple key equality match (e.g., {scope:"session", enabled:true}) */
  discover(query = {}) {
    const out = [];
    for (const [, d] of this.directives) {
      if (this._matchesQuery(d, query)) out.push(d);
    }
    return out;
  }

  /**
   * Evaluate all directives against input signals & context.
   * @param {Object} input - { findings?: Array, events?: Array, state?: any }
   * @param {Object} ctx - { subject?: object, effectors?: Record<string,Function>, options?: object }
   * @returns {{executed: Array, skipped: Array}}
   */
  evaluate(input = {}, ctx = {}) {
    const now = Date.now();
    const findings = Array.isArray(input.findings) ? input.findings : [];
    const events = Array.isArray(input.events) ? input.events : [];
    const state = input.state || {};

    const subject = ctx.subject || {}; // e.g., { userId, sessionId, tenantId }
    const effectors = ctx.effectors || {}; // map action.type -> async fn(action, ctx)
    const opts = ctx.options || {}; // { dryRun?:boolean }

    // 1) Collect candidates (directives whose triggers & guards match)
    const candidates = [];
    for (const [, dir] of this.directives) {
      if (!dir.enabled) continue;
      if (this._isExpired(dir, now)) continue;
      if (!this._inRollout(dir, subject)) continue;

      const trg = this._triggerMatches(dir.trigger, { findings, events, state, subject, now });
      if (!trg.matched) continue;

      // Guards (preconditions)
      if (!this._guardsPass(dir.context?.guards, { state, subject })) continue;

      // Resource controls
      if (!this._cooldownPass(dir, subject, now)) continue;
      if (!this._rateLimitPass(dir, subject, now)) continue;

      candidates.push({ dir, trigger: trg });
    }

    if (candidates.length === 0) return { executed: [], skipped: [] };

    // 2) Conflict resolution (exclusivity & conflictsWith)
    const selected = this._resolveConflicts(candidates);

    // 3) Execute selected actions (idempotent; respect timeout)
    const executed = [];
    const skipped = [];

    for (const c of candidates) {
      if (!selected.has(c.dir.id)) { skipped.push({ id: c.dir.id, reason: "conflict_resolution" }); continue; }

      const action = c.dir.action;
      const subjectKey = this._subjectKey(c.dir, subject);
      const cacheKey = this._actionCacheKey(c.dir.id, subjectKey, action);

      if (this.execCache.has(cacheKey) && action.idempotent !== false) {
        skipped.push({ id: c.dir.id, reason: "idempotent_already_executed" });
        continue;
      }

      const effector = effectors[action.type] || this._defaultEffector(action.type);
      const payload = {
        directive: c.dir,
        action,
        subject,
        trigger: c.trigger,
        context: c.dir.context || {},
        at: now
      };

      try {
        const res = effector ? effector(action, payload) : null;
        this.execCache.add(cacheKey);
        this._markCooldown(c.dir, subject, now);
        executed.push({ id: c.dir.id, result: res });
      } catch (err) {
        skipped.push({ id: c.dir.id, reason: `effector_error: ${err?.message || err}` });
      }
    }

    return { executed, skipped };
  }

  // ---------------- Trigger matching ----------------

  _triggerMatches(trigger, env) {
    const { findings, events, state, subject, now } = env;
    const type = trigger?.type;

    if (type === "temporal_finding") {
      // match any finding that satisfies the match query (dot-notation exact equals)
      const q = trigger.match || {};
      const match = findings.find((f) => this._matchesQuery(f, q));
      if (!match) return { matched: false };
      return { matched: true, source: "TemporalCore", finding: match };
    }

    if (type === "event") {
      const q = trigger.pattern || trigger.match || {};
      const match = events.find((e) => this._matchesQuery(e, q));
      return match ? { matched: true, event: match } : { matched: false };
    }

    if (type === "schedule") {
      // simple: always match when evaluate() is called; real impl would check cron
      return { matched: true, schedule: true };
    }

    if (type === "state_change") {
      const q = trigger.match || {};
      const ok = this._matchesQuery(state, q);
      return ok ? { matched: true, state } : { matched: false };
    }

    return { matched: false };
  }

  // ---------------- Guards & Policies ----------------

  _guardsPass(guards, { state, subject }) {
    if (!Array.isArray(guards) || guards.length === 0) return true;
    for (const g of guards) {
      const left = this._getPath(g.field, { state, subject });
      const right = g.value;
      const op = g.operator || "==";
      if (!this._compare(left, right, op)) return false;
    }
    return true;
  }

  _cooldownPass(dir, subject, now) {
    const cd = dir.trigger?.cooldown;
    if (!cd) return true;
    const key = this._cooldownKey(dir, subject);
    const last = this.cooldowns.get(key);
    if (!last) return true;
    const ms = this._parseDuration(cd);
    return (now - last) >= ms;
  }

  _markCooldown(dir, subject, now) {
    const cd = dir.trigger?.cooldown;
    if (!cd) return;
    const key = this._cooldownKey(dir, subject);
    this.cooldowns.set(key, now);
  }

  _rateLimitPass(dir, subject, now) {
    const rl = dir.trigger?.rateLimit;
    if (!rl) return true;
    const windowMs = this._parseDuration(rl.window);
    const bucketStart = now - (now % windowMs);
    const rateKey = `${dir.id}|${this._getPath(rl.key, subject) ?? "_"}|${bucketStart}`;
    const count = this.rateBuckets.get(rateKey) || 0;
    if (count >= rl.max) return false;
    this.rateBuckets.set(rateKey, count + 1);
    return true;
  }

  _resolveConflicts(candidates) {
    // 1) Remove explicit conflictsWith (keep higher priority)
    const byId = new Map(candidates.map((c) => [c.dir.id, c]));
    const losers = new Set();
    for (const c of candidates) {
      const conflicts = c.dir.policy?.conflictsWith || [];
      for (const pat of conflicts) {
        const re = this._wildcardToRegExp(pat);
        for (const d of candidates) {
          if (d.dir.id === c.dir.id) continue;
          if (re.test(d.dir.id)) {
            const keep = (c.dir.priority >= d.dir.priority) ? c : d;
            const drop = (keep === c) ? d : c;
            losers.add(drop.dir.id);
          }
        }
      }
    }

    // 2) Exclusivity per key: keep highest priority within each exclusivityKey bucket
    const groups = new Map(); // key -> array of candidates
    for (const c of candidates) {
      if (losers.has(c.dir.id)) continue;
      const key = c.dir.policy?.exclusivityKey || null;
      if (!key) continue;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(c);
    }

    for (const [key, arr] of groups) {
      arr.sort((a, b) => b.dir.priority - a.dir.priority);
      // drop all but first
      for (let i = 1; i < arr.length; i++) losers.add(arr[i].dir.id);
    }

    // 3) Resolution strategy fallback (currently highest_priority)
    const selected = new Set();
    for (const c of candidates) {
      if (!losers.has(c.dir.id)) selected.add(c.dir.id);
    }
    return selected;
  }

  // ---------------- Helpers ----------------

  _normalizeDirective(d) {
    return {
      id: d.id || this._randId("prg"),
      protocol: d.protocol || "pragmatic/core/v1.0.0",
      goal: d.goal || "",
      priority: Number.isFinite(d.priority) ? d.priority : 50,
      enabled: d.enabled !== false,
      scope: d.scope || "session", // user | session | tenant | system
      rollout: d.rollout || null,    // {percent, experimentId}
      trigger: d.trigger || { type: "temporal_finding", match: {} },
      context: d.context || { selector: "", guards: [] },
      action: d.action || { type: "message", payload: { text: "noop" }, idempotent: true },
      policy: d.policy || { exclusivityKey: null, conflictsWith: [] },
      effects: Array.isArray(d.effects) ? d.effects : [],
      safety: d.safety || {},
      audit: d.audit || { logEvent: "PRAGMATIC_ACTION" },
      metadata: d.metadata || {},
      ttl: d.ttl || null,            // e.g., "30d" or ISO until
    };
  }

  _isExpired(dir, now) {
    const ttl = dir.ttl;
    if (!ttl) return false;
    // support ISO timestamp or duration string
    if (typeof ttl === "string" && /\d{4}-\d{2}-\d{2}T/.test(ttl)) return now > Date.parse(ttl);
    const ms = this._parseDuration(ttl);
    const created = dir.metadata?.createdAt ? Date.parse(dir.metadata.createdAt) : 0;
    return created ? (now - created) > ms : false;
  }

  _inRollout(dir, subject) {
    const r = dir.rollout;
    if (!r || r.percent == null) return true;
    const p = Math.max(0, Math.min(100, Number(r.percent)));
    const subjKey = this._subjectKey(dir, subject);
    const h = this._hash(`${dir.id}|${subjKey}|${r.experimentId || "exp"}`);
    const bucket = h % 100; // 0..99
    return bucket < p;
  }

  _subjectKey(dir, subject) {
    switch (dir.scope) {
      case "user": return subject.userId || "_";
      case "tenant": return subject.tenantId || "_";
      case "system": return "system";
      case "session":
      default: return subject.sessionId || "_";
    }
  }

  _cooldownKey(dir, subject) {
    return `${dir.id}|${this._subjectKey(dir, subject)}`;
  }

  _actionCacheKey(dirId, subjectKey, action) {
    const body = JSON.stringify(action?.payload ?? {});
    return `${dirId}|${subjectKey}|${this._hash(`${action.type}|${body}`)}`;
  }

  _matchesQuery(obj, query) {
    for (const [path, expected] of Object.entries(query)) {
      const got = this._getPath(path, obj);
      if (Array.isArray(got)) {
        if (!got.includes(expected)) return false;
      } else if (typeof expected === "object" && expected !== null) {
        // simple subset match
        if (typeof got !== "object" || got === null) return false;
        for (const [k, v] of Object.entries(expected)) {
          if (got[k] !== v) return false;
        }
      } else {
        if (got !== expected) return false;
      }
    }
    return true;
  }

  _compare(left, right, op) {
    switch (op) {
      case "==": return left === right;
      case "!=": return left !== right;
      case ">": return Number(left) > Number(right);
      case ">=": return Number(left) >= Number(right);
      case "<": return Number(left) < Number(right);
      case "<=": return Number(left) <= Number(right);
      case "in": return Array.isArray(right) && right.includes(left);
      case "not_in": return Array.isArray(right) && !right.includes(left);
      case "exists": return left !== undefined && left !== null;
      default: return false;
    }
  }

  _getPath(path, obj) {
    if (!path) return undefined;
    const parts = String(path).split(".");
    let cur = obj;
    for (const p of parts) {
      if (cur == null) return undefined;
      cur = cur[p];
    }
    return cur;
  }

  _wildcardToRegExp(pat) {
    const escaped = pat.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const re = new RegExp('^' + escaped.replace(/\\\*/g, '.*') + '$');
    return re;
  }

  _parseDuration(s) {
    if (!s) return 0;
    if (typeof s === "number") return s;
    const m = String(s).trim().match(/^(\d+)(ms|s|m|h|d)$/);
    if (!m) return 0;
    const n = Number(m[1]);
    const u = m[2];
    switch (u) {
      case "ms": return n;
      case "s": return n * 1000;
      case "m": return n * 60 * 1000;
      case "h": return n * 60 * 60 * 1000;
      case "d": return n * 24 * 60 * 60 * 1000;
      default: return 0;
    }
  }

  _hash(str) {
    // tiny deterministic hash (djb2 variant)
    let h = 5381;
    for (let i = 0; i < str.length; i++) h = ((h << 5) + h) ^ str.charCodeAt(i);
    return (h >>> 0);
  }

  _randId(prefix) {
    return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  }

  _defaultEffector(type) {
    return (action, payload) => {
      // No-op effector: useful for testing
      return { ok: true, info: `noop effector for ${type}`, action, payload };
    };
  }
}

// UMD export
if (typeof module !== "undefined" && module.exports) {
  module.exports = PragmaticCore;
} else if (typeof window !== "undefined") {
  window.PragmaticCore = PragmaticCore;
}

/* -------------------------------- Example Usage --------------------------------

// Wire to TemporalCore findings
const TemporalCore = require('./temporal-core.js');
const PragmaticCore = require('./pragmatic-core.js');

const temporal = new TemporalCore();
const pragmatic = new PragmaticCore();

// Register one directive that listens for a failing TH finding at checkout step 3
pragmatic.registerDirective({
  id: 'pragmatic_nudge_on_stall_1',
  protocol: 'pragmatic/core/v1.0.0',
  goal: 'Increase checkout conversion by 5%',
  enabled: true,
  priority: 70,
  scope: 'session',
  rollout: { percent: 50, experimentId: 'exp_checkout_nudge_A' },
  trigger: {
    type: 'temporal_finding',
    source: 'TemporalCore',
    match: { 'bindings.flow': 'checkout', 'bindings.step': '3', metric: 'temporal.metric.th.v1', ok: false },
    cooldown: '30m',
    rateLimit: { key: 'sessionId', max: 1, window: '2h' }
  },
  context: {
    selector: 'flow:checkout step:3 criticality:high',
    guards: [ { field: 'subject.authenticated', operator: '==', value: true } ]
  },
  action: {
    type: 'ui_intervention',
    target: 'self',
    idempotent: true,
    payload: { component: 'ProgressNudge', props: { message: 'Need a hand finishing up?' } },
    timeout: '5s'
  },
  policy: { exclusivityKey: 'checkout.help_surface', conflictsWith: ['pragmatic_offer_discount_*'] },
  effects: [ { metric: 'temporal.metric.fdd.v1', direction: 'decrease', window: '7d' } ],
  audit: { logEvent: 'PRAGMATIC_NUDGE_SHOWN', attributes: ['userId','sessionId','flow','step','variant'] },
  metadata: { author: 'ux-optimization-squad', createdAt: new Date().toISOString() }
});

// Later: feed findings from TemporalCore.evaluate(...)
const findings = [ /* ... from temporal.evaluate(...) ... * / ];
const result = pragmatic.evaluate(
  { findings },
  {
    subject: { userId: 'u1', sessionId: 's1', tenantId: 't1', authenticated: true },
    effectors: {
      ui_intervention: (action, payload) => {
        // Bridge to your UI layer
        console.log('UI intervention:', action.payload);
        return { ok: true };
      },
      api_call: async (action, payload) => { /* ... * / }
    },
    options: { dryRun: false }
  }
);
console.log('Pragmatic decisions:', result);

-------------------------------------------------------------------------------- */
