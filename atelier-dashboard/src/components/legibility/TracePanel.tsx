'use client';

/**
 * AT-026 — TracePanel (Mid legibility).
 *
 * The live agentic trace surfaced during generation: one row per DDLC specialist
 * as it hands off, one row per WRAI research query with its citation, and a
 * D-O-R-A-V axis legend whose every axis carries a REAL tooltip explanation. This
 * is the "show your work" half of the accountability layer (PRD §3.5) — the user
 * watches the multi-specialist DAG progress in real time (< 1s per event) and can
 * see WHAT each step contributed and WHY each judge axis scored as it did.
 *
 * Pure presentational component: it renders the trace arrays the shell accumulates
 * from the `specialist_trace` / `research_query` SSE events. No data fetching, no
 * side effects. Design system: dark Studio chrome (`--g-*`), lucide-react icons,
 * plain Tailwind — no new dependencies. Accessible: a labelled region, a real
 * <dl> for the trace, citations are real links, and each D-O-R-A-V axis term is a
 * <button> whose tooltip is wired via aria-describedby so it is reachable by
 * keyboard and screen readers (not a hover-only title).
 */
import React, { useState } from 'react';
import { Workflow, Search, ExternalLink, Info } from 'lucide-react';
import type { SpecialistTraceData, ResearchQueryData } from '@/lib/api';
import { DORAV_AXIS_META } from './dorav';

export interface TracePanelProps {
  /** AT-026: one entry per DDLC specialist hand-off, in arrival order. */
  specialistTraces: SpecialistTraceData[];
  /** AT-026: one entry per WRAI research query, in arrival order. */
  researchQueries: ResearchQueryData[];
}

/** Pretty role label: ux_research -> "UX Research". */
function roleLabel(role: string): string {
  return role
    .replace(/_/g, ' ')
    .replace(/\bui\b/i, 'UI')
    .replace(/\bia\b/i, 'IA')
    .replace(/\bux\b/i, 'UX')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** One D-O-R-A-V axis legend item with a keyboard-reachable tooltip. */
function AxisLegendItem({
  axisKey,
  label,
  explanation,
}: {
  axisKey: string;
  label: string;
  explanation: string;
}) {
  const [open, setOpen] = useState(false);
  const tipId = `dorav-tip-${axisKey}`;
  return (
    <li className="relative">
      <button
        type="button"
        data-testid={`dorav-tooltip-trigger-${axisKey}`}
        aria-describedby={open ? tipId : undefined}
        aria-expanded={open}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1 rounded border border-[var(--g-outline)] bg-black/30 px-1.5 py-0.5 text-[10px] text-[var(--g-text)] hover:border-[var(--g-info)]/50 focus:outline-none focus:ring-1 focus:ring-[var(--g-primary-blue)]"
      >
        {label}
        <Info size={10} aria-hidden="true" className="text-[var(--g-info)]" />
      </button>
      {open && (
        <span
          id={tipId}
          role="tooltip"
          data-testid={`dorav-tooltip-${axisKey}`}
          className="absolute left-0 top-full z-50 mt-1 w-56 rounded border border-[var(--g-outline)] bg-[var(--g-surface)] px-2.5 py-2 text-[11px] leading-relaxed text-[var(--g-text)] shadow-xl"
        >
          {explanation}
        </span>
      )}
    </li>
  );
}

export default function TracePanel({ specialistTraces, researchQueries }: TracePanelProps) {
  return (
    <section
      data-testid="trace-panel"
      aria-labelledby="trace-panel-heading"
      className="text-[11px]"
    >
      <div className="h-px bg-[var(--g-outline)] my-4" />
      <h4
        id="trace-panel-heading"
        className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider font-semibold text-[var(--g-text-muted)] mb-3"
      >
        <Workflow size={12} className="text-[var(--g-info)]" aria-hidden="true" />
        Agent Trace
        <span
          data-testid="trace-panel-count"
          className="ml-auto px-1.5 py-0.5 rounded text-[9px] bg-[var(--g-info)]/20 text-[var(--g-info)] font-mono border border-[var(--g-info)]/30"
        >
          {specialistTraces.length} steps
        </span>
      </h4>

      {/* Research queries — the grounded provenance of what Atelier looked up. */}
      {researchQueries.length > 0 && (
        <div data-testid="trace-research" className="mb-3">
          <h5 className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-[var(--g-text-muted)] mb-1.5">
            <Search size={11} className="text-[var(--g-info)]" aria-hidden="true" />
            Research
          </h5>
          <ul className="space-y-1">
            {researchQueries.map((q, i) => (
              <li
                key={`${q.query}-${i}`}
                data-testid="trace-research-row"
                className="rounded bg-black/20 border border-[var(--g-outline)] px-2 py-1.5"
              >
                <p className="text-[var(--g-text)] truncate" title={q.query}>
                  {q.query}
                </p>
                {q.top_citation ? (
                  <a
                    href={q.top_citation}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-0.5 inline-flex items-center gap-1 text-[10px] text-[var(--g-info)] hover:underline"
                  >
                    <ExternalLink size={10} aria-hidden="true" className="shrink-0" />
                    <span className="truncate">{q.top_title || q.top_citation}</span>
                  </a>
                ) : (
                  <span className="text-[10px] text-[var(--g-text-muted)] italic">
                    no surfaced result
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Specialist hand-offs — one row per DDLC role as it completes. */}
      {specialistTraces.length > 0 ? (
        <dl data-testid="trace-specialists" className="space-y-1">
          {specialistTraces.map((t, i) => (
            <div
              key={`${t.role}-${t.iteration}-${i}`}
              data-testid={`trace-specialist-row-${t.role}`}
              className="rounded bg-black/20 border border-[var(--g-outline)] px-2 py-1.5"
            >
              <dt className="flex items-center justify-between gap-2">
                <span className="text-[10px] font-semibold text-[var(--g-success)]">
                  {roleLabel(t.role)}
                </span>
                <span className="text-[9px] font-mono text-[var(--g-text-muted)]">
                  iter {t.iteration + 1}
                </span>
              </dt>
              <dd className="mt-0.5 text-[10px] text-[var(--g-text-muted)] whitespace-pre-wrap">
                {t.summary}
              </dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="text-[10px] text-[var(--g-text-muted)] italic">No specialist activity yet.</p>
      )}

      {/* D-O-R-A-V axis legend — every axis explained on hover/focus (legibility). */}
      <div data-testid="trace-dorav-legend" className="mt-3">
        <h5 className="text-[10px] uppercase tracking-wider text-[var(--g-text-muted)] mb-1.5">
          D-O-R-A-V axes
        </h5>
        <ul className="flex flex-wrap gap-1.5">
          {DORAV_AXIS_META.map((axis) => (
            <AxisLegendItem
              key={axis.key}
              axisKey={axis.key}
              label={axis.label}
              explanation={axis.explanation}
            />
          ))}
        </ul>
      </div>
    </section>
  );
}
