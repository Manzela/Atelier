/**
 * AT-027 Playwright acceptance suite — Optimize asset surfacing (read-only).
 *
 * Hermetic: intercepts /v1/generate/stream with a local SSE fixture that emits
 * the two AT-027 read-only event types — `route_decision` (the MoE routing
 * decision) and `dreaming_artifact` (a dreaming/DPO preference pair) — and
 * asserts the Studio renders both via OptimizeArtifactCard. No live backend.
 *
 * Non-vacuousness guarantee:
 *   - the route-decision test WOULD FAIL if the expert / routing_mode were not
 *     rendered (it asserts the exact fixture values appear).
 *   - the DPO test WOULD FAIL if the chosen/rejected/margin were not rendered.
 *   - the read-only test WOULD FAIL if any control mutating routing/training
 *     state were present (it asserts the read-only badge and the absence of an
 *     edit/apply affordance inside the card).
 */
import { test, expect } from './fixtures';

const KNOWN_HTML =
  '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"></head><body><h1>AT-027 fixture</h1></body></html>';

const ROUTE_DECISION = {
  expert: 'gemini-3-pro',
  phase: 'judge_candidates',
  score: 0.74,
  rationale: 'exploit:greedy ε=0.020 pulls=12 μ=0.740',
  fallback_chain: ['gemini-3-flash', 'gemini-2.5-pro'],
  routing_mode: 'v1_bandit',
};

const DREAMING_ARTIFACT = {
  surface_id: 'surface-abc',
  node_name: 'N3a.generator',
  chosen_score: 0.91,
  rejected_score: 0.62,
  margin: 0.29,
};

function buildSseBody(): string {
  return [
    'event: plan',
    'data: {"surfaces":["home"]}',
    '',
    'event: route_decision',
    `data: ${JSON.stringify(ROUTE_DECISION)}`,
    '',
    'event: dreaming_artifact',
    `data: ${JSON.stringify(DREAMING_ARTIFACT)}`,
    '',
    'event: complete',
    `data: ${JSON.stringify({ best_html: KNOWN_HTML, converged: true, composite_score: 0.8 })}`,
    '',
    '',
  ].join('\n');
}

async function runWithFixture(page: import('@playwright/test').Page): Promise<void> {
  await page.route('**/v1/generate/stream', (route) =>
    route.fulfill({
      status: 200,
      headers: { 'content-type': 'text/event-stream' },
      body: buildSseBody(),
    })
  );
  await page.goto('/studio/at027-test?brief=acceptance');
  await page.getByRole('button', { name: /^Run$/i }).click();
}

test('AT-027: the MoE routing decision renders read-only in the trace', async ({
  authenticatedPage: page,
}) => {
  await runWithFixture(page);

  const card = page.locator('[data-testid="optimize-artifact-card"]');
  await expect(card).toBeVisible({ timeout: 8000 });

  const route = page.locator('[data-testid="optimize-route-decision"]');
  await expect(route).toBeVisible();
  // expert + routing_mode are the load-bearing "which model and why" surface.
  await expect(page.locator('[data-testid="optimize-route-expert"]')).toContainText('gemini-3-pro');
  await expect(page.locator('[data-testid="optimize-route-mode"]')).toContainText('v1_bandit');
  await expect(page.locator('[data-testid="optimize-route-score"]')).toContainText('0.74');
  // fallback chain (the resilience story) is surfaced too.
  await expect(page.locator('[data-testid="optimize-route-fallback"]')).toContainText(
    'gemini-3-flash'
  );
});

test('AT-027: a dreaming/DPO artifact renders read-only in the trace', async ({
  authenticatedPage: page,
}) => {
  await runWithFixture(page);

  const dpo = page.locator('[data-testid="optimize-dreaming-artifact"]');
  await expect(dpo).toBeVisible({ timeout: 8000 });
  await expect(page.locator('[data-testid="optimize-dpo-chosen"]')).toContainText('0.91');
  await expect(page.locator('[data-testid="optimize-dpo-rejected"]')).toContainText('0.62');
  await expect(page.locator('[data-testid="optimize-dpo-margin"]')).toContainText('0.29');
});

test('AT-027: the optimize surface is read-only (no mutating control)', async ({
  authenticatedPage: page,
}) => {
  await runWithFixture(page);

  const card = page.locator('[data-testid="optimize-artifact-card"]');
  await expect(card).toBeVisible({ timeout: 8000 });
  // The read-only contract: a badge says so, and the card contains no button /
  // input / editable affordance that could mutate routing or training state.
  await expect(card).toContainText('read-only');
  await expect(card.locator('button')).toHaveCount(0);
  await expect(card.locator('input')).toHaveCount(0);
  await expect(card.locator('[contenteditable="true"]')).toHaveCount(0);
});
