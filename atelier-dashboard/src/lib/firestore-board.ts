/**
 * AT-041 — Board task-doc reader over Firestore `onSnapshot`.
 *
 * The Kanban Board (/board) READS the §7A.5 task docs the AT-020b emitter writes
 * at `tenants/{tenant_id}/projects/{project_id}/tasks/{task_id}`. Each doc is one
 * card; the board subscribes to the whole `tasks` collection via `onSnapshot` so
 * the lane is live: as the autonomous run drives the lead card through the exact
 * ordered 6-column set, the board re-renders with no polling and no push.
 *
 * A manual drag persists the moved card back via `updateTaskColumn` (the new
 * `columnId` + a freshly computed LexoRank). The autonomous writer (AT-020b) and
 * the manual reader (here) thus share ONE doc per card and ONE rank space.
 *
 * Firebase symbols are verified against firebase ^12.13.0 (firebase/firestore):
 *   - getFirestore(app): Firestore
 *   - collection(db, ...path): CollectionReference
 *   - doc(db, ...path): DocumentReference
 *   - onSnapshot(query, onNext, onError): Unsubscribe
 *   - updateDoc(ref, data): Promise<void>
 *   - serverTimestamp(): FieldValue
 * (the same set AT-042's approval-listener.ts uses — already proven in prod.)
 *
 * E2E seam: when `window.__ATELIER_FIRESTORE__` is present (Playwright installs
 * an in-memory shim mirroring this exact `subscribeTasks` / `updateTaskColumn`
 * contract), it takes priority so the board is provable without a live Firestore
 * project or emulator. In production the shim is absent and the real
 * firebase/firestore path runs.
 */
import {
  getFirestore,
  collection,
  doc,
  onSnapshot,
  updateDoc,
  serverTimestamp,
  type DocumentData,
} from 'firebase/firestore';
import { firebaseApp } from './firebase';

/**
 * The exact ordered 6-column set — mirrors `atelier-core`
 * `BoardColumnId` EXACTLY (declaration order IS the legal lane order, §7A.5).
 * Single-sourced here for the reader; the writer single-sources from the enum.
 */
export const BOARD_COLUMNS = [
  'Brief',
  'Decompose',
  'Awaiting Sign-off',
  'Generating',
  'QA',
  'Done',
] as const;

export type BoardColumnId = (typeof BOARD_COLUMNS)[number];

/** A single board card — the §7A.5 wire shape the AT-020b emitter writes. */
export interface BoardTask {
  task_id: string;
  run_id: string;
  columnId: BoardColumnId;
  agentRole: string;
  statusLine: string;
  rank: string;
}

/** The E2E shim contract (window-injected). Mirrors the real path below. */
interface BoardShim {
  subscribeTasks: (
    tenantId: string,
    projectId: string,
    onChange: (tasks: BoardTask[]) => void,
    onError?: (error: Error) => void
  ) => () => void;
  updateTaskColumn: (
    tenantId: string,
    projectId: string,
    taskId: string,
    patch: { columnId: BoardColumnId; rank: string }
  ) => Promise<void>;
}

function getShim(): BoardShim | null {
  if (typeof window === 'undefined') return null;
  const w = window as unknown as { __ATELIER_FIRESTORE__?: BoardShim };
  const shim = w.__ATELIER_FIRESTORE__;
  // The AT-042 sign-off shim also lives on this key; only treat it as a board
  // shim when it actually implements the board contract.
  return shim && typeof shim.subscribeTasks === 'function' ? shim : null;
}

/** The tasks collection path: tenant- and project-scoped (AT-084 rules pin it). */
function tasksPath(tenantId: string, projectId: string): [string, string, string, string, string] {
  return ['tenants', tenantId, 'projects', projectId, 'tasks'];
}

const VALID_COLUMNS = new Set<string>(BOARD_COLUMNS);

/** Narrow an untyped Firestore doc into a BoardTask, dropping malformed rows. */
function toBoardTask(id: string, data: DocumentData): BoardTask | null {
  const columnId = data.columnId;
  if (typeof columnId !== 'string' || !VALID_COLUMNS.has(columnId)) {
    // A doc with an unknown column is not renderable on the fixed 6-lane board.
    // Drop it (fail-soft) rather than crash the whole board on one bad row.
    return null;
  }
  return {
    task_id: typeof data.task_id === 'string' ? data.task_id : id,
    run_id: typeof data.run_id === 'string' ? data.run_id : '',
    columnId: columnId as BoardColumnId,
    agentRole: typeof data.agentRole === 'string' ? data.agentRole : '',
    statusLine: typeof data.statusLine === 'string' ? data.statusLine : '',
    rank: typeof data.rank === 'string' ? data.rank : '',
  };
}

/**
 * Subscribe to a project's board tasks. Fires `onChange` immediately with the
 * current collection (real Firestore `onSnapshot` behaviour) and again on every
 * subsequent change, until the returned unsubscribe is called. Returns a no-op
 * unsubscribe when Firestore is unconfigured AND no shim is present (SSR / a
 * misconfigured client) — the caller treats "no tasks" as an empty board, never
 * as an error.
 *
 * @param onError invoked with structured context on a listener error; the caller
 *   acknowledges it (fail-soft). Never swallowed silently.
 */
export function subscribeTasks(
  tenantId: string,
  projectId: string,
  onChange: (tasks: BoardTask[]) => void,
  onError?: (error: Error) => void
): () => void {
  const shim = getShim();
  if (shim) {
    return shim.subscribeTasks(tenantId, projectId, onChange, onError);
  }

  if (!firebaseApp) {
    onError?.(new Error('Firestore is not configured; board subscription is inactive.'));
    return () => {};
  }

  const db = getFirestore(firebaseApp);
  const ref = collection(db, ...tasksPath(tenantId, projectId));
  return onSnapshot(
    ref,
    (snap) => {
      const tasks: BoardTask[] = [];
      snap.forEach((d) => {
        const task = toBoardTask(d.id, d.data());
        if (task) tasks.push(task);
      });
      onChange(tasks);
    },
    (error) => {
      // Fail-soft: report with structured context; the caller acknowledges the
      // degradation. The subscription is torn down by the SDK on error.
      onError?.(
        error instanceof Error
          ? error
          : new Error(`onSnapshot error for board ${tenantId}/${projectId}: ${String(error)}`)
      );
    }
  );
}

/**
 * Persist a manual card move: write the new `columnId` and the freshly computed
 * LexoRank back to the single task doc. The `onSnapshot` subscription observes
 * the change and reconciles the optimistic local move — no push.
 *
 * @throws when the write fails — the caller MUST catch and acknowledge the
 *   degradation (the move did not land); never fire-and-forget.
 */
export async function updateTaskColumn(
  tenantId: string,
  projectId: string,
  taskId: string,
  patch: { columnId: BoardColumnId; rank: string }
): Promise<void> {
  const shim = getShim();
  if (shim) {
    await shim.updateTaskColumn(tenantId, projectId, taskId, patch);
    return;
  }

  if (!firebaseApp) {
    throw new Error('Firestore is not configured; cannot persist the card move.');
  }

  const db = getFirestore(firebaseApp);
  const ref = doc(db, ...tasksPath(tenantId, projectId), taskId);
  await updateDoc(ref, { ...patch, updated_at: serverTimestamp() });
}
