'use client';

import React from 'react';
import { TopologyGraphView } from '@/components/legibility/TopologyGraph';
import type { TopologyGraphSpec } from '@/lib/api';

interface PlatformTopologyGraphProps {
  /** System topology spec returned by GET /v1/platform/topology. */
  spec: TopologyGraphSpec;
  /** Optional section heading rendered above the graph. */
  title?: string;
  /** Stable testid forwarded to the graph container. */
  testId?: string;
}

/**
 * Thin adapter that maps the `/v1/platform/topology` response onto the
 * generalized `TopologyGraphView`. Phase-C callers (PillarBuild, PillarGovern)
 * pass the raw API response directly; this component handles the node/edge
 * reshaping so each pillar stays free of graph-rendering concerns.
 *
 * Execution telemetry fields (state, durationMs, tokens, status) are absent
 * for the static system topology — nodes render as `idle` / design-time style.
 */
export default function PlatformTopologyGraph({
  spec,
  title = 'System Topology',
  testId = 'platform-topology-graph',
}: PlatformTopologyGraphProps) {
  return (
    <TopologyGraphView
      nodes={spec.nodes.map((n) => ({
        id: n.id,
        label: n.label,
        kind: n.kind,
        status: n.model ?? undefined,
      }))}
      edges={spec.edges}
      title={title}
      testId={testId}
    />
  );
}
