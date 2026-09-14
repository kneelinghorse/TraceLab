import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { canonicalLink } from './canonical-link.js';

beforeEach(() => {
  vi.stubEnv('TRACELAB_FRONTEND_URL', '');
  delete process.env.TRACELAB_FRONTEND_URL;
  vi.stubEnv('TRACELAB_API_URL', 'https://api.tracelab.aquex.ai');
});
afterEach(() => vi.unstubAllEnvs());

describe('canonical browser links', () => {
  it.each(['project', 'document', 'collection', 'report', 'mission', 'evidence'] as const)('links %s entities to the rebuilt route', kind => {
    expect(canonicalLink(kind, 'entity-id')).toBe(`https://tracelab.aquex.ai/${kind === 'evidence' ? kind : kind + 's'}/entity-id`);
  });
  it('encodes identifiers as a single segment and never allows dot navigation', () => {
    expect(canonicalLink('mission', 'MIGRATION/1?#')).toBe('https://tracelab.aquex.ai/missions/MIGRATION%2F1%3F%23');
    for (const id of ['', ' ', '.', '..', ' id ']) expect(() => canonicalLink('mission', id)).toThrow();
    expect(canonicalLink('document', null)).toBeUndefined();
    expect(canonicalLink('document', undefined)).toBeUndefined();
  });
  it('uses the known local frontend and requires an explicit origin for custom deployments', () => {
    vi.stubEnv('TRACELAB_API_URL', 'http://127.0.0.1:8123');
    expect(canonicalLink('mission', 'MIGRATION-1')).toBe('http://localhost:3000/missions/MIGRATION-1');
    vi.stubEnv('TRACELAB_API_URL', 'https://research-api.example.test');
    expect(() => canonicalLink('mission', 'MIGRATION-1')).toThrow('Set TRACELAB_FRONTEND_URL');
    vi.stubEnv('TRACELAB_FRONTEND_URL', 'https://research.example.test/');
    expect(canonicalLink('mission', 'MIGRATION-1')).toBe('https://research.example.test/missions/MIGRATION-1');
  });
  it.each(['javascript:alert(1)', 'https://user:password@example.test', 'https://example.test/console', 'https://example.test/?key=secret', 'https://example.test/#fragment'])('rejects non-origin configuration %s', origin => {
    vi.stubEnv('TRACELAB_FRONTEND_URL', origin);
    expect(() => canonicalLink('mission', 'MIGRATION-1')).toThrow();
  });
});
