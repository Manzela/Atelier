/**
 * AT-096 Playwright acceptance suite — live token meter.
 *
 * Hermetic: all tests intercept /v1/generate/stream with a local SSE fixture.
 * No live backend required.
 *
 * The fixture emits multiple token_delta events with a CLIMBING cumulative so
 * that the meter visibly tracks the LATEST value (not a per-run sum of deltas).
 *
 * Non-vacuousness guarantee:
 *   - cumulative test WOULD FAIL if the meter showed a running sum instead of
 *     the latest cumulative_user_tokens (e.g. 100k+200k=300k ≠ 1_000_000).
 *   - thinking test WOULD FAIL if the thinking breakdown were not rendered.
 *   - soft-warning tests WOULD FAIL if the threshold logic were inverted.
 */
import { test, expect } from './fixtures';

// ── Shared helpers ────────────────────────────────────────────────────────────

const KNOWN_HTML =
  '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"></head><body><h1>AT-096 fixture</h1></body></html>';

function buildSseBody(
  tokenDeltas: Array<{
    input: number;
    output: number;
    thinking: number;
    cumulative_user_tokens: number;
  }>
): string {
  const lines: string[] = ['event: plan', 'data: {"surfaces":["home"]}', ''];

  for (const delta of tokenDeltas) {
    lines.push('event: token_delta');
    lines.push(`data: ${JSON.stringify(delta)}`);
    lines.push('');
  }

  lines.push(
    'event: complete',
    `data: ${JSON.stringify({ best_html: KNOWN_HTML, converged: true, composite_score: 0.8 })}`,
    '',
    ''
  );

  return lines.join('\n');
}

async function runWithFixture(
  page: import('@playwright/test').Page,
  sseBody: string
): Promise<void> {
  await page.route('**/v1/generate/stream', (route) =>
    route.fulfill({
      status: 200,
      headers: { 'content-type': 'text/event-stream' },
      body: sseBody,
    })
  );

  await page.goto('/studio/at096-test?brief=acceptance');
  await page.getByRole('button', { name: /^Run$/i }).click();
}

// ── Test 1: cumulative tracks the LATEST token_delta value ────────────────────
// Two token_delta events. The final cumulative (1_200_000) deliberately differs
// from EVERY wrong answer a regression would produce, so the assertion is fully
// non-vacuous:
//   - sum of per-event deltas    = 100k + 300k        = 400k    (≠ 1.2M)
//   - sum of per-event cumulatives = 900k + 1.2M       = 2.1M    (≠ 1.2M)
//   - first/stale value           = 900k              (≠ 1.2M)
//   - reset-to-zero               = 0                 (≠ 1.2M)
// Only "show the LATEST cumulative_user_tokens" yields 1_200_000.
test('AT-096: data-cumulative reflects the latest cumulative_user_tokens', async ({
  authenticatedPage: page,
}) => {
  const SSE = buildSseBody([
    { input: 60_000, output: 30_000, thinking: 10_000, cumulative_user_tokens: 900_000 },
    { input: 200_000, output: 80_000, thinking: 20_000, cumulative_user_tokens: 1_200_000 },
  ]);

  await runWithFixture(page, SSE);

  // Wait for the meter to show the FINAL cumulative (1_200_000), not a partial sum.
  await expect
    .poll(async () => page.locator('[data-testid="token-meter"]').getAttribute('data-cumulative'), {
      timeout: 8000,
      intervals: [100, 200, 400],
    })
    .toBe('1200000');
});

// ── Test 2: thinking tokens are shown distinctly ──────────────────────────────
test('AT-096: thinking tokens shown distinctly in token-meter-thinking', async ({
  authenticatedPage: page,
}) => {
  const THINKING_VAL = 42_000;
  const SSE = buildSseBody([
    { input: 200_000, output: 50_000, thinking: THINKING_VAL, cumulative_user_tokens: 500_000 },
  ]);

  await runWithFixture(page, SSE);

  // Wait for the meter to appear with data
  await expect
    .poll(async () => page.locator('[data-testid="token-meter"]').getAttribute('data-cumulative'), {
      timeout: 8000,
      intervals: [100, 200, 400],
    })
    .toBe('500000');

  // Thinking breakdown must show the latest delta's thinking value
  const thinkingText = await page.locator('[data-testid="token-meter-thinking"]').innerText();
  // The component formats with toLocaleString; strip non-digits and compare
  const digits = thinkingText.replace(/\D/g, '');
  expect(Number(digits)).toBe(THINKING_VAL);
});

// ── Test 3: soft-warning appears at >=90% and is dismissible ──────────────────
test('AT-096: soft-warning appears at >=90% cumulative and dismisses correctly', async ({
  authenticatedPage: page,
}) => {
  // 4_600_000 / 5_000_000 = 92% → above the 90% threshold
  const SSE = buildSseBody([
    { input: 4_000_000, output: 500_000, thinking: 100_000, cumulative_user_tokens: 4_600_000 },
  ]);

  await runWithFixture(page, SSE);

  // Wait for the meter to reflect the high-cumulative value
  await expect
    .poll(async () => page.locator('[data-testid="token-meter"]').getAttribute('data-cumulative'), {
      timeout: 8000,
      intervals: [100, 200, 400],
    })
    .toBe('4600000');

  // Soft warning must be visible
  const warning = page.locator('[data-testid="token-soft-warning"]');
  await expect(warning).toBeVisible({ timeout: 3000 });

  // Dismiss it
  await warning.getByRole('button', { name: /dismiss/i }).click();

  // Warning must be gone
  await expect(warning).not.toBeVisible();

  // STAYS dismissed across a NEW run (acceptance 4: "rendered exactly once" — the
  // dismissal flag must NOT be reset in startGeneration). Re-run with a DIFFERENT
  // still->=90% cumulative (4_800_000) so the second run provably executed, and
  // assert the warning does NOT reappear.
  await page.unroute('**/v1/generate/stream');
  const SSE2 = buildSseBody([
    { input: 4_200_000, output: 500_000, thinking: 100_000, cumulative_user_tokens: 4_800_000 },
  ]);
  await page.route('**/v1/generate/stream', (route) =>
    route.fulfill({
      status: 200,
      headers: { 'content-type': 'text/event-stream' },
      body: SSE2,
    })
  );
  await page.getByRole('button', { name: /^Run$/i }).click();
  await expect
    .poll(async () => page.locator('[data-testid="token-meter"]').getAttribute('data-cumulative'), {
      timeout: 8000,
      intervals: [100, 200, 400],
    })
    .toBe('4800000');
  // Still >=90%, but dismissed-once persists across the run → no reappearance.
  await expect(page.locator('[data-testid="token-soft-warning"]')).not.toBeVisible();
});

// ── Test 4: soft-warning does NOT appear when cumulative < 90% ────────────────
test('AT-096: no soft-warning when cumulative is well under 90%', async ({
  authenticatedPage: page,
}) => {
  // 2_000_000 / 5_000_000 = 40% — well under threshold
  const SSE = buildSseBody([
    { input: 1_800_000, output: 150_000, thinking: 50_000, cumulative_user_tokens: 2_000_000 },
  ]);

  await runWithFixture(page, SSE);

  // Wait for the meter to reflect the value
  await expect
    .poll(async () => page.locator('[data-testid="token-meter"]').getAttribute('data-cumulative'), {
      timeout: 8000,
      intervals: [100, 200, 400],
    })
    .toBe('2000000');

  // Soft warning must NOT be present
  await expect(page.locator('[data-testid="token-soft-warning"]')).not.toBeVisible();
});
