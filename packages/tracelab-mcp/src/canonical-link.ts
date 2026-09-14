const routes = {
  project: 'projects',
  document: 'documents',
  collection: 'collections',
  report: 'reports',
  mission: 'missions',
  evidence: 'evidence',
} as const;

/** Build generated browser links; source URLs and authored content never enter here. */
export function canonicalLink(
  entity: keyof typeof routes,
  id: string | null | undefined,
): string | undefined {
  if (id == null) return undefined;
  if (!id.trim() || id !== id.trim() || id === '.' || id === '..') {
    throw new TypeError('Canonical links require a nonempty entity identifier');
  }
  return new URL(`/${routes[entity]}/${encodeURIComponent(id)}`, canonicalFrontendOrigin()).href;
}

/** Validate browser configuration before login or any tool can perform a write. */
export function canonicalFrontendOrigin(): string {
  let origin = process.env.TRACELAB_FRONTEND_URL;
  if (origin === undefined) {
    const api = new URL(process.env.TRACELAB_API_URL || 'http://localhost:8000');
    if (api.origin === 'https://api.tracelab.aquex.ai') origin = 'https://tracelab.aquex.ai';
    else if (['localhost', '127.0.0.1', '[::1]'].includes(api.hostname)) origin = 'http://localhost:3000';
    else throw new TypeError('Set TRACELAB_FRONTEND_URL for this API deployment');
  }
  const base = new URL(origin);
  if (!['http:', 'https:'].includes(base.protocol) || base.username || base.password || base.search || base.hash || base.pathname !== '/') {
    throw new TypeError('TRACELAB_FRONTEND_URL must be an HTTP(S) origin without credentials, path, query or fragment');
  }
  return base.origin;
}
