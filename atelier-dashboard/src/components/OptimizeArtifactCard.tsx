'use client';

/**
 * AT-027 — OptimizeArtifactCard (read-only Optimize surfacing).
 *
 * Surfaces the two previously-hidden optimize assets, read-only, in the Studio
 * trace area:
 *
 *  - The MoE routing decision (`RouteDecisionData`, mirrors atelier-core
 *    `RouteDecision`): which expert the phase-aware bandit router selected, with
 *    its score, rationale, and fallback chain. This is the "which model and why"
 *    half of the agent's legibility.
 *  - A dreaming / DPO artifact (`DreamingArtifactData`, mirrors atelier-core
 *    `ExtractedPair`): one preference pair the dreaming flywheel would learn from
 *    — chosen vs rejected scores and the margin. The chosen score already
 *    reflects the §3.6 anti-sycophancy reward (flattery without justification is
 *    down-weighted), so the surface is honest about the optimizer's bias guard.
 *
 * Pure presentational component — no data fetching, no side effects. It renders
 * whatever the shell accumulated from the `route_decision` / `dreaming_artifact`
 * SSE events (or a future /v1/replay fetch). Read-only by construction: there is
 * no control that mutates routing or training state.
 *
 * Design system: dark Studio chrome (`--g-*` tokens), lucide-react icons, plain
 * Tailwind — no new dependencies, matching TracePanel (AT-026). Accessible: a
 * labelled region, real <dl> semantics, and pass/fail-free numeric framing so no
 * meaning is conveyed by color alone.
 */
import React from 'react';
import { Cpu, Sparkles, GitBranch } from 'lucide-react';
import type { RouteDecisionData, DreamingArtifactData } from '@/lib/api';
import { formatRouteDecisionLabel } from '@/lib/optimize-trace';

export interface OptimizeArtifactCardProps {
  /** AT-027: the read-only MoE routing decision for the run, if surfaced. */
  routeDecision?: RouteDecisionData | null;
  /** AT-027: a read-only dreaming/DPO artifact for the run, if surfaced. */
  dreamingArtifact?: DreamingArtifactData | null;
}

function fmt(n: number): string {
  return n.toFixed(2);
}

export default function OptimizeArtifactCard({
  routeDecision,
  dreamingArtifact,
}: OptimizeArtifactCardProps) {
  if (!routeDecision && !dreamingArtifact) return null;

  return (
    <section
      data-testid="optimize-artifact-card"
      aria-labelledby="optimize-artifact-heading"
      className="text-[11px]"
    >
      <div className="h-px bg-[var(--g-outline)] my-4" />
      <h4
        id="optimize-artifact-heading"
        className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider font-semibold text-gray-500 mb-3"
      >
        <Sparkles size={12} className="text-[var(--g-info)]" aria-hidden="true" />
        Optimize
        <span className="ml-auto px-1.5 py-0.5 rounded text-[9px] bg-[var(--g-info)]/20 text-[var(--g-info)] font-mono border border-[var(--g-info)]/30">
          read-only
        </span>
      </h4>

      {/* MoE routing decision — which expert, why, and the fallback chain. */}
      {routeDecision && (
        <div
          data-testid="optimize-route-decision"
          className="mb-3 rounded bg-black/20 border border-[var(--g-outline)] px-2 py-1.5"
        >
          <div className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-gray-500">
              <Cpu size={11} className="text-[var(--g-info)]" aria-hidden="true" />
              MoE route
            </span>
            <span
              data-testid="optimize-route-mode"
              className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-black/30 text-gray-400 border border-[var(--g-outline)]"
            >
              {routeDecision.routing_mode}
            </span>
          </div>
          <p
            data-testid="optimize-route-expert"
            className="mt-1 text-[12px] font-semibold text-emerald-400"
          >
            {formatRouteDecisionLabel(routeDecision)}
          </p>
          <dl className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[10px]">
            <dt className="text-gray-500">Phase</dt>
            <dd className="text-gray-300 font-mono text-right">{routeDecision.phase}</dd>
            <dt className="text-gray-500">Score</dt>
            <dd data-testid="optimize-route-score" className="text-gray-300 font-mono text-right">
              {fmt(routeDecision.score)}
            </dd>
          </dl>
          {routeDecision.rationale && (
            <p
              className="mt-1 text-[10px] text-gray-400 line-clamp-2"
              title={routeDecision.rationale}
            >
              {routeDecision.rationale}
            </p>
          )}
          {routeDecision.fallback_chain.length > 0 && (
            <div
              data-testid="optimize-route-fallback"
              className="mt-1.5 flex items-center gap-1 flex-wrap"
            >
              <GitBranch size={10} className="text-gray-600" aria-hidden="true" />
              <span className="text-[9px] uppercase tracking-wider text-gray-600">fallback</span>
              {routeDecision.fallback_chain.map((e) => (
                <span
                  key={e}
                  className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-black/30 text-gray-400 border border-[var(--g-outline)]"
                >
                  {e}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Dreaming / DPO artifact — one preference pair the flywheel would learn. */}
      {dreamingArtifact && (
        <div
          data-testid="optimize-dreaming-artifact"
          className="rounded bg-black/20 border border-[var(--g-outline)] px-2 py-1.5"
        >
          <div className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-gray-500">
              <Sparkles size={11} className="text-[var(--g-info)]" aria-hidden="true" />
              DPO pair
            </span>
            <span className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-black/30 text-gray-400 border border-[var(--g-outline)]">
              {dreamingArtifact.node_name}
            </span>
          </div>
          <dl className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[10px]">
            <dt className="text-gray-500">Chosen</dt>
            <dd data-testid="optimize-dpo-chosen" className="text-emerald-400 font-mono text-right">
              {fmt(dreamingArtifact.chosen_score)}
            </dd>
            <dt className="text-gray-500">Rejected</dt>
            <dd data-testid="optimize-dpo-rejected" className="text-gray-400 font-mono text-right">
              {fmt(dreamingArtifact.rejected_score)}
            </dd>
            <dt className="text-gray-500">Margin</dt>
            <dd data-testid="optimize-dpo-margin" className="text-gray-300 font-mono text-right">
              {fmt(dreamingArtifact.margin)}
            </dd>
          </dl>
          <p className="mt-1 text-[9px] text-gray-600 italic">
            Chosen score reflects the anti-sycophancy reward (unjustified praise is down-weighted).
          </p>
        </div>
      )}
    </section>
  );
}
