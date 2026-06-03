'use client';

/**
 * AT-042 — ApprovalCard (tokens + scope, push-free).
 *
 * The human-in-the-loop sign-off surface. After the planner locks the plan and
 * scope (N0/N1/N2) the run halts on the AT-031 sign-off gate; this card surfaces
 * the locked plan for review and approval BEFORE any screen generation burns a
 * token. It shows: number of screens, estimated tokens, WCAG target, specialist
 * count, AND the editable plan pre-filled with the AT-030 cited `proposed_defaults`
 * — each carrying its citation so the user can verify and EDIT a value before
 * approving (steerability + legibility, PRD §3.5).
 *
 * Approve persists the (possibly edited) plan + `signoff_status: APPROVED` to the
 * run doc via `submitApproval`; a cold clone subscribed to that doc via
 * `onSnapshot` resumes the run with no push (no FCM). See approval-listener.ts.
 *
 * Design system: dark Studio chrome (`--g-*` tokens), lucide-react icons, plain
 * Tailwind — no new dependencies. Accessible: a labelled dialog, one heading per
 * region, every editable field has an associated <label>, citations are real
 * links, and the primary action is a real <button>.
 */
import React, { useCallback, useMemo, useState } from 'react';
import {
  CheckCircle2,
  ShieldCheck,
  Coins,
  Layers,
  Users,
  ExternalLink,
  Pencil,
  HelpCircle,
  AlertTriangle,
} from 'lucide-react';
import type { PlanData, ProposedDefault } from '@/lib/api';

export interface ApprovalCardProps {
  /** The locked pre-sign-off plan to review. */
  plan: PlanData;
  /** Called with the (possibly edited) plan when the user approves. */
  onApprove: (editedPlan: PlanData) => void;
  /** Optional reject/back affordance. */
  onReject?: () => void;
  /** True while the approval write is in flight (disables the buttons). */
  isSubmitting?: boolean;
}

/** A single editable, cited default row. */
function DefaultRow({
  def,
  value,
  onChange,
}: {
  def: ProposedDefault;
  value: string;
  onChange: (next: string) => void;
}) {
  const inputId = `approval-default-input-${def.standard_id}`;
  const trustPct = Math.round((def.trust_score ?? 0) * 100);
  return (
    <li
      data-testid={`approval-default-row-${def.standard_id}`}
      className="rounded-md border border-[var(--g-outline)] bg-[var(--g-bg)]/60 p-3"
    >
      <div className="flex items-start justify-between gap-2 mb-1.5">
        <label htmlFor={inputId} className="text-[12px] font-medium text-[var(--g-text)]">
          {def.name}
        </label>
        <span className="shrink-0 inline-flex items-center gap-1 rounded-full border border-[var(--g-outline)] px-1.5 py-0.5 text-[10px] font-mono text-[var(--g-text-muted)]">
          trust {trustPct}%
        </span>
      </div>
      <div className="flex items-center gap-1.5 text-[11px] text-[var(--g-info)] mb-2">
        <Pencil size={11} aria-hidden="true" className="shrink-0" />
        <span className="text-[var(--g-text-muted)]">
          Editable default &mdash; adjust before approving
        </span>
      </div>
      <input
        id={inputId}
        data-testid={`approval-default-input-${def.standard_id}`}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded border border-[var(--g-outline)] bg-[var(--g-surface)] px-2.5 py-1.5 text-[12px] text-[var(--g-text)] outline-none focus:border-[var(--g-primary-blue)] focus:ring-1 focus:ring-[var(--g-primary-blue)]"
      />
      <a
        data-testid={`approval-default-cite-${def.standard_id}`}
        href={def.citation_url}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-2 inline-flex items-center gap-1 text-[11px] text-[var(--g-info)] hover:underline"
      >
        <ExternalLink size={11} aria-hidden="true" className="shrink-0" />
        <span className="truncate">Source: {def.name}</span>
      </a>
    </li>
  );
}

/** A summary stat tile (screens / tokens / WCAG / specialists). */
function StatTile({
  testid,
  icon,
  label,
  value,
}: {
  testid: string;
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div
      data-testid={testid}
      className="flex flex-col gap-1 rounded-md border border-[var(--g-outline)] bg-[var(--g-bg)]/60 p-3"
    >
      <div className="flex items-center gap-1.5 text-[var(--g-text-muted)]">
        <span aria-hidden="true" className="text-[var(--g-info)]">
          {icon}
        </span>
        <span className="text-[10px] uppercase tracking-wider">{label}</span>
      </div>
      <span className="text-[18px] font-semibold text-[var(--g-text)] tabular-nums">{value}</span>
    </div>
  );
}

export default function ApprovalCard({
  plan,
  onApprove,
  onReject,
  isSubmitting = false,
}: ApprovalCardProps) {
  const defaults = useMemo(() => plan.proposed_defaults ?? [], [plan.proposed_defaults]);
  const openQuestions = plan.open_questions ?? [];
  const gaps = plan.gaps ?? [];
  const screenCount = plan.surfaces?.length ?? 0;
  const specialistCount = plan.specialist_count ?? 6; // 6-role DDLC specialist pipeline
  const wcagTarget = plan.wcag_target ?? 'AA';

  // Steerability: each cited default's recommended value (its `rule`) is editable.
  // The edits layer over the plan so Approve carries what the user actually
  // confirmed, not the original draft.
  const [edits, setEdits] = useState<Record<string, string>>(() =>
    Object.fromEntries(defaults.map((d) => [d.standard_id, d.rule]))
  );

  const handleEdit = useCallback((standardId: string, next: string) => {
    setEdits((prev) => ({ ...prev, [standardId]: next }));
  }, []);

  const tokensLabel = plan.est_tokens != null ? plan.est_tokens.toLocaleString('en-US') : '—';

  const handleApprove = useCallback(() => {
    // Fold the edits back into the proposed_defaults so the approved plan is the
    // plan of record (durable steerability).
    const editedPlan: PlanData = {
      ...plan,
      proposed_defaults: defaults.map((d) => ({
        ...d,
        rule: edits[d.standard_id] ?? d.rule,
      })),
    };
    onApprove(editedPlan);
  }, [plan, defaults, edits, onApprove]);

  return (
    <div
      data-testid="approval-card"
      role="dialog"
      aria-modal="false"
      aria-labelledby="approval-card-title"
      className="w-full h-full overflow-y-auto bg-[var(--g-surface)] text-[var(--g-text)] px-6 py-5"
    >
      <div className="mx-auto max-w-[560px]">
        {/* Header */}
        <div className="flex items-start gap-3 mb-1">
          <ShieldCheck
            size={22}
            className="mt-0.5 shrink-0 text-[var(--g-info)]"
            aria-hidden="true"
          />
          <div>
            <h2 id="approval-card-title" className="text-[16px] font-semibold leading-tight">
              Review and approve the plan
            </h2>
            <p className="mt-1 text-[12px] text-[var(--g-text-muted)]">
              Atelier locked the plan and scope and is paused for your sign-off. Generation will not
              start until you approve. Edit any cited default first &mdash; what you approve is the
              plan of record.
            </p>
          </div>
        </div>

        {/* Summary stats */}
        <div className="mt-4 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
          <StatTile
            testid="approval-screens"
            icon={<Layers size={14} />}
            label="Screens"
            value={screenCount}
          />
          <StatTile
            testid="approval-tokens"
            icon={<Coins size={14} />}
            label="Est. tokens"
            value={tokensLabel}
          />
          <StatTile
            testid="approval-wcag"
            icon={<ShieldCheck size={14} />}
            label="WCAG target"
            value={wcagTarget}
          />
          <StatTile
            testid="approval-specialists"
            icon={<Users size={14} />}
            label="Specialists"
            value={specialistCount}
          />
        </div>

        {/* Surfaces list — the concrete screens to be generated */}
        {screenCount > 0 && (
          <p className="mt-3 text-[12px] text-[var(--g-text-muted)]">
            <span className="text-[var(--g-text)]">Surfaces:</span> {plan.surfaces.join(', ')}
          </p>
        )}

        {/* Editable cited defaults */}
        {defaults.length > 0 && (
          <section className="mt-5" aria-labelledby="approval-defaults-heading">
            <h3
              id="approval-defaults-heading"
              className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-[var(--g-text-muted)]"
            >
              Proposed defaults (cited &mdash; editable)
            </h3>
            <ul className="space-y-2.5">
              {defaults.map((d) => (
                <DefaultRow
                  key={d.standard_id}
                  def={d}
                  value={edits[d.standard_id] ?? d.rule}
                  onChange={(next) => handleEdit(d.standard_id, next)}
                />
              ))}
            </ul>
          </section>
        )}

        {/* Open questions — surfaced, not silently defaulted */}
        {openQuestions.length > 0 && (
          <section className="mt-5" aria-labelledby="approval-questions-heading">
            <h3
              id="approval-questions-heading"
              className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--g-text-muted)]"
            >
              <HelpCircle size={12} aria-hidden="true" className="text-[var(--g-info)]" />
              Open questions
            </h3>
            <ul className="space-y-1.5 text-[12px] text-[var(--g-text-muted)]">
              {openQuestions.map((q, i) => (
                <li key={i} className="flex gap-2">
                  <span aria-hidden="true" className="text-[var(--g-info)]">
                    &bull;
                  </span>
                  <span>{q}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Acknowledged gaps — the agent always acknowledges degradation */}
        {gaps.length > 0 && (
          <div
            role="status"
            className="mt-5 flex items-start gap-2 rounded-md border border-[var(--g-warning)]/40 bg-[var(--g-warning)]/10 px-3 py-2.5"
          >
            <AlertTriangle
              size={14}
              aria-hidden="true"
              className="mt-0.5 shrink-0 text-[var(--g-warning)]"
            />
            <div className="text-[11px] text-[var(--g-text-muted)]">
              <span className="font-semibold text-[var(--g-text)]">Acknowledged gaps:</span>
              <ul className="mt-1 space-y-1">
                {gaps.map((g, i) => (
                  <li key={i}>{g}</li>
                ))}
              </ul>
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="mt-6 flex items-center justify-end gap-2.5 border-t border-[var(--g-outline)] pt-4">
          {onReject && (
            <button
              type="button"
              data-testid="approval-reject"
              onClick={onReject}
              disabled={isSubmitting}
              className="rounded-md border border-[var(--g-outline)] px-3.5 py-2 text-[13px] font-medium text-[var(--g-text-muted)] transition-colors hover:bg-[var(--g-surface-hover)] hover:text-[var(--g-text)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              Back
            </button>
          )}
          <button
            type="button"
            data-testid="approval-approve"
            onClick={handleApprove}
            disabled={isSubmitting}
            className="inline-flex items-center gap-1.5 rounded-md bg-[var(--g-primary-blue)] px-4 py-2 text-[13px] font-semibold text-white transition-colors hover:bg-[var(--g-primary-blue-hover)] disabled:cursor-not-allowed disabled:opacity-60"
          >
            <CheckCircle2 size={15} aria-hidden="true" />
            {isSubmitting ? 'Approving…' : 'Approve & generate'}
          </button>
        </div>
      </div>
    </div>
  );
}
