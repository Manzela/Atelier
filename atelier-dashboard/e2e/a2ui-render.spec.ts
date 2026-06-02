/**
 * ADR-0024 / P0.4 — Governed A2UI render acceptance (FRONTEND SLICE 2).
 *
 * Hermetic: intercepts /v1/generate/stream with a local SSE fixture whose
 * `complete` event carries the agent-emitted `a2ui_payload` — the EXACT ordered
 * message list `atelier-core/src/atelier/a2ui/surface.py` emits. Asserts the
 * `@a2ui/react` renderer mounts the surface (token rows resolve via data-binding)
 * under the `NEXT_PUBLIC_A2UI_RENDER` flag, themed to the Material-3 dark Stitch
 * system, and that fail-soft falls back to the hand-built panel on a bad payload.
 *
 * The flag is build-time (`NEXT_PUBLIC_*` is statically inlined), so this suite
 * SKIPS unless the app was built/served with `NEXT_PUBLIC_A2UI_RENDER=1`. Default
 * CI builds flag-off (the hand-built panel, covered by at044-design-system-panel).
 * Run flag-on:  NEXT_PUBLIC_A2UI_RENDER=1 npx playwright test a2ui-render
 */
import { test, expect } from './fixtures';
import type { Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

// The canonical Atelier catalog id — byte-identical to the TS constant
// (`ATELIER_CATALOG_ID` in src/components/a2ui/atelierCatalog.ts) and the two
// Python mirrors. The hermetic fixture's `createSurface.catalogId` MUST equal
// it or the renderer's MessageProcessor matches nothing (the surface is the one
// that RENDERS, so this is the cross-track contract under test).
const ATELIER_CATALOG_ID =
  'https://atelier.autonomous-agent.dev/a2ui/catalogs/design-system/v1.json';

test.skip(
  process.env.NEXT_PUBLIC_A2UI_RENDER !== '1',
  'Governed A2UI render requires a flag-on build (NEXT_PUBLIC_A2UI_RENDER=1)'
);

// Minimal converged HTML for the iframe (the deliverable is unrelated to A2UI).
const SURFACE_HTML =
  '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">' +
  '<style>body{background:#0f1013;color:#e3e3e3;font-family:system-ui;margin:0;padding:24px}</style>' +
  '</head><body><main><h1>Converged</h1></main></body></html>';

// The exact a2ui_payload shape emitted by build_design_system_surface(...) for a
// 5-token system (generated from the backend builder; mirrors surface.py). v0.9
// wire const; relative {path: "path"}/{path: "value"} row bindings (post slash-fix).
const A2UI_PAYLOAD = [
  {
    version: 'v0.9',
    createSurface: {
      surfaceId: 'atelier-design-system',
      catalogId: ATELIER_CATALOG_ID,
    },
  },
  {
    version: 'v0.9',
    updateComponents: {
      surfaceId: 'atelier-design-system',
      components: [
        { id: 'root', component: 'Card', child: 'ds_column' },
        {
          id: 'ds_column',
          component: 'Column',
          children: ['ds_title', 'ds_divider', 'ds_token_list'],
          align: 'stretch',
        },
        { id: 'ds_title', component: 'Text', variant: 'h3', text: 'Design System' },
        { id: 'ds_divider', component: 'Divider', axis: 'horizontal' },
        {
          id: 'ds_token_list',
          component: 'List',
          direction: 'vertical',
          children: { componentId: 'token_row', path: '/tokens' },
        },
        {
          id: 'token_row',
          component: 'Row',
          children: ['token_row_path', 'token_row_value'],
          justify: 'spaceBetween',
          align: 'center',
        },
        { id: 'token_row_path', component: 'Text', variant: 'body', text: { path: 'path' } },
        { id: 'token_row_value', component: 'Text', variant: 'caption', text: { path: 'value' } },
      ],
    },
  },
  {
    version: 'v0.9',
    updateDataModel: {
      surfaceId: 'atelier-design-system',
      path: '/',
      value: {
        tokens: [
          { path: 'color-primary', value: '#1a73e8' },
          { path: 'color-surface', value: '#1e1f22' },
          { path: 'color-ink', value: '#e3e3e3' },
          { path: 'font-body', value: 'Google Sans' },
          { path: 'space-base', value: '1rem' },
        ],
      },
    },
  },
];

function sseBody(a2uiPayload: unknown): string {
  return [
    'event: plan',
    'data: {"surfaces":["home"]}',
    '',
    'event: complete',
    `data: ${JSON.stringify({ best_html: SURFACE_HTML, converged: true, a2ui_payload: a2uiPayload })}`,
    '',
    '',
  ].join('\n');
}

async function run(page: Page, a2uiPayload: unknown): Promise<void> {
  await page.route('**/v1/generate/stream', (route) =>
    route.fulfill({
      status: 200,
      headers: { 'content-type': 'text/event-stream' },
      body: sseBody(a2uiPayload),
    })
  );
  await page.goto('/studio/a2ui-test?brief=design-system');
  await page.getByRole('button', { name: /^Run$/i }).click();
  await page.waitForSelector('iframe[title="Converged design output"]', { timeout: 20_000 });
}

test.describe('Governed A2UI render (flag-on)', () => {
  test('mounts the agent-emitted A2UI surface with data-bound token rows, themed', async ({
    authenticatedPage: page,
  }) => {
    await run(page, A2UI_PAYLOAD);

    const panel = page.getByTestId('studio-a2ui-design-system');
    await panel.waitFor({ state: 'visible', timeout: 15_000 });

    // The surface is self-describing (renders its own title) ...
    await expect(panel).toContainText('Design System');
    // ... and every token NAME resolves through the /tokens data-binding template.
    for (const name of ['color-primary', 'color-surface', 'color-ink', 'font-body', 'space-base']) {
      await expect(panel.getByText(name, { exact: false }).first()).toBeVisible();
    }
    // At least one token VALUE resolves too (caption side of the row binding).
    await expect(panel.getByText('Google Sans', { exact: false }).first()).toBeVisible();

    // --- G4 semantic-HTML contract (the Atelier catalog upgrade vs basicCatalog,
    //     which rendered bare <div>/<span>). These also stand in for the catalog
    //     unit test: there is no jsdom/vitest runner in this project (Playwright
    //     e2e only — see package.json), so the catalog's own DOM contract is
    //     asserted here against a real Chromium render of `atelierCatalog`. ---

    // Text variant:'h3' (the "Design System" title) renders as a semantic heading
    // (the Atelier Text emits <h3>; markdown-it produces the inner heading text).
    await expect(panel.getByRole('heading', { name: /Design System/i }).first()).toBeVisible();
    // List renders as a semantic <ul> with each token row wrapped in an <li>.
    await expect(panel.locator('ul')).toHaveCount(1);
    await expect(panel.locator('ul > li').first()).toBeVisible();
    // Card → <article>, Divider → <hr> (native separator), Row → role="group".
    await expect(panel.locator('article')).toHaveCount(1);
    await expect(panel.locator('hr')).toHaveCount(1);
    await expect(panel.getByRole('group').first()).toBeVisible();

    // Governed-A2UI provenance badge (design-system colored, not indigo).
    await expect(
      page.getByTestId('studio-a2ui-section').getByText('A2UI', { exact: true })
    ).toBeVisible();

    // Visual artifact for design-fidelity review (Stitch-dark, Google Sans, 8px).
    await panel.screenshot({ path: 'e2e/__artifacts__/a2ui-panel.png' });
  });

  test('A2UI panel is axe-clean (labelled controls + contrast ≥ WCAG AA), focusable, with a live region', async ({
    authenticatedPage: page,
  }) => {
    await run(page, A2UI_PAYLOAD);

    const panel = page.getByTestId('studio-a2ui-design-system');
    await panel.waitFor({ state: 'visible', timeout: 15_000 });
    // Wait for the surface to materialize (token value resolved) so axe scans the
    // fully-rendered semantic DOM, not a mid-mount frame.
    await expect(panel.getByText('Google Sans', { exact: false }).first()).toBeVisible();

    // G3: scope axe to the Atelier-owned wrapper only (the page-level scan is
    // at043's job). Assert 0 critical/serious — INCLUDING color-contrast, which
    // empirically validates the measured 6.24:1 / 12.84:1 ratios in a real DOM.
    const results = await new AxeBuilder({ page })
      .include('[data-testid="studio-a2ui-design-system"]')
      .analyze();
    const violations = results.violations.filter(
      (v) => v.impact === 'critical' || v.impact === 'serious'
    );
    expect(
      violations,
      `axe-core found ${violations.length} critical/serious violation(s): ${violations
        .map((v) => `[${v.impact}] ${v.id}: ${v.description}`)
        .join('; ')}`
    ).toEqual([]);

    // G3: the focus-on-remount target — the wrapper is programmatically focusable.
    await expect(panel).toHaveAttribute('tabindex', '-1');
    await expect(panel).toHaveAttribute('role', 'group');
    await expect(panel).toHaveAttribute('aria-label', 'Generated design system');

    // G3: the persistent shell-level live region exists with the right semantics
    // (it pre-exists the surface so AT announcements are not missed).
    const liveRegion = page.getByTestId('a2ui-live-region');
    await expect(liveRegion).toHaveAttribute('role', 'status');
    await expect(liveRegion).toHaveAttribute('aria-live', 'polite');
    // It announces readiness once the surface mounts (onSurfaceReady → shell).
    await expect(liveRegion).toHaveText(/Design system panel ready/i);
  });

  test('fail-soft: a payload that yields no surface falls back to the hand-built panel', async ({
    authenticatedPage: page,
  }) => {
    // Non-empty payload (so the shell captures it) that creates NO surface — the
    // renderer throws "no surfaces" → the error boundary signals onRenderError →
    // the shell latches and swaps in the hand-built ds-panel. Never a silent blank.
    await run(page, [
      { version: 'v0.9', updateDataModel: { surfaceId: 'orphan', path: '/', value: {} } },
    ]);

    await expect(page.getByTestId('ds-panel')).toBeVisible({ timeout: 15_000 });
  });
});
