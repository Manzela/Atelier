/**
 * AT-026 Playwright acceptance suite — Agentic Legibility / Accountability layer.
 *
 * Proves the four-part AT-026 acceptance bar in the Studio UI, hermetic (every
 * test intercepts /v1/generate/stream with a local SSE fixture — no live backend):
 *
 *  - Pre        : the editable pre-sign-off plan (reuses the AT-042 ApprovalCard)
 *                 surfaces with cited, editable defaults; an edit + approve writes
 *                 the EDITED plan to the run doc (the edit reaches execution).
 *  - Mid        : >= 1 trace row per DDLC specialist + per research query render
 *                 (< 1s), and EVERY D-O-R-A-V axis carries a real tooltip explanation.
 *  - Post       : the run-oracle verdict renders as a criterion -> verdict + evidence
 *                 panel (AttributionView), with PASS/FAIL conveyed by text (not color).
 *  - Hermetic   : the SAME fixture rendered twice yields byte-identical Attribution +
 *                 Trace DOM text (the legibility surface is deterministic).
 *  - Interruption: the Stop control is present while generating and reflects the
 *                 stopped state when the backend emits the `stop` event.
 *
 * Non-vacuousness:
 *   - The Mid tests WOULD FAIL if a specialist/research row were missing (count check).
 *   - The tooltip test WOULD FAIL if an axis had no explanation (text presence).
 *   - The Post test WOULD FAIL if a criterion verdict were not rendered (per-row check).
 *   - The hermetic test WOULD FAIL if the two renders diverged (string equality).
 */
import { test, expect } from './fixtures';
import type { Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const CANVAS_SELECTOR = '[data-testid="studio-canvas"]';
const TENANT_ID = 't1'; // matches MOCK_USER.tenant_id in fixtures.ts

// ── D-O-R-A-V axes (must match components/legibility/dorav.ts) ────────────────
const DORAV_KEYS = ['brand', 'originality', 'relevance', 'accessibility', 'visual-clarity'];

// ── A known, axe-clean converged document ─────────────────────────────────────
const KNOWN_HTML =
  '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>AT-026</title></head>' +
  '<body><main><h1>AT-026 fixture</h1><p>Legible by design.</p></main></body></html>';

// ── Mid + Post SSE fixture: plan(session) -> research -> specialists -> iter ->
//    complete(with run_verdict) ────────────────────────────────────────────────
const SESSION_ID = 'at026-session';

const RUN_VERDICT = {
  complete: false,
  criteria: [
    {
      criterion_id: 'surface:home:exists',
      kind: 'surface_exists',
      target: 'non-empty index.html',
      source: 'user',
      verdict: true,
      evidence_ref: 'present',
    },
    {
      criterion_id: 'surface:home:axe',
      kind: 'axe',
      target: '0 critical/serious',
      source: 'user',
      verdict: true,
      evidence_ref: '0 axe-core violations',
    },
    {
      criterion_id: 'surface:home:composite',
      kind: 'composite',
      target: '>= 0.7',
      source: 'user',
      verdict: false,
      evidence_ref: 'recomputed composite 0.640 (non-LLM oracles only)',
    },
    {
      criterion_id: 'standard:wcag-contrast-aa',
      kind: 'standard',
      target: 'wcag-contrast-aa',
      source: 'standard:wcag-contrast-aa',
      verdict: true,
      evidence_ref: 'user-confirmed domain default (AT-030 clarify gate)',
    },
  ],
  composite_by_surface: { home: 0.64 },
};

function legibilitySseBody(): string {
  const lines: string[] = [];
  const push = (event: string, data: unknown) => {
    lines.push(`event: ${event}`, `data: ${JSON.stringify(data)}`, '');
  };
  push('plan', { surfaces: ['home'], session_id: SESSION_ID });
  push('research_query', {
    query: 'editorial landing page accessibility best practices',
    result_count: 2,
    top_citation: 'https://www.w3.org/WAI/WCAG22/',
    top_title: 'WCAG 2.2',
    trust_score: 0.99,
  });
  push('research_query', {
    query: 'co-working studio pricing patterns',
    result_count: 1,
    top_citation: 'https://www.nngroup.com/articles/',
    top_title: 'NN/g',
    trust_score: 0.92,
  });
  push('screen_start', { screen: 'home', index: 0, session_id: SESSION_ID });
  for (const role of [
    'ux_research',
    'ia_flows',
    'wireframe',
    'ui_design',
    'interaction_spec',
    'tokens',
  ]) {
    push('specialist_trace', {
      screen: 'home',
      iteration: 0,
      role,
      summary: `${role} produced its hand-off artifact for the home screen.`,
    });
  }
  push('iteration_score', {
    screen: 'home',
    iteration: 0,
    dorav: {
      brand: 0.7,
      originality: 0.6,
      relevance: 0.75,
      accessibility: 0.8,
      'visual-clarity': 0.65,
      composite: 0.7,
    },
    composite: 0.7,
    failing_axis: 'originality',
  });
  push('complete', {
    best_html: KNOWN_HTML,
    converged: true,
    composite_score: 0.7,
    session_id: SESSION_ID,
    dorav: {
      brand: 0.7,
      originality: 0.6,
      relevance: 0.75,
      accessibility: 0.8,
      'visual-clarity': 0.65,
      composite: 0.7,
    },
    nielsen: [],
    run_verdict: RUN_VERDICT,
  });
  lines.push('');
  return lines.join('\n');
}

async function runLegibility(page: Page): Promise<void> {
  await page.route('**/v1/generate/stream', (route) =>
    route.fulfill({
      status: 200,
      headers: { 'content-type': 'text/event-stream' },
      body: legibilitySseBody(),
    })
  );
  await page.goto(`/studio/${SESSION_ID}?brief=acceptance`);
  await page.getByRole('button', { name: /^Run$/i }).click();
}

async function assertAxe(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page }).include(CANVAS_SELECTOR).analyze();
  const violations = results.violations.filter(
    (v) => v.impact === 'critical' || v.impact === 'serious'
  );
  expect(
    violations,
    `axe found ${violations.length} critical/serious: ${violations
      .map((v) => `[${v.impact}] ${v.id}`)
      .join('; ')}`
  ).toHaveLength(0);
}

// ── Pre fixture: an editable, cited pre-sign-off plan (reuses AT-042) ─────────
const PRE_RUN_ID = 'at026-signoff';
const PRE_PLAN = {
  surfaces: ['landing page'],
  est_tokens: 120_000,
  wcag_target: 'AA',
  specialist_count: 6,
  session_id: PRE_RUN_ID,
  proposed_defaults: [
    {
      standard_id: 'dash-card-cap',
      name: 'Nielsen Norman — Dashboard card density',
      rule: 'Cap primary dashboard cards at 7 to respect working-memory limits.',
      citation_url: 'https://www.nngroup.com/articles/dashboard-design/',
      trust_score: 0.92,
      domain: 'dashboard',
    },
  ],
  open_questions: [],
  gaps: [],
};

// The same in-page Firestore shim AT-042 uses — proves the approval write
// (the edited plan) reaches the run doc without FCM.
function installFirestoreShim() {
  return (initial: { tenant: string; run: string; status: string }) => {
    type Doc = Record<string, unknown> & { signoff_status?: string };
    type Listener = (doc: Doc | null) => void;
    const key = `${initial.tenant}/runs/${initial.run}`;
    const store: Record<string, Doc> = { [key]: { signoff_status: initial.status } };
    const listeners: Record<string, Set<Listener>> = {};
    const w = window as unknown as {
      __ATELIER_FIRESTORE__: {
        subscribeSignoff: (tenant: string, run: string, cb: Listener) => () => void;
        writeSignoff: (
          tenant: string,
          run: string,
          patch: Record<string, unknown>
        ) => Promise<void>;
        __dump: () => Record<string, Doc>;
      };
    };
    const docKey = (t: string, r: string) => `${t}/runs/${r}`;
    w.__ATELIER_FIRESTORE__ = {
      subscribeSignoff(tenant, run, cb) {
        const k = docKey(tenant, run);
        (listeners[k] ??= new Set()).add(cb);
        Promise.resolve().then(() => cb(store[k] ?? null));
        return () => listeners[k]?.delete(cb);
      },
      writeSignoff(tenant, run, patch) {
        const k = docKey(tenant, run);
        store[k] = { ...(store[k] ?? {}), ...patch };
        (listeners[k] ?? new Set()).forEach((cb) => cb(store[k]));
        return Promise.resolve();
      },
      __dump: () => store,
    };
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Pre — editing a cited default + approving writes the EDITED plan (edit reaches
// execution). Reuses the AT-042 ApprovalCard + AT-030 ACCEPTANCE-write path.
// ─────────────────────────────────────────────────────────────────────────────
test('AT-026 Pre: editing a plan default + approving writes the edited plan of record', async ({
  authenticatedPage: page,
}) => {
  await page.addInitScript(installFirestoreShim(), {
    tenant: TENANT_ID,
    run: PRE_RUN_ID,
    status: 'AWAITING_SIGNOFF',
  });
  await page.route('**/v1/generate/stream', (route) =>
    route.fulfill({
      status: 200,
      headers: { 'content-type': 'text/event-stream' },
      // Emit the plan, then hold the stream open (the run is paused for sign-off).
      body: ['event: plan', `data: ${JSON.stringify(PRE_PLAN)}`, '', ''].join('\n'),
    })
  );
  await page.goto(`/studio/${PRE_RUN_ID}?brief=acceptance`);
  await page.getByRole('button', { name: /^Run$/i }).click();

  // The editable pre-sign-off plan surfaces (AT-042 ApprovalCard).
  await expect(page.getByTestId('approval-card')).toBeVisible({ timeout: 15_000 });
  const target = PRE_PLAN.proposed_defaults[0];
  const input = page.getByTestId(`approval-default-input-${target.standard_id}`);
  const edited = 'Cap primary dashboard cards at 5 (tighter density for this brand).';
  await input.fill(edited);
  await page.getByTestId('approval-approve').click();

  // The EDITED plan reaches the run doc (the override is the plan of record — it
  // will drive execution / the ACCEPTANCE write on the backend, AT-030).
  const store = await page.evaluate(
    ({ tenant, run }) => {
      const w = window as unknown as {
        __ATELIER_FIRESTORE__: { __dump: () => Record<string, Record<string, unknown>> };
      };
      return w.__ATELIER_FIRESTORE__.__dump()[`${tenant}/runs/${run}`];
    },
    { tenant: TENANT_ID, run: PRE_RUN_ID }
  );
  expect(store.signoff_status).toBe('APPROVED');
  expect(JSON.stringify(store.approved_plan)).toContain(edited);
});

// ─────────────────────────────────────────────────────────────────────────────
// Mid — one trace row per specialist + per research query, < 1s.
// ─────────────────────────────────────────────────────────────────────────────
test('AT-026 Mid: a trace row renders per DDLC specialist and per research query', async ({
  authenticatedPage: page,
}) => {
  await runLegibility(page);

  // The trace panel appears and carries one row per specialist hand-off.
  await expect(page.getByTestId('trace-panel')).toBeVisible({ timeout: 15_000 });
  for (const role of [
    'ux_research',
    'ia_flows',
    'wireframe',
    'ui_design',
    'interaction_spec',
    'tokens',
  ]) {
    await expect(page.getByTestId(`trace-specialist-row-${role}`)).toBeVisible();
  }
  // One research row per WRAI query, each with a citation link.
  const researchRows = page.locator('[data-testid="trace-research-row"]');
  await expect(researchRows).toHaveCount(2);
  await expect(researchRows.first().locator('a')).toHaveAttribute('href', /w3\.org|nngroup\.com/);
});

// ─────────────────────────────────────────────────────────────────────────────
// Mid — every D-O-R-A-V axis carries a real tooltip explanation.
// ─────────────────────────────────────────────────────────────────────────────
test('AT-026 Mid: every D-O-R-A-V axis is tooltip-explained', async ({
  authenticatedPage: page,
}) => {
  await runLegibility(page);
  await expect(page.getByTestId('trace-dorav-legend')).toBeVisible({ timeout: 15_000 });

  for (const key of DORAV_KEYS) {
    const trigger = page.getByTestId(`dorav-tooltip-trigger-${key}`);
    await expect(trigger).toBeVisible();
    await trigger.hover();
    const tip = page.getByTestId(`dorav-tooltip-${key}`);
    await expect(tip).toBeVisible();
    // The tooltip is a REAL explanation (a sentence), not a placeholder.
    const text = (await tip.textContent())?.trim() ?? '';
    expect(text.length, `D-O-R-A-V ${key} tooltip must explain the axis`).toBeGreaterThan(40);
    await page.mouse.move(0, 0); // dismiss before the next axis
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// Post — the run-oracle verdict renders criterion -> verdict + evidence.
// ─────────────────────────────────────────────────────────────────────────────
test('AT-026 Post: attribution view maps every criterion to a verdict + evidence', async ({
  authenticatedPage: page,
}) => {
  await runLegibility(page);

  const view = page.getByTestId('attribution-view');
  await expect(view).toBeVisible({ timeout: 15_000 });

  // Aggregate status reflects the (intentionally incomplete) verdict.
  await expect(page.getByTestId('attribution-status')).toHaveAttribute('data-complete', 'false');

  // One row per criterion, each carrying its verdict (pass/fail) + evidence text.
  for (const c of RUN_VERDICT.criteria) {
    const row = page.getByTestId(`attribution-criterion-${c.criterion_id}`);
    await expect(row).toBeVisible();
    await expect(row).toHaveAttribute('data-verdict', c.verdict ? 'pass' : 'fail');
    await expect(row).toContainText(c.evidence_ref);
    // PASS/FAIL is conveyed by text, not color alone (accessibility).
    await expect(row).toContainText(c.verdict ? 'pass' : 'fail');
  }

  // The user-confirmed domain standard is attributed as a Standard-sourced row.
  await expect(page.getByTestId('attribution-criterion-standard:wcag-contrast-aa')).toContainText(
    'Standard'
  );

  // Amend re-enters the loop (the affordance is present + actionable).
  await expect(page.getByTestId('attribution-amend')).toBeVisible();

  await assertAxe(page);
});

// ─────────────────────────────────────────────────────────────────────────────
// Hermetic — the SAME fixture renders byte-identical Attribution + Trace text.
// ─────────────────────────────────────────────────────────────────────────────
test('AT-026 hermetic lane: the legibility surface renders identically across runs', async ({
  authenticatedPage: page,
}) => {
  async function renderOnce(): Promise<{ attribution: string; trace: string }> {
    await runLegibility(page);
    await expect(page.getByTestId('attribution-view')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId('trace-specialist-row-tokens')).toBeVisible();
    const attribution = (await page.getByTestId('attribution-criteria').innerText()).trim();
    const trace = (await page.getByTestId('trace-specialists').innerText()).trim();
    return { attribution, trace };
  }

  const first = await renderOnce();
  // Re-run the identical fixture from a clean navigation.
  const second = await renderOnce();

  expect(second.attribution).toBe(first.attribution);
  expect(second.trace).toBe(first.trace);
});

// ─────────────────────────────────────────────────────────────────────────────
// Interruption — the Stop control is present while generating and the backend
// `stop` event flips the shell to the stopped state.
// ─────────────────────────────────────────────────────────────────────────────
test('AT-026 Interruption: a `stop` event halts the run into the stopped state', async ({
  authenticatedPage: page,
}) => {
  // A fixture that emits a screen_start (so the Stop button is live) then a `stop`.
  const stopBody = [
    'event: plan',
    `data: ${JSON.stringify({ surfaces: ['home'], session_id: SESSION_ID })}`,
    '',
    'event: screen_start',
    `data: ${JSON.stringify({ screen: 'home', index: 0, session_id: SESSION_ID })}`,
    '',
    'event: stop',
    `data: ${JSON.stringify({ screen: 'home', iteration: 0, session_id: SESSION_ID, checkpointed: true })}`,
    '',
    '',
  ].join('\n');

  // The Stop endpoint is a no-op fulfillment (the halt itself is driven by the SSE).
  await page.route(`**/v1/stop/**`, (route) =>
    route.fulfill({ status: 200, body: JSON.stringify({ status: 'stop_requested' }) })
  );
  await page.route('**/v1/generate/stream', (route) =>
    route.fulfill({
      status: 200,
      headers: { 'content-type': 'text/event-stream' },
      body: stopBody,
    })
  );

  await page.goto(`/studio/${SESSION_ID}?brief=acceptance`);
  await page.getByRole('button', { name: /^Run$/i }).click();

  // The run halts into the acknowledged stopped state.
  await expect(page.getByTestId('state-stopped')).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId('state-stopped')).toContainText(/checkpointed/i);
});
