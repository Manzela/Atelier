'use client';

/**
 * AT-041 — BoardClientShell.
 *
 * Client wrapper for the /board route: resolves the authenticated tenant from
 * the localStorage session (same guard as StudioClientShell — redirect to
 * /login when absent) and the project id from the `?project=` query param
 * (default `p1`), then mounts the live <KanbanBoard />.
 *
 * Auth is read inside a ref callback (not in render) so SSR never touches
 * localStorage; the board only subscribes once the tenant is known.
 */
import React, { useCallback, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import KanbanBoard from './KanbanBoard';

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
  const projectId = searchParams.get('project') ?? 'p1';
  const initialized = useRef(false);
  const [tenantId, setTenantId] = useState<string | null>(null);

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
      {tenantId ? (
        <KanbanBoard tenantId={tenantId} projectId={projectId} />
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
