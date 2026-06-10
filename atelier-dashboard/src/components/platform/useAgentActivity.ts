'use client';

import { useState, useEffect } from 'react';
import { subscribeAgentActivity } from '@/lib/firestore-agents';
import type { AgentActivityMap } from '@/lib/firestore-agents';

/**
 * Reads the authenticated tenant id from localStorage using the same
 * convention as `BoardClientShell` and `usePlatformData`: the `user` key
 * stores a JSON object with a `tenant_id` field. Returns `null` when the
 * session is absent or malformed (SSR, unauthenticated).
 */
function getStoredTenantId(): string | null {
  try {
    const raw = typeof window !== 'undefined' ? localStorage.getItem('user') : null;
    if (!raw) return null;
    return (JSON.parse(raw) as { tenant_id: string }).tenant_id ?? null;
  } catch {
    return null;
  }
}

/**
 * Subscribe to live per-agent activity for the authenticated tenant's project.
 *
 * The tenant id is derived from the Phase-A corrected `localStorage` session —
 * never a hardcoded value. The project id is likewise never hardcoded: the
 * server-side board emitter writes task docs under
 * `tenants/{tenant}/projects/{GOOGLE_CLOUD_PROJECT}/tasks`, so callers pass the
 * `project_id` surfaced by GET /v1/platform/topology (`TopologyGraphSpec`).
 * While the id is still unresolved (`undefined` — e.g. the topology fetch is in
 * flight), the hook does NOT subscribe and the map stays empty (nodes render as
 * `idle`); the subscription starts as soon as the id arrives.
 *
 * Returns an `AgentActivityMap` that is kept live via Firestore `onSnapshot`.
 * The map starts as `{}` (empty, all nodes render as `idle`) and is updated on
 * every subsequent change. No polling is used.
 *
 * @param projectId  Project id to subscribe to — the `/v1/platform/topology`
 *   `project_id` (or an explicit override). `undefined` = not yet resolved.
 */
export function useAgentActivity(projectId?: string): AgentActivityMap {
  const [activityMap, setActivityMap] = useState<AgentActivityMap>({});

  useEffect(() => {
    if (!projectId) {
      // Project id not resolved yet (topology fetch in flight or unavailable):
      // subscribing to a guessed path would read a collection the server never
      // writes — stay idle until the canonical id arrives.
      return;
    }
    const tenantId = getStoredTenantId();
    if (!tenantId) {
      // No session: leave the map empty (nodes render as idle). Do not error.
      return;
    }

    const unsubscribe = subscribeAgentActivity(
      tenantId,
      projectId,
      (map) => {
        setActivityMap(map);
      },
      (error) => {
        // Fail-soft: log the degradation; the component keeps the last-known map.
        console.warn(
          // nosemgrep: javascript.lang.security.audit.unsafe-formatstring.unsafe-formatstring -- template literals, not a printf-style format string; no format-specifier injection is possible.
          `[useAgentActivity] Firestore agent-activity subscription error for ` +
            `${tenantId}/${projectId}:`,
          error
        );
      }
    );

    return unsubscribe;
  }, [projectId]);

  return activityMap;
}
