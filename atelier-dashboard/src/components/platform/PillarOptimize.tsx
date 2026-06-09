'use client';

import React, { useState, useEffect } from 'react';
import { Loader2, AlertCircle, ChevronRight, ExternalLink } from 'lucide-react';
import { usePlatformData } from './usePlatformData';
import { TopologyGraphView } from '@/components/legibility/TopologyGraph';
import type { GraphNode, GraphEdge } from '@/components/legibility/TopologyGraph';
import type {
  PlatformOptimize,
  RecentRun,
  SessionReplayPayload,
  ReplaySpan,
  GateScore,
} from '@/lib/api';
import { getReplay } from '@/lib/api';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getStoredToken(): string | null {
  try {
    const raw = typeof window !== 'undefined' ? localStorage.getItem('user') : null;
    if (!raw) return null;
    return (JSON.parse(raw) as { token: string }).token ?? null;
  } catch {
    return null;
  }
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function formatDurationMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function OutcomeBadge({ outcome }: { outcome: string }) {
  const cls =
    outcome === 'completed'
      ? 'bg-[var(--g-success)]/15 text-[var(--g-success)] border-[var(--g-success)]/30'
      : outcome === 'degraded'
        ? 'bg-amber-500/15 text-amber-400 border-amber-500/30'
        : 'bg-rose-500/15 text-rose-400 border-rose-500/30';
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold border ${cls}`}
    >
      {outcome}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Span-to-graph conversion
//
// The backend issues spans with duration_ms=0 when not pre-computed. We derive
// durations client-side from started_at / ended_at. Spans are ordered by
// started_at ascending. We build a flat node strip (no true tree layout) since
// the backend notes parent_span_id is not reliably populated.
// ---------------------------------------------------------------------------

function spanDurationMs(span: ReplaySpan): number {
  if (span.duration_ms && span.duration_ms > 0) return span.duration_ms;
  try {
    const start = new Date(span.started_at).getTime();
    const end = new Date(span.ended_at).getTime();
    const diff = end - start;
    return diff > 0 ? diff : 0;
  } catch {
    return 0;
  }
}

function spansToGraph(spans: ReplaySpan[]): { nodes: GraphNode[]; edges: GraphEdge[] } {
  // Sort by started_at ascending.
  const sorted = [...spans].sort(
    (a, b) => new Date(a.started_at).getTime() - new Date(b.started_at).getTime()
  );

  const nodes: GraphNode[] = sorted.map(
    (span): GraphNode => ({
      id: span.span_id,
      label: span.node_name,
      kind: 'agent',
      state: span.status === 'error' ? 'error' : 'done',
      durationMs: spanDurationMs(span),
      tokens: span.input_tokens + span.output_tokens || undefined,
      status: span.model_id ?? undefined,
    })
  );

  // Linear chain: each span connects to the next by started_at order.
  const edges: GraphEdge[] = [];
  for (let i = 0; i < sorted.length - 1; i++) {
    edges.push({ from: sorted[i].span_id, to: sorted[i + 1].span_id });
  }

  return { nodes, edges };
}

// ---------------------------------------------------------------------------
// Gate score table
// ---------------------------------------------------------------------------

function GateScoreTable({ scores }: { scores: GateScore[] }) {
  if (scores.length === 0) {
    return <p className="text-sm text-[var(--g-text-muted)]">No gate scores recorded.</p>;
  }
  return (
    <div className="rounded-lg border border-[var(--g-outline)] overflow-hidden">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-[var(--g-outline)] bg-black/30">
            {['Axis', 'Score', 'CI (95%)', 'Judge', 'Reasoning'].map((h) => (
              <th
                key={h}
                className="text-left px-3 py-2 text-[10px] uppercase tracking-wider text-[var(--g-text-muted)] font-semibold"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--g-outline)]">
          {scores.map((gs) => (
            <tr key={gs.axis} className="hover:bg-black/20 transition-colors">
              <td className="px-3 py-2 font-semibold text-[var(--g-text)]">{gs.axis}</td>
              <td className="px-3 py-2 font-mono text-[var(--g-text)]">{gs.score.toFixed(3)}</td>
              <td className="px-3 py-2 font-mono text-[var(--g-text-muted)]">
                [{gs.confidence_low.toFixed(3)}, {gs.confidence_high.toFixed(3)}]
              </td>
              <td className="px-3 py-2 text-[var(--g-text-muted)]">{gs.judge_model}</td>
              <td className="px-3 py-2 text-[var(--g-text-muted)] max-w-xs truncate">
                {gs.reasoning}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Replay detail drawer (shown below the selected run row)
// ---------------------------------------------------------------------------

function ReplayDetail({ sessionId }: { sessionId: string }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [payload, setPayload] = useState<SessionReplayPayload | null>(null);
  const [retryTick, setRetryTick] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;

    const run = async () => {
      const token = getStoredToken();
      if (!token) {
        if (signal.aborted) return;
        setError('Authentication token unavailable.');
        setLoading(false);
        return;
      }
      if (signal.aborted) return;
      setLoading(true);
      setError(null);
      try {
        const p = await getReplay(sessionId, token);
        if (signal.aborted) return;
        setPayload(p);
        setLoading(false);
      } catch (err: unknown) {
        if (signal.aborted) return;
        if (err instanceof DOMException && err.name === 'AbortError') return;
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      }
    };

    void run();
    return () => controller.abort();
  }, [sessionId, retryTick]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-[var(--g-text-muted)] text-sm p-4">
        <Loader2 size={14} className="animate-spin" />
        <span>Loading replay...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col gap-2 p-4">
        <div className="flex items-center gap-2 text-rose-400 text-sm">
          <AlertCircle size={14} />
          <span>{error}</span>
        </div>
        <button
          onClick={() => setRetryTick((n) => n + 1)}
          className="text-xs text-[var(--g-info)] hover:underline self-start"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!payload) return null;

  const { nodes: spanNodes, edges: spanEdges } = spansToGraph(payload.spans);
  const totalDurationMs = (() => {
    try {
      return new Date(payload.ended_at).getTime() - new Date(payload.started_at).getTime();
    } catch {
      return 0;
    }
  })();

  return (
    <div className="flex flex-col gap-5 p-4 border-t border-[var(--g-outline)] bg-black/10">
      {/* Run summary */}
      <dl className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
        {[
          { label: 'Composite Score', value: payload.composite_score.toFixed(3) },
          {
            label: 'Total Duration',
            value: totalDurationMs ? formatDurationMs(totalDurationMs) : '—',
          },
          { label: 'Total Cost', value: `$${payload.total_cost_usd.toFixed(4)}` },
          {
            label: 'Tokens',
            value: `${payload.total_input_tokens.toLocaleString()} in / ${payload.total_output_tokens.toLocaleString()} out`,
          },
        ].map(({ label, value }) => (
          <div key={label}>
            <dt className="text-[10px] uppercase tracking-wider text-[var(--g-text-muted)]">
              {label}
            </dt>
            <dd className="mt-0.5 font-mono text-[var(--g-text)]">{value}</dd>
          </div>
        ))}
      </dl>

      {/* Execution topology */}
      {spanNodes.length > 0 && (
        <div>
          <h4 className="text-[10px] uppercase tracking-wider text-[var(--g-text-muted)] mb-2">
            Execution Topology
          </h4>
          <TopologyGraphView
            nodes={spanNodes}
            edges={spanEdges}
            testId={`replay-topology-${sessionId}`}
          />
        </div>
      )}

      {/* Gate scores */}
      <div>
        <h4 className="text-[10px] uppercase tracking-wider text-[var(--g-text-muted)] mb-2">
          Gate Scores (O-R-A-V)
        </h4>
        <GateScoreTable scores={payload.gate_scores} />
      </div>

      {/* Degradation reason */}
      {payload.degradation_reason && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-xs text-amber-400">
          <span className="font-semibold">Degradation reason: </span>
          {payload.degradation_reason}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Recent runs table
// ---------------------------------------------------------------------------

function RunRow({
  run,
  isSelected,
  onToggle,
}: {
  run: RecentRun;
  isSelected: boolean;
  onToggle: () => void;
}) {
  return (
    <>
      <tr
        className={`cursor-pointer transition-colors ${isSelected ? 'bg-[var(--g-info)]/10' : 'hover:bg-black/20'}`}
        onClick={onToggle}
      >
        <td className="px-3 py-2 text-[var(--g-text-muted)]">{formatDate(run.ended_at)}</td>
        <td className="px-3 py-2">
          <OutcomeBadge outcome={run.outcome} />
        </td>
        <td className="px-3 py-2 font-mono text-[var(--g-text)]">
          {run.composite_score.toFixed(3)}
        </td>
        <td className="px-3 py-2 font-mono text-[var(--g-text-muted)]">{run.iteration}</td>
        <td className="px-3 py-2 font-mono text-[var(--g-text-muted)]">
          ${run.total_cost_usd.toFixed(4)}
        </td>
        <td className="px-3 py-2 text-center">
          <div className="flex items-center justify-center gap-1">
            <ChevronRight
              size={12}
              className={`transition-transform ${isSelected ? 'rotate-90 text-[var(--g-info)]' : 'text-[var(--g-text-muted)]'}`}
            />
            <ExternalLink size={11} className="text-[var(--g-text-muted)]" />
          </div>
        </td>
      </tr>
      {isSelected && (
        <tr>
          <td colSpan={6} className="p-0">
            <ReplayDetail sessionId={run.session_id} />
          </td>
        </tr>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Optimize pillar root
// ---------------------------------------------------------------------------

/**
 * Optimize pillar — Platform > Optimize.
 *
 * Surfaces recent pipeline runs as telemetry. Selecting a run expands an inline
 * drawer that loads the full replay payload from /v1/replay/{session_id},
 * renders the per-run execution topology (spans ordered by started_at, durations
 * computed client-side), and displays the O-R-A-V gate scorecard.
 *
 * Honesty (RR-05): the cost figures are observed telemetry, not an enforced
 * spend cap — the surface never claims caps are enforced.
 */
export default function PillarOptimize() {
  const { loading, error, data, refetch } =
    usePlatformData<PlatformOptimize>('/v1/platform/optimize');
  const [selectedRun, setSelectedRun] = useState<string | null>(null);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-[var(--g-text-muted)] text-sm p-4">
        <Loader2 size={14} className="animate-spin" />
        <span>Loading recent runs...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col gap-2 p-4">
        <div className="flex items-center gap-2 text-rose-400 text-sm">
          <AlertCircle size={14} />
          <span>{error}</span>
        </div>
        <button
          onClick={refetch}
          className="text-xs text-[var(--g-info)] hover:underline self-start"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!data || !data.available || !data.runs) {
    return (
      <div className="flex items-center gap-2 p-4 text-sm text-[var(--g-text-muted)]">
        <AlertCircle size={14} />
        <span>Recent-run telemetry is currently unavailable.</span>
      </div>
    );
  }

  const runs = data.runs;

  if (runs.length === 0) {
    return (
      <div className="p-4 text-sm text-[var(--g-text-muted)]">
        No runs recorded yet. Trigger a generation to populate this view.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-[var(--g-text-muted)]">
          Recent Runs
        </h3>
        <span className="text-[10px] text-[var(--g-text-muted)]">
          Observed telemetry — costs are not an enforced spend cap.
        </span>
      </div>
      <div className="rounded-lg border border-[var(--g-outline)] overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-[var(--g-outline)] bg-black/30">
              {['Ended', 'Outcome', 'Score', 'Iterations', 'Cost', ''].map((h) => (
                <th
                  key={h}
                  className="text-left px-3 py-2 text-[10px] uppercase tracking-wider text-[var(--g-text-muted)] font-semibold"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--g-outline)]">
            {runs.map((run) => (
              <RunRow
                key={run.session_id}
                run={run}
                isSelected={selectedRun === run.session_id}
                onToggle={() =>
                  setSelectedRun((prev) => (prev === run.session_id ? null : run.session_id))
                }
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
