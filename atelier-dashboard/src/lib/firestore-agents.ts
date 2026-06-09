/**
 * AT-Phase-D — Real-time per-agent activity subscription over Firestore `onSnapshot`.
 *
 * Derives live per-agent state by subscribing to the same tenant-scoped tasks
 * collection that the Kanban board reads (`tenants/{tenant_id}/projects/{project_id}/tasks`).
 * Each task doc carries an `agentRole` and a `columnId`; this module collapses that
 * collection into a `AgentActivityMap` — a stable `Record<agentRole, NodeState>` the
 * platform pillars can use to drive live topology-graph node colours without polling.
 *
 * Column-to-state mapping (matches the §7A.5 BoardColumnId enum):
 *   "Generating"       → "active"   (agent is running)
 *   "QA"               → "active"   (agent output is under automated quality gate)
 *   "Done"             → "done"
 *   "Brief"            → "idle"     (not yet dispatched)
 *   "Decompose"        → "idle"
 *   "Awaiting Sign-off"→ "idle"     (waiting for human approval — agent not running)
 *
 * The live `NodeState` vocabulary mirrors `@/components/legibility/TopologyGraph#NodeState`
 * exactly so callers can pass the map straight into graph node `state` fields.
 *
 * This module follows the same structural conventions as `firestore-board.ts`:
 *   - E2E shim via `window.__ATELIER_AGENT_ACTIVITY__` (same contract)
 *   - Fail-soft: unconfigured Firestore → empty map + optional onError callback
 *   - No polling; pure `onSnapshot` push
 */
import { getFirestore, collection, onSnapshot, type DocumentData } from 'firebase/firestore';
import { firebaseApp } from './firebase';
import type { NodeState } from '@/components/legibility/TopologyGraph';

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

/**
 * Live per-agent state map. Keys are `agentRole` values exactly as stored in the
 * task docs (e.g. `"ux_research"`, `"ui_design"`). Values are `NodeState`.
 * Absent keys mean the agent has no active task doc — treat as `"idle"`.
 */
export type AgentActivityMap = Record<string, NodeState>;

/** Callback signature — fired immediately and on every subsequent change. */
export type AgentActivityCallback = (map: AgentActivityMap) => void;

// ---------------------------------------------------------------------------
// Column → NodeState mapping
// ---------------------------------------------------------------------------

const COLUMN_STATE: Record<string, NodeState> = {
  Brief: 'idle',
  Decompose: 'idle',
  'Awaiting Sign-off': 'idle',
  Generating: 'active',
  QA: 'active',
  Done: 'done',
};

function columnToState(columnId: string): NodeState {
  return COLUMN_STATE[columnId] ?? 'idle';
}

// ---------------------------------------------------------------------------
// E2E shim
// ---------------------------------------------------------------------------

interface AgentActivityShim {
  subscribeAgentActivity: (
    tenantId: string,
    projectId: string,
    onChange: AgentActivityCallback,
    onError?: (error: Error) => void
  ) => () => void;
}

function getShim(): AgentActivityShim | null {
  if (typeof window === 'undefined') return null;
  const w = window as unknown as { __ATELIER_AGENT_ACTIVITY__?: AgentActivityShim };
  const shim = w.__ATELIER_AGENT_ACTIVITY__;
  return shim && typeof shim.subscribeAgentActivity === 'function' ? shim : null;
}

// ---------------------------------------------------------------------------
// Document → AgentActivityMap
// ---------------------------------------------------------------------------

/**
 * Collapse a Firestore task-doc snapshot into a per-agent state map. When
 * multiple task docs share the same `agentRole`, the most active state wins
 * (active > done > idle).
 */
function collapseSnapshot(docs: { id: string; data: DocumentData }[]): AgentActivityMap {
  const STATE_PRIORITY: Record<NodeState, number> = {
    active: 2,
    done: 1,
    idle: 0,
    error: 0,
  };

  const map: AgentActivityMap = {};
  for (const { data } of docs) {
    const agentRole = typeof data.agentRole === 'string' ? data.agentRole : null;
    const columnId = typeof data.columnId === 'string' ? data.columnId : null;
    if (!agentRole || !columnId) continue;

    const newState = columnToState(columnId);
    const existing = map[agentRole];
    if (existing === undefined || STATE_PRIORITY[newState] > STATE_PRIORITY[existing]) {
      map[agentRole] = newState;
    }
  }
  return map;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Subscribe to live per-agent activity for a project. Calls `onChange`
 * immediately with the current state and again on every subsequent Firestore
 * change. Returns an unsubscribe function. Never polls.
 *
 * The tenant MUST come from the Phase-A corrected client derivation
 * (`user.tenant_id` from the `localStorage` session) — never a hardcoded string.
 *
 * @param tenantId  Tenant id from the authenticated session (`user.tenant_id`).
 * @param projectId Project id (e.g. the `?project=` query param, defaulting to `"p1"`).
 * @param onChange  Fired on every live update with the collapsed `AgentActivityMap`.
 * @param onError   Fail-soft: called with structured context on listener error;
 *                  never swallowed silently. The caller acknowledges the degradation.
 */
export function subscribeAgentActivity(
  tenantId: string,
  projectId: string,
  onChange: AgentActivityCallback,
  onError?: (error: Error) => void
): () => void {
  const shim = getShim();
  if (shim) {
    return shim.subscribeAgentActivity(tenantId, projectId, onChange, onError);
  }

  if (!firebaseApp) {
    onError?.(new Error('Firestore is not configured; agent-activity subscription is inactive.'));
    return () => {};
  }

  const db = getFirestore(firebaseApp);
  const ref = collection(db, 'tenants', tenantId, 'projects', projectId, 'tasks');
  return onSnapshot(
    ref,
    (snap) => {
      const docs = snap.docs.map((d) => ({ id: d.id, data: d.data() }));
      onChange(collapseSnapshot(docs));
    },
    (error) => {
      onError?.(
        error instanceof Error
          ? error
          : new Error(
              `onSnapshot error for agent-activity ${tenantId}/${projectId}: ${String(error)}`
            )
      );
    }
  );
}
