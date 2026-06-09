'use client';

import React from 'react';
import { Loader2, AlertCircle, CheckCircle2, ShieldCheck, ShieldAlert } from 'lucide-react';
import { usePlatformData } from './usePlatformData';
import PlatformTopologyGraph from './PlatformTopologyGraph';
import type { PlatformGovern, TopologyGraphSpec } from '@/lib/api';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function UsageBar({
  tier,
  used,
  remaining,
  cap,
}: {
  tier: string;
  used: number;
  remaining: number;
  cap: number;
}) {
  const pct = cap > 0 ? Math.min((used / cap) * 100, 100) : 0;
  const isWarning = pct >= 80;
  const isCritical = pct >= 95;

  const barColor = isCritical ? 'bg-rose-500' : isWarning ? 'bg-amber-500' : 'bg-[var(--g-info)]';

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between text-xs">
        <span className="font-semibold text-[var(--g-text)] capitalize">
          {tier.replace(/_/g, ' ')}
        </span>
        <span className="font-mono text-[var(--g-text-muted)]">
          {used.toLocaleString()} / {cap.toLocaleString()}
          <span className="ml-1 text-[10px]">({remaining.toLocaleString()} remaining)</span>
        </span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-black/30 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-300 ${barColor}`}
          style={{ width: `${pct}%` }}
          role="progressbar"
          aria-valuenow={used}
          aria-valuemin={0}
          aria-valuemax={cap}
          aria-label={`${tier} usage: ${Math.round(pct)}%`}
        />
      </div>
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
// Govern pillar
// ---------------------------------------------------------------------------

/**
 * Govern pillar — Platform > Govern.
 *
 * Surfaces:
 *   - Caller identity (Firebase UID + tenant + email-verified state).
 *   - Per-tier token usage bars (the usage map keyed by tier name).
 *   - Model Armor summary (always-on injection guard + Vertex template state).
 *   - Rate-limit and circuit-breaker thresholds.
 *   - System Topology graph for governance context.
 *
 * Every sub-block is fail-soft and guarded on its own `available` flag.
 */
export default function PillarGovern() {
  const { loading, error, data, refetch } = usePlatformData<PlatformGovern>('/v1/platform/govern');

  const {
    loading: topoLoading,
    error: topoError,
    data: topoData,
  } = usePlatformData<TopologyGraphSpec>('/v1/platform/topology');

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-[var(--g-text-muted)] text-sm p-4">
        <Loader2 size={14} className="animate-spin" />
        <span>Loading governance data...</span>
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

  if (!data || !data.available) {
    return <UnavailablePane label="Governance surface is currently unavailable." />;
  }

  const usage = data.usage;
  const usageTiers = usage.available && usage.tiers ? Object.entries(usage.tiers) : [];
  const armor = data.model_armor;
  const thresholds = data.thresholds;

  return (
    <div className="flex flex-col gap-6">
      {/* Identity */}
      <section>
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-[var(--g-text-muted)] mb-3">
          Identity
        </h3>
        <dl className="rounded-lg border border-[var(--g-outline)] bg-black/20 grid sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-[var(--g-outline)]">
          <div className="px-4 py-3">
            <dt className="text-[10px] uppercase tracking-wider text-[var(--g-text-muted)]">
              Firebase UID
            </dt>
            <dd className="mt-1 text-xs font-mono text-[var(--g-text)] truncate">
              {data.identity.uid}
            </dd>
          </div>
          <div className="px-4 py-3">
            <dt className="text-[10px] uppercase tracking-wider text-[var(--g-text-muted)]">
              Tenant
            </dt>
            <dd className="mt-1 text-xs font-mono text-[var(--g-text)] truncate">
              {data.identity.tenant_id}
            </dd>
          </div>
          <div className="px-4 py-3">
            <dt className="text-[10px] uppercase tracking-wider text-[var(--g-text-muted)]">
              Email Verified
            </dt>
            <dd className="mt-1 text-xs font-mono text-[var(--g-text)]">
              {data.identity.email_verified ? 'Yes' : 'No'}
            </dd>
          </div>
        </dl>
      </section>

      {/* Token usage by tier */}
      <section>
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-[var(--g-text-muted)] mb-3">
          Token Usage by Tier
        </h3>
        {!usage.available ? (
          <UnavailablePane label="Usage data is currently unavailable." />
        ) : usageTiers.length === 0 ? (
          <p className="text-sm text-[var(--g-text-muted)]">No usage data available.</p>
        ) : (
          <div className="rounded-lg border border-[var(--g-outline)] bg-black/20 p-4 flex flex-col gap-4">
            {usageTiers.map(([tier, counters]) => (
              <UsageBar
                key={tier}
                tier={tier}
                used={counters.used}
                remaining={counters.remaining}
                cap={counters.cap}
              />
            ))}
            {typeof usage.total_tokens === 'number' && (
              <div className="flex items-center justify-between text-[10px] text-[var(--g-text-muted)] pt-1 border-t border-[var(--g-outline)]">
                <span className="uppercase tracking-wider">Total tokens</span>
                <span className="font-mono text-[var(--g-text)]">
                  {usage.total_tokens.toLocaleString()}
                </span>
              </div>
            )}
          </div>
        )}
      </section>

      {/* Model Armor */}
      <section>
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-[var(--g-text-muted)] mb-3">
          Model Armor
        </h3>
        {!armor.available ? (
          <UnavailablePane label="Model Armor data is currently unavailable." />
        ) : (
          <div className="rounded-lg border border-[var(--g-outline)] bg-black/20 grid sm:grid-cols-2 divide-y sm:divide-y-0 sm:divide-x divide-[var(--g-outline)]">
            <div className="px-4 py-3 flex flex-col gap-1.5">
              <div className="flex items-center gap-1.5">
                <ShieldCheck size={12} className="text-[var(--g-success)]" />
                <span className="text-xs font-semibold text-[var(--g-text)]">
                  Deterministic Injection Guard
                </span>
              </div>
              <span className="text-[10px] text-[var(--g-text-muted)]">
                {armor.deterministic_injection_guard?.always_on ? 'Always on' : 'Disabled'}
                {armor.deterministic_injection_guard
                  ? ` · ${armor.deterministic_injection_guard.marker_count} markers`
                  : ''}
              </span>
            </div>
            <div className="px-4 py-3 flex flex-col gap-1.5">
              <div className="flex items-center gap-1.5">
                {armor.vertex_model_armor_template?.enabled ? (
                  <CheckCircle2 size={12} className="text-[var(--g-success)]" />
                ) : (
                  <ShieldAlert size={12} className="text-[var(--g-text-muted)]" />
                )}
                <span className="text-xs font-semibold text-[var(--g-text)]">
                  Vertex Model Armor Template
                </span>
              </div>
              <span className="text-[10px] text-[var(--g-text-muted)]">
                {armor.vertex_model_armor_template?.enabled ? 'Enabled' : 'Not enabled'}
              </span>
            </div>
          </div>
        )}
      </section>

      {/* Rate and circuit-breaker thresholds */}
      <section>
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-[var(--g-text-muted)] mb-3">
          Rate and Circuit-Breaker Thresholds
        </h3>
        {!thresholds.available || !thresholds.rate_limit || !thresholds.circuit_breaker ? (
          <UnavailablePane label="Threshold configuration is currently unavailable." />
        ) : (
          <dl className="rounded-lg border border-[var(--g-outline)] bg-black/20 grid sm:grid-cols-2 gap-0 divide-y sm:divide-y-0 sm:divide-x divide-[var(--g-outline)]">
            {[
              {
                label: 'Max Requests per Window',
                value: thresholds.rate_limit.max_requests.toLocaleString(),
              },
              {
                label: 'Rate Window',
                value: `${thresholds.rate_limit.window_seconds}s`,
              },
              {
                label: 'Circuit Breaker Budget',
                value: thresholds.circuit_breaker.enabled
                  ? `${thresholds.circuit_breaker.global_token_budget_per_window.toLocaleString()} tokens`
                  : 'Disabled',
              },
              {
                label: 'Breaker Cooldown',
                value: `${thresholds.circuit_breaker.cooldown_seconds}s`,
              },
            ].map(({ label, value }) => (
              <div key={label} className="px-4 py-3">
                <dt className="text-[10px] uppercase tracking-wider text-[var(--g-text-muted)]">
                  {label}
                </dt>
                <dd className="mt-1 text-xs font-mono text-[var(--g-text)]">{value}</dd>
              </div>
            ))}
          </dl>
        )}
      </section>

      {/* System Topology */}
      <section>
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-[var(--g-text-muted)] mb-3">
          System Topology
        </h3>
        {topoLoading ? (
          <div className="flex items-center gap-2 text-[var(--g-text-muted)] text-sm p-4">
            <Loader2 size={14} className="animate-spin" />
            <span>Loading topology...</span>
          </div>
        ) : topoError ? (
          <div className="p-4 text-sm text-rose-400 flex items-center gap-2">
            <AlertCircle size={14} />
            <span>{topoError}</span>
          </div>
        ) : topoData?.available ? (
          <PlatformTopologyGraph spec={topoData} title="Specialist DAG" />
        ) : (
          <UnavailablePane label="System topology is currently unavailable." />
        )}
      </section>
    </div>
  );
}
