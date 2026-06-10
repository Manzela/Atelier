'use client';

/**
 * AT-041 — BoardClientShell.
 *
 * Client wrapper for the /board route: resolves the authenticated tenant from
 * the localStorage session (same guard as StudioClientShell — redirect to
 * /login when absent) and the project id, then mounts the live <KanbanBoard />.
 *
 * Project-id resolution (GAP-3): the server-side board emitter writes task docs
 * under `tenants/{tenant}/projects/{GOOGLE_CLOUD_PROJECT}/tasks`, so the live
 * board MUST subscribe to that same path segment. The id comes from, in order:
 *   1. the `?project=` query param (explicit override — debugging / e2e), else
 *   2. the `project_id` surfaced by GET /v1/platform/topology (the canonical
 *      server-declared value).
 * There is deliberately NO hardcoded fallback: subscribing to a guessed path
 * (the old `'p1'` default) rendered a permanently-empty board against a
 * collection the server never writes.
 *
 * Auth is read inside a ref callback (not in render) so SSR never touches
 * localStorage; the board only subscribes once tenant + project are known.
 */
import React, { useCallback, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import KanbanBoard from './KanbanBoard';
import { usePlatformData } from './platform/usePlatformData';
import type { TopologyGraphSpec } from '@/lib/api';

interface UserSession {
  uid: string;
  email: string;
  displayName: string;
  token: string;
  tenant_id: string;
}

export default function BoardClientShell() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const projectOverride = searchParams.get('project');
  const initialized = useRef(false);
  const [tenantId, setTenantId] = useState<string | null>(null);

  // Canonical project id from the platform API — skipped entirely when an
  // explicit `?project=` override is present (no fetch, no error).
  const {
    error: topoError,
    data: topoData,
    refetch: refetchTopo,
  } = usePlatformData<TopologyGraphSpec>('/v1/platform/topology', projectOverride === null);
  const projectId = projectOverride ?? topoData?.project_id ?? null;

  const initRef = useCallback(
    (node: HTMLDivElement | null) => {
      if (initialized.current || !node) return;
      initialized.current = true;
      const userStr = localStorage.getItem('user');
      if (!userStr) {
        router.push('/login');
        return;
      }
      try {
        const user = JSON.parse(userStr) as UserSession;
        setTenantId(user.tenant_id);
      } catch {
        localStorage.removeItem('user');
        router.push('/login');
      }
    },
    [router]
  );

  return (
    <div ref={initRef} className="flex h-screen w-full flex-col overflow-hidden">
      {tenantId && projectId ? (
        <KanbanBoard tenantId={tenantId} projectId={projectId} />
      ) : !projectId && topoError ? (
        <div
          className="flex h-full w-full flex-col items-center justify-center gap-2 bg-[var(--g-bg)] text-[var(--g-text-muted)]"
          role="alert"
        >
          <span className="text-[13px]">
            Couldn&rsquo;t resolve the live board project from the platform API.
          </span>
          <button
            onClick={refetchTopo}
            className="text-xs text-[var(--g-info)] hover:underline"
            type="button"
          >
            Retry
          </button>
        </div>
      ) : (
        <div
          className="flex h-full w-full items-center justify-center bg-[var(--g-bg)] text-[var(--g-text-muted)]"
          role="status"
        >
          <span className="text-[13px]">Loading the board…</span>
        </div>
      )}
    </div>
  );
}
