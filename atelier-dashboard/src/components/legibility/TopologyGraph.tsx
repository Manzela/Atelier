'use client';

import React from 'react';
import {
  Users,
  Map,
  Layout,
  Palette,
  Zap,
  Database,
  ArrowRight,
  CheckCircle2,
  Play,
  AlertCircle,
  HelpCircle,
} from 'lucide-react';
import type { SpecialistTraceData } from '@/lib/api';

export interface TopologyGraphProps {
  specialistTraces: SpecialistTraceData[];
  error?: string | null;
}

interface NodeMeta {
  role: string;
  label: string;
  description: string;
  icon: React.ComponentType<{ className?: string; size?: number }>;
}

const NODES: NodeMeta[] = [
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
    icon: Map,
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

type NodeState = 'idle' | 'active' | 'done' | 'error';

export default function TopologyGraph({ specialistTraces, error }: TopologyGraphProps) {
  // Determine state of each node based on specialistTraces
  const completedRoles = new Set(specialistTraces.map((t) => ROLE_NAME_MAP[t.role] || t.role));

  // Find the first role that is not completed
  const activeRoleIndex = NODES.findIndex((node) => !completedRoles.has(node.role));

  return (
    <div
      data-testid="topology-graph"
      className="rounded-lg border border-[var(--g-outline)] bg-black/20 p-4 mb-4"
    >
      <h4 className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider font-semibold text-gray-500 mb-4">
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--g-info)] opacity-75"></span>
          <span className="relative inline-flex rounded-full h-2 w-2 bg-[var(--g-info)]"></span>
        </span>
        Live Graph Topology
      </h4>

      <div className="flex flex-col lg:flex-row items-center justify-between gap-2 lg:gap-1 overflow-x-auto py-2">
        {NODES.map((node, index) => {
          const isDone = completedRoles.has(node.role);
          let state: NodeState = 'idle';

          if (isDone) {
            state = 'done';
          } else if (index === activeRoleIndex) {
            state = error ? 'error' : 'active';
          } else if (error && index > activeRoleIndex) {
            state = 'idle';
          }

          const Icon = node.icon;

          return (
            <React.Fragment key={node.role}>
              {/* Node Card */}
              <div
                data-testid={`topology-node-${node.role}`}
                className={`relative flex flex-row lg:flex-col items-center gap-3 lg:gap-2 p-3 lg:p-2.5 rounded-lg border w-full lg:w-36 text-left lg:text-center transition-all duration-300 ${
                  state === 'done'
                    ? 'border-emerald-500/30 bg-emerald-950/10 hover:border-emerald-500/50'
                    : state === 'active'
                      ? 'border-[var(--g-info)] bg-[var(--g-info)]/10 ring-1 ring-[var(--g-info)] animate-pulse'
                      : state === 'error'
                        ? 'border-rose-500/30 bg-rose-950/10'
                        : 'border-[var(--g-outline)] bg-black/10 opacity-60'
                }`}
                tabIndex={0}
                aria-label={`${node.label}: status ${state}. ${node.description}`}
              >
                {/* Node Status Indicator */}
                <div className="absolute top-1.5 right-1.5">
                  {state === 'done' && <CheckCircle2 size={12} className="text-emerald-400" />}
                  {state === 'active' && (
                    <Play size={10} className="text-[var(--g-info)] animate-bounce" />
                  )}
                  {state === 'error' && <AlertCircle size={12} className="text-rose-400" />}
                  {state === 'idle' && <HelpCircle size={12} className="text-gray-600" />}
                </div>

                {/* Icon wrapper */}
                <div
                  className={`p-2 rounded-full ${
                    state === 'done'
                      ? 'bg-emerald-950/30 text-emerald-400'
                      : state === 'active'
                        ? 'bg-[var(--g-info)]/20 text-[var(--g-info)]'
                        : state === 'error'
                          ? 'bg-rose-950/30 text-rose-400'
                          : 'bg-black/40 text-gray-500'
                  }`}
                >
                  <Icon size={16} />
                </div>

                <div className="flex flex-col">
                  <span className="text-[11px] font-semibold text-gray-200">{node.label}</span>
                  <span className="text-[9px] text-gray-500 line-clamp-1 lg:line-clamp-2">
                    {node.description}
                  </span>
                </div>
              </div>

              {/* Edge Connecting Arrow */}
              {index < NODES.length - 1 && (
                <div
                  className={`flex items-center justify-center shrink-0 ${
                    state === 'done' ? 'text-emerald-500/40' : 'text-gray-700'
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
