'use client';

import { useState, useEffect, useCallback } from 'react';
import { authedGet } from '@/lib/api';

/**
 * Generic fetch hook for authenticated /v1/platform/* endpoints.
 *
 * Resolves the Bearer token from localStorage (`user.token`) using the same
 * pattern established by the existing `useClientAuth` hook in StitchClientShell.
 * Returns a typed `{ loading, error, data }` triple; callers never touch the
 * HTTP layer directly.
 *
 * A stable `refetch` callback is exposed so pillar components can retry on user
 * request without remounting. The hook threads an `AbortController` signal
 * through `authedGet`, so an in-flight request is genuinely cancelled on unmount
 * or refetch (the signal both aborts `fetch` and gates the state updates).
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

export function usePlatformData<T>(path: string, enabled = true): UsePlatformDataResult<T> {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<T | null>(null);
  const [tick, setTick] = useState(0);

  const refetch = useCallback(() => setTick((n) => n + 1), []);

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
      const token = getStoredToken();
      if (!token) {
        if (signal.aborted) return;
        setError('Authentication token unavailable. Please sign in.');
        setLoading(false);
        return;
      }

      if (signal.aborted) return;
      setLoading(true);
      setError(null);

      try {
        const result = await authedGet<T>(path, token, signal);
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
