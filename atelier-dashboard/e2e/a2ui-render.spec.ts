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
      catalogId: 'https://a2ui.org/specification/v0_9/basic_catalog.json',
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

    // Governed-A2UI provenance badge (design-system colored, not indigo).
    await expect(
      page.getByTestId('studio-a2ui-section').getByText('A2UI', { exact: true })
    ).toBeVisible();

    // Visual artifact for design-fidelity review (Stitch-dark, Google Sans, 8px).
    await panel.screenshot({ path: 'e2e/__artifacts__/a2ui-panel.png' });
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
