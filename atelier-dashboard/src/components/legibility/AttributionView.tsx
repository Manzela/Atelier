'use client';

/**
 * AT-026 — AttributionView (Post legibility / accountability).
 *
 * The run-completion oracle's verdict rendered as a criterion -> verdict + evidence
 * panel: every ACCEPTANCE.json condition the run was held to, whether it PASSED or
 * FAILED, the concrete evidence (the deterministic oracle's diagnostic), and the
 * provenance source (a user criterion vs. a cited domain standard the user accepted
 * at sign-off). This is the "prove your work" half of the accountability layer
 * (PRD §7A.4 / §14) — the design is not "done because the agent said so"; it is
 * complete iff every machine-checkable criterion holds, and the user can see each
 * one. The oracle recomputes from artifacts (it never trusts the agent-written
 * converged/composite), so a green panel is an independent attestation.
 *
 * Pure presentational: renders the `run_verdict` from the `complete` SSE event.
 * `null` verdict -> an honest "unavailable" state (the oracle could not run on a
 * degraded path), never a fabricated pass. Design system: dark Studio chrome,
 * lucide-react icons, plain Tailwind. Accessible: a labelled region, a real list,
 * and PASS/FAIL conveyed by icon + text (never color alone).
 */
import React from 'react';
import { CheckCircle2, XCircle, ClipboardCheck, AlertCircle } from 'lucide-react';
import type { RunVerdict, CriterionVerdict } from '@/lib/api';

export interface AttributionViewProps {
  /** AT-026: the run-oracle verdict from the `complete` event, or null if unavailable. */
  runVerdict: RunVerdict | null | undefined;
  /** Called when the user amends — re-enters the loop (Post: "amend re-enters the loop"). */
  onAmend?: () => void;
}

/** Short, readable label for a criterion source: "standard:wcag-x" -> "Standard". */
function sourceLabel(source: string): string {
  if (source.startsWith('standard:')) return 'Standard';
  return 'Required';
}

function CriterionRow({ c }: { c: CriterionVerdict }) {
  return (
    <li
      data-testid={`attribution-criterion-${c.criterion_id}`}
      data-verdict={c.verdict ? 'pass' : 'fail'}
      className={`rounded border px-2.5 py-2 ${
        c.verdict ? 'border-emerald-500/40 bg-emerald-950/20' : 'border-red-500/50 bg-red-950/25'
      }`}
    >
      <div className="flex items-start gap-2">
        {c.verdict ? (
          <CheckCircle2 size={14} className="mt-0.5 shrink-0 text-emerald-400" aria-hidden="true" />
        ) : (
          <XCircle size={14} className="mt-0.5 shrink-0 text-red-400" aria-hidden="true" />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-medium text-gray-200 truncate" title={c.criterion_id}>
              {c.target}
            </span>
            <span
              className={`shrink-0 text-[9px] font-mono uppercase tracking-wider ${
                c.verdict ? 'text-emerald-400' : 'text-red-400'
              }`}
            >
              {c.verdict ? 'pass' : 'fail'}
            </span>
          </div>
          <p className="mt-0.5 text-[10px] text-gray-400 break-words">{c.evidence_ref}</p>
          <span className="mt-1 inline-block rounded-full border border-[var(--g-outline)] px-1.5 py-0.5 text-[9px] font-mono text-gray-500">
            {sourceLabel(c.source)}
            {c.source.startsWith('standard:') ? `: ${c.source.slice('standard:'.length)}` : ''}
          </span>
        </div>
      </div>
    </li>
  );
}

export default function AttributionView({ runVerdict, onAmend }: AttributionViewProps) {
  return (
    <section
      data-testid="attribution-view"
      aria-labelledby="attribution-heading"
      className="text-[11px]"
    >
      <div className="h-px bg-[var(--g-outline)] my-4" />
      <h4
        id="attribution-heading"
        className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider font-semibold text-gray-500 mb-3"
      >
        <ClipboardCheck size={12} className="text-[var(--g-info)]" aria-hidden="true" />
        Acceptance Verdict
        {runVerdict && (
          <span
            data-testid="attribution-status"
            data-complete={runVerdict.complete ? 'true' : 'false'}
            className={`ml-auto px-1.5 py-0.5 rounded text-[9px] font-mono border ${
              runVerdict.complete
                ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                : 'bg-amber-500/20 text-amber-400 border-amber-500/30'
            }`}
          >
            {runVerdict.complete ? 'COMPLETE' : 'INCOMPLETE'}
          </span>
        )}
      </h4>

      {!runVerdict ? (
        <div
          data-testid="attribution-unavailable"
          role="status"
          className="flex items-start gap-2 rounded border border-[var(--g-outline)] bg-black/20 px-2.5 py-2 text-gray-400"
        >
          <AlertCircle size={14} className="mt-0.5 shrink-0 text-gray-500" aria-hidden="true" />
          <span className="text-[10px]">
            Acceptance verdict unavailable for this run — the run-oracle could not evaluate the
            surfaces.
          </span>
        </div>
      ) : (
        <>
          <ul data-testid="attribution-criteria" className="space-y-1.5">
            {runVerdict.criteria.map((c) => (
              <CriterionRow key={c.criterion_id} c={c} />
            ))}
          </ul>
          {onAmend && (
            <button
              type="button"
              data-testid="attribution-amend"
              onClick={onAmend}
              className="mt-3 w-full rounded-md border border-[var(--g-outline)] px-3 py-2 text-[12px] font-medium text-[var(--g-text-muted)] transition-colors hover:bg-[var(--g-surface-hover)] hover:text-[var(--g-text)]"
            >
              Amend &amp; regenerate
            </button>
          )}
        </>
      )}
    </section>
  );
}
