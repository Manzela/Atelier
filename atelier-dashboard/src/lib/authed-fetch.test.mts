/**
 * Unit test for authedGetJson's 401 token-refresh retry (RC-5).
 * Run: node --experimental-strip-types src/lib/authed-fetch.test.mts
 *
 * Locks the recovery the Build pillar needs: a Firebase ID token cached at login
 * expires after ~1h, so a long-open dashboard answers HTTP 401 on its next
 * platform GET. authedGetJson must force ONE token refresh and retry before the
 * failure ever reaches the UI — while leaving the fail-soft 200 path and the
 * no-refresher back-compat path untouched.
 */
import assert from 'node:assert/strict';

import { authedGetJson } from './authed-fetch.ts';

let passed = 0;
async function test(name: string, fn: () => Promise<void>): Promise<void> {
  await fn();
  passed += 1;
  console.log(`  ok  ${name}`);
}

interface Call {
  bearer: string;
}

function install(statuses: Array<{ status: number; body: unknown }>): Call[] {
  const calls: Call[] = [];
  let i = 0;
  globalThis.fetch = (async (_url: string, init: RequestInit): Promise<Response> => {
    const headers = (init.headers ?? {}) as Record<string, string>;
    calls.push({ bearer: (headers.Authorization ?? '').replace('Bearer ', '') });
    const spec = statuses[Math.min(i, statuses.length - 1)];
    i += 1;
    return new Response(JSON.stringify(spec.body), {
      status: spec.status,
      headers: { 'content-type': 'application/json' },
    });
  }) as unknown as typeof fetch;
  return calls;
}

const readErrorDetail = async (r: Response): Promise<string> => {
  try {
    const body = (await r.json()) as { detail?: string };
    return body.detail ?? String(r.status);
  } catch {
    return String(r.status);
  }
};

await test('refreshes the token and retries once on 401, then succeeds', async () => {
  const calls = install([
    { status: 401, body: { detail: 'expired' } },
    { status: 200, body: { ok: 1 } },
  ]);
  let refreshes = 0;
  const result = await authedGetJson<{ ok: number }>('http://x/v1/platform/agents', 'stale', {
    refreshToken: async () => {
      refreshes += 1;
      return 'fresh-token';
    },
    readErrorDetail,
  });
  assert.equal(result.ok, 1);
  assert.equal(refreshes, 1, 'refresh attempted exactly once');
  assert.equal(calls.length, 2, 'one original + one retry');
  assert.equal(calls[0].bearer, 'stale');
  assert.equal(calls[1].bearer, 'fresh-token', 'retry uses the refreshed token');
});

await test('does not refresh or retry when the first response is ok', async () => {
  const calls = install([{ status: 200, body: { available: true } }]);
  let refreshes = 0;
  await authedGetJson('http://x/v1/platform/agents', 'good', {
    refreshToken: async () => {
      refreshes += 1;
      return 'unused';
    },
    readErrorDetail,
  });
  assert.equal(refreshes, 0);
  assert.equal(calls.length, 1);
});

await test('throws when the refreshed retry is still unauthorized', async () => {
  install([
    { status: 401, body: { detail: 'expired' } },
    { status: 401, body: { detail: 'still expired' } },
  ]);
  await assert.rejects(
    authedGetJson('http://x/v1/platform/agents', 'stale', {
      refreshToken: async () => 'fresh',
      readErrorDetail,
    }),
    /HTTP 401/,
  );
});

await test('without a refreshToken a 401 throws immediately (back-compat)', async () => {
  const calls = install([{ status: 401, body: { detail: 'expired' } }]);
  await assert.rejects(
    authedGetJson('http://x/v1/platform/agents', 'stale', { readErrorDetail }),
    /HTTP 401/,
  );
  assert.equal(calls.length, 1, 'no retry without a refresher');
});

await test('does not retry when the refresher returns the same (or no) token', async () => {
  const calls = install([{ status: 401, body: { detail: 'expired' } }]);
  await assert.rejects(
    authedGetJson('http://x/v1/platform/agents', 'stale', {
      refreshToken: async () => 'stale', // unchanged → retrying is pointless
      readErrorDetail,
    }),
    /HTTP 401/,
  );
  assert.equal(calls.length, 1, 'no retry when the token did not actually change');
});

await test('a fail-soft 200 {available:false} neither throws nor refreshes', async () => {
  let refreshes = 0;
  install([{ status: 200, body: { available: false, reason: 'source down' } }]);
  const result = await authedGetJson<{ available: boolean }>('http://x/v1/platform/scale', 'tok', {
    refreshToken: async () => {
      refreshes += 1;
      return 'x';
    },
    readErrorDetail,
  });
  assert.equal(result.available, false);
  assert.equal(refreshes, 0);
});

console.log(`\n${passed} passed`);
