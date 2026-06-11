/**
 * Pure transport: an authenticated JSON GET with a single 401 token-refresh
 * retry (RC-5).
 *
 * Extracted as a leaf module with NO app imports so it is unit-testable under
 * `node --experimental-strip-types` (the same pattern as `sse-parser.ts`).
 * `api.ts`'s `authedGet` wraps it with `getApiUrl()` and `readErrorDetail()`.
 *
 * Why the retry exists: every /v1/platform/* GET authenticates with a Firebase
 * ID token. Those tokens expire after ~1h, and the dashboard caches the token
 * captured at login — so a session left open longer answers HTTP 401 on its next
 * platform fetch (the Build-pillar 401 the operator hit). A single forced token
 * refresh + retry recovers transparently before any failure reaches the UI.
 */
export interface AuthedGetOptions {
  /** Forwarded to `fetch` so the caller can cancel an in-flight request. */
  signal?: AbortSignal;
  /**
   * Returns a freshly-minted bearer when the server answers 401. Invoked at most
   * once per call; the request is retried with the new token only when it differs
   * from the one that just failed.
   */
  refreshToken?: () => Promise<string | null>;
  /** Reads a human-readable detail string from a non-2xx response body. */
  readErrorDetail?: (response: Response) => Promise<string>;
}

export async function authedGetJson<T>(
  url: string,
  token: string,
  options: AuthedGetOptions = {}
): Promise<T> {
  const { signal, refreshToken, readErrorDetail } = options;
  const send = (bearer: string): Promise<Response> =>
    fetch(url, {
      method: 'GET',
      headers: { Authorization: `Bearer ${bearer}`, Accept: 'application/json' },
      signal,
    });

  let response = await send(token);
  // RC-5: a 401 means the bearer expired (Firebase IDs last ~1h and the dashboard
  // caches the login-time token). Force ONE refresh and retry before surfacing
  // the failure — but only when the refresher actually yields a NEW token, so a
  // genuinely-unauthorized caller still fails fast (no retry storm).
  if (response.status === 401 && refreshToken) {
    const fresh = await refreshToken();
    if (fresh && fresh !== token) {
      response = await send(fresh);
    }
  }
  if (!response.ok) {
    const detail = readErrorDetail ? await readErrorDetail(response) : String(response.status);
    throw new Error(`HTTP ${response.status}: ${detail}`);
  }
  return response.json() as Promise<T>;
}
