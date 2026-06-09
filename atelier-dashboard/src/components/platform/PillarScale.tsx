'use client';

import React from 'react';
import { Loader2, AlertCircle, CheckCircle2, XCircle } from 'lucide-react';
import { usePlatformData } from './usePlatformData';
import type { PlatformScale } from '@/lib/api';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function HealthBadge({ available, status }: { available: boolean; status: string }) {
  if (available && status === 'healthy') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-[var(--g-success)]/15 text-[var(--g-success)] border border-[var(--g-success)]/30">
        <CheckCircle2 size={10} />
        Healthy
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-rose-500/15 text-rose-400 border border-rose-500/30">
      <XCircle size={10} />
      Unavailable
    </span>
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
// Scale pillar
// ---------------------------------------------------------------------------

/**
 * Scale pillar — Platform > Scale.
 *
 * Surfaces:
 *   - Serving-stack health rollup.
 *   - Model routing catalog (id, display name, tier, token cap, task types).
 *   - Session/usage backend modes.
 *   - Agent Engine deploy configuration.
 *
 * Every sub-block is fail-soft: the backend returns `available: false` (HTTP
 * 200) for any offline source, so each block is guarded before rendering.
 */
export default function PillarScale() {
  const { loading, error, data, refetch } = usePlatformData<PlatformScale>('/v1/platform/scale');

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-[var(--g-text-muted)] text-sm p-4">
        <Loader2 size={14} className="animate-spin" />
        <span>Loading scale configuration...</span>
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
    return <UnavailablePane label="Scale surface is currently unavailable." />;
  }

  const catalog = data.model_catalog;
  const deploy = data.deploy_config;

  return (
    <div className="flex flex-col gap-6">
      {/* Health banner */}
      <div className="flex items-center justify-between rounded-lg border border-[var(--g-outline)] bg-black/20 px-4 py-3">
        <span className="text-xs text-[var(--g-text-muted)]">
          Serving stack health
          <span className="ml-2 font-mono text-[var(--g-text)]">{data.health.service}</span>
        </span>
        <HealthBadge available={data.health.available} status={data.health.status} />
      </div>

      {/* Model catalog */}
      <section>
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-[var(--g-text-muted)] mb-3">
          Model Catalog
        </h3>
        {!catalog.available || !catalog.models ? (
          <UnavailablePane label="Model catalog is currently unavailable." />
        ) : catalog.models.length === 0 ? (
          <p className="text-sm text-[var(--g-text-muted)]">No models registered.</p>
        ) : (
          <div className="rounded-lg border border-[var(--g-outline)] overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-[var(--g-outline)] bg-black/30">
                  <th className="text-left px-3 py-2 text-[10px] uppercase tracking-wider text-[var(--g-text-muted)] font-semibold">
                    Model
                  </th>
                  <th className="text-left px-3 py-2 text-[10px] uppercase tracking-wider text-[var(--g-text-muted)] font-semibold">
                    Tier
                  </th>
                  <th className="text-right px-3 py-2 text-[10px] uppercase tracking-wider text-[var(--g-text-muted)] font-semibold">
                    Token Cap
                  </th>
                  <th className="text-left px-3 py-2 text-[10px] uppercase tracking-wider text-[var(--g-text-muted)] font-semibold">
                    Task Types
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--g-outline)]">
                {catalog.models.map((entry) => (
                  <tr key={entry.model_id} className="hover:bg-black/20 transition-colors">
                    <td className="px-3 py-2">
                      <div className="font-mono text-[var(--g-text)]">{entry.model_id}</div>
                      <div className="text-[10px] text-[var(--g-text-muted)]">
                        {entry.display_name}
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <span className="px-1.5 py-0.5 rounded text-[9px] font-mono uppercase bg-[var(--g-info)]/10 border border-[var(--g-info)]/20 text-[var(--g-info)]">
                        {entry.tier}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-[var(--g-text-muted)]">
                      {entry.token_cap.toLocaleString()}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-1">
                        {entry.task_types.map((tt) => (
                          <span
                            key={tt}
                            className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-black/30 border border-[var(--g-outline)] text-[var(--g-text-muted)]"
                          >
                            {tt}
                          </span>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Session / usage backend modes */}
      <section>
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-[var(--g-text-muted)] mb-3">
          Session and Usage Backends
        </h3>
        <dl className="rounded-lg border border-[var(--g-outline)] bg-black/20 grid sm:grid-cols-2 divide-y sm:divide-y-0 sm:divide-x divide-[var(--g-outline)]">
          {[
            { label: 'Session Backend', value: data.session_backend },
            { label: 'Usage Backend', value: data.usage_backend },
          ].map(({ label, value }) => (
            <div key={label} className="px-4 py-3">
              <dt className="text-[10px] uppercase tracking-wider text-[var(--g-text-muted)]">
                {label}
              </dt>
              <dd className="mt-1 text-xs font-mono text-[var(--g-text)] truncate">{value}</dd>
            </div>
          ))}
        </dl>
      </section>

      {/* Agent Engine deploy config */}
      <section>
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-[var(--g-text-muted)] mb-3">
          Agent Engine Deploy Configuration
        </h3>
        {!deploy.available ? (
          <UnavailablePane label="Deploy configuration is currently unavailable." />
        ) : (
          <dl className="rounded-lg border border-[var(--g-outline)] bg-black/20 grid sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-[var(--g-outline)]">
            {[
              { label: 'Project', value: deploy.project ?? '—' },
              { label: 'Location', value: deploy.location ?? '—' },
              { label: 'Agent Name', value: deploy.display_name ?? '—' },
              { label: 'Staging Bucket', value: deploy.staging_bucket ?? '—' },
              { label: 'Description', value: deploy.description ?? '—' },
            ].map(({ label, value }) => (
              <div key={label} className="px-4 py-3">
                <dt className="text-[10px] uppercase tracking-wider text-[var(--g-text-muted)]">
                  {label}
                </dt>
                <dd className="mt-1 text-xs font-mono text-[var(--g-text)] truncate">{value}</dd>
              </div>
            ))}
          </dl>
        )}
      </section>
    </div>
  );
}
