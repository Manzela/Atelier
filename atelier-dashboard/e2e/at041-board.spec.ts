/**
 * AT-041 Playwright acceptance suite — Kanban Board (/board).
 *
 * The board is the visual task pipeline. It READS the §7A.5 task docs that the
 * AT-020b emitter writes at tenants/{tenant_id}/projects/{id}/tasks/{task_id}
 * and renders a 6-column drag-drop board over a Firestore `onSnapshot`
 * subscription. The exact ordered column set (single-sourced from
 * atelier-core BoardColumnId) is:
 *
 *     [Brief, Decompose, Awaiting Sign-off, Generating, QA, Done]
 *
 * Acceptance (features.json AT-041 / build plan):
 *   1. A /board route renders 6 column containers for the exact ordered set.
 *   2. Cards come from Firestore `onSnapshot` of the tasks/{id} docs; the
 *      statusLine is shown and carries the active agentRole for >=1 snapshot of
 *      a Generating card.
 *   3. Manual drag persists ONE doc with a valid LexoRank (strictly between its
 *      new neighbours).
 *   4. onSnapshot observes >=6 distinct column states for the lead card (the
 *      board reflects the full lifecycle).
 *
 * Hermetic. Like AT-042, the Firestore layer is driven by an in-page shim
 * (`window.__ATELIER_FIRESTORE__`) installed before navigation. The shim mirrors
 * the production `subscribeTasks` / `updateTaskColumn` contract (onSnapshot
 * semantics over an in-memory tasks collection) so the board is provable WITHOUT
 * a live Firestore project and WITHOUT an emulator. Production code uses the real
 * firebase/firestore `onSnapshot` + `updateDoc` (see src/lib/firestore-board.ts).
 *
 * The shim also exposes `__advance()` (drives the lead card forward one column,
 * fires the listeners — i.e. replays the AT-020b autonomous lifecycle) and
 * `__dump()` (returns the current tasks collection so the test can assert the
 * persisted columnId + rank after a manual drag).
 */
import { test, expect } from './fixtures';
import type { Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

// The exact ordered 6-column set — mirrors atelier-core BoardColumnId EXACTLY.
const COLUMNS = ['Brief', 'Decompose', 'Awaiting Sign-off', 'Generating', 'QA', 'Done'] as const;

// The board reads tenant from the localStorage session (MOCK_USER.tenant_id ===
// 't1' via fixtures.ts) and project from the `?project=` query param. The shim
// keys its in-memory tasks collection by task_id, so only the project param is
// passed on navigation.
const PROJECT_ID = 'p1';

// ── In-page Firestore shim (board contract) ───────────────────────────────────
// Installed before navigation. Provides the exact contract firestore-board.ts
// consumes plus two test helpers (__advance / __dump). The store is an in-memory
// tasks collection keyed by task_id; subscribeTasks fires immediately (real
// onSnapshot behaviour) and on every subsequent change.
function installBoardShim() {
  return (init: { columns: readonly string[]; leadTaskId: string }) => {
    type TaskDoc = {
      task_id: string;
      run_id: string;
      columnId: string;
      agentRole: string;
      statusLine: string;
      rank: string;
      [k: string]: unknown;
    };
    type Listener = (docs: TaskDoc[]) => void;

    // A tiny base-36 midpoint LexoRank, matching the production TS port — used
    // by the shim to seed lane ranks. The production updateTaskColumn writes the
    // app-computed rank; the shim just stores whatever it is handed.
    const ALPHABET = '0123456789abcdefghijklmnopqrstuvwxyz';
    function rankAfter(prev: string | null): string {
      if (!prev) return 'n';
      const result: string[] = [];
      let i = 0;
      for (;;) {
        const lo = i < prev.length ? ALPHABET.indexOf(prev[i]) : 0;
        const hi = ALPHABET.length;
        const mid = Math.floor((lo + hi) / 2);
        if (mid !== lo) {
          result.push(ALPHABET[mid]);
          return result.join('');
        }
        result.push(ALPHABET[lo]);
        i += 1;
        if (i >= prev.length) {
          result.push(ALPHABET[Math.floor(ALPHABET.length / 2)]);
          return result.join('');
        }
      }
    }

    // Seed: ONE lead card at the first column (Brief). The board renders it; the
    // test then drives it forward via __advance to prove the lifecycle, plus two
    // sibling cards in other columns so drag-between-neighbours is exercisable.
    let lastRank = rankAfter(null);
    const store: Record<string, TaskDoc> = {
      [init.leadTaskId]: {
        task_id: init.leadTaskId,
        run_id: 'at041-run',
        columnId: init.columns[0],
        agentRole: 'intake',
        statusLine: 'Parsing the brief',
        rank: lastRank,
      },
    };
    // One extra Brief-column card (queue depth) + one card already sitting in the
    // SECOND column (Decompose) so a manual move of the lead card lands at the
    // Decompose tail — i.e. with a real existing neighbour, exercising the
    // between-neighbours LexoRank path (not the empty-column seed).
    lastRank = rankAfter(lastRank);
    store['card-b'] = {
      task_id: 'card-b',
      run_id: 'at041-run',
      columnId: init.columns[0],
      agentRole: 'intake',
      statusLine: 'Queued',
      rank: lastRank,
    };
    lastRank = rankAfter(lastRank);
    store['neighbour'] = {
      task_id: 'neighbour',
      run_id: 'at041-run',
      columnId: init.columns[1], // Decompose — the move destination
      agentRole: 'planner',
      statusLine: 'Decomposing scope',
      rank: lastRank,
    };

    const listeners = new Set<Listener>();
    const emit = () => {
      const docs = Object.values(store).map((d) => ({ ...d }));
      listeners.forEach((cb) => cb(docs));
    };

    // The role each column advertises as the lifecycle advances (mirrors the
    // AT-020b emitter's per-column agentRole; Generating carries the role in the
    // statusLine per U6).
    const ROLE_BY_COLUMN: Record<string, string> = {
      Brief: 'intake',
      Decompose: 'planner',
      'Awaiting Sign-off': 'signoff',
      Generating: 'ui_design',
      QA: 'judge',
      Done: 'orchestrator',
    };

    const w = window as unknown as {
      __ATELIER_FIRESTORE__: {
        subscribeTasks: (
          tenant: string,
          project: string,
          cb: Listener,
          onError?: (e: Error) => void
        ) => () => void;
        updateTaskColumn: (
          tenant: string,
          project: string,
          taskId: string,
          patch: { columnId: string; rank: string }
        ) => Promise<void>;
        __advance: () => void;
        __dump: () => Record<string, TaskDoc>;
        /** GAP-3 oracle: every (tenant, project) pair the board subscribed with. */
        __subscriptions: { tenant: string; project: string }[];
      };
    };

    w.__ATELIER_FIRESTORE__ = {
      __subscriptions: [],
      subscribeTasks(tenant, project, cb) {
        // Record the subscription path so tests can assert the board targets
        // the SERVER-written `tenants/{t}/projects/{p}/tasks` segment (GAP-3),
        // not a client-side hardcoded default.
        w.__ATELIER_FIRESTORE__.__subscriptions.push({ tenant, project });
        listeners.add(cb);
        // onSnapshot fires immediately with the current collection.
        Promise.resolve().then(emit);
        return () => listeners.delete(cb);
      },
      updateTaskColumn(_tenant, _project, taskId, patch) {
        const doc = store[taskId];
        if (doc) {
          store[taskId] = { ...doc, ...patch };
          emit();
        }
        return Promise.resolve();
      },
      // Drive the lead card forward exactly one column (replays AT-020b).
      __advance() {
        const lead = store[init.leadTaskId];
        if (!lead) return;
        const idx = init.columns.indexOf(lead.columnId);
        if (idx < 0 || idx >= init.columns.length - 1) return;
        const nextCol = init.columns[idx + 1];
        const role = ROLE_BY_COLUMN[nextCol] ?? 'orchestrator';
        lastRank = rankAfter(lastRank);
        const statusLine =
          nextCol === 'Generating'
            ? `${role}: composing the landing surface`
            : `Working: ${nextCol}`;
        store[init.leadTaskId] = {
          ...lead,
          columnId: nextCol,
          agentRole: role,
          statusLine,
          rank: lastRank,
        };
        emit();
      },
      __dump: () => store,
    };
  };
}

async function gotoBoard(page: Page): Promise<void> {
  await page.addInitScript(installBoardShim(), {
    columns: COLUMNS,
    leadTaskId: 'lead',
  });
  await page.goto(`/board?project=${PROJECT_ID}`);
  await expect(page.getByTestId('kanban-board')).toBeVisible({ timeout: 15_000 });
}

const BOARD_SELECTOR = '[data-testid="kanban-board"]';

async function assertAxe(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page }).include(BOARD_SELECTOR).analyze();
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
// Clause 1: the board renders 6 column containers for the exact ordered set.
// ─────────────────────────────────────────────────────────────────────────────
test('AT-041 renders the exact ordered 6-column set, in document order', async ({
  authenticatedPage: page,
}) => {
  await gotoBoard(page);

  const cols = page.locator('[data-testid^="kanban-column-"]');
  await expect(cols).toHaveCount(6);

  // Each column carries an aria-label naming its canonical column; assert the
  // names appear in EXACT document order (no skips, no reordering).
  const labels = await cols.evaluateAll((nodes) => nodes.map((n) => n.getAttribute('aria-label')));
  expect(labels).toEqual(COLUMNS.map((c) => `${c} column`));

  await assertAxe(page);
});

// ─────────────────────────────────────────────────────────────────────────────
// Clause 2 + 4: cards come from onSnapshot; statusLine carries the active
// agentRole for a Generating card; onSnapshot observes >=6 distinct column
// states for the lead card across the full lifecycle.
// ─────────────────────────────────────────────────────────────────────────────
test('AT-041 cards from onSnapshot — statusLine+agentRole on Generating, >=6 lifecycle states', async ({
  authenticatedPage: page,
}) => {
  await gotoBoard(page);

  const leadCard = page.getByTestId('kanban-card-lead');

  // The lead card is initially in the Brief column (from the seeded snapshot).
  await expect(leadCard).toBeVisible();
  await expect(page.getByTestId('kanban-column-Brief')).toContainText('intake');

  // Drive the lead card through the FULL lifecycle, recording the column it
  // occupies at each snapshot — proving onSnapshot observes >=6 distinct states.
  const observed: string[] = [COLUMNS[0]];
  let generatingStatus: string | null = null;

  for (let step = 0; step < COLUMNS.length - 1; step++) {
    await page.evaluate(() => {
      (
        window as unknown as { __ATELIER_FIRESTORE__: { __advance: () => void } }
      ).__ATELIER_FIRESTORE__.__advance();
    });
    const expectedCol = COLUMNS[step + 1];
    // The lead card must now live INSIDE the expected column container (scoped
    // locator: the card with testid `kanban-card-lead` is a descendant of the
    // expected column section). This is what proves onSnapshot moved the card.
    const columnTestId = `kanban-column-${expectedCol.replace(/\s/g, '-')}`;
    await expect(
      page.locator(`[data-testid="${columnTestId}"] [data-testid="kanban-card-lead"]`)
    ).toBeVisible({ timeout: 10_000 });
    observed.push(expectedCol);

    if (expectedCol === 'Generating') {
      generatingStatus = await page.getByTestId('kanban-card-lead-status').innerText();
    }
  }

  // Clause 4: >=6 distinct column states observed for the lead card.
  expect(new Set(observed).size).toBeGreaterThanOrEqual(6);
  expect(observed).toEqual([...COLUMNS]);

  // Clause 2: the Generating snapshot's statusLine carries the active agentRole.
  expect(generatingStatus, 'no Generating snapshot captured').not.toBeNull();
  expect(generatingStatus).toContain('ui_design');

  await assertAxe(page);
});

// ─────────────────────────────────────────────────────────────────────────────
// Clause 3: a manual drag persists ONE doc with a valid LexoRank (strictly
// between its new neighbours), via keyboard-operable move (a11y path).
// ─────────────────────────────────────────────────────────────────────────────
test('AT-041 manual move persists one doc with a between-neighbours LexoRank', async ({
  authenticatedPage: page,
}) => {
  await gotoBoard(page);

  // Capture the pre-move ranks of the cards already in the Decompose column so we
  // can assert the moved card's rank sorts strictly between two neighbours. The
  // seed put card-b and card-c in Brief; advance the lead so Decompose has cards,
  // then move card-b into Decompose between neighbours. Simpler: move the lead
  // card from Brief to Decompose via keyboard and assert its persisted rank is a
  // valid, non-empty LexoRank string that differs from the original.

  const before = await page.evaluate(() => {
    const w = window as unknown as {
      __ATELIER_FIRESTORE__: { __dump: () => Record<string, { columnId: string; rank: string }> };
    };
    return w.__ATELIER_FIRESTORE__.__dump();
  });

  // Keyboard-operable move: focus the lead card, pick it up, move right one
  // column (Brief -> Decompose), drop. The board's onDrop computes a LexoRank
  // between the destination column's neighbours and persists via updateTaskColumn.
  const leadCard = page.getByTestId('kanban-card-lead');
  await leadCard.focus();
  await page.keyboard.press('Enter'); // pick up
  await page.keyboard.press('ArrowRight'); // move to the next column
  await page.keyboard.press('Enter'); // drop

  // The persisted doc moved to Decompose with a fresh, valid LexoRank: the lead
  // card now renders inside the Decompose column (scoped descendant locator).
  await expect(
    page.locator('[data-testid="kanban-column-Decompose"] [data-testid="kanban-card-lead"]')
  ).toBeVisible({ timeout: 10_000 });

  const after = await page.evaluate(() => {
    const w = window as unknown as {
      __ATELIER_FIRESTORE__: { __dump: () => Record<string, { columnId: string; rank: string }> };
    };
    return w.__ATELIER_FIRESTORE__.__dump();
  });

  // Exactly ONE doc changed column (the lead card) — a single-doc persist.
  const moved = Object.keys(after).filter((k) => after[k].columnId !== before[k].columnId);
  expect(moved).toEqual(['lead']);
  expect(after.lead.columnId).toBe('Decompose');

  // The new rank is a valid, non-empty base-36 LexoRank string.
  const newRank = after.lead.rank;
  expect(newRank).toMatch(/^[0-9a-z]+$/);
  expect(newRank.length).toBeGreaterThan(0);

  // Between-neighbours invariant: Decompose already held `neighbour`; the moved
  // card lands at the column tail, so its rank must sort STRICTLY AFTER the
  // existing neighbour's rank (lexicographic) — and the neighbour is unchanged.
  const neighbourRank = after.neighbour.rank;
  expect(after.neighbour.columnId).toBe('Decompose');
  expect(neighbourRank).toBe(before.neighbour.rank);
  expect(newRank > neighbourRank).toBe(true);

  await assertAxe(page);
});

// ─────────────────────────────────────────────────────────────────────────────
// GAP-3: without a `?project=` override, the board resolves its project id from
// GET /v1/platform/topology (`project_id` — the Firestore path segment the
// server-side AT-020b emitter actually writes under), NEVER a client-side
// hardcoded default. The `?project=` override path is exercised by every other
// test in this file (gotoBoard navigates with `?project=`).
//
// bypassCSP: the production-built dashboard ships an S8-hardened CSP whose
// connect-src deliberately drops http://localhost:* — correct for the deployed
// app (the API is reached via the *.autonomous-agent.dev origins, which ARE
// allow-listed), but it blocks this hermetic suite's route-mocked fetch to the
// e2e default API origin (http://localhost:8000) before page.route can answer.
// The CSP itself is not the contract under test here; the project-id plumbing is.
// ─────────────────────────────────────────────────────────────────────────────
test.describe('AT-041/GAP-3 — board project-id resolution', () => {
  test.use({ bypassCSP: true });

  test('/board without ?project= subscribes with the server-declared project id', async ({
    authenticatedPage: page,
  }) => {
    const CANONICAL_PROJECT = 'atelier-build-2026';

    // Hermetic platform API: fulfill /v1/platform/topology (and its CORS
    // preflight — authedGet sends an Authorization header, which forces one)
    // with the real response shape carrying the server-declared project_id.
    await page.route('**/v1/platform/topology', async (route) => {
      if (route.request().method() === 'OPTIONS') {
        await route.fulfill({
          status: 204,
          headers: {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, OPTIONS',
            'Access-Control-Allow-Headers': 'authorization, accept',
          },
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: { 'Access-Control-Allow-Origin': '*' },
        body: JSON.stringify({
          available: true,
          kind: 'static_pipeline_dag',
          project_id: CANONICAL_PROJECT,
          nodes: [],
          edges: [],
        }),
      });
    });

    await page.addInitScript(installBoardShim(), {
      columns: COLUMNS,
      leadTaskId: 'lead',
    });
    await page.goto('/board');

    // The board renders once tenant (localStorage session) + project (topology
    // fetch) are both resolved — no override, no hardcoded default.
    await expect(page.getByTestId('kanban-board')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId('kanban-card-lead')).toBeVisible();

    // The real contract: the Firestore subscription targets
    // tenants/{MOCK_USER.tenant_id}/projects/{server-declared project_id}/tasks.
    const subscriptions = await page.evaluate(() => {
      const w = window as unknown as {
        __ATELIER_FIRESTORE__: { __subscriptions: { tenant: string; project: string }[] };
      };
      return w.__ATELIER_FIRESTORE__.__subscriptions;
    });
    expect(subscriptions).toContainEqual({ tenant: 't1', project: CANONICAL_PROJECT });
    // And it never subscribed with the legacy fabricated default.
    expect(subscriptions.map((s) => s.project)).not.toContain('p1');
  });
});
