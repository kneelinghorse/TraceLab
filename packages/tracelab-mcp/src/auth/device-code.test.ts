import { describe, it, expect, vi } from 'vitest';

import {
  buildUserAgent,
  DeviceCodeError,
  pollForToken,
  requestDeviceCode,
  runDeviceCodeFlow,
} from './device-code';

const BASE = 'http://tracelab.test';

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

describe('buildUserAgent', () => {
  it('formats version + platform + hostname', () => {
    expect(buildUserAgent('1.2.3', 'darwin', 'laptop.local')).toBe(
      'tracelab-mcp/1.2.3 (darwin; laptop.local)'
    );
  });
});

describe('requestDeviceCode', () => {
  it('parses the snake_case server response into camelCase', async () => {
    const fetchImpl = vi.fn().mockResolvedValueOnce(
      jsonResponse(200, {
        device_code: 'dev-token-abc',
        user_code: 'WDJB-MJHT',
        verification_uri: 'http://tracelab.test/device',
        expires_in: 600,
        interval: 5,
      })
    );
    const out = await requestDeviceCode(BASE, 'tracelab-mcp/test', { fetchImpl });
    expect(out).toEqual({
      deviceCode: 'dev-token-abc',
      userCode: 'WDJB-MJHT',
      verificationUri: 'http://tracelab.test/device',
      expiresIn: 600,
      interval: 5,
    });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    const [calledUrl, init] = fetchImpl.mock.calls[0];
    expect(calledUrl).toBe('http://tracelab.test/api/v1/auth/device/code');
    const headers = (init as RequestInit).headers as Record<string, string>;
    expect(headers['User-Agent']).toBe('tracelab-mcp/test');
  });

  it('throws DeviceCodeError(malformed_response) when fields are missing', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(200, { user_code: 'WDJB-MJHT' }));
    await expect(
      requestDeviceCode(BASE, 'ua', { fetchImpl })
    ).rejects.toMatchObject({ code: 'malformed_response' });
  });

  it('throws DeviceCodeError(request_failed) on non-2xx', async () => {
    const fetchImpl = vi.fn().mockResolvedValueOnce(new Response('boom', { status: 500 }));
    await expect(
      requestDeviceCode(BASE, 'ua', { fetchImpl })
    ).rejects.toMatchObject({ code: 'request_failed' });
  });
});

describe('pollForToken', () => {
  const noSleep: (ms: number) => Promise<void> = () => Promise.resolve();

  it('returns the minted credential on the first 200 poll', async () => {
    const fetchImpl = vi.fn().mockResolvedValueOnce(
      jsonResponse(200, {
        access_token: 'tl_abc123',
        token_type: 'api_key',
        key: 'tl_abc123',
        key_id: '11111111-1111-1111-1111-111111111111',
        label: 'tracelab-mcp/0.1.0 (darwin; mbp)',
      })
    );
    const result = await pollForToken(BASE, 'dev', 'ua', 5, 60, {
      fetchImpl,
      sleepFn: noSleep,
      nowFn: () => 0,
    });
    expect(result).toEqual({
      accessToken: 'tl_abc123',
      keyId: '11111111-1111-1111-1111-111111111111',
      label: 'tracelab-mcp/0.1.0 (darwin; mbp)',
    });
  });

  it('continues on authorization_pending then succeeds', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(400, { detail: { error: 'authorization_pending' } })
      )
      .mockResolvedValueOnce(
        jsonResponse(400, { detail: { error: 'authorization_pending' } })
      )
      .mockResolvedValueOnce(
        jsonResponse(200, {
          access_token: 'tl_xyz',
          token_type: 'api_key',
          key: 'tl_xyz',
          key_id: 'k',
          label: 'L',
        })
      );
    const result = await pollForToken(BASE, 'dev', 'ua', 5, 60, {
      fetchImpl,
      sleepFn: noSleep,
      nowFn: () => 0,
    });
    expect(result.accessToken).toBe('tl_xyz');
    expect(fetchImpl).toHaveBeenCalledTimes(3);
  });

  it('extends the interval on slow_down and continues', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(400, { detail: { error: 'slow_down' } })
      )
      .mockResolvedValueOnce(
        jsonResponse(200, {
          access_token: 'tl_zzz',
          token_type: 'api_key',
          key: 'tl_zzz',
          key_id: 'k',
          label: 'L',
        })
      );
    const sleeps: number[] = [];
    const sleepFn: (ms: number) => Promise<void> = async (ms) => {
      sleeps.push(ms);
    };
    await pollForToken(BASE, 'dev', 'ua', 5, 600, {
      fetchImpl,
      sleepFn,
      nowFn: () => 0,
    });
    // First sleep at the baseline 5s, then slow_down → +5s → 10s for the
    // second poll. Server-side test_poll_token_returns_slow_down asserts the
    // server emits this; this confirms the client honors it.
    expect(sleeps).toEqual([5000, 10_000]);
  });

  it('throws DeviceCodeError(expired_token) on RFC error', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(400, { detail: { error: 'expired_token' } })
      );
    await expect(
      pollForToken(BASE, 'dev', 'ua', 5, 60, { fetchImpl, sleepFn: noSleep, nowFn: () => 0 })
    ).rejects.toMatchObject({ code: 'expired_token' });
  });

  it('throws DeviceCodeError(access_denied) and surfaces the description', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(400, {
          detail: {
            error: 'access_denied',
            error_description: 'User denied the device code.',
          },
        })
      );
    try {
      await pollForToken(BASE, 'dev', 'ua', 5, 60, { fetchImpl, sleepFn: noSleep, nowFn: () => 0 });
      throw new Error('should have thrown');
    } catch (err) {
      const dce = err as DeviceCodeError;
      expect(dce.code).toBe('access_denied');
      expect(dce.description).toBe('User denied the device code.');
    }
  });

  it('also unwraps the raw RFC envelope (no FastAPI detail wrapper)', async () => {
    // Future-proof against backend/proxy variants that don't envelope.
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(400, { error: 'expired_token' }));
    await expect(
      pollForToken(BASE, 'dev', 'ua', 5, 60, { fetchImpl, sleepFn: noSleep, nowFn: () => 0 })
    ).rejects.toMatchObject({ code: 'expired_token' });
  });

  it('throws expired_token when the deadline has already passed at entry', async () => {
    // Deadline check fires at the top of the loop before any sleep/fetch.
    // Start the clock past the deadline so the very first iteration throws.
    const fetchImpl = vi.fn();
    let now = 1_000_000;
    const expiresIn = 0; // deadline = now + 0 = now → immediately expired
    await expect(
      pollForToken(BASE, 'dev', 'ua', 5, expiresIn, {
        fetchImpl,
        sleepFn: async () => {
          now += 60_000;
        },
        nowFn: () => now,
      })
    ).rejects.toMatchObject({ code: 'expired_token' });
    expect(fetchImpl).not.toHaveBeenCalled();
  });
});

describe('runDeviceCodeFlow', () => {
  it('invokes the prompter then polls until approval', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(200, {
          device_code: 'dc',
          user_code: 'WDJB-MJHT',
          verification_uri: 'http://tracelab.test/device',
          expires_in: 60,
          interval: 5,
        })
      )
      .mockResolvedValueOnce(
        jsonResponse(200, {
          access_token: 'tl_minted',
          token_type: 'api_key',
          key: 'tl_minted',
          key_id: 'k1',
          label: 'tracelab-mcp/test (darwin; host)',
        })
      );
    const prompter = vi.fn();
    const result = await runDeviceCodeFlow({
      baseUrl: BASE,
      version: '0.0.0-test',
      platform: 'darwin',
      hostname: 'test-host',
      prompter,
      fetchImpl,
      sleepFn: async () => {},
    });
    expect(prompter).toHaveBeenCalledTimes(1);
    expect(prompter.mock.calls[0][0].userCode).toBe('WDJB-MJHT');
    expect(result.accessToken).toBe('tl_minted');
    // Both endpoints should have been hit with the User-Agent we expect.
    const headers0 = (fetchImpl.mock.calls[0][1] as RequestInit).headers as Record<string, string>;
    expect(headers0['User-Agent']).toBe('tracelab-mcp/0.0.0-test (darwin; test-host)');
  });
});
