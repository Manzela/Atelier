/**
 * AT-044 Playwright acceptance suite — Design-system panel + agent-generated controls.
 *
 * Acceptance (features.json AT-044):
 *  1. The panel renders one row per `tokens.json` entry (count matches the
 *     canonical leaf count, read live from disk — drift guard).
 *  2. Editing `color.primary` A->B updates that cell (Playwright computed-color)
 *     AND propagates to >=1 other surface's rendered output (the converged
 *     iframe surface, read via getComputedStyle inside the sandboxed frame).
 *  3. >=1 agent-generated control is present and bound to a real `tokens.json`
 *     token; and the synthesized control SET tracks the design system (a
 *     color-only system yields the hue knob but no scale sliders — not a
 *     fixed set).
 *
 * Hermetic: intercepts /v1/generate/stream with a local SSE fixture; the
 * `complete` event carries the design system as `tokens`. No live backend.
 */
import fs from 'fs';
import path from 'path';
import { test, expect } from './fixtures';
import type { Page } from '@playwright/test';
import {
  flattenDesignSystem,
  DEFAULT_DESIGN_SYSTEM,
  type DesignSystem,
} from '../src/lib/design-system';

// --- canonical token source (single source of truth, AT-050) ----------------

function loadCanonicalTokens(): DesignSystem {
  const candidates = [
    path.resolve(process.cwd(), '../design-tokens/tokens.json'),
    path.resolve(process.cwd(), 'design-tokens/tokens.json'),
  ];
  if (typeof __dirname !== 'undefined') {
    candidates.push(path.resolve(__dirname, '../../design-tokens/tokens.json'));
  }
  for (const p of candidates) {
    if (fs.existsSync(p)) return JSON.parse(fs.readFileSync(p, 'utf-8')) as DesignSystem;
  }
  throw new Error(`canonical tokens.json not found; checked:\n${candidates.join('\n')}`);
}

const CANONICAL = loadCanonicalTokens();
const CANONICAL_LEAVES = flattenDesignSystem(CANONICAL);
const slug = (p: string): string => p.split('.').join('-');

/**
 * Independent leaf oracle — a raw JSON walk written WITHOUT flattenDesignSystem,
 * so the expected count/set is not produced by the same function under test. A
 * flatten regression that drops a real leaf disagrees with this oracle and goes
 * red (the shared-oracle trap the row-count assertion would otherwise have).
 */
function collectLeafPathsRaw(node: unknown, prefix: string[], out: string[]): void {
  if (node === null || typeof node !== 'object') return;
  const obj = node as Record<string, unknown>;
  if ('$value' in obj) {
    out.push(prefix.join('.'));
    return;
  }
  for (const key of Object.keys(obj)) {
    if (key.startsWith('$')) continue;
    collectLeafPathsRaw(obj[key], [...prefix, key], out);
  }
}

const RAW_CANONICAL_PATHS: string[] = [];
collectLeafPathsRaw(CANONICAL, [], RAW_CANONICAL_PATHS);
// Literal anchor: pins the canonical leaf count independently of any code path.
const EXPECTED_LEAF_COUNT = 31;
// A few hand-listed leaves (incl. a digit-bearing and a nested one) as a direct
// spot-check that the panel renders the real tokens, not just the right count.
const SPOT_CHECK_SLUGS = [
  'color-primary',
  'font-size-2xl',
  'font-family-sans',
  'space-md',
  'radius-full',
];

// A->B color edit. #2563eb -> rgb(37, 99, 235); #db2777 -> rgb(219, 39, 119).
const PRIMARY_A_RGB = 'rgb(37, 99, 235)';
const PRIMARY_B_HEX = '#db2777';
const PRIMARY_B_RGB = 'rgb(219, 39, 119)';

// A converged surface that consumes the design token the standards-compliant
// way: `var(--color-primary)`. The baked `:root` (blue) never changes; the
// live :root the panel injects must override it, so the post-edit color proves
// propagation (non-vacuous).
const SURFACE_HTML =
  '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">' +
  '<style>:root{--color-primary:#2563eb}*{margin:0;box-sizing:border-box}body{background:#fff}</style>' +
  '</head><body>' +
  '<div data-testid="ds-surface-primary" style="background-color: var(--color-primary); width:120px; height:120px;"></div>' +
  '</body></html>';

function sseBody(tokens: DesignSystem): string {
  return [
    'event: plan',
    'data: {"surfaces":["home"]}',
    '',
    'event: complete',
    `data: ${JSON.stringify({ best_html: SURFACE_HTML, converged: true, tokens })}`,
    '',
    '',
  ].join('\n');
}

async function runWithTokens(page: Page, tokens: DesignSystem): Promise<void> {
  await page.route('**/v1/generate/stream', (route) =>
    route.fulfill({
      status: 200,
      headers: { 'content-type': 'text/event-stream' },
      body: sseBody(tokens),
    })
  );
  await page.goto('/studio/at044-test?brief=design-system');
  await page.getByRole('button', { name: /^Run$/i }).click();
  await page.waitForSelector('iframe[title="Converged design output"]', { timeout: 15_000 });
  await page.getByTestId('ds-panel').waitFor({ state: 'visible', timeout: 10_000 });
  await page
    .frameLocator('iframe[title="Converged design output"]')
    .locator('[data-testid="ds-surface-primary"]')
    .waitFor({ state: 'visible', timeout: 10_000 });
}

// Set a React-controlled input's value via the native setter so React's value
// tracker observes the change (plain el.value = ... is swallowed by React).
async function setReactInput(page: Page, testId: string, value: string): Promise<void> {
  await page.getByTestId(testId).evaluate((el, val) => {
    const input = el as HTMLInputElement;
    const setter = Object.getOwnPropertyDescriptor(
      Object.getPrototypeOf(input) as object,
      'value'
    )?.set;
    setter?.call(input, val);
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }, value);
}

function surfaceColor(page: Page): Promise<string> {
  return page
    .frameLocator('iframe[title="Converged design output"]')
    .locator('[data-testid="ds-surface-primary"]')
    .evaluate((el) => window.getComputedStyle(el).backgroundColor);
}

// ---------------------------------------------------------------------------

test.describe('AT-044 design-system panel', () => {
  test('vendored default design system matches canonical tokens.json (drift guard)', () => {
    // Anchor both flatten outputs to the INDEPENDENT raw-JSON oracle (and the
    // literal count) so a flatten regression cannot hide behind a shared oracle.
    expect(RAW_CANONICAL_PATHS.length).toBe(EXPECTED_LEAF_COUNT);
    expect(CANONICAL_LEAVES.map((t) => t.path).sort()).toEqual([...RAW_CANONICAL_PATHS].sort());

    const def = flattenDesignSystem(DEFAULT_DESIGN_SYSTEM);
    expect(def.map((t) => t.path).sort()).toEqual([...RAW_CANONICAL_PATHS].sort());
    const canonByPath = new Map(CANONICAL_LEAVES.map((t) => [t.path, JSON.stringify(t.value)]));
    for (const t of def) {
      expect(JSON.stringify(t.value)).toBe(canonByPath.get(t.path));
    }
  });

  test('panel renders exactly one row per tokens.json entry', async ({
    authenticatedPage: page,
  }) => {
    await runWithTokens(page, CANONICAL);

    const rowSlugs = await page
      .locator('[data-testid^="ds-token-row-"]')
      .evaluateAll((els) =>
        els.map((e) => (e.getAttribute('data-testid') ?? '').replace('ds-token-row-', '')).sort()
      );

    // Assert the rendered rows against the INDEPENDENT oracle + a literal count,
    // not against flattenDesignSystem (which also produces the rows). A flatten
    // bug that drops a leaf renders fewer rows and fails here.
    expect(rowSlugs.length).toBe(EXPECTED_LEAF_COUNT);
    expect(rowSlugs).toEqual([...RAW_CANONICAL_PATHS].map(slug).sort());
    await expect(page.getByTestId('ds-panel-count')).toHaveText(`${EXPECTED_LEAF_COUNT} tokens`);
    // Direct spot-checks that the real tokens render (digit-bearing + nested).
    for (const s of SPOT_CHECK_SLUGS) {
      expect(rowSlugs).toContain(s);
    }
  });

  test('editing color.primary A->B updates the cell and propagates to the surface', async ({
    authenticatedPage: page,
  }) => {
    await runWithTokens(page, CANONICAL);

    // Initial: panel cell and the surface both resolve to A.
    await expect(page.getByTestId('ds-token-swatch-color-primary')).toHaveCSS(
      'background-color',
      PRIMARY_A_RGB
    );
    await expect.poll(() => surfaceColor(page)).toBe(PRIMARY_A_RGB);

    // Edit color.primary A -> B in the panel.
    await setReactInput(page, 'ds-token-input-color-primary', PRIMARY_B_HEX);

    // The cell updates (parent DOM)...
    await expect(page.getByTestId('ds-token-swatch-color-primary')).toHaveCSS(
      'background-color',
      PRIMARY_B_RGB
    );
    // ...and the change propagates to the rendered surface (inside the iframe).
    await expect.poll(() => surfaceColor(page)).toBe(PRIMARY_B_RGB);
  });

  test('an agent-generated control is present, bound to a real token, and functional', async ({
    authenticatedPage: page,
  }) => {
    await runWithTokens(page, CANONICAL);

    // The synthesized set for this system: a primary-hue knob + per-scale sliders.
    await expect(page.getByTestId('ds-generated-controls')).toBeVisible();
    await expect(page.locator('[data-testid^="ds-generated-control-"]')).toHaveCount(3);

    const hue = page.getByTestId('ds-generated-control-color-primary-hue');
    await expect(hue).toBeVisible();
    const boundToken = await hue.getAttribute('data-token');
    expect(boundToken).toBe('color.primary');
    // Bound to a token that actually exists in tokens.json.
    expect(CANONICAL_LEAVES.map((t) => t.path)).toContain(boundToken);

    // Functional: moving the hue knob rewrites color.primary and re-flows the surface.
    const before = await page
      .getByTestId('ds-token-swatch-color-primary')
      .evaluate((el) => window.getComputedStyle(el).backgroundColor);
    await setReactInput(page, 'ds-generated-input-color-primary-hue', '125');
    const after = await page
      .getByTestId('ds-token-swatch-color-primary')
      .evaluate((el) => window.getComputedStyle(el).backgroundColor);
    expect(after).not.toBe(before);
    await expect.poll(() => surfaceColor(page)).toBe(after);
  });

  test('the synthesized control set tracks the design (color-only -> hue, no scales)', async ({
    authenticatedPage: page,
  }) => {
    const VARIANT: DesignSystem = {
      color: {
        $type: 'color',
        primary: { $value: '#0ea5e9' },
        accent: { $value: '#f43f5e' },
      },
    };
    await runWithTokens(page, VARIANT);

    // Row count tracks the variant system, not a fixed 31.
    await expect(page.locator('[data-testid^="ds-token-row-"]')).toHaveCount(
      flattenDesignSystem(VARIANT).length
    );

    // The hue knob is still derived (a primary color exists)...
    await expect(page.getByTestId('ds-generated-control-color-primary-hue')).toBeVisible();
    // ...but no dimension groups -> no scale sliders. The set adapts.
    await expect(page.locator('[data-testid^="ds-generated-control-"]')).toHaveCount(1);
    await expect(page.getByTestId('ds-generated-control-space-scale')).toHaveCount(0);
    await expect(page.getByTestId('ds-generated-control-radius-scale')).toHaveCount(0);
  });
});
