/**
 * AT-052 Playwright acceptance suite — Studio iframe token round-trip.
 *
 * Proves that the Studio iframe renders a token color injected via the
 * `complete` SSE event's `best_html`.  The fixture serves HTML that sets
 * `background-color: #facade` on an element with `data-testid="token-swatch"`,
 * then we read `getComputedStyle(el).backgroundColor` inside the iframe and
 * assert it equals `rgb(250, 202, 222)` — the browser's RGB expansion of #facade.
 *
 * This test is intentionally non-vacuous: the assertion depends on the iframe
 * actually rendering the color from `srcDoc`, not on any mock.  If `best_html`
 * is not forwarded to `srcDoc` the computed color will not match.
 *
 * Hermetic: intercepts /v1/generate/stream with a local SSE fixture.
 * No live backend is needed.
 */
import { test, expect } from './fixtures';

// ---------------------------------------------------------------------------
// Sentinel color (mirrors the code-surface sentinel in verify-token-roundtrip.mjs)
// #facade = 0xFA 0xCA 0xDE  →  rgb(250, 202, 222)
// ---------------------------------------------------------------------------

const SENTINEL_HEX = '#facade';
const SENTINEL_RGB = 'rgb(250, 202, 222)';

// ---------------------------------------------------------------------------
// Fixture HTML: a minimal document that applies the sentinel as a swatch.
// The element carries data-testid="token-swatch" so the Playwright selector
// is stable and independent of layout changes.
// ---------------------------------------------------------------------------

const SWATCH_HTML = `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><style>*{margin:0;box-sizing:border-box}body{background:#fff}</style></head><body><div data-testid="token-swatch" style="background-color:${SENTINEL_HEX};width:100px;height:100px;"></div></body></html>`;

// ---------------------------------------------------------------------------
// Nielsen entries (required field in CompleteData)
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// SSE fixture: a `complete` event whose best_html is the swatch document.
// ---------------------------------------------------------------------------

const SSE_BODY = [
  'event: plan',
  'data: {"surfaces":["home"]}',
  '',
  'event: complete',
  `data: ${JSON.stringify({
    best_html: SWATCH_HTML,
    converged: true,
    composite_score: 0.9,
    dorav: {
      brand: 0.9,
      originality: 0.9,
      relevance: 0.9,
      accessibility: 0.9,
      'visual-clarity': 0.9,
      composite: 0.9,
    },
    nielsen: NIELSEN_ENTRIES,
  })}`,
  '',
  '',
].join('\n');

// ---------------------------------------------------------------------------
// Helper: intercept the SSE endpoint, navigate to Studio, trigger a run,
// and wait for the converged iframe to be present and painted.
// Mirrors the runWithFixture() pattern from at040-canvas.spec.ts.
// ---------------------------------------------------------------------------

async function runWithSwatchFixture(page: import('@playwright/test').Page): Promise<void> {
  await page.route('**/v1/generate/stream', (route) =>
    route.fulfill({
      status: 200,
      headers: { 'content-type': 'text/event-stream' },
      body: SSE_BODY,
    })
  );

  await page.goto('/studio/at052-test?brief=token-roundtrip');

  await page.getByRole('button', { name: /^Run$/i }).click();

  // Wait for the converged iframe to appear.
  await page.waitForSelector('iframe[title="Converged design output"]', { timeout: 15_000 });

  // Wait for the swatch element inside the iframe — confirms srcDoc has painted.
  await page
    .frameLocator('iframe[title="Converged design output"]')
    .locator('[data-testid="token-swatch"]')
    .waitFor({ state: 'visible', timeout: 10_000 });
}

// ---------------------------------------------------------------------------
// Test: computed background-color of the swatch element equals SENTINEL_RGB.
// ---------------------------------------------------------------------------

test('Studio iframe renders token sentinel color via srcDoc', async ({
  authenticatedPage: page,
}) => {
  await runWithSwatchFixture(page);

  const computedColor = await page
    .frameLocator('iframe[title="Converged design output"]')
    .locator('[data-testid="token-swatch"]')
    .evaluate((el) => window.getComputedStyle(el).backgroundColor);

  expect(computedColor).toBe(SENTINEL_RGB);
});
