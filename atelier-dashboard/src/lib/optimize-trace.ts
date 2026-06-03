/**
 * AT-027 — optimize-trace parsing/formatting helpers.
 *
 * Pure, dependency-free utilities that the Studio shell uses to ingest the two
 * read-only AT-027 SSE event types (`route_decision`, `dreaming_artifact`) and
 * the replay payload arrays of the same shape. Kept side-effect-free so they are
 * trivially unit/e2e testable and reusable by a future replay view.
 */
import type { RouteDecisionData, DreamingArtifactData } from '@/lib/api';

/** Narrow an unknown SSE/replay payload to a RouteDecisionData, or null. */
export function parseRouteDecision(payload: unknown): RouteDecisionData | null {
  if (typeof payload !== 'object' || payload === null) return null;
  const p = payload as Record<string, unknown>;
  if (typeof p.expert !== 'string' || p.expert.length === 0) return null;
  const chain = Array.isArray(p.fallback_chain)
    ? p.fallback_chain.filter((e): e is string => typeof e === 'string')
    : [];
  return {
    expert: p.expert,
    phase: typeof p.phase === 'string' ? p.phase : '',
    score: typeof p.score === 'number' ? p.score : 0,
    rationale: typeof p.rationale === 'string' ? p.rationale : '',
    fallback_chain: chain,
    routing_mode: typeof p.routing_mode === 'string' ? p.routing_mode : '',
  };
}

/** Narrow an unknown SSE/replay payload to a DreamingArtifactData, or null. */
export function parseDreamingArtifact(payload: unknown): DreamingArtifactData | null {
  if (typeof payload !== 'object' || payload === null) return null;
  const p = payload as Record<string, unknown>;
  if (typeof p.surface_id !== 'string' || p.surface_id.length === 0) return null;
  return {
    surface_id: p.surface_id,
    node_name: typeof p.node_name === 'string' ? p.node_name : '',
    chosen_score: typeof p.chosen_score === 'number' ? p.chosen_score : 0,
    rejected_score: typeof p.rejected_score === 'number' ? p.rejected_score : 0,
    margin: typeof p.margin === 'number' ? p.margin : 0,
  };
}

/** Human-readable one-line label for a route decision (used in headers / a11y). */
export function formatRouteDecisionLabel(d: RouteDecisionData): string {
  const mode = d.routing_mode || 'router';
  return `${d.expert} (${mode})`;
}
