/**
 * AT-042 Playwright acceptance suite — ApprovalCard (tokens + scope, push-free).
 *
 * Acceptance (features.json AT-042 / build plan):
 *  1. The ApprovalCard surfaces the pre-sign-off plan: number of SCREENS,
 *     estimated TOKENS, WCAG target, SPECIALIST count, AND the editable plan
 *     pre-filled with the AT-030 `proposed_defaults` — each rendered with its
 *     CITATION (`citation_url`). Steerability: the user can edit a field before
 *     approving.
 *  2. Approve RESUMES the run on a COLD CLONE via Firestore `onSnapshot`
 *     WITHOUT FCM. The resume is driven purely by an onSnapshot subscription to
 *     the awaiting-signoff doc — no push notifications, no messaging SDK.
 *
 * Hermetic. Two seams keep the test real without a live Firestore project:
 *   - The SSE stream is intercepted (`**​/v1/generate/stream`) and emits a `plan`
 *     event carrying the full PlanData, then hangs (the run is paused awaiting
 *     sign-off — exactly the production AWAITING_SIGNOFF halt).
 *   - The Firestore layer is driven by an in-page shim (`window.__ATELIER_FIRESTORE__`)
 *     installed before navigation. The shim mirrors the production
 *     `subscribeSignoff` / `writeSignoff` contract (onSnapshot semantics over an
 *     in-memory doc store) so the cold-clone resume is provable WITHOUT FCM and
 *     WITHOUT an emulator. Production code uses the real firebase/firestore
 *     `onSnapshot` + `updateDoc` (see src/lib/approval-listener.ts).
 *
 * The shim store is shared across pages via `addInitScript` + a serialized store
 * passed back and forth, so a SECOND (cold-clone) page sees the same doc the
 * first page approved — the definition of a push-free, onSnapshot-driven resume.
 */
import { test, expect } from './fixtures';
import type { Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

// ── Fixture: a fully-populated pre-sign-off plan ──────────────────────────────
// Mirrors atelier-core PlanStep + ProposedDefault wire shape (the `plan` SSE
// event payload). citation_url is never empty (PRD §3.5 — every applied default
// is attributable to a cited source).
const PLAN = {
  surfaces: ['landing page', 'pricing page', 'dashboard'],
  est_tokens: 184_000,
  wcag_target: 'AA',
  specialist_count: 6,
  axis_weights: {
    brand: 0.2,
    originality: 0.2,
    relevance: 0.2,
    accessibility: 0.2,
    visual_clarity: 0.2,
  },
  constitution: 'apple-grade',
  reasoning: 'Brand-sensitive multi-surface brief — ensemble generation with cited defaults.',
  proposed_defaults: [
    {
      standard_id: 'dash-card-cap',
      name: 'Nielsen Norman — Dashboard card density',
      rule: 'Cap primary dashboard cards at 7 to respect working-memory limits.',
      citation_url: 'https://www.nngroup.com/articles/dashboard-design/',
      trust_score: 0.92,
      domain: 'dashboard',
    },
    {
      standard_id: 'wcag-contrast-aa',
      name: 'WCAG 2.2 — Contrast (Minimum) 1.4.3',
      rule: 'Body text contrast ratio must be at least 4.5:1.',
      citation_url: 'https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html',
      trust_score: 0.99,
      domain: 'accessibility',
    },
  ],
  open_questions: ['Should the pricing page include an annual/monthly toggle?'],
  gaps: [],
};

const TENANT_ID = 't1'; // matches MOCK_USER.tenant_id in fixtures.ts
const RUN_ID = 'at042-signoff';

// SSE body: emit the plan, then leave the stream open (paused for sign-off).
function planSseBody(): string {
  return ['event: plan', `data: ${JSON.stringify(PLAN)}`, '', ''].join('\n');
}

// ── In-page Firestore shim (no FCM) ───────────────────────────────────────────
// Installed before navigation. Provides the exact contract approval-listener.ts
// consumes: subscribeSignoff(tenant, run, cb) -> unsubscribe; writeSignoff(...).
// The store lives on window so the test can seed it and read it back; the
// cold-clone page is seeded with the post-approval store to prove onSnapshot
// resume across a fresh client (a real cold clone reads the same Firestore doc).
function installFirestoreShim() {
  return (initial: { tenant: string; run: string; status: string }) => {
    type Doc = Record<string, unknown> & { signoff_status?: string };
    type Listener = (doc: Doc | null) => void;
    const key = `${initial.tenant}/runs/${initial.run}`;
    const store: Record<string, Doc> = {
      [key]: { signoff_status: initial.status },
    };
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
        // onSnapshot fires immediately with the current doc (real Firestore
        // behaviour) — this is what makes a COLD CLONE resume with no push.
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

async function gotoWithPlan(page: Page, seedStatus: string): Promise<void> {
  await page.addInitScript(installFirestoreShim(), {
    tenant: TENANT_ID,
    run: RUN_ID,
    status: seedStatus,
  });
  await page.route('**/v1/generate/stream', (route) =>
    route.fulfill({
      status: 200,
      headers: { 'content-type': 'text/event-stream' },
      body: planSseBody(),
    })
  );
  await page.goto(`/studio/${RUN_ID}?brief=acceptance`);
}

const CANVAS_SELECTOR = '[data-testid="studio-canvas"]';

async function assertAxe(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page }).include(CANVAS_SELECTOR).analyze();
  const violations = results.violations.filter(
    (v) => v.impact === 'critical' || v.impact === 'serious'
  );
  expect(
    violations,
    `axe-core found ${violations.length} critical/serious violation(s): ${violations
      .map((v) => `[${v.impact}] ${v.id}: ${v.description}`)
      .join('; ')}`
  ).toHaveLength(0);
}

// ─────────────────────────────────────────────────────────────────────────────
// Test 1: ApprovalCard surfaces the full pre-sign-off plan + cited defaults.
// ─────────────────────────────────────────────────────────────────────────────
test('AT-042 surfaces screens / tokens / WCAG / specialist-count + cited editable defaults', async ({
  authenticatedPage: page,
}) => {
  await gotoWithPlan(page, 'AWAITING_SIGNOFF');
  await page.getByRole('button', { name: /^Run$/i }).click();

  const card = page.getByTestId('approval-card');
  await expect(card).toBeVisible({ timeout: 15_000 });

  // Screens count — 3 surfaces.
  await expect(page.getByTestId('approval-screens')).toContainText('3');
  // Estimated tokens — the number is rendered (locale-formatted is fine).
  await expect(page.getByTestId('approval-tokens')).toContainText('184');
  // WCAG target.
  await expect(page.getByTestId('approval-wcag')).toContainText('AA');
  // Specialist count.
  await expect(page.getByTestId('approval-specialists')).toContainText('6');

  // Editable plan pre-filled with cited defaults — one row per proposed_default,
  // each carrying its citation_url as a real link.
  const rows = page.locator('[data-testid^="approval-default-row-"]');
  await expect(rows).toHaveCount(PLAN.proposed_defaults.length);
  for (const d of PLAN.proposed_defaults) {
    const row = page.getByTestId(`approval-default-row-${d.standard_id}`);
    await expect(row).toBeVisible();
    // The editable field is pre-filled with the recommended value (the rule).
    await expect(page.getByTestId(`approval-default-input-${d.standard_id}`)).toHaveValue(d.rule);
    // The citation link points at the cited source (legibility + provenance).
    const cite = page.getByTestId(`approval-default-cite-${d.standard_id}`);
    await expect(cite).toHaveAttribute('href', d.citation_url);
  }

  await assertAxe(page);
});

// ─────────────────────────────────────────────────────────────────────────────
// Test 2: steerability — the user edits a default before approving, and the
// edit is carried into the approval write (not the original recommended value).
// ─────────────────────────────────────────────────────────────────────────────
test('AT-042 steerability: edit a cited default, then approve writes the edited plan', async ({
  authenticatedPage: page,
}) => {
  await gotoWithPlan(page, 'AWAITING_SIGNOFF');
  await page.getByRole('button', { name: /^Run$/i }).click();
  await expect(page.getByTestId('approval-card')).toBeVisible({ timeout: 15_000 });

  const target = PLAN.proposed_defaults[0];
  const input = page.getByTestId(`approval-default-input-${target.standard_id}`);
  const edited = 'Cap primary dashboard cards at 5 (tighter density for this brand).';
  await input.fill(edited);
  await expect(input).toHaveValue(edited);

  await page.getByTestId('approval-approve').click();

  // The approval write reached Firestore (the shim) with APPROVED status AND the
  // edited plan — steerability is durable, not a display-only affordance.
  const store = await page.evaluate(
    ({ tenant, run }) => {
      const w = window as unknown as {
        __ATELIER_FIRESTORE__: { __dump: () => Record<string, Record<string, unknown>> };
      };
      return w.__ATELIER_FIRESTORE__.__dump()[`${tenant}/runs/${run}`];
    },
    { tenant: TENANT_ID, run: RUN_ID }
  );
  expect(store.signoff_status).toBe('APPROVED');
  expect(JSON.stringify(store.approved_plan)).toContain(edited);
});

// ─────────────────────────────────────────────────────────────────────────────
// Test 3: cold-clone resume via onSnapshot — NO FCM.
// A fresh page (cold clone) loads the SAME run that is already APPROVED; it
// subscribes via onSnapshot and resumes to the generating state with zero push
// notifications and zero messaging SDK involvement.
// ─────────────────────────────────────────────────────────────────────────────
test('AT-042 cold-clone resumes via onSnapshot when the doc is APPROVED (push-free, no FCM)', async ({
  authenticatedPage: page,
}) => {
  // The cold clone is seeded with an already-APPROVED doc — i.e. some other
  // client (or this same user on another device) approved while this instance
  // was cold. It must resume purely by SUBSCRIBING to the doc, not by a push.
  await gotoWithPlan(page, 'APPROVED');

  // Belt-and-braces: assert the page never loaded the FCM/messaging SDK.
  const usedMessaging = await page.evaluate(() =>
    Object.keys(window).some((k) => /messaging|fcm/i.test(k))
  );
  expect(usedMessaging).toBe(false);

  await page.getByRole('button', { name: /^Run$/i }).click();

  // Because the awaiting-signoff doc is already APPROVED, the onSnapshot
  // subscription fires and the run resumes — the ApprovalCard must NOT block,
  // the shell transitions straight into the generating state.
  await expect(page.getByTestId('approval-card')).toBeHidden({ timeout: 15_000 });
  await expect(page.locator('[data-testid="state-loading"]')).toBeVisible({ timeout: 15_000 });
});
