/**
 * AT-043 Playwright acceptance suite — designed Studio states.
 *
 * Hermetic: each test drives the shell into a specific state via SSE route
 * intercept. No screenshots. Runs on macOS + Linux without a reference PNG.
 *
 * For each of the 5 states (empty, loading, degraded, error, cap-reached):
 *   1. Assert the data-testid element is visible in the canvas region.
 *   2. Run axe-core scoped to the canvas region — assert 0 critical/serious violations.
 */
import { test, expect } from './fixtures';
import AxeBuilder from '@axe-core/playwright';

// ── Shared fixture data ───────────────────────────────────────────────────────
const BEST_HTML =
  '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><style>body{margin:0;font-family:Arial,sans-serif;background:#f8fafc;color:#1e293b}.hero{padding:40px 32px}.h1{font-size:28px;font-weight:700}</style></head><body><section class="hero"><div class="h1">Atelier</div></section></body></html>';

const DORAV = {
  brand: 0.9,
  originality: 0.85,
  relevance: 0.88,
  accessibility: 0.92,
  'visual-clarity': 0.86,
  composite: 0.87,
};

const NIELSEN_ENTRIES = [
  { heuristic: 'visibility_of_system_status', present: true, votes: 2 },
  { heuristic: 'match_between_system_and_real_world', present: false, votes: 0 },
];

// ── Helper: build SSE body from lines ────────────────────────────────────────
function sseBody(lines: string[]): string {
  return lines.join('\n') + '\n\n';
}

// ── Canvas region selector (the m.div wrapping all state components) ─────────
const CANVAS_SELECTOR = '[data-testid="studio-canvas"]';

// ── Accessibility helper ──────────────────────────────────────────────────────
async function assertAxe(page: import('@playwright/test').Page): Promise<void> {
  const results = await new AxeBuilder({ page }).include(CANVAS_SELECTOR).analyze();

  const violations = results.violations.filter(
    (v) => v.impact === 'critical' || v.impact === 'serious'
  );

  expect(
    violations,
    `axe-core found ${violations.length} critical/serious violation(s): ${violations
      .map((v) => `[${v.impact}] ${v.id}: ${v.description}`)
      .join('; ')}`
  ).toHaveLength(0);
}

// ─────────────────────────────────────────────────────────────────────────────
// Test 1: empty state (navigate, do NOT click Run)
// ─────────────────────────────────────────────────────────────────────────────
test('AT-043 empty: state-empty component visible + axe 0 critical/serious', async ({
  authenticatedPage: page,
}) => {
  // No route intercept needed — just navigate without triggering generation
  await page.goto('/studio/at043-empty?brief=acceptance');

  const emptyEl = page.locator('[data-testid="state-empty"]');
  await expect(emptyEl).toBeVisible({ timeout: 10_000 });

  await assertAxe(page);
});

// ─────────────────────────────────────────────────────────────────────────────
// Test 2: loading state (intercept a stream that emits plan but never completes)
// ─────────────────────────────────────────────────────────────────────────────
test('AT-043 loading: state-loading component visible + axe 0 critical/serious', async ({
  authenticatedPage: page,
}) => {
  // Stream emits a plan event then hangs (never sends complete)
  const hangingBody = sseBody([
    'event: plan',
    'data: {"surfaces":["home"]}',
    '',
    // No complete event — stream is intentionally left pending
  ]);

  await page.route('**/v1/generate/stream', (route) =>
    route.fulfill({
      status: 200,
      headers: { 'content-type': 'text/event-stream' },
      body: hangingBody,
    })
  );

  await page.goto('/studio/at043-loading?brief=acceptance');
  await page.getByRole('button', { name: /^Run$/i }).click();

  const loadingEl = page.locator('[data-testid="state-loading"]');
  await expect(loadingEl).toBeVisible({ timeout: 10_000 });

  await assertAxe(page);
});

// ─────────────────────────────────────────────────────────────────────────────
// Test 3: degraded state (complete event with degraded:true)
// ─────────────────────────────────────────────────────────────────────────────
test('AT-043 degraded: state-degraded component visible + axe 0 critical/serious', async ({
  authenticatedPage: page,
}) => {
  const degradedBody = sseBody([
    'event: plan',
    'data: {"surfaces":["home"]}',
    '',
    'event: complete',
    `data: ${JSON.stringify({
      best_html: BEST_HTML,
      converged: false,
      composite_score: 0.42,
      degraded: true,
      degradation_reason: 'Consensus gate passed only 1/3 iterations within the budget.',
      dorav: DORAV,
      nielsen: NIELSEN_ENTRIES,
    })}`,
    '',
  ]);

  await page.route('**/v1/generate/stream', (route) =>
    route.fulfill({
      status: 200,
      headers: { 'content-type': 'text/event-stream' },
      body: degradedBody,
    })
  );

  await page.goto('/studio/at043-degraded?brief=acceptance');
  await page.getByRole('button', { name: /^Run$/i }).click();

  const degradedEl = page.locator('[data-testid="state-degraded"]');
  await expect(degradedEl).toBeVisible({ timeout: 15_000 });

  await assertAxe(page);
});

// ─────────────────────────────────────────────────────────────────────────────
// Test 4: error state (SSE error event)
// ─────────────────────────────────────────────────────────────────────────────
test('AT-043 error: state-error component visible + axe 0 critical/serious', async ({
  authenticatedPage: page,
}) => {
  const errorBody = sseBody([
    'event: plan',
    'data: {"surfaces":["home"]}',
    '',
    'event: error',
    'data: {"detail":"Vertex AI quota exceeded — no fallback available."}',
    '',
  ]);

  await page.route('**/v1/generate/stream', (route) =>
    route.fulfill({
      status: 200,
      headers: { 'content-type': 'text/event-stream' },
      body: errorBody,
    })
  );

  await page.goto('/studio/at043-error?brief=acceptance');
  await page.getByRole('button', { name: /^Run$/i }).click();

  const errorEl = page.locator('[data-testid="state-error"]');
  await expect(errorEl).toBeVisible({ timeout: 15_000 });

  await assertAxe(page);
});

// ─────────────────────────────────────────────────────────────────────────────
// Test 5: cap-reached state (cap_reached SSE event)
// ─────────────────────────────────────────────────────────────────────────────
test('AT-043 cap-reached: state-cap-reached component visible + axe 0 critical/serious', async ({
  authenticatedPage: page,
}) => {
  const capBody = sseBody([
    'event: plan',
    'data: {"surfaces":["home"]}',
    '',
    'event: cap_reached',
    'data: {"detail":"Per-user 5 M-token cap reached. Resets at 00:00 UTC."}',
    '',
  ]);

  await page.route('**/v1/generate/stream', (route) =>
    route.fulfill({
      status: 200,
      headers: { 'content-type': 'text/event-stream' },
      body: capBody,
    })
  );

  await page.goto('/studio/at043-cap?brief=acceptance');
  await page.getByRole('button', { name: /^Run$/i }).click();

  const capEl = page.locator('[data-testid="state-cap-reached"]');
  await expect(capEl).toBeVisible({ timeout: 15_000 });

  await assertAxe(page);
});

// ═════════════════════════════════════════════════════════════════════════════
// AT-094 — Acknowledged-degradation surfacing (R9) in the UI.
// Three clauses: forced-degradation acknowledgement, offline skeleton+banner,
// cap-hit SPEC-EXACT stop string (PRD §13.2 — governor.py TOKEN_CAP_MESSAGE).
// ═════════════════════════════════════════════════════════════════════════════

// The one branded cap stop string, byte-identical to the backend constant
// `atelier-core/src/atelier/orchestrator/governor.py::TOKEN_CAP_MESSAGE`
// (PRD §13.2). The UI must render it VERBATIM, not a paraphrase. The live API
// emits it as the `cap_reached` event `detail`; the local fallback must match.
const TOKEN_CAP_MESSAGE =
  "You've reached this account's usage limit. Contact administrator to continue.";

// ─────────────────────────────────────────────────────────────────────────────
// Test 6 (AT-094): offline state — state-offline skeleton+banner is shown when
// the browser goes offline (navigator.onLine === false) + axe 0 critical/serious
// ─────────────────────────────────────────────────────────────────────────────
test('AT-094 offline: state-offline component visible + axe 0 critical/serious', async ({
  authenticatedPage: page,
  context,
}) => {
  // Load the page while online (going offline first blocks the navigation
  // itself with ERR_INTERNET_DISCONNECTED), then drive the real browser offline.
  await page.goto('/studio/at094-offline?brief=acceptance');
  await expect(page.locator('[data-testid="state-empty"]')).toBeVisible({ timeout: 10_000 });

  // Flips navigator.onLine to false and fires the `offline` window event the
  // shell's useOnlineStatus hook listens for (not a hard-coded UI toggle).
  await context.setOffline(true);

  const offlineEl = page.locator('[data-testid="state-offline"]');
  await expect(offlineEl).toBeVisible({ timeout: 10_000 });

  // The acknowledgement must carry a non-empty, human-readable banner label
  // (agent always acknowledges degradation — no silent blank).
  await expect(offlineEl).toContainText(/connection/i);

  await assertAxe(page);

  // Recovering connection clears the offline acknowledgement back to the
  // generatable empty state (the `online` event re-renders).
  await context.setOffline(false);
  await expect(offlineEl).toBeHidden({ timeout: 10_000 });
  await expect(page.locator('[data-testid="state-empty"]')).toBeVisible({ timeout: 10_000 });
});

// ─────────────────────────────────────────────────────────────────────────────
// Test 7 (AT-094): cap-hit shows the SPEC-EXACT stop string verbatim.
// ─────────────────────────────────────────────────────────────────────────────
test('AT-094 cap-exact-string: cap-reached renders the PRD §13.2 stop string verbatim', async ({
  authenticatedPage: page,
}) => {
  // The live backend emits TOKEN_CAP_MESSAGE as the cap_reached `detail`.
  const capBody = sseBody([
    'event: plan',
    'data: {"surfaces":["home"]}',
    '',
    'event: cap_reached',
    `data: ${JSON.stringify({ detail: TOKEN_CAP_MESSAGE })}`,
    '',
  ]);

  await page.route('**/v1/generate/stream', (route) =>
    route.fulfill({
      status: 200,
      headers: { 'content-type': 'text/event-stream' },
      body: capBody,
    })
  );

  await page.goto('/studio/at094-cap?brief=acceptance');
  await page.getByRole('button', { name: /^Run$/i }).click();

  const capEl = page.locator('[data-testid="state-cap-reached"]');
  await expect(capEl).toBeVisible({ timeout: 15_000 });
  // Verbatim, not a paraphrase: the exact branded stop string must be present.
  await expect(capEl).toContainText(TOKEN_CAP_MESSAGE);
});

// ─────────────────────────────────────────────────────────────────────────────
// Test 8 (AT-094): cap-hit fallback (no server detail) STILL renders the
// SPEC-EXACT stop string — the UI must not drift to a paraphrase locally.
// ─────────────────────────────────────────────────────────────────────────────
test('AT-094 cap-exact-string fallback: empty-detail cap still shows the §13.2 stop string', async ({
  authenticatedPage: page,
}) => {
  // cap_reached with NO detail — exercises the client-side fallback message.
  const capBody = sseBody([
    'event: plan',
    'data: {"surfaces":["home"]}',
    '',
    'event: cap_reached',
    'data: {}',
    '',
  ]);

  await page.route('**/v1/generate/stream', (route) =>
    route.fulfill({
      status: 200,
      headers: { 'content-type': 'text/event-stream' },
      body: capBody,
    })
  );

  await page.goto('/studio/at094-cap-fallback?brief=acceptance');
  await page.getByRole('button', { name: /^Run$/i }).click();

  const capEl = page.locator('[data-testid="state-cap-reached"]');
  await expect(capEl).toBeVisible({ timeout: 15_000 });
  await expect(capEl).toContainText(TOKEN_CAP_MESSAGE);
});

// ─────────────────────────────────────────────────────────────────────────────
// Test 9 (AT-094): forced degradation surfaces an on-screen acknowledgement.
// (Re-asserts the R9 acknowledgement contract from the AT-094 acceptance bar —
// the degraded banner carries a visible, non-silent "degraded" acknowledgement.)
// ─────────────────────────────────────────────────────────────────────────────
test('AT-094 forced-degradation: state-degraded surfaces an on-screen acknowledgement', async ({
  authenticatedPage: page,
}) => {
  const degradedBody = sseBody([
    'event: plan',
    'data: {"surfaces":["home"]}',
    '',
    'event: complete',
    `data: ${JSON.stringify({
      best_html: BEST_HTML,
      converged: false,
      composite_score: 0.41,
      degraded: true,
      degradation_reason: 'Consensus gate passed only 1/3 iterations within the budget.',
      dorav: DORAV,
      nielsen: NIELSEN_ENTRIES,
    })}`,
    '',
  ]);

  await page.route('**/v1/generate/stream', (route) =>
    route.fulfill({
      status: 200,
      headers: { 'content-type': 'text/event-stream' },
      body: degradedBody,
    })
  );

  await page.goto('/studio/at094-degraded?brief=acceptance');
  await page.getByRole('button', { name: /^Run$/i }).click();

  const degradedEl = page.locator('[data-testid="state-degraded"]');
  await expect(degradedEl).toBeVisible({ timeout: 15_000 });
  // The acknowledgement is explicit and announced (role=status), never silent.
  await expect(degradedEl.getByRole('status')).toContainText(/degraded/i);
  await expect(degradedEl).toContainText(
    'Consensus gate passed only 1/3 iterations within the budget.'
  );
});
