/**
 * AT-042 — push-free sign-off resume over Firestore `onSnapshot`.
 *
 * The Studio sign-off gate (AT-031, `atelier-core/src/atelier/gates/signoff.py`)
 * halts the run at an idempotent `AWAITING_SIGNOFF` checkpoint and persists the
 * `signoff_status` lifecycle (AWAITING_SIGNOFF -> APPROVED -> COMPLETED) on the
 * run doc. The dashboard resumes purely by SUBSCRIBING to that doc — there is no
 * FCM, no messaging SDK, no push. A cold clone (a fresh client, possibly on
 * another device) reads the same doc and resumes the moment `onSnapshot` fires
 * with an APPROVED status. Approve writes that status back via `updateDoc`.
 *
 * Firebase symbols are verified against firebase ^12.13.0 (firebase/firestore):
 *   - getFirestore(app): Firestore
 *   - doc(db, ...path): DocumentReference
 *   - onSnapshot(ref, onNext, onError): Unsubscribe
 *   - updateDoc(ref, data): Promise<void>
 *   - serverTimestamp(): FieldValue
 * (`import 'firebase/messaging'` is intentionally NEVER used — the resume must
 * stay push-free.)
 *
 * E2E seam: when `window.__ATELIER_FIRESTORE__` is present (Playwright installs
 * an in-memory shim mirroring this exact contract), it takes priority so the
 * cold-clone resume is provable without a live Firestore project or emulator.
 * In production the shim is absent and the real firebase/firestore path runs.
 */
import {
  getFirestore,
  doc,
  onSnapshot,
  updateDoc,
  serverTimestamp,
  type DocumentData,
} from 'firebase/firestore';
import { firebaseApp } from './firebase';
import type { PlanData } from './api';

/** `signoff_status` lifecycle — mirrors `atelier-core` gates/signoff.py EXACTLY. */
export const SIGNOFF_AWAITING = 'AWAITING_SIGNOFF';
export const SIGNOFF_APPROVED = 'APPROVED';
export const SIGNOFF_COMPLETED = 'COMPLETED';
export const SIGNOFF_REJECTED = 'REJECTED';

export type SignoffStatus =
  | typeof SIGNOFF_AWAITING
  | typeof SIGNOFF_APPROVED
  | typeof SIGNOFF_COMPLETED
  | typeof SIGNOFF_REJECTED;

/** A run doc snapshot, narrowed to the field this layer cares about. */
export interface SignoffSnapshot {
  signoff_status?: SignoffStatus;
  [k: string]: unknown;
}

/** The E2E shim contract (window-injected). Mirrors the real path below. */
interface FirestoreShim {
  subscribeSignoff: (
    tenantId: string,
    runId: string,
    onChange: (doc: SignoffSnapshot | null) => void
  ) => () => void;
  writeSignoff: (tenantId: string, runId: string, patch: Record<string, unknown>) => Promise<void>;
}

function getShim(): FirestoreShim | null {
  if (typeof window === 'undefined') return null;
  const w = window as unknown as { __ATELIER_FIRESTORE__?: FirestoreShim };
  return w.__ATELIER_FIRESTORE__ ?? null;
}

/**
 * The run doc path. Tenant-isolated and covered by firestore.rules' tenant
 * `{document=**}` allow (a tenant member may read+write their own run docs).
 * `runs/{runId}` sits directly under the tenant root (AT-031 checkpoint home).
 */
function runDocPath(tenantId: string, runId: string): [string, string, string, string] {
  return ['tenants', tenantId, 'runs', runId];
}

/**
 * Subscribe to a run's sign-off status. Fires `onChange` immediately with the
 * current doc (real Firestore `onSnapshot` behaviour — the cold-clone resume
 * hook) and again on every subsequent change, until the returned unsubscribe is
 * called. Returns a no-op unsubscribe when Firestore is unconfigured AND no shim
 * is present (e.g. SSR or a misconfigured client) — the caller treats "no
 * status" as "still awaiting", never as an error.
 *
 * @param onError - invoked with structured context on a listener error; the
 *   caller decides how to surface it (fail-soft). Never swallowed silently.
 */
export function subscribeSignoff(
  tenantId: string,
  runId: string,
  onChange: (snapshot: SignoffSnapshot | null) => void,
  onError?: (error: Error) => void
): () => void {
  const shim = getShim();
  if (shim) {
    return shim.subscribeSignoff(tenantId, runId, onChange);
  }

  if (!firebaseApp) {
    // Firestore unconfigured and no shim: nothing to subscribe to. Acknowledge
    // (the caller logs) rather than throw — the gate simply stays awaiting.
    onError?.(new Error('Firestore is not configured; sign-off subscription is inactive.'));
    return () => {};
  }

  const db = getFirestore(firebaseApp);
  const ref = doc(db, ...runDocPath(tenantId, runId));
  return onSnapshot(
    ref,
    (snap) => {
      onChange(snap.exists() ? (snap.data() as SignoffSnapshot) : null);
    },
    (error) => {
      // Fail-soft: report with structured context; the caller acknowledges the
      // degradation. The subscription itself is torn down by the SDK on error.
      onError?.(
        error instanceof Error
          ? error
          : new Error(`onSnapshot error for run ${runId}: ${String(error)}`)
      );
    }
  );
}

/**
 * Write the human sign-off APPROVAL to the run doc. This is the single mutation
 * that unblocks the AT-031 gate: a cold clone subscribed via `subscribeSignoff`
 * observes the APPROVED transition and resumes — no push involved.
 *
 * The (possibly user-edited) plan is persisted as `approved_plan` so the
 * approval is steerable and durable: what the user approved — including any
 * edits to the cited defaults — is the plan of record, not the original draft.
 *
 * @throws when the write fails — the caller MUST catch and acknowledge the
 *   degradation (the approval did not land); never fire-and-forget.
 */
export async function submitApproval(
  tenantId: string,
  runId: string,
  approvedBy: string,
  approvedPlan: PlanData
): Promise<void> {
  const patch: Record<string, unknown> = {
    signoff_status: SIGNOFF_APPROVED,
    approved_by: approvedBy,
    approved_plan: approvedPlan as unknown as DocumentData,
  };

  const shim = getShim();
  if (shim) {
    await shim.writeSignoff(tenantId, runId, patch);
    return;
  }

  if (!firebaseApp) {
    throw new Error('Firestore is not configured; cannot submit sign-off approval.');
  }

  const db = getFirestore(firebaseApp);
  const ref = doc(db, ...runDocPath(tenantId, runId));
  await updateDoc(ref, { ...patch, approved_at: serverTimestamp() });
}
