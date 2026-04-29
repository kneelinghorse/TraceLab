// ABOUTME: Filesystem credential persistence for the TraceLab MCP device login.
// ABOUTME: Single-user, JSON file at ~/.config/tracelab-mcp/credentials.json (chmod 600).

import os from 'os';
import path from 'path';
import { promises as fs } from 'fs';

/**
 * On-disk record for a single TraceLab MCP API key.
 *
 * `key` is the plaintext `tl_*` returned by `/auth/device/token` once on
 * approval — we never see it from the server again, so we have to persist
 * it locally. `keyId` and `label` mirror what the web `/api-keys` UI shows
 * so users can revoke from there if a credential leaks.
 *
 * `apiBaseUrl` is recorded so the credential survives a `TRACELAB_API_URL`
 * env-var change (e.g. the user pointed the MCP at a staging deployment
 * once and forgot). The startup loader compares the stored base URL to the
 * effective one and re-runs device login if they diverge — same behavior
 * cmos-mcp uses against multiple dashboard tenants.
 */
export interface StoredCredential {
  apiBaseUrl: string;
  key: string;
  keyId: string;
  label: string;
  issuedAt: string;
}

const FILE_MODE = 0o600;
const DIR_MODE = 0o700;

function defaultCredentialPath(): string {
  // XDG-ish: ~/.config/tracelab-mcp/credentials.json. Mirrors cmos-mcp's
  // layout so tooling that already understands one path can extend trivially.
  const home = os.homedir();
  return path.join(home, '.config', 'tracelab-mcp', 'credentials.json');
}

export interface CredentialStoreOptions {
  /** Override the credential path (tests). Defaults to ~/.config/tracelab-mcp/credentials.json. */
  filePath?: string;
}

export class CredentialStore {
  private readonly filePath: string;

  constructor(options: CredentialStoreOptions = {}) {
    this.filePath = options.filePath ?? defaultCredentialPath();
  }

  /** Read the stored credential, or null if none. Malformed file → null. */
  async read(): Promise<StoredCredential | null> {
    try {
      const raw = await fs.readFile(this.filePath, 'utf-8');
      const parsed = JSON.parse(raw) as Partial<StoredCredential>;
      if (
        typeof parsed.apiBaseUrl === 'string' &&
        typeof parsed.key === 'string' &&
        typeof parsed.keyId === 'string' &&
        typeof parsed.label === 'string' &&
        typeof parsed.issuedAt === 'string'
      ) {
        return {
          apiBaseUrl: parsed.apiBaseUrl,
          key: parsed.key,
          keyId: parsed.keyId,
          label: parsed.label,
          issuedAt: parsed.issuedAt,
        };
      }
      return null;
    } catch (err) {
      const code = (err as NodeJS.ErrnoException).code;
      if (code === 'ENOENT') return null;
      // Malformed credential is a corrupted file — return null so the
      // caller falls back to the device-code flow rather than crashing.
      return null;
    }
  }

  /** Persist a new credential, replacing any existing file. chmod 600. */
  async write(record: StoredCredential): Promise<void> {
    const dir = path.dirname(this.filePath);
    await fs.mkdir(dir, { recursive: true, mode: DIR_MODE });
    const contents = JSON.stringify(record, null, 2) + '\n';
    await fs.writeFile(this.filePath, contents, { mode: FILE_MODE });
    // Re-chmod in case the file existed already with a different mode.
    await fs.chmod(this.filePath, FILE_MODE).catch(() => {
      /* best-effort on platforms that don't honor mode (e.g. Windows) */
    });
  }

  /** Remove the credential. Idempotent — missing file is not an error. */
  async clear(): Promise<void> {
    try {
      await fs.unlink(this.filePath);
    } catch (err) {
      const code = (err as NodeJS.ErrnoException).code;
      if (code !== 'ENOENT') throw err;
    }
  }

  /** Where the credential lives — surfaced in startup logs for debuggability. */
  get path(): string {
    return this.filePath;
  }
}
