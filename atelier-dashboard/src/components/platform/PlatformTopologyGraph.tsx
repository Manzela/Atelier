'use client';

import React from 'react';
import { TopologyGraphView } from '@/components/legibility/TopologyGraph';
import type { NodeState } from '@/components/legibility/TopologyGraph';
import type { AgentActivityMap } from '@/lib/firestore-agents';
import type { TopologyGraphSpec } from '@/lib/api';

interface PlatformTopologyGraphProps {
  /** System topology spec returned by GET /v1/platform/topology. */
  spec: TopologyGraphSpec;
  /** Optional section heading rendered above the graph. */
  title?: string;
  /** Stable testid forwarded to the graph container. */
  testId?: string;
  /**
   * Live per-agent state overrides from `subscribeAgentActivity`. When present,
   * each node whose `id` matches an `agentRole` key in the map gets its `state`
   * replaced with the live value. Absent keys fall back to `idle` (design-time).
   * Set `live` on the title indicator whenever the map is non-empty.
   */
  nodeStates?: AgentActivityMap;
}

/**
 * Thin adapter that maps the `/v1/platform/topology` response onto the
 * generalized `TopologyGraphView`. Phase-C callers (PillarBuild, PillarGovern)
 * pass the raw API response directly; this component handles the node/edge
 * reshaping so each pillar stays free of graph-rendering concerns.
 *
 * When `nodeStates` is provided (Phase-D live-sync), node states are driven from
 * real Firestore task docs rather than the static `idle` default. The pulsing live
 * indicator appears in the title bar whenever at least one node is `active`.
 */
export default function PlatformTopologyGraph({
  spec,
  title = 'System Topology',
  testId = 'platform-topology-graph',
  nodeStates,
}: PlatformTopologyGraphProps) {
  const hasLiveActivity =
    nodeStates !== undefined && Object.values(nodeStates).some((s: NodeState) => s === 'active');

  return (
    <TopologyGraphView
      nodes={spec.nodes.map((n) => ({
        id: n.id,
        label: n.label,
        kind: n.kind,
        status: n.model ?? undefined,
        state: nodeStates?.[n.id] ?? 'idle',
      }))}
      edges={spec.edges}
      title={title}
      testId={testId}
      live={hasLiveActivity}
    />
  );
}
