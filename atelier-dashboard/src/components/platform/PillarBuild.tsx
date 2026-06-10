'use client';

import React, { useState, useEffect } from 'react';
import { ChevronRight, Loader2, AlertCircle, Box, Cpu, Layers, Wrench } from 'lucide-react';
import { usePlatformData } from './usePlatformData';
import { useAgentActivity } from './useAgentActivity';
import PlatformTopologyGraph from './PlatformTopologyGraph';
import type {
  AgentSummary,
  AgentDescriptor,
  AgentsResponse,
  PlatformBuild,
  TopologyGraphSpec,
} from '@/lib/api';
import { getAgent } from '@/lib/api';

// ---------------------------------------------------------------------------
// Internal helpers
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

function LoadingPane({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 text-[var(--g-text-muted)] text-sm p-4">
      <Loader2 size={14} className="animate-spin" />
      <span>{label}</span>
    </div>
  );
}

function ErrorPane({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex flex-col gap-2 p-4">
      <div className="flex items-center gap-2 text-rose-400 text-sm">
        <AlertCircle size={14} />
        <span>{message}</span>
      </div>
      <button onClick={onRetry} className="text-xs text-[var(--g-info)] hover:underline self-start">
        Retry
      </button>
    </div>
  );
}

function UnavailablePane({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 p-4 text-sm text-[var(--g-text-muted)]">
      <AlertCircle size={14} />
      <span>{label}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Agent detail panel
// ---------------------------------------------------------------------------

function AgentDetailPanel({ agentId }: { agentId: string }) {
  const [descriptor, setDescriptor] = useState<AgentDescriptor | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
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
        const res = await getAgent(agentId, token);
        if (signal.aborted) return;
        // Backend returns { available, agent } — guard before rendering.
        setDescriptor(res.available && res.agent ? res.agent : null);
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
  }, [agentId, retryTick]);

  if (loading) return <LoadingPane label="Loading agent descriptor..." />;
  if (error) return <ErrorPane message={error} onRetry={() => setRetryTick((n) => n + 1)} />;
  if (!descriptor) {
    return (
      <div className="p-4 text-[var(--g-text-muted)] text-sm">
        Agent descriptor unavailable for <code className="font-mono">{agentId}</code>.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      {/* Header */}
      <div>
        <h3 className="text-base font-semibold text-[var(--g-text)]">{descriptor.name}</h3>
        <p className="text-xs text-[var(--g-text-muted)] mt-0.5">{descriptor.description}</p>
      </div>

      {/* Meta grid */}
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
        <div>
          <dt className="text-[var(--g-text-muted)] uppercase tracking-wider text-[10px]">Kind</dt>
          <dd className="text-[var(--g-text)] font-mono mt-0.5">{descriptor.kind}</dd>
        </div>
        <div>
          <dt className="text-[var(--g-text-muted)] uppercase tracking-wider text-[10px]">
            ADK Type
          </dt>
          <dd className="text-[var(--g-text)] font-mono mt-0.5">{descriptor.adk_type}</dd>
        </div>
        <div>
          <dt className="text-[var(--g-text-muted)] uppercase tracking-wider text-[10px]">Model</dt>
          <dd className="text-[var(--g-text)] font-mono mt-0.5">{descriptor.model_id}</dd>
        </div>
        <div>
          <dt className="text-[var(--g-text-muted)] uppercase tracking-wider text-[10px]">
            Task Type
          </dt>
          <dd className="text-[var(--g-text)] font-mono mt-0.5">{descriptor.task_type ?? '—'}</dd>
        </div>
        {descriptor.subagent_of && (
          <div className="col-span-2">
            <dt className="text-[var(--g-text-muted)] uppercase tracking-wider text-[10px]">
              Subagent of
            </dt>
            <dd className="text-[var(--g-text)] font-mono mt-0.5">{descriptor.subagent_of}</dd>
          </div>
        )}
      </dl>

      {/* Tools */}
      {descriptor.tools.length > 0 && (
        <div>
          <h4 className="text-[10px] uppercase tracking-wider text-[var(--g-text-muted)] mb-1.5">
            Tools
          </h4>
          <div className="flex flex-wrap gap-1.5">
            {descriptor.tools.map((t) => (
              <span
                key={t}
                className="px-2 py-0.5 rounded text-[10px] font-mono bg-black/30 border border-[var(--g-outline)] text-[var(--g-text-muted)]"
              >
                {t}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Upstream / output keys */}
      <div className="grid grid-cols-2 gap-4">
        {descriptor.upstream_keys.length > 0 && (
          <div>
            <h4 className="text-[10px] uppercase tracking-wider text-[var(--g-text-muted)] mb-1.5">
              Reads (upstream)
            </h4>
            <ul className="flex flex-col gap-1">
              {descriptor.upstream_keys.map((k) => (
                <li key={k} className="text-[10px] font-mono text-[var(--g-text-muted)]">
                  {k}
                </li>
              ))}
            </ul>
          </div>
        )}
        <div>
          <h4 className="text-[10px] uppercase tracking-wider text-[var(--g-text-muted)] mb-1.5">
            Writes (output)
          </h4>
          <span className="text-[10px] font-mono text-[var(--g-text-muted)]">
            {descriptor.output_key}
          </span>
        </div>
      </div>

      {/* System prompt excerpt */}
      {descriptor.prompt && (
        <div>
          <h4 className="text-[10px] uppercase tracking-wider text-[var(--g-text-muted)] mb-1.5">
            System Prompt
            {descriptor.prompt_source && (
              <span className="ml-2 normal-case font-normal text-[var(--g-text-muted)]">
                — {descriptor.prompt_source}
              </span>
            )}
          </h4>
          <pre className="text-[10px] font-mono text-[var(--g-text-muted)] whitespace-pre-wrap bg-black/30 border border-[var(--g-outline)] rounded p-3 max-h-40 overflow-y-auto">
            {descriptor.prompt}
          </pre>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Agent registry list
// ---------------------------------------------------------------------------

/**
 * A small pulsing dot indicating the agent is currently executing a task.
 * Shown inline next to the agent name when `active` is true.
 */
function LiveDot({ state }: { state: 'active' | 'done' | 'idle' | 'error' | undefined }) {
  if (state === 'active') {
    return (
      <span className="relative flex h-2 w-2 shrink-0" title="Running">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--g-info)] opacity-75" />
        <span className="relative inline-flex rounded-full h-2 w-2 bg-[var(--g-info)]" />
      </span>
    );
  }
  if (state === 'done') {
    return (
      <span
        className="inline-flex h-2 w-2 shrink-0 rounded-full bg-[var(--g-success)]"
        title="Done"
      />
    );
  }
  return null;
}

function AgentList({
  agents,
  selectedId,
  onSelect,
  agentActivity,
}: {
  agents: AgentSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  /** Live per-agent state map from `useAgentActivity`. Keys are agentRole / agent id. */
  agentActivity: Record<string, 'active' | 'done' | 'idle' | 'error'>;
}) {
  return (
    <ul className="divide-y divide-[var(--g-outline)]">
      {agents.map((agent) => {
        const liveState = agentActivity[agent.id] ?? agentActivity[agent.task_type ?? ''];
        return (
          <li key={agent.id}>
            <button
              onClick={() => onSelect(agent.id)}
              className={`w-full text-left px-3 py-2.5 flex items-center justify-between gap-2 transition-colors ${
                selectedId === agent.id
                  ? 'bg-[var(--g-info)]/10 text-[var(--g-info)]'
                  : 'text-[var(--g-text)] hover:bg-black/20'
              }`}
            >
              <div className="flex flex-col min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-semibold truncate">{agent.name}</span>
                  <LiveDot state={liveState} />
                </div>
                <span className="text-[10px] text-[var(--g-text-muted)] font-mono truncate">
                  {agent.task_type ?? agent.kind} — {agent.model_id}
                </span>
              </div>
              <ChevronRight
                size={12}
                className={`shrink-0 ${selectedId === agent.id ? 'text-[var(--g-info)]' : 'text-[var(--g-text-muted)]'}`}
              />
            </button>
          </li>
        );
      })}
    </ul>
  );
}

// ---------------------------------------------------------------------------
// Build pillar root
// ---------------------------------------------------------------------------

/**
 * Build pillar — Platform > Build.
 *
 * Surfaces three sub-sections:
 *   1. Agent Registry master-detail (roster on the left, full descriptor on the right).
 *   2. System Topology graph (the static specialist DAG from /v1/platform/topology).
 *   3. A2A Agent Card skills and MCP toolsets from /v1/platform/build.
 *
 * Phase-D: live per-agent state is subscribed via `useAgentActivity` (Firestore
 * `onSnapshot`) and surfaced both in the Agent Registry list (pulsing live dot)
 * and in the System Topology graph node colours.
 */
export default function PillarBuild() {
  const {
    loading: agentsLoading,
    error: agentsError,
    data: agentsData,
    refetch: refetchAgents,
  } = usePlatformData<AgentsResponse>('/v1/platform/agents');

  const {
    loading: buildLoading,
    error: buildError,
    data: buildData,
    refetch: refetchBuild,
  } = usePlatformData<PlatformBuild>('/v1/platform/build');

  const {
    loading: topoLoading,
    error: topoError,
    data: topoData,
  } = usePlatformData<TopologyGraphSpec>('/v1/platform/topology');

  // Phase-D: live agent activity — subscribed to the tenant's task docs via
  // Firestore onSnapshot. Empty map on initial render; no polling. The project
  // id is the server-written Firestore path segment surfaced on /topology
  // (GAP-3): until it loads, the hook stays unsubscribed (nodes render idle).
  const agentActivity = useAgentActivity(topoData?.project_id);

  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);

  // The /agents endpoint returns an envelope; the roster lives on `.agents`.
  const agents = agentsData?.available ? agentsData.agents : null;

  // Auto-select the first agent when the list loads. Deriving the effective
  // selection here (rather than committing it in an effect) keeps the render
  // pure and avoids a synchronous setState-in-effect.
  const effectiveAgent = selectedAgent ?? (agents && agents.length > 0 ? agents[0].id : null);

  const buildAvailable = buildData?.available === true;
  const skills = buildAvailable ? buildData.skills : [];
  const toolsets = buildAvailable ? buildData.mcp_toolsets : [];

  return (
    <div className="flex flex-col gap-6">
      {/* Summary badges */}
      <div className="flex items-center gap-4">
        {[
          {
            icon: <Box size={14} />,
            label: 'Agents',
            value: buildLoading
              ? '…'
              : buildAvailable
                ? String(buildData.counts.agents_total)
                : '—',
          },
          {
            icon: <Layers size={14} />,
            label: 'Skills',
            value: buildLoading ? '…' : buildAvailable ? String(buildData.counts.skills) : '—',
          },
          {
            icon: <Wrench size={14} />,
            label: 'Toolsets',
            value: buildLoading
              ? '…'
              : buildAvailable
                ? String(buildData.counts.mcp_toolsets)
                : '—',
          },
        ].map(({ icon, label, value }) => (
          <div
            key={label}
            className="flex items-center gap-2 px-3 py-1.5 rounded-md border border-[var(--g-outline)] bg-black/20"
          >
            <span className="text-[var(--g-text-muted)]">{icon}</span>
            <span className="text-xs text-[var(--g-text-muted)]">{label}</span>
            <span className="text-xs font-semibold text-[var(--g-text)]">{value}</span>
          </div>
        ))}
      </div>

      {/* Agent Registry */}
      <section>
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-[var(--g-text-muted)] mb-3">
          Agent Registry
        </h3>
        {agentsLoading ? (
          <LoadingPane label="Loading agent roster..." />
        ) : agentsError ? (
          <ErrorPane message={agentsError} onRetry={refetchAgents} />
        ) : !agents ? (
          <UnavailablePane label="Agent registry is currently unavailable." />
        ) : agents.length === 0 ? (
          <div className="text-sm text-[var(--g-text-muted)] p-4">No agents registered.</div>
        ) : (
          <div className="rounded-lg border border-[var(--g-outline)] overflow-hidden grid lg:grid-cols-[240px_1fr]">
            {/* Left: roster */}
            <div className="border-b lg:border-b-0 lg:border-r border-[var(--g-outline)] overflow-y-auto max-h-96">
              <AgentList
                agents={agents}
                selectedId={effectiveAgent}
                onSelect={setSelectedAgent}
                agentActivity={agentActivity}
              />
            </div>
            {/* Right: detail */}
            <div className="overflow-y-auto max-h-96">
              {effectiveAgent ? (
                <AgentDetailPanel agentId={effectiveAgent} />
              ) : (
                <div className="p-4 text-sm text-[var(--g-text-muted)]">
                  Select an agent to view its descriptor.
                </div>
              )}
            </div>
          </div>
        )}
      </section>

      {/* System Topology */}
      <section>
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-[var(--g-text-muted)] mb-3">
          System Topology
        </h3>
        {topoLoading ? (
          <LoadingPane label="Loading topology..." />
        ) : topoError ? (
          <div className="p-4 text-sm text-rose-400 flex items-center gap-2">
            <AlertCircle size={14} />
            <span>{topoError}</span>
          </div>
        ) : topoData?.available ? (
          <PlatformTopologyGraph
            spec={topoData}
            title="Specialist DAG"
            nodeStates={agentActivity}
          />
        ) : (
          <UnavailablePane label="System topology is currently unavailable." />
        )}
      </section>

      {/* A2A Agent Card Skills + MCP Toolsets */}
      {buildLoading ? null : buildError ? (
        <ErrorPane message={buildError} onRetry={refetchBuild} />
      ) : !buildAvailable ? (
        <UnavailablePane label="Build surface is currently unavailable." />
      ) : (
        <>
          <section>
            <h3 className="text-[11px] uppercase tracking-wider font-semibold text-[var(--g-text-muted)] mb-3">
              A2A Agent Card Skills
            </h3>
            {skills.length === 0 ? (
              <p className="text-sm text-[var(--g-text-muted)]">No skills declared.</p>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {skills.map((skill, i) => (
                  <div
                    key={skill.id ?? skill.name ?? `skill-${i}`}
                    className="rounded-lg border border-[var(--g-outline)] bg-black/20 p-3 flex flex-col gap-1.5"
                  >
                    <span className="text-xs font-semibold text-[var(--g-text)]">
                      {skill.name ?? skill.id ?? 'Unnamed skill'}
                    </span>
                    <span className="text-[10px] text-[var(--g-text-muted)]">
                      {skill.description}
                    </span>
                    {skill.tags.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-auto">
                        {skill.tags.map((tag) => (
                          <span
                            key={tag}
                            className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-[var(--g-info)]/10 border border-[var(--g-info)]/20 text-[var(--g-info)]"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* MCP Toolsets */}
          <section>
            <h3 className="text-[11px] uppercase tracking-wider font-semibold text-[var(--g-text-muted)] mb-3">
              MCP Toolsets
            </h3>
            {toolsets.length === 0 ? (
              <p className="text-sm text-[var(--g-text-muted)]">No MCP toolsets registered.</p>
            ) : (
              <div className="flex flex-col gap-3">
                {toolsets.map((ts) => (
                  <div
                    key={ts.toolset}
                    className="rounded-lg border border-[var(--g-outline)] bg-black/20 p-3"
                  >
                    <div className="flex items-center gap-1.5 mb-2">
                      <Cpu size={12} className="text-[var(--g-text-muted)]" />
                      <span className="text-xs font-semibold text-[var(--g-text)]">
                        {ts.toolset}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {ts.agents.map((agentId) => (
                        <span
                          key={agentId}
                          className="px-2 py-0.5 rounded text-[10px] font-mono bg-black/30 border border-[var(--g-outline)] text-[var(--g-text-muted)]"
                        >
                          {agentId}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
