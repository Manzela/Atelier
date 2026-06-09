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
 * never a hardcoded value. The project id defaults to `"p1"` (the same default
 * the Kanban board uses when no `?project=` query param is present).
 *
 * Returns an `AgentActivityMap` that is kept live via Firestore `onSnapshot`.
 * The map starts as `{}` (empty, all nodes render as `idle`) and is updated on
 * every subsequent change. No polling is used.
 *
 * @param projectId  Project id to subscribe to. Defaults to `"p1"`.
 */
export function useAgentActivity(projectId = 'p1'): AgentActivityMap {
  const [activityMap, setActivityMap] = useState<AgentActivityMap>({});

  useEffect(() => {
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
