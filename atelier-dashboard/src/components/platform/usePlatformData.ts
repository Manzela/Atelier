'use client';

import { onIdTokenChanged } from 'firebase/auth';
import { useState, useEffect, useCallback, useRef } from 'react';

import { authedGet } from '@/lib/api';
import { auth } from '@/lib/firebase';

/**
 * Generic fetch hook for authenticated /v1/platform/* endpoints.
 *
 * Token freshness (RC-5): a Firebase ID token expires after ~1h. The previous
 * version read ONLY the login-time snapshot from localStorage, so a dashboard
 * left open longer hit HTTP 401 on its next platform GET — the Build-pillar 401
 * the operator saw. This hook now (a) sources a LIVE token from the Firebase SDK
 * (`getIdToken()` auto-refreshes when expired), (b) forwards a force-refresh
 * retry to `authedGet` so a 401 recovers in-flight, and (c) re-fetches whenever
 * the SDK rotates the token (`onIdTokenChanged`). It falls back to the cached
 * localStorage token before the SDK has restored auth state (and mirrors any
 * refreshed token back into localStorage so other readers stay current).
 *
 * Returns a typed `{ loading, error, data }` triple plus a stable `refetch`.
 * The hook threads an `AbortController` signal through `authedGet`, so an
 * in-flight request is genuinely cancelled on unmount or refetch.
 *
 * The optional `enabled` flag (default `true`) lets a caller mount the hook
 * without issuing the request (hooks cannot be conditional); when disabled the
 * triple resolves immediately to `{ loading: false, error: null, data: null }`.
 */
export interface UsePlatformDataResult<T> {
  loading: boolean;
  error: string | null;
  data: T | null;
  refetch: () => void;
}

interface StoredUser {
  token: string;
}

function getStoredToken(): string | null {
  try {
    const raw = typeof window !== 'undefined' ? localStorage.getItem('user') : null;
    if (!raw) return null;
    return (JSON.parse(raw) as StoredUser).token ?? null;
  } catch {
    return null;
  }
}

/** Persist a refreshed token back onto the stored `user` so other readers
 * (e.g. StudioClientShell's session) do not keep using the stale one. */
function syncStoredToken(token: string): void {
  try {
    if (typeof window === 'undefined') return;
    const raw = localStorage.getItem('user');
    if (!raw) return;
    const user = JSON.parse(raw) as Record<string, unknown>;
    if (user.token === token) return;
    localStorage.setItem('user', JSON.stringify({ ...user, token }));
  } catch {
    /* non-fatal: the in-memory token is still used for this request */
  }
}

/**
 * Resolve a usable bearer token. Prefers a live Firebase token — `getIdToken()`
 * transparently refreshes an expired one; `getIdToken(true)` forces a refresh
 * after a 401 — and falls back to the localStorage snapshot before the SDK has
 * restored the signed-in user (or when Firebase is not configured).
 */
async function getFreshToken(forceRefresh = false): Promise<string | null> {
  try {
    const user = auth?.currentUser;
    if (user) {
      const fresh = await user.getIdToken(forceRefresh);
      if (fresh) {
        syncStoredToken(fresh);
        return fresh;
      }
    }
  } catch {
    /* fall through to the cached token */
  }
  return getStoredToken();
}

export function usePlatformData<T>(path: string, enabled = true): UsePlatformDataResult<T> {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<T | null>(null);
  const [tick, setTick] = useState(0);

  const refetch = useCallback(() => setTick((n) => n + 1), []);

  // Re-fetch when the Firebase SDK rotates the ID token (hourly refresh, or a
  // sign-in completing after mount). The first onIdTokenChanged callback fires
  // synchronously with the current auth state, which the main effect already
  // covers — skip it so mount does not double-fetch.
  const sawFirstTokenEvent = useRef(false);
  useEffect(() => {
    if (!auth) return;
    const unsub = onIdTokenChanged(auth, () => {
      if (!sawFirstTokenEvent.current) {
        sawFirstTokenEvent.current = true;
        return;
      }
      setTick((n) => n + 1);
    });
    return unsub;
  }, []);

  useEffect(() => {
    // `enabled: false` callers (e.g. the board shell when a `?project=`
    // override is present) skip the fetch entirely — no request, no error.
    // No state write here (no setState-in-effect): the returned `loading`
    // is derived as `enabled && loading` below.
    if (!enabled) return;

    const controller = new AbortController();
    const { signal } = controller;

    // All state transitions run inside this async closure (after a microtask),
    // never synchronously in the effect body — and each is gated on the abort
    // signal so an unmounted/superseded request can never update state.
    const run = async () => {
      const token = await getFreshToken();
      if (signal.aborted) return;
      if (!token) {
        setError('Authentication token unavailable. Please sign in.');
        setLoading(false);
        return;
      }

      setLoading(true);
      setError(null);

      try {
        const result = await authedGet<T>(path, token, signal, () => getFreshToken(true));
        if (signal.aborted) return;
        setData(result);
        setLoading(false);
      } catch (err: unknown) {
        if (signal.aborted) return;
        // A genuine abort surfaces as an AbortError — swallow it (the signal
        // guard above already covers the common path) rather than show an error.
        if (err instanceof DOMException && err.name === 'AbortError') return;
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      }
    };

    void run();

    return () => {
      controller.abort();
    };
  }, [path, tick, enabled]);

  return { loading: enabled && loading, error, data, refetch };
}
