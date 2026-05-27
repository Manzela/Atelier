# Antigravity Handoff Brief — R11 Sprint (2026-05-27)

**Competition deadline**: June 5, 2026 (internal target June 3 noon — 7 days)
**Branch**: `phase/2` — worktree at `.worktrees/phase2-consensus-agent/`
**Claude commit ref**: `1957525` (runner LLM judge wiring, just landed on `phase/2`)

---

## Context — what Claude shipped this session

- **Runner LLM judge wiring** (`1957525`): `AtelierRunner` now auto-creates
  `VertexAIJudgeClient` when `ATELIER_JUDGE_MODE=llm`. N3d `evaluate_candidate`
  passes the client through. 603/603 tests green. **Activation requires the env
  var task below (R11-AG-01).**

- **Dashboard audit** of your `2d707cf` commit: ran 4-subagent parallel sweep +
  own line-by-line re-audit. Confirmed 8 real findings (all MEDIUM/LOW; none
  exploitable in the current threat model). Remediation tasks R11-AG-02..R11-AG-08
  below. All files are yours — Claude did not touch them.

---

## P0 — Production activation (do first, no code change needed)

### R11-AG-01 — Activate LLM judges on Cloud Run

**Priority**: P0 — enables real Vertex AI judging for the competition demo
**Est**: 5 min

```bash
gcloud run services update atelier-api-staging \
  --region us-central1 \
  --project atelier-build-2026 \
  --update-env-vars ATELIER_JUDGE_MODE=llm,ATELIER_GCP_PROJECT=atelier-build-2026
```

**Verify**:

```bash
# Hit generate endpoint, then check bench dashboard judge_model column.
# Should show "Design Judge (Flash Vision) (gemini-2.5-flash-preview-05-20)"
# instead of "Design Judge (Flash Vision) (Phase 1 stub)"
curl -sf https://atelier-api-staging-537337457799.us-central1.run.app/health
```

Three valid modes:

- `llm` — all 5 axes use Vertex AI Gemini (competition mode)
- `hybrid` — LLM score wins, heuristic disagreement recorded (calibration mode)
- `heuristic` — Phase 1 deterministic only (default / fallback)

---

## P0 — Security (judge-visible surface)

### R11-AG-02 — Add Content Security Policy to auth dashboard

**File**: `docs/dashboards/auth/index.html`
**Issue**: No CSP meta tag on the page that loads external Firebase SDK + Google Fonts.
**Risk**: MEDIUM (defense-in-depth; no known exploit path).

Add immediately after the `<meta name="color-scheme">` tag (line 6):

```html
<meta
  http-equiv="Content-Security-Policy"
  content="default-src 'self'; script-src 'self' https://www.gstatic.com; connect-src 'self' https://*.googleapis.com https://*.firebaseio.com https://*.google.com; img-src 'self' data: https:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com;"
/>
```

Note: `'unsafe-inline'` for styles is required because all three dashboards use
`<style>` blocks. If you move CSS to external files a stricter policy is possible.

---

## P1 — Visual polish (judges see this immediately)

### R11-AG-03 — Fix Google Fonts font family (3 files)

**Files**: `docs/dashboards/auth/index.html:11`, `docs/dashboards/bench/index.html:11`,
`docs/dashboards/replay/index.html:11`
**Issue**: `family=Google+Sans` is a Google-internal proprietary font; Google Fonts
API returns empty CSS for it. Browsers fall back to Roboto (the next in the stack),
which is fine but wastes a font request.
**Risk**: LOW (UX/perf — silent fallback to Roboto).

Change all three `<link href="https://fonts.googleapis.com/css2?family=...">` lines:

```
# Before (in all 3 files)
family=Google+Sans:wght@400;500

# After
family=Google+Sans+Text:wght@400;500
```

The CSS font-family declaration in `:root` (`'Google Sans'`) should also change:

```css
/* Before */
--font-sans: 'Google Sans', 'Roboto', system-ui, sans-serif;
/* After */
--font-sans: 'Google Sans Text', 'Roboto', system-ui, sans-serif;
```

---

## P1 — Defense-in-depth escaping (replay dashboard)

### R11-AG-04 — Escape 4 numeric interpolations in replay summary grid

**File**: `docs/dashboards/replay/index.html`
**Issue**: Four interpolation sites render integer values from the server without
`escapeHTML()`. Exploitable only if BigQuery is compromised; escaping costs nothing.

Find `document.getElementById('summary-grid').innerHTML = \`` (around line 1024)
and apply these 4 changes within that template literal:

```js
// Line ~1051: iteration count
// Before:
${data.iteration}
// After:
${escapeHTML(String(data.iteration))}

// Line ~1055: candidate count
// Before:
${data.candidate_count}
// After:
${escapeHTML(String(data.candidate_count))}

// Line ~1063: token counts (two sites on same line)
// Before:
${data.total_input_tokens} / ${data.total_output_tokens}
// After:
${escapeHTML(String(data.total_input_tokens))} / ${escapeHTML(String(data.total_output_tokens))}
```

> `String()` coercion before `escapeHTML` is intentional — `escapeHTML(null)` is
> already handled by the `if (str == null) return ''` guard in the function.

---

## P2 — Cross-browser compatibility

### R11-AG-05 — Add `@media (prefers-color-scheme: dark)` fallback (2 files)

**Files**: `docs/dashboards/auth/index.html`, `docs/dashboards/replay/index.html`
**Issue**: Both files use `light-dark()` exclusively. Browsers < Chrome 123 (Mar 2024) /
Firefox 120 (Nov 2023) / Safari 17.5 (May 2024) don't support `light-dark()` and
render in light mode only regardless of system preference.
**Bench already has this fallback** (lines 105-127) — mirror it to auth and replay.

At the end of the `<style>` block in each file (just before `</style>`), add:

```css
@media (prefers-color-scheme: dark) {
  :root {
    --md-primary: var(--md-primary-dark);
    --md-primary-container: var(--md-primary-container-dark);
    --md-on-primary-container: var(--md-on-primary-container-dark);
    --md-bg: var(--md-bg-dark);
    --md-surface-container: var(--md-surface-container-dark);
    --md-surface-container-high: var(--md-surface-container-high-dark);
    --md-on-surface: var(--md-on-surface-dark);
    --md-on-surface-variant: var(--md-on-surface-variant-dark);
    --md-outline-variant: var(--md-outline-variant-dark);
    --md-outline: var(--md-outline-dark);
    --md-error: var(--md-error-dark);
  }
}
```

Modern browsers with `light-dark()` support ignore this block (the `light-dark()`
semantic tokens already override it via specificity). Older browsers use it as their
only dark-mode signal.

---

## P2 — Code quality

### R11-AG-06 — Whitelist badge CSS class in bench trajectory table

**File**: `docs/dashboards/bench/index.html:1282`
**Issue**: `class="badge ${escapeHTML(t.outcome)}"` — `escapeHTML` prevents attribute
breakout (`"` is escaped) but doesn't prevent CSS class pollution if `outcome`
contains a space. The blast radius is CSS confusion only.

```js
// Before (line ~1282):
<td>
  <span class="badge ${escapeHTML(t.outcome)}">
    ${BADGE_ICONS[t.outcome] || ''} ${escapeHTML(t.outcome)}
  </span>
</td>;

// After:
const outcomeCls = ['accepted', 'rejected', 'error'].includes(t.outcome) ? t.outcome : 'error';
<td>
  <span class="badge ${outcomeCls}">
    ${BADGE_ICONS[t.outcome] || ''} ${escapeHTML(t.outcome)}
  </span>
</td>;
```

The `const outcomeCls` declaration goes inside the `trajectories.slice(0, 50).map((t) =>` arrow function, before the template literal.

---

### R11-AG-07 — Refactor open-redirect validator to URL constructor

**File**: `docs/dashboards/auth/index.html:344-348`
**Issue**: Current `startsWith()` guard is correct against all tested bypasses but
brittle — future edge cases are hard to reason about. The URL constructor is
the canonical WHATWG-compliant approach.

```js
// Before (lines 344-348):
const rawRedirect = new URLSearchParams(window.location.search).get('redirect') || '../bench/';
const isSafe = rawRedirect.startsWith('../') || rawRedirect.startsWith('/');
const redirect = isSafe && !rawRedirect.startsWith('//') ? rawRedirect : '../bench/';
window.location.replace(redirect);

// After:
const rawRedirect = new URLSearchParams(window.location.search).get('redirect') || '../bench/';
let redirect = '../bench/';
try {
  const parsed = new URL(rawRedirect, window.location.origin);
  if (parsed.origin === window.location.origin) {
    redirect = parsed.pathname + parsed.search + parsed.hash;
  }
} catch {
  // Invalid URL — fall through to default '../bench/'
}
window.location.replace(redirect);
```

Note: `new URL(rawRedirect, window.location.origin)` rejects `javascript:` schemes
because they don't resolve to the base origin. `parsed.origin === window.location.origin`
blocks all external redirects regardless of bypass variant.

---

## P2 — Outstanding blocker

### R11-AG-08 — Create `atelier_trajectories.dpo_pairs` BigQuery table (FA-012)

**Status**: Still blocking T7 integration path (Claude's `GeneratorTuner.mine_pairs()`)
**File to add**: `infra/terraform/main.tf` or a migration script

The table schema required by `atelier-core/src/atelier/optimize/generator_tuner.py`:

```sql
CREATE TABLE IF NOT EXISTS `atelier-build-2026.atelier_trajectories.dpo_pairs` (
  pair_id       STRING NOT NULL,
  tenant_id     STRING NOT NULL,
  session_id    STRING,
  created_at    TIMESTAMP,
  prompt        STRING,
  chosen        STRING,
  rejected      STRING,
  chosen_score  FLOAT64,
  rejected_score FLOAT64,
  delta_score   FLOAT64
)
PARTITION BY DATE(created_at)
CLUSTER BY tenant_id;
```

Add as a `google_bigquery_table` resource in `main.tf` alongside the existing
`atelier_trajectories` dataset tables. Commit + `terraform apply` to provision.

---

## Not in this handoff (confirmed clean / deferred)

- `escapeHTML` implementation in bench + replay — **textbook-correct** (textContent
  DOM method, null-safe, escapes all 6 critical chars). Do not touch.
- `BADGE_ICONS` whitelist — correct defensive lookup with `|| ''` fallback. ✓
- Firebase SDK SRI — **not fixable** with ES module imports; browser limitation.
  Architectural, not a bug. Document as known limitation if raised in review.
- Open-redirect bypass vectors (backslash, mixed-case scheme, triple-slash,
  whitespace-prefix, URL-encoded backslash) — **all tested, none succeed** against
  the current 3-clause guard. R11-AG-07 is hardening, not a bug fix.
- Mobile touch targets (bench bottom nav) — `nav-item` is ≥56×~64px; passes
  WCAG 2.5.8 AA (24×24 minimum). False positive from original audit.
- Reduced-motion, landmark structure, aria-current, heading hierarchy,
  html lang, color contrast — all confirmed clean. ✓
- GitHub Dependabot PRs #21/#22 (Vite 5→6) — dev-only dep, deferred since D1.
  Address post-submission or merge if CI is green.

---

## Commit discipline reminder

Per CLAUDE.md: conventional commit per task, `--no-verify` never, push to `phase/2` only.

Suggested commit types for these tasks:

- R11-AG-01: `chore(deploy):` (env var, no code)
- R11-AG-02: `fix(security):` or `fix(dashboard):`
- R11-AG-03: `fix(dashboard):`
- R11-AG-04: `fix(dashboard):`
- R11-AG-05: `fix(dashboard):`
- R11-AG-06: `fix(dashboard):`
- R11-AG-07: `refactor(dashboard):`
- R11-AG-08: `feat(infra):`
