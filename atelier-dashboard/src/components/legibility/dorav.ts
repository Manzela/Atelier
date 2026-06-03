/**
 * AT-026 — D-O-R-A-V axis legibility metadata.
 *
 * The five judge axes the N3d consensus panel scores each candidate on (mirrors
 * `atelier-core` `JudgeAxis`). Every axis carries a REAL one-sentence explanation
 * of what it measures, surfaced as a tooltip on the scorecard so the score is
 * legible — the user understands WHY a candidate scored the way it did, not just a
 * bare number (PRD §3.5 legibility). The order matches the Studio scorecard
 * (`DORAV_AXES` in StudioClientShell) so the tooltip maps row-for-row.
 */
export interface DoravAxisMeta {
  /** Wire key (matches the `dorav` SSE payload + the scorecard row). */
  key: 'brand' | 'originality' | 'relevance' | 'accessibility' | 'visual-clarity';
  /** Human label shown on the row. */
  label: string;
  /** A real explanation of what this axis measures (the tooltip body). */
  explanation: string;
}

export const DORAV_AXIS_META: readonly DoravAxisMeta[] = [
  {
    key: 'brand',
    label: 'Brand',
    explanation:
      'How faithfully the design honors the signed-off brand: the design-token palette, type, and constitution. The zero-tolerance token gate enforces it — an off-system color literal fails this axis.',
  },
  {
    key: 'originality',
    label: 'Originality',
    explanation:
      'Whether the design is a distinctive, considered composition rather than a generic template. Penalizes boilerplate layouts and rewards intentional, brief-specific structure.',
  },
  {
    key: 'relevance',
    label: 'Relevance',
    explanation:
      'How well the design satisfies the brief and the UX research: the right surfaces, the right content hierarchy, and the jobs-to-be-done the brief named — not a plausible but off-target screen.',
  },
  {
    key: 'accessibility',
    label: 'Accessibility',
    explanation:
      'WCAG 2.2 AA conformance — landmarks, accessible names, heading order, and 4.5:1 contrast. Backed by the deterministic axe-core gate: a single critical/serious violation rejects the screen.',
  },
  {
    key: 'visual-clarity',
    label: 'Visual Clarity',
    explanation:
      'Whether the layout reads cleanly: legible hierarchy, balanced spacing and density, and unambiguous primary actions — the design communicates at a glance.',
  },
] as const;
