/**
 * Single source of truth for DDLC stage ordering across all dashboard views (L08).
 *
 * The run timeline (TracePanel), the topology graph (TopologyGraph), and the
 * Build-pillar roster (PillarBuild) previously each ordered agents differently —
 * SSE arrival order vs the fixed SPECIALISTS array vs raw `/v1/platform/agents`
 * order — so the same run looked inconsistent ("UX researcher first" in one view,
 * "UI designer first" in another; steps appearing skipped). Every view now sorts
 * by `stageIndex`, which mirrors the backend canonical order in
 * `atelier-core/.../orchestrator/specialists.py` (`SPECIALIST_OUTPUT_KEYS`, itself
 * drift-guarded against the live `_SPECIALISTS` tuple) so FE and BE cannot diverge.
 */

/**
 * The 6 DDLC specialist `output_key`s in canonical execution order. Mirrors
 * `SPECIALIST_OUTPUT_KEYS` in the backend (keep in lockstep if that tuple changes).
 */
export const CANONICAL_STAGE_ORDER = [
  'ux_research',
  'ia_flows',
  'wireframe',
  'ui_design',
  'interaction_spec',
  'tokens',
] as const;

/**
 * camelCase specialist role names — as emitted on the `specialist_trace` SSE
 * `role` field (e.g. `"UIDesigner"`) — mapped to their snake_case `output_key`.
 */
export const ROLE_NAME_MAP: Record<string, string> = {
  UXResearcher: 'ux_research',
  IAFlowDesigner: 'ia_flows',
  Wireframer: 'wireframe',
  UIDesigner: 'ui_design',
  InteractionDesigner: 'interaction_spec',
  TokenGenerator: 'tokens',
};

/**
 * Roster-only pipeline nodes that bracket the specialists in the Build pillar
 * (which lists the full agent registry, not just the 6 specialists). Intake leads;
 * the specialists run in canonical order; the fixer and any judges/critics follow.
 */
const PIPELINE_PREFIX = ['planner', 'intake_brief_parser'];
const PIPELINE_SUFFIX = ['fixer'];

/**
 * The Build-pillar roster sorts by an agent's `task_type` (the model-routing
 * TaskType enum), which DIVERGES from the specialist `output_key` for three stages:
 * `ia_flow`≠`ia_flows`, `interaction`≠`interaction_spec`, `token_gen`≠`tokens`.
 * Without these aliases those three fall to the unknown bucket and sort AFTER the
 * fixer, so the roster disagrees with the trace/topology (which key off output_key
 * / camelCase role) — the exact cross-view inconsistency this module exists to kill
 * (observed live in Jam d32cc59c after the L08 fix).
 */
const TASK_TYPE_ALIASES: Record<string, string> = {
  ia_flow: 'ia_flows',
  interaction: 'interaction_spec',
  token_gen: 'tokens',
};

/**
 * Normalize any agent identifier to its canonical specialist `output_key`, or ''
 * if it is not one of the 6 specialists. Accepts the snake `output_key`
 * (`ui_design`), the camelCase trace role (`UIDesigner`), the roster id form
 * (`specialist_uidesigner`), and the model-routing `task_type` (`ia_flow`).
 */
export function normalizeRole(role: string | null | undefined): string {
  if (!role) return '';
  if ((CANONICAL_STAGE_ORDER as readonly string[]).includes(role)) return role;
  if (role in TASK_TYPE_ALIASES) return TASK_TYPE_ALIASES[role];
  if (role in ROLE_NAME_MAP) return ROLE_NAME_MAP[role];
  const stripped = role.replace(/^specialist_/, '').toLowerCase();
  for (const [camel, snake] of Object.entries(ROLE_NAME_MAP)) {
    if (camel.toLowerCase() === stripped) return snake;
  }
  return '';
}

/**
 * Sort key for any agent/stage identifier — lower sorts earlier in the pipeline.
 * Intake first (0..), the 6 specialists in canonical order, then the fixer, then
 * anything unknown (judges/critics/etc.) last. Unknown ids share the max index so
 * a STABLE sort preserves their incoming order.
 */
export function stageIndex(role: string | null | undefined): number {
  if (!role) return Number.MAX_SAFE_INTEGER;
  const prefixIdx = PIPELINE_PREFIX.indexOf(role);
  if (prefixIdx !== -1) return prefixIdx;
  const snake = normalizeRole(role);
  if (snake) {
    return PIPELINE_PREFIX.length + (CANONICAL_STAGE_ORDER as readonly string[]).indexOf(snake);
  }
  const suffixIdx = PIPELINE_SUFFIX.indexOf(role);
  if (suffixIdx !== -1) return PIPELINE_PREFIX.length + CANONICAL_STAGE_ORDER.length + suffixIdx;
  return Number.MAX_SAFE_INTEGER;
}
