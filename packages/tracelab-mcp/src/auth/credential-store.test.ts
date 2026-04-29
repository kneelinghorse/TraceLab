import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { promises as fs } from 'fs';
import os from 'os';
import path from 'path';

import { CredentialStore, type StoredCredential } from './credential-store';

let tmpDir: string;
let filePath: string;

beforeEach(async () => {
  tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), 'tl-mcp-cred-'));
  filePath = path.join(tmpDir, 'credentials.json');
});

afterEach(async () => {
  await fs.rm(tmpDir, { recursive: true, force: true });
});

const sample = (): StoredCredential => ({
  apiBaseUrl: 'http://tracelab.test',
  key: 'tl_abc123',
  keyId: '11111111-1111-1111-1111-111111111111',
  label: 'tracelab-mcp/test (darwin; host)',
  issuedAt: '2026-04-29T13:00:00Z',
});

describe('CredentialStore', () => {
  it('returns null when no file exists yet', async () => {
    const store = new CredentialStore({ filePath });
    expect(await store.read()).toBeNull();
  });

  it('writes and reads back a credential round-trip', async () => {
    const store = new CredentialStore({ filePath });
    await store.write(sample());
    const read = await store.read();
    expect(read).toEqual(sample());
  });

  it('returns null on malformed JSON instead of throwing', async () => {
    await fs.mkdir(path.dirname(filePath), { recursive: true });
    await fs.writeFile(filePath, '{not valid json');
    const store = new CredentialStore({ filePath });
    expect(await store.read()).toBeNull();
  });

  it('returns null when required fields are missing', async () => {
    await fs.mkdir(path.dirname(filePath), { recursive: true });
    await fs.writeFile(
      filePath,
      JSON.stringify({ apiBaseUrl: 'http://tracelab.test' })
    );
    const store = new CredentialStore({ filePath });
    expect(await store.read()).toBeNull();
  });

  it('clear() is idempotent and removes the credential', async () => {
    const store = new CredentialStore({ filePath });
    await store.clear(); // pre-existing-empty case
    await store.write(sample());
    await store.clear();
    expect(await store.read()).toBeNull();
    await store.clear(); // double-clear case
  });

  it('chmod 600 on the credential file (Unix only)', async () => {
    if (process.platform === 'win32') return;
    const store = new CredentialStore({ filePath });
    await store.write(sample());
    const stat = await fs.stat(filePath);
    // Bottom 9 bits = mode permissions
    expect((stat.mode & 0o777).toString(8)).toBe('600');
  });
});
