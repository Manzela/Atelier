/**
 * AT-090 Playwright acceptance suite — competitor-contrast beat.
 *
 * Hermetic: all tests intercept /v1/generate/stream with a local SSE fixture.
 * No live backend is needed.
 *
 * Non-vacuousness guarantees:
 *   - Test 1 WOULD FAIL if the beat section did not render on convergence.
 *   - Test 2 WOULD FAIL if the dismiss button did not hide the beat.
 *   - Test 3 WOULD FAIL if the README did not contain the anchor phrase.
 *
 * ADR-0020 / PRD §13.5 guardrail: the competitor beat is product COPY only.
 * No runtime Claude integration is present in the component or this test.
 */
import * as fs from 'fs';
import * as path from 'path';
import { test, expect } from './fixtures';

// ── Anchor phrase (must match README.md exactly) ──────────────────────────────
// The README competitor-contrast section documents "reject+halt" as the
// skeleton-gate behavior. This string is greppable and must be present.
const README_ANCHOR = 'reject+halt';

// ── SSE fixture: converged run ─────────────────────────────────────────────────
const KNOWN_HTML =
  '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"></head><body><h1>AT-090 fixture</h1></body></html>';

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

const SSE_BODY = [
  'event: plan',
  'data: {"surfaces":["home"]}',
  '',
  'event: complete',
  `data: ${JSON.stringify({
    best_html: KNOWN_HTML,
    converged: true,
    composite_score: 0.87,
    dorav: {
      brand: 0.9,
      originality: 0.85,
      relevance: 0.88,
      accessibility: 0.92,
      'visual-clarity': 0.86,
      composite: 0.87,
    },
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

  await page.goto('/studio/at090-test?brief=acceptance');
  await page.getByRole('button', { name: /^Run$/i }).click();

  // Wait for the converged iframe to confirm the complete event was processed
  await page.waitForSelector('iframe[title="Converged design output"]', { timeout: 15_000 });
}

// ── Test 1: beat is visible after convergence ─────────────────────────────────
test('AT-090: competitor-contrast beat is visible after convergence', async ({
  authenticatedPage: page,
}) => {
  await runWithFixture(page);

  // The beat must be present and visible
  const beat = page.getByTestId('competitor-contrast-beat');
  await expect(beat).toBeVisible({ timeout: 5_000 });

  // Non-vacuous: the beat must contain the honest-read phrase about Claude Design
  await expect(beat).toContainText('reject+halt');
});

// ── Test 2: dismiss hides the beat ────────────────────────────────────────────
test('AT-090: dismissing the beat hides it', async ({ authenticatedPage: page }) => {
  await runWithFixture(page);

  // Wait for the beat to appear
  const beat = page.getByTestId('competitor-contrast-beat');
  await expect(beat).toBeVisible({ timeout: 5_000 });

  // Click the dismiss button
  await page.getByTestId('competitor-contrast-dismiss').click();

  // The beat must now be hidden (AnimatePresence will remove it from the DOM)
  await expect(beat).toBeHidden({ timeout: 3_000 });
});

// ── Test 3: README contains the anchor phrase ─────────────────────────────────
test('AT-090: README.md contains the anchor phrase', () => {
  // Resolve the README path relative to this spec file's location:
  // e2e/ is inside atelier-dashboard/, README.md is two levels up.
  const readmePath = path.resolve(__dirname, '..', '..', 'README.md');
  const readme = fs.readFileSync(readmePath, 'utf8');
  expect(readme).toContain(README_ANCHOR);
});
