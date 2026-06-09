'use client';

import React from 'react';
import {
  Users,
  Map as MapIcon,
  Layout,
  Palette,
  Zap,
  Database,
  ArrowRight,
  CheckCircle2,
  Play,
  AlertCircle,
  HelpCircle,
  Boxes,
  Brain,
  Wrench,
  Workflow,
} from 'lucide-react';
import type { SpecialistTraceData } from '@/lib/api';

/**
 * Per-node lifecycle state. Drives the card's color/ring/indicator. `idle` is a
 * not-yet-reached / dimmed node; `active` is the currently-running node; `done`
 * is a completed node; `error` is a failed node.
 */
export type NodeState = 'idle' | 'active' | 'done' | 'error';

type IconComponent = React.ComponentType<{ className?: string; size?: number }>;

/**
 * A single renderable node in the generalized topology graph. `id` is the stable
 * key (also used to resolve edges). `label`/`description` are the visible text.
 * `icon` or `kind` selects the glyph (`icon` wins; `kind` falls back to a default
 * map). The remaining fields are optional execution-mode telemetry surfaced for
 * replay/system views (latency, token cost, and a free-form status line).
 */
export interface GraphNode {
  id: string;
  label: string;
  description?: string;
  icon?: IconComponent;
  /** Coarse node category used to pick a default icon when `icon` is absent. */
  kind?: string;
  /** Lifecycle state. When omitted, the renderer treats the node as `idle`. */
  state?: NodeState;
  /** Execution latency in milliseconds (execution mode). */
  durationMs?: number;
  /** Token usage attributed to this node (execution mode). */
  tokens?: number;
  /** Free-form status line (e.g. model id or HTTP status) for execution mode. */
  status?: string;
}

/** A directed edge between two node ids. Mirrors `/v1/platform/topology` edges. */
export interface GraphEdge {
  from: string;
  to: string;
}

export interface TopologyGraphViewProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  /** Optional section heading shown above the graph. */
  title?: string;
  /** Render the pulsing live indicator next to the title (legibility view). */
  live?: boolean;
  /** Stable testid for the container (defaults to `topology-graph`). */
  testId?: string;
}

/**
 * Default icon per coarse node `kind`. Phase-C surfaces (system topology, replay)
 * supply a `kind` rather than an explicit `icon`; this keeps glyphs consistent
 * without forcing every caller to import lucide components.
 */
const KIND_ICONS: Record<string, IconComponent> = {
  agent: Brain,
  model: Boxes,
  tool: Wrench,
  toolset: Wrench,
  pipeline: Workflow,
  workflow: Workflow,
  registry: Database,
};

function iconFor(node: GraphNode): IconComponent {
  if (node.icon) return node.icon;
  if (node.kind && KIND_ICONS[node.kind]) return KIND_ICONS[node.kind];
  return Boxes;
}

/**
 * Order nodes for left-to-right rendering. When the edge set forms a simple
 * chain we follow it (so the linear legibility/DAG views render in pipeline
 * order); otherwise we fall back to the caller-provided node order. Arrows are
 * drawn between consecutive rendered nodes, matching the existing single-row
 * visual. This is a layout heuristic, not a full DAG router — branchy graphs
 * still render every node, just in declaration order.
 */
function orderNodes(nodes: GraphNode[], edges: GraphEdge[]): GraphNode[] {
  if (nodes.length <= 1 || edges.length === 0) return nodes;

  const byId = new Map(nodes.map((n) => [n.id, n]));
  const outDegree = new Map<string, number>();
  const inDegree = new Map<string, number>();
  const next = new Map<string, string>();

  for (const e of edges) {
    if (!byId.has(e.from) || !byId.has(e.to)) return nodes; // unknown id -> bail to declaration order
    outDegree.set(e.from, (outDegree.get(e.from) ?? 0) + 1);
    inDegree.set(e.to, (inDegree.get(e.to) ?? 0) + 1);
    next.set(e.from, e.to);
  }

  // A simple chain has every node with in/out degree <= 1 and exactly one root.
  for (const n of nodes) {
    if ((outDegree.get(n.id) ?? 0) > 1 || (inDegree.get(n.id) ?? 0) > 1) {
      return nodes;
    }
  }

  const roots = nodes.filter((n) => (inDegree.get(n.id) ?? 0) === 0);
  if (roots.length !== 1) return nodes;

  const ordered: GraphNode[] = [];
  const seen = new Set<string>();
  let cursor: string | undefined = roots[0].id;
  while (cursor && !seen.has(cursor)) {
    const node = byId.get(cursor);
    if (!node) break;
    ordered.push(node);
    seen.add(cursor);
    cursor = next.get(cursor);
  }

  // If we failed to walk every node (disconnected), fall back to declaration order.
  return ordered.length === nodes.length ? ordered : nodes;
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(ms < 10000 ? 2 : 1)}s`;
}

function formatTokens(tokens: number): string {
  if (tokens < 1000) return `${tokens} tok`;
  return `${(tokens / 1000).toFixed(1)}k tok`;
}

/**
 * Generalized, data-driven topology renderer. Accepts an arbitrary `{nodes, edges}`
 * graph plus optional per-node execution telemetry and paints the same horizontal
 * node-and-arrow strip used by the legibility view. Phase-C pillars feed this the
 * system topology (`/v1/platform/topology`) and the per-run execution graph
 * (replay spans); the legibility view feeds it the fixed specialist subgraph via
 * the default-export adapter below.
 */
export function TopologyGraphView({
  nodes,
  edges,
  title,
  live = false,
  testId = 'topology-graph',
}: TopologyGraphViewProps) {
  const ordered = orderNodes(nodes, edges);

  return (
    <div
      data-testid={testId}
      className="rounded-lg border border-[var(--g-outline)] bg-black/20 p-4 mb-4"
    >
      {title && (
        <h4 className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider font-semibold text-[var(--g-text-muted)] mb-4">
          {live && (
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--g-info)] opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-[var(--g-info)]"></span>
            </span>
          )}
          {title}
        </h4>
      )}

      <div className="flex flex-col lg:flex-row items-center justify-between gap-2 lg:gap-1 overflow-x-auto py-2">
        {ordered.map((node, index) => {
          const state: NodeState = node.state ?? 'idle';
          const Icon = iconFor(node);
          const hasMeta =
            node.durationMs !== undefined ||
            node.tokens !== undefined ||
            (node.status !== undefined && node.status !== '');

          return (
            <React.Fragment key={node.id}>
              {/* Node Card */}
              <div
                data-testid={`topology-node-${node.id}`}
                className={`relative flex flex-row lg:flex-col items-center gap-3 lg:gap-2 p-3 lg:p-2.5 rounded-lg border w-full lg:w-36 text-left lg:text-center transition-all duration-300 ${
                  state === 'done'
                    ? 'border-[var(--g-success)]/30 bg-[var(--g-success)]/5 hover:border-[var(--g-success)]/50'
                    : state === 'active'
                      ? 'border-[var(--g-info)] bg-[var(--g-info)]/10 ring-1 ring-[var(--g-info)] animate-pulse'
                      : state === 'error'
                        ? 'border-rose-500/30 bg-rose-950/10'
                        : 'border-[var(--g-outline)] bg-black/10 opacity-60'
                }`}
                tabIndex={0}
                aria-label={`${node.label}: status ${state}.${node.description ? ` ${node.description}` : ''}`}
              >
                {/* Node Status Indicator */}
                <div className="absolute top-1.5 right-1.5">
                  {state === 'done' && (
                    <CheckCircle2 size={12} className="text-[var(--g-success)]" />
                  )}
                  {state === 'active' && (
                    <Play size={10} className="text-[var(--g-info)] animate-bounce" />
                  )}
                  {state === 'error' && <AlertCircle size={12} className="text-rose-400" />}
                  {state === 'idle' && (
                    <HelpCircle size={12} className="text-[var(--g-text-muted)]" />
                  )}
                </div>

                {/* Icon wrapper */}
                <div
                  className={`p-2 rounded-full ${
                    state === 'done'
                      ? 'bg-[var(--g-success)]/20 text-[var(--g-success)]'
                      : state === 'active'
                        ? 'bg-[var(--g-info)]/20 text-[var(--g-info)]'
                        : state === 'error'
                          ? 'bg-rose-950/30 text-rose-400'
                          : 'bg-black/40 text-[var(--g-text-muted)]'
                  }`}
                >
                  <Icon size={16} />
                </div>

                <div className="flex flex-col">
                  <span className="text-[11px] font-semibold text-[var(--g-text)]">
                    {node.label}
                  </span>
                  {node.description && (
                    <span className="text-[9px] text-[var(--g-text-muted)] line-clamp-1 lg:line-clamp-2">
                      {node.description}
                    </span>
                  )}
                  {hasMeta && (
                    <span className="mt-0.5 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[9px] font-mono text-[var(--g-text-muted)] lg:justify-center">
                      {node.durationMs !== undefined && (
                        <span data-testid={`topology-node-${node.id}-duration`}>
                          {formatDuration(node.durationMs)}
                        </span>
                      )}
                      {node.tokens !== undefined && (
                        <span data-testid={`topology-node-${node.id}-tokens`}>
                          {formatTokens(node.tokens)}
                        </span>
                      )}
                      {node.status !== undefined && node.status !== '' && (
                        <span data-testid={`topology-node-${node.id}-status`}>{node.status}</span>
                      )}
                    </span>
                  )}
                </div>
              </div>

              {/* Edge Connecting Arrow */}
              {index < ordered.length - 1 && (
                <div
                  className={`flex items-center justify-center shrink-0 ${
                    state === 'done' ? 'text-[var(--g-success)]/40' : 'text-[var(--g-outline)]'
                  }`}
                  aria-hidden="true"
                >
                  <ArrowRight size={14} className="rotate-90 lg:rotate-0 my-1 lg:my-0" />
                </div>
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Legibility adapter (default export) — byte-compatible with the prior view.
// ---------------------------------------------------------------------------

export interface TopologyGraphProps {
  specialistTraces: SpecialistTraceData[];
  error?: string | null;
}

interface SpecialistMeta {
  role: string;
  label: string;
  description: string;
  icon: IconComponent;
}

/**
 * The fixed DDLC specialist subgraph. Order encodes the deterministic hand-off
 * chain UX Research -> IA/Flows -> Wireframe -> UI -> Interaction -> Tokens.
 */
const SPECIALISTS: SpecialistMeta[] = [
  {
    role: 'ux_research',
    label: 'UX Researcher',
    description: 'Synthesizes users, JTBD, and success criteria.',
    icon: Users,
  },
  {
    role: 'ia_flows',
    label: 'IA / Flows',
    description: 'Defines information architecture and user flows.',
    icon: MapIcon,
  },
  {
    role: 'wireframe',
    label: 'Wireframer',
    description: 'Produces structural layouts (semantic regions).',
    icon: Layout,
  },
  {
    role: 'ui_design',
    label: 'UI Designer',
    description: 'Generates shippable CSS/HTML (Stitch-first).',
    icon: Palette,
  },
  {
    role: 'interaction_spec',
    label: 'Interaction Designer',
    description: 'Specifies interactive states and ARIA behaviors.',
    icon: Zap,
  },
  {
    role: 'tokens',
    label: 'Token Generator',
    description: 'Extracts DTCG semantic tokens.',
    icon: Database,
  },
];

const ROLE_NAME_MAP: Record<string, string> = {
  UXResearcher: 'ux_research',
  IAFlowDesigner: 'ia_flows',
  Wireframer: 'wireframe',
  UIDesigner: 'ui_design',
  InteractionDesigner: 'interaction_spec',
  TokenGenerator: 'tokens',
};

/**
 * Build the legibility `{nodes, edges}` from the live specialist traces, deriving
 * per-node state with the exact rules of the prior hardwired component: completed
 * roles are `done`; the first incomplete role is `active` (or `error` on failure);
 * everything after stays `idle`.
 */
function buildSpecialistGraph(
  specialistTraces: SpecialistTraceData[],
  error?: string | null
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const completedRoles = new Set(specialistTraces.map((t) => ROLE_NAME_MAP[t.role] || t.role));
  const activeRoleIndex = SPECIALISTS.findIndex((node) => !completedRoles.has(node.role));

  const nodes: GraphNode[] = SPECIALISTS.map((spec, index) => {
    const isDone = completedRoles.has(spec.role);
    let state: NodeState = 'idle';
    if (isDone) {
      state = 'done';
    } else if (index === activeRoleIndex) {
      state = error ? 'error' : 'active';
    } else if (error && index > activeRoleIndex) {
      state = 'idle';
    }
    return {
      id: spec.role,
      label: spec.label,
      description: spec.description,
      icon: spec.icon,
      state,
    };
  });

  const edges: GraphEdge[] = [];
  for (let i = 0; i < SPECIALISTS.length - 1; i++) {
    edges.push({ from: SPECIALISTS[i].role, to: SPECIALISTS[i + 1].role });
  }

  return { nodes, edges };
}

/**
 * Legibility view (unchanged behavior): the live DDLC specialist topology shown
 * in the Studio while a generation runs. Thin adapter over {@link TopologyGraphView}.
 */
export default function TopologyGraph({ specialistTraces, error }: TopologyGraphProps) {
  const { nodes, edges } = buildSpecialistGraph(specialistTraces, error);
  return <TopologyGraphView nodes={nodes} edges={edges} title="Live Graph Topology" live />;
}
