import { Suspense } from 'react';
import BoardClientShell from '../../components/BoardClientShell';
import ErrorBoundary from '../../components/ErrorBoundary';

/**
 * AT-041 — /board route.
 *
 * The Kanban Board: a live, 6-column view of the §7A.5 task pipeline (writer
 * AT-020b, reader here). Wrapped in an ErrorBoundary (fail-soft chrome) and a
 * Suspense boundary required by `useSearchParams` (Next 16 client-nav contract).
 */
export const metadata = {
  title: 'Atelier — Board',
};

export default function BoardPage() {
  return (
    <ErrorBoundary>
      <Suspense
        fallback={
          <div
            className="flex h-screen w-full items-center justify-center bg-[var(--g-bg)] text-[var(--g-text-muted)]"
            role="status"
          >
            <span className="text-[13px]">Loading the board…</span>
          </div>
        }
      >
        <BoardClientShell />
      </Suspense>
    </ErrorBoundary>
  );
}
