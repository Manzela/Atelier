/**
 * AT-040 Playwright acceptance suite — canvas + device-frame toggle.
 *
 * Hermetic: all tests intercept /v1/generate/stream with a local SSE fixture.
 * No live backend is needed. The deterministic KNOWN_HTML constant is the
 * byte-equality oracle; its hash also seeds the screenshot regression test.
 */
import { test, expect } from './fixtures';

// ── Deterministic acceptance fixture (byte-equality oracle) ──────────────────
const KNOWN_HTML =
  '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><style>*{margin:0;box-sizing:border-box}body{font-family:Arial,Helvetica,sans-serif;background:#0f172a;color:#f8fafc}.hero{padding:48px 32px;background:#1e293b}.h1{font-size:32px;font-weight:700;color:#38bdf8}.p{font-size:16px;margin-top:12px;color:#cbd5e1}.cta{margin-top:24px;display:inline-block;padding:12px 24px;background:#38bdf8;color:#0f172a;border-radius:8px;font-weight:600}</style></head><body><section class="hero"><div class="h1">Atelier Studio</div><div class="p">Deterministic acceptance fixture for AT-040.</div><div class="cta">Get started</div></section></body></html>';

// ── SSE fixture ───────────────────────────────────────────────────────────────
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

// Helper: intercept the SSE endpoint and trigger a generation run, then wait
// for the iframe to appear.
async function runWithFixture(page: import('@playwright/test').Page): Promise<void> {
  await page.route('**/v1/generate/stream', (route) =>
    route.fulfill({
      status: 200,
      headers: { 'content-type': 'text/event-stream' },
      body: SSE_BODY,
    })
  );

  await page.goto('/studio/at040-test?brief=acceptance');

  // Click the Run button (aria-label not set → match visible text)
  await page.getByRole('button', { name: /^Run$/i }).click();

  // Wait until the converged iframe appears AND its srcdoc content has painted.
  // Playwright's screenshot stability detection does not see into the sandboxed
  // (opaque-origin) iframe, so we must explicitly wait for its content — otherwise
  // a screenshot can capture an unpainted frame and flake across runs.
  await page.waitForSelector('iframe[title="Converged design output"]', { timeout: 15_000 });
  await page
    .frameLocator('iframe[title="Converged design output"]')
    .locator('.hero')
    .waitFor({ state: 'visible', timeout: 10_000 });
}

// ── Test 1: srcDoc byte-equality ─────────────────────────────────────────────
test('srcDoc byte-equals KNOWN_HTML', async ({ authenticatedPage: page }) => {
  await runWithFixture(page);

  const srcdoc = await page
    .locator('iframe[title="Converged design output"]')
    .getAttribute('srcdoc');
  expect(srcdoc).toBe(KNOWN_HTML);
});

// ── Test 2: device toggle exact px ───────────────────────────────────────────
test('device toggle sets offsetWidth exactly', async ({ authenticatedPage: page }) => {
  // Use a wide viewport so device-1280 is not clipped by the browser window
  await page.setViewportSize({ width: 1600, height: 900 });
  await runWithFixture(page);

  const canvas = page.locator('[data-testid="studio-canvas"]');

  for (const width of [390, 768, 1280] as const) {
    await page.click(`[data-testid="device-${width}"]`);
    // Poll until offsetWidth stabilises to the expected value (framer-motion settle)
    await expect
      .poll(async () => canvas.evaluate((el) => (el as HTMLElement).offsetWidth), {
        timeout: 3000,
        intervals: [100, 200, 400],
      })
      .toBe(width);
  }
});

// ── Test 3: offline lane — iframe body has a visible background ───────────────
test('offline: rendered iframe body has non-transparent background', async ({
  authenticatedPage: page,
}) => {
  await runWithFixture(page);

  // Go offline after the fixture content is already loaded
  await page.context().setOffline(true);

  // Use frameLocator to get a locator inside the iframe's document
  const frame = page.frameLocator('iframe[title="Converged design output"]');

  const bg = await frame.locator('body').evaluate((body) => {
    return window.getComputedStyle(body).backgroundColor;
  });

  // Must not be transparent / empty
  expect(bg).not.toBe('rgba(0, 0, 0, 0)');
  expect(bg).not.toBe('transparent');
  expect(bg.length).toBeGreaterThan(0);

  // Restore online for subsequent tests
  await page.context().setOffline(false);
});

// ── Test 4: iframe screenshot regression (Linux reference generated in CI) ────
// Screenshots the IFRAME (the converged design — deterministic static HTML), not
// the framer-motion canvas wrapper (whose scale-spring/shadow flake). The reference
// PNG is generated on Linux in CI and committed at
// e2e/at040-canvas.spec.ts-snapshots/converged-iframe-chromium-linux.png.
// EXPECTED TO FAIL locally with "missing snapshot" (Linux-only reference).
test('iframe matches screenshot reference (Linux CI reference)', async ({
  authenticatedPage: page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await runWithFixture(page);

  await expect(page.locator('iframe[title="Converged design output"]')).toHaveScreenshot(
    'converged-iframe.png',
    { animations: 'disabled', maxDiffPixelRatio: 0.02 }
  );
});
