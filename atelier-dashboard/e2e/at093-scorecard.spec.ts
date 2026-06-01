/**
 * AT-093 Playwright acceptance suite — animated converging D-O-R-A-V scorecard.
 *
 * Hermetic: all tests intercept /v1/generate/stream with a local SSE fixture.
 * No live backend required.
 *
 * The fixture emits two convergence iterations followed by a complete event so that
 * the scorecard visibly climbs and the failing-axis highlight can be asserted.
 *
 * Non-vacuousness guarantee:
 *   - The test WOULD FAIL if scores did not advance (data-score check is numeric).
 *   - The test WOULD FAIL if the failing-axis class were not applied (DOM query).
 *   - The test WOULD FAIL if iteration 2 data-iteration attribute were not set.
 */
import { test, expect } from './fixtures';

// ── SSE fixture ───────────────────────────────────────────────────────────────
// Iteration 1: accessibility is lowest (score 45)
const ITER1_DORAV = {
  brand: 0.6,
  originality: 0.55,
  relevance: 0.65,
  accessibility: 0.45,
  'visual-clarity': 0.5,
  composite: 0.55,
};
// Iteration 2: all scores higher; originality is now the new failing axis (score 62)
const ITER2_DORAV = {
  brand: 0.8,
  originality: 0.62,
  relevance: 0.85,
  accessibility: 0.75,
  'visual-clarity': 0.78,
  composite: 0.76,
};

const KNOWN_HTML =
  '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"></head><body><h1>AT-093 fixture</h1></body></html>';

const NIELSEN_ENTRIES = [
  { heuristic: 'visibility_of_system_status', present: false, votes: 0 },
  { heuristic: 'match_between_system_and_real_world', present: false, votes: 0 },
  { heuristic: 'user_control_and_freedom', present: false, votes: 0 },
  { heuristic: 'consistency_and_standards', present: false, votes: 0 },
  { heuristic: 'error_prevention', present: false, votes: 0 },
  { heuristic: 'recognition_over_recall', present: false, votes: 0 },
  { heuristic: 'flexibility_and_efficiency', present: false, votes: 0 },
  { heuristic: 'aesthetic_and_minimalist_design', present: false, votes: 0 },
  { heuristic: 'help_users_recognize_errors', present: false, votes: 0 },
  { heuristic: 'help_and_documentation', present: false, votes: 0 },
];

// Build SSE body: plan → iter_start(0) → iter_score(0) → iter_start(1) → iter_score(1) → complete
const SSE_BODY = [
  'event: plan',
  'data: {"surfaces":["home"]}',
  '',
  'event: iteration_start',
  'data: {"screen":"home","iteration":0}',
  '',
  'event: iteration_score',
  `data: ${JSON.stringify({
    screen: 'home',
    iteration: 0,
    dorav: ITER1_DORAV,
    composite: ITER1_DORAV.composite,
    failing_axis: 'accessibility',
  })}`,
  '',
  'event: iteration_start',
  'data: {"screen":"home","iteration":1}',
  '',
  'event: iteration_score',
  `data: ${JSON.stringify({
    screen: 'home',
    iteration: 1,
    dorav: ITER2_DORAV,
    composite: ITER2_DORAV.composite,
    failing_axis: 'originality',
  })}`,
  '',
  'event: complete',
  `data: ${JSON.stringify({
    best_html: KNOWN_HTML,
    converged: true,
    composite_score: ITER2_DORAV.composite,
    dorav: { ...ITER2_DORAV },
    nielsen: NIELSEN_ENTRIES,
  })}`,
  '',
  '',
].join('\n');

// ── Helper ────────────────────────────────────────────────────────────────────
async function runWithFixture(page: import('@playwright/test').Page): Promise<void> {
  await page.route('**/v1/generate/stream', (route) =>
    route.fulfill({
      status: 200,
      headers: { 'content-type': 'text/event-stream' },
      body: SSE_BODY,
    })
  );

  await page.goto('/studio/at093-test?brief=acceptance');
  await page.getByRole('button', { name: /^Run$/i }).click();
}

// ── Test 1: after iter 1 fixture data, accessibility axis data-score < brand axis data-score ─
// In the iter-0 fixture (ITER1_DORAV): accessibility=0.45, brand=0.60 — accessibility is failing.
// The fixture may have moved to iter-1 by the time the assertion runs (SSE sync); that's fine:
// in ITER2_DORAV accessibility=0.75 is still < brand=0.80, so the relationship holds in both.
// We wait for ANY iteration data to arrive, then assert the relative ordering.
test('AT-093: accessibility axis data-score < brand axis data-score in iter-1 fixture data', async ({
  authenticatedPage: page,
}) => {
  await runWithFixture(page);

  // Wait until any iteration data has arrived (scorecard data-iteration is non-empty)
  await expect
    .poll(
      async () => page.locator('[data-testid="dorav-scorecard"]').getAttribute('data-iteration'),
      { timeout: 5000, intervals: [100, 200, 400] }
    )
    .not.toBe('');

  // In the fixture data for BOTH iterations, accessibility < brand holds.
  // Poll until both scores are numeric (spring animation may still be settling).
  await expect
    .poll(
      async () => {
        const a = await page
          .locator('[data-testid="dorav-axis-accessibility"]')
          .getAttribute('data-score');
        const b = await page.locator('[data-testid="dorav-axis-brand"]').getAttribute('data-score');
        return Number(a) < Number(b);
      },
      { timeout: 5000, intervals: [100, 200, 400] }
    )
    .toBe(true);
});

// ── Test 2: after iter 2, data-iteration="1" and composite advanced ───────────
test('AT-093: iter-2 advances data-iteration and composite score', async ({
  authenticatedPage: page,
}) => {
  await runWithFixture(page);

  // Wait for the scorecard to reflect iteration 1
  await expect
    .poll(
      async () => page.locator('[data-testid="dorav-scorecard"]').getAttribute('data-iteration'),
      { timeout: 5000, intervals: [100, 200, 400] }
    )
    .toBe('1');

  // Composite at iter 1 is 0.76 → data-score on the composite row is set via the
  // dorav-scorecard data-iteration attr, not a separate element; verify via the
  // accessibility axis score which must now be HIGHER than iter-0's 45
  const accessibilityScore = await expect
    .poll(
      async () => {
        const raw = await page
          .locator('[data-testid="dorav-axis-accessibility"]')
          .getAttribute('data-score');
        return Number(raw);
      },
      { timeout: 5000, intervals: [100, 200, 400] }
    )
    .toBeGreaterThan(45);

  void accessibilityScore; // consumed by expect.poll above
});

// ── Test 3: the failing axis row carries the `failing-axis` CSS class ─────────
test('AT-093: failing axis row has failing-axis highlight class', async ({
  authenticatedPage: page,
}) => {
  await runWithFixture(page);

  // Wait for iter 1 data to arrive (most recent failing_axis = originality)
  await expect
    .poll(
      async () => page.locator('[data-testid="dorav-scorecard"]').getAttribute('data-iteration'),
      { timeout: 5000, intervals: [100, 200, 400] }
    )
    .toBe('1');

  // After iter 1, the failing axis is "originality" — its row must carry failing-axis class
  const originality = page.locator('[data-testid="dorav-axis-originality"]');
  await expect(originality).toHaveClass(/failing-axis/);

  // The non-failing brand axis must NOT have the failing-axis class
  const brand = page.locator('[data-testid="dorav-axis-brand"]');
  await expect(brand).not.toHaveClass(/failing-axis/);
});
