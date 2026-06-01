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
