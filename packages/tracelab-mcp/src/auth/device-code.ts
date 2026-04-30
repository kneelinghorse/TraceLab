// ABOUTME: RFC 8628 device-code client for the TraceLab device-login flow.
// ABOUTME: Ported from cmos-mcp (T42.4); contract is intentionally identical.

/**
 * RFC 8628 device-code client for TraceLab.
 *
 * Pulled verbatim in shape from cmos-mcp's `auth/device-code.ts` and adapted
 * for TraceLab's endpoint paths (`/api/v1/auth/device/code` and `/token`)
 * and its `tracelab-mcp/<version>` User-Agent prefix. The wire contract on
 * the TraceLab side (`app/api/v1/auth_device.py`) is also a deliberate
 * mirror of cmos-mcp's so future cross-mcp library extraction stays cheap.
 *
 * Server contract (T42.4):
 * - `POST /api/v1/auth/device/code` →
 *     `{device_code, user_code, verification_uri, expires_in, interval}`
 * - `POST /api/v1/auth/device/token` body `{device_code}`:
 *     - HTTP 200 + `{access_token, token_type, key, key_id, label}` on approval
 *     - HTTP 400 + `{detail: {error, error_description?}}` where
 *       `error ∈ {authorization_pending, slow_down, expired_token, access_denied}`
 *
 * One client-side adaptation: TraceLab's FastAPI envelopes 400 errors as
 * `{detail: {error: ...}}` (FastAPI's convention) where cmos-dashboard
 * returns the error fields at the body root. The poll function unwraps both
 * shapes so the same module would be reusable against either backend.
 */

import os from 'os';
import path from 'path';
import { promises as fs } from 'fs';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** Response from `POST /api/v1/auth/device/code`. */
export interface DeviceCodeResponse {
  deviceCode: string;
  userCode: string;
  verificationUri: string;
  /** Seconds until `deviceCode` expires. */
  expiresIn: number;
  /** Seconds between successive polls (baseline; slow_down adds to it). */
  interval: number;
}

/** Successful token body returned by `POST /api/v1/auth/device/token`. */
export interface DeviceTokenSuccess {
  accessToken: string;
  keyId: string;
  label: string;
}

/** RFC 8628 error code strings returned by the token endpoint. */
export type DeviceCodeErrorCode =
  | 'authorization_pending'
  | 'slow_down'
  | 'expired_token'
  | 'access_denied';

/** Typed error covering the four RFC 8628 strings plus transport failures. */
export class DeviceCodeError extends Error {
  public readonly code: DeviceCodeErrorCode | 'request_failed' | 'malformed_response';
  public readonly description?: string;

  constructor(code: DeviceCodeError['code'], message: string, description?: string) {
    super(message);
    this.name = 'DeviceCodeError';
    this.code = code;
    if (description !== undefined) {
      this.description = description;
    }
  }
}

type FetchImpl = typeof fetch;
type SleepFn = (ms: number) => Promise<void>;
type Prompter = (response: DeviceCodeResponse) => void;

const DEFAULT_TIMEOUT_MS = 10_000;
const SLOW_DOWN_INCREMENT_SECONDS = 5;

/**
 * Build the MCP User-Agent string for device-code calls.
 * Server parses this to auto-populate the api-key label on issuance.
 */
export function buildUserAgent(
  version: string,
  platform: string = os.platform(),
  hostname: string = os.hostname()
): string {
  return `tracelab-mcp/${version} (${platform}; ${hostname})`;
}

/** Read the package version so the runtime User-Agent matches the shipped build. */
export async function readPackageVersion(): Promise<string> {
  const pkgPath = path.join(__dirname, '..', '..', 'package.json');
  try {
    const raw = await fs.readFile(pkgPath, 'utf-8');
    const parsed = JSON.parse(raw) as { version?: string };
    return parsed.version ?? 'unknown';
  } catch {
    return 'unknown';
  }
}

async function fetchWithTimeout(
  fetchImpl: FetchImpl,
  url: string,
  init: RequestInit,
  timeoutMs: number
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetchImpl(url, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

interface ServerDeviceCodeBody {
  device_code: string;
  user_code: string;
  verification_uri: string;
  expires_in: number;
  interval: number;
}

interface ServerTokenSuccessBody {
  access_token: string;
  token_type: string;
  key: string;
  key_id: string;
  label: string;
}

/** Internal: POST `/api/v1/auth/device/code` and return the parsed response. */
export async function requestDeviceCode(
  baseUrl: string,
  userAgent: string,
  options: { fetchImpl?: FetchImpl; timeoutMs?: number } = {}
): Promise<DeviceCodeResponse> {
  const fetchImpl = options.fetchImpl ?? fetch;
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const url = `${baseUrl.replace(/\/+$/, '')}/api/v1/auth/device/code`;

  let response: Response;
  try {
    response = await fetchWithTimeout(
      fetchImpl,
      url,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
          'User-Agent': userAgent,
        },
        body: JSON.stringify({}),
      },
      timeoutMs
    );
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new DeviceCodeError('request_failed', `device/code request failed: ${msg}`);
  }

  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new DeviceCodeError(
      'request_failed',
      `device/code HTTP ${response.status}: ${text || 'no body'}`
    );
  }

  let body: Partial<ServerDeviceCodeBody>;
  try {
    body = (await response.json()) as Partial<ServerDeviceCodeBody>;
  } catch {
    throw new DeviceCodeError('malformed_response', 'device/code returned invalid JSON');
  }

  if (
    typeof body.device_code !== 'string' ||
    typeof body.user_code !== 'string' ||
    typeof body.verification_uri !== 'string' ||
    typeof body.expires_in !== 'number' ||
    typeof body.interval !== 'number'
  ) {
    throw new DeviceCodeError('malformed_response', 'device/code missing required fields');
  }

  return {
    deviceCode: body.device_code,
    userCode: body.user_code,
    verificationUri: body.verification_uri,
    expiresIn: body.expires_in,
    interval: body.interval,
  };
}

/**
 * Extract the RFC 8628 error fields from a 400 response body, accepting both
 * the FastAPI envelope (`{detail: {error: ..., error_description: ...}}`)
 * and the raw form (`{error: ..., error_description: ...}`).
 */
function unwrapErrorBody(
  body: unknown
): { error?: string; description?: string } {
  if (typeof body !== 'object' || body === null) return {};
  const root = body as Record<string, unknown>;
  const detail = root.detail;
  if (typeof detail === 'object' && detail !== null) {
    const inner = detail as Record<string, unknown>;
    return {
      error: typeof inner.error === 'string' ? inner.error : undefined,
      description:
        typeof inner.error_description === 'string'
          ? inner.error_description
          : undefined,
    };
  }
  return {
    error: typeof root.error === 'string' ? root.error : undefined,
    description:
      typeof root.error_description === 'string'
        ? root.error_description
        : undefined,
  };
}

/**
 * Internal: poll `/api/v1/auth/device/token` until success or terminal error.
 * Honors RFC 8628 semantics:
 *  - `authorization_pending` → wait `interval` seconds and retry
 *  - `slow_down` → add 5s to `interval` and retry
 *  - `expired_token` / `access_denied` → throw `DeviceCodeError`
 */
export async function pollForToken(
  baseUrl: string,
  deviceCode: string,
  userAgent: string,
  initialIntervalSeconds: number,
  expiresInSeconds: number,
  options: {
    fetchImpl?: FetchImpl;
    sleepFn?: SleepFn;
    timeoutMs?: number;
    nowFn?: () => number;
  } = {}
): Promise<DeviceTokenSuccess> {
  const fetchImpl = options.fetchImpl ?? fetch;
  const sleepFn =
    options.sleepFn ?? ((ms: number) => new Promise((r) => setTimeout(r, ms)));
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const nowFn = options.nowFn ?? (() => Date.now());

  const url = `${baseUrl.replace(/\/+$/, '')}/api/v1/auth/device/token`;
  const deadlineMs = nowFn() + expiresInSeconds * 1000;
  let intervalSeconds = initialIntervalSeconds;

  // eslint-disable-next-line no-constant-condition
  while (true) {
    if (nowFn() >= deadlineMs) {
      throw new DeviceCodeError(
        'expired_token',
        'device code expired before authorization completed'
      );
    }

    await sleepFn(intervalSeconds * 1000);

    let response: Response;
    try {
      response = await fetchWithTimeout(
        fetchImpl,
        url,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json',
            'User-Agent': userAgent,
          },
          body: JSON.stringify({ device_code: deviceCode }),
        },
        timeoutMs
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      throw new DeviceCodeError('request_failed', `device/token request failed: ${msg}`);
    }

    if (response.status === 200) {
      let body: Partial<ServerTokenSuccessBody>;
      try {
        body = (await response.json()) as Partial<ServerTokenSuccessBody>;
      } catch {
        throw new DeviceCodeError('malformed_response', 'device/token returned invalid JSON');
      }
      if (
        typeof body.access_token !== 'string' ||
        typeof body.key_id !== 'string' ||
        typeof body.label !== 'string'
      ) {
        throw new DeviceCodeError('malformed_response', 'device/token missing required fields');
      }
      return {
        accessToken: body.access_token,
        keyId: body.key_id,
        label: body.label,
      };
    }

    if (response.status === 400) {
      let body: unknown;
      try {
        body = await response.json();
      } catch {
        throw new DeviceCodeError(
          'malformed_response',
          'device/token 400 response was not valid JSON'
        );
      }
      const { error, description } = unwrapErrorBody(body);
      if (error === 'authorization_pending') {
        continue;
      }
      if (error === 'slow_down') {
        intervalSeconds += SLOW_DOWN_INCREMENT_SECONDS;
        continue;
      }
      if (error === 'expired_token' || error === 'access_denied') {
        throw new DeviceCodeError(
          error,
          `device/token: ${error}`,
          description
        );
      }
      throw new DeviceCodeError(
        'request_failed',
        `device/token returned unknown error '${error ?? 'missing'}'`,
        description
      );
    }

    const text = await response.text().catch(() => '');
    throw new DeviceCodeError(
      'request_failed',
      `device/token HTTP ${response.status}: ${text || 'no body'}`
    );
  }
}

/** Print the user-facing prompt to stderr in a terminal-friendly form. */
export function defaultPrompter(response: DeviceCodeResponse): void {
  const divider = '─'.repeat(60);
  process.stderr.write(
    [
      '',
      divider,
      '[tracelab-mcp] Login required',
      divider,
      `Open:  ${response.verificationUri}?code=${response.userCode}`,
      `Code:  ${response.userCode}`,
      `(Code expires in ${response.expiresIn}s; this client will poll every ${response.interval}s.)`,
      divider,
      '',
    ].join('\n')
  );
}

export interface DeviceCodeFlowOptions {
  /** TraceLab API base URL (e.g. `https://tracelab.aquex.ai`). */
  baseUrl: string;
  /** MCP version for the User-Agent (default: read from package.json at runtime). */
  version?: string;
  /** Platform string (default: `os.platform()`). */
  platform?: string;
  /** Hostname (default: `os.hostname()`). */
  hostname?: string;
  /** How the user is prompted to visit the verification_uri (default: stderr). */
  prompter?: Prompter;
  /** Injected fetch (tests). Default: global fetch. */
  fetchImpl?: FetchImpl;
  /** Injected sleep (tests). Default: setTimeout-backed. */
  sleepFn?: SleepFn;
  /** Per-HTTP-request timeout (default 10s). */
  timeoutMs?: number;
  /** Clock function (tests). Default: Date.now. */
  nowFn?: () => number;
  /** Supply a User-Agent override (tests). Default: buildUserAgent(version, ...). */
  userAgent?: string;
}

/**
 * Full RFC 8628 bootstrap: request a device code, print the prompt, poll
 * until approval or terminal error. Returns the minted API key + metadata
 * so the caller can persist it (via CredentialStore) and proceed.
 */
export async function runDeviceCodeFlow(
  options: DeviceCodeFlowOptions
): Promise<DeviceTokenSuccess> {
  const version = options.version ?? (await readPackageVersion());
  const userAgent =
    options.userAgent ?? buildUserAgent(version, options.platform, options.hostname);
  const prompter = options.prompter ?? defaultPrompter;

  const codeResponse = await requestDeviceCode(options.baseUrl, userAgent, {
    ...(options.fetchImpl ? { fetchImpl: options.fetchImpl } : {}),
    ...(options.timeoutMs !== undefined ? { timeoutMs: options.timeoutMs } : {}),
  });
  prompter(codeResponse);

  return pollForToken(
    options.baseUrl,
    codeResponse.deviceCode,
    userAgent,
    codeResponse.interval,
    codeResponse.expiresIn,
    {
      ...(options.fetchImpl ? { fetchImpl: options.fetchImpl } : {}),
      ...(options.sleepFn ? { sleepFn: options.sleepFn } : {}),
      ...(options.timeoutMs !== undefined ? { timeoutMs: options.timeoutMs } : {}),
      ...(options.nowFn ? { nowFn: options.nowFn } : {}),
    }
  );
}
