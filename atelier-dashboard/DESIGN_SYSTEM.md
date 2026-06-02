# Atelier Dashboard — Design System

The dashboard is a Google-native, Material-3 dark surface modelled 1:1 on Google Labs Stitch
(PRD AT-040, section 25). This document is the single source of truth for its visual language;
all UI must reference these tokens rather than ad-hoc Tailwind colour utilities.

## Foundations

Tokens are CSS custom properties declared in `src/app/globals.css` (`:root`). Reference them as
`var(--token)` or the Tailwind arbitrary form `text-[var(--token)]`.

### Colour

| Token                    | Value     | Role                                                                   |
| ------------------------ | --------- | ---------------------------------------------------------------------- |
| `--g-bg`                 | `#0f1013` | App background (with the dot-grid `.stitch-grid-bg`)                   |
| `--g-surface`            | `#1e1f22` | Cards, panels, navbars                                                 |
| `--g-surface-hover`      | `#2d2f31` | Hover/raised surface                                                   |
| `--g-outline`            | `#2c2d30` | Borders, dividers, hairlines                                           |
| `--g-primary-blue`       | `#1a73e8` | Primary action (Run), primary fills, slider track                      |
| `--g-primary-blue-hover` | `#1765cc` | Primary action hover                                                   |
| `--g-info`               | `#8ab4f8` | Accent for informational/agent surfaces (labels, active chips, badges) |
| `--g-text`               | `#e3e3e3` | Body text                                                              |
| `--g-text-muted`         | `#9aa0a6` | Secondary text, captions                                               |
| `--g-success`            | `#81c995` | Success / passing scores                                               |
| `--g-warning`            | `#fdd663` | Warning / soft cap / failing axis                                      |
| `--g-error`              | `#f28b82` | Error / cap-reached                                                    |

**Accent decision (resolved 2026-06-02).** The product uses exactly two blues: `--g-primary-blue`
for primary _actions_ and primary fills, and `--g-info` (the lighter Google blue) for _accent_
treatments on the agentic-legibility surfaces (panel headers, active states, badges, slider
accents). Tailwind `indigo-*` utilities are **off-system and prohibited** — they introduced a
second, non-Google accent that competed with the Google-blue primary. Anything that previously
used `indigo-*` maps to `--g-info` (text/borders/accents) or `--g-primary-blue` (fills).

### Typography

- Display / headings: `Google Sans` (weights 400/500/700). Applied to `h1`-`h6` (weight 500).
- Body / UI: `Google Sans Text` (400/500/700).
- Monospace (token paths, numerals, code): the platform mono stack (`ui-monospace`).
- Scale (Tailwind): hero `text-5xl`/`text-6xl`; section labels `text-[11px] uppercase tracking-wider`;
  body `text-xs`/`text-sm`; dense metadata `text-[10px]`.

### Shape, spacing, motion

- Radius: `8px` (`.g-card`, panels, controls). Pills use `rounded-full`.
- Border: `1px solid var(--g-outline)` on all raised surfaces.
- Spacing rhythm: `4 / 8 / 16 / 24 / 40` (Tailwind `1/2/4/6/10`).
- Background: `.stitch-grid-bg` (24px radial dot grid) on full-bleed canvases.
- Motion: framer-motion springs (`bounce: 0`, `duration` 0.35-0.4) for reveals; no gratuitous
  animation. Respect the existing `AnimatedScoreValue` spring for numeric transitions.

## Components

- `.g-card` — `--g-surface` fill, `--g-outline` border, `8px` radius; hover -> `--g-surface-hover`.
- Section label — `text-[11px] uppercase tracking-wider font-semibold text-[var(--g-text-muted)]`.
- Primary button — `--g-primary-blue` fill, white text, `--g-primary-blue-hover` on hover.
- Slider — native `range` with `accent-color: var(--g-primary-blue)` (set globally on `body`).
- Badge / chip — `--g-info` text on a 12-20% `--g-info` tint, `--g-info` border at ~30%.

## Information architecture (Studio right rail)

The rail is the **agentic-legibility surface** (PRD section 14). Order, top to bottom:

1. **Design System** (AT-044) — the agent-generated, design-specific controls + the token table.
2. **D-O-R-A-V Scorecard** (AT-093) — converging quality, per-axis.
3. **Token Usage** (AT-096) — the lifetime cap meter.
4. **Nielsen Heuristics** — presence checklist.
5. **Model settings** (Vertex inference knobs) — demoted; advanced/secondary, not the hero.
6. **Why Atelier** (AT-090 competitor beat) — on convergence, dismissible.

Rationale: the legibility/steering surfaces lead; raw inference knobs (temperature/top-K) are
advanced controls a design user rarely needs and must not out-rank the agent's glass-box.

## Invariants (do not break)

- All `data-testid` contracts are load-bearing for the Playwright e2e suite.
- The converged iframe `srcDoc` is byte-exact until a design-system edit (AT-040); a token edit
  re-flows surfaces via the live `:root` injection (AT-044).
- The legibility UI is axe-clean (AT-043): every control labelled, contrast >= WCAG AA.
- Model identifier is the AT-024 pin; never a hard-coded stale label.
