/**
 * ADR-0024 / P0.4 (G4) — Atelier catalog contract test.
 *
 * RUNNER NOTE (verified): this project has NO unit-test runner installed — no
 * vitest, no jest, no @testing-library/react (see package.json; the only test
 * tooling is `@playwright/test` with `testDir: './e2e'`). Per the G4 spec, the
 * catalog's DOM-render assertions (Text h3 → <h3>, List → <ul><li>, Card →
 * <article>, Divider → <hr>, accessibility.label → aria-label) are therefore
 * FOLDED INTO the e2e (`e2e/a2ui-render.spec.ts`), which renders `atelierCatalog`
 * in a real Chromium DOM and asserts the semantic roles + axe-cleanliness.
 *
 * This file holds the STATIC contract assertions that need no DOM — the catalog
 * id and the exact 6-component allowlist — written runner-AGNOSTIC so they:
 *   (a) typecheck under the existing `tsc --noEmit` and lint clean under
 *       `eslint src/` (the file imports ONLY the catalog — no uninstalled deps),
 *   (b) auto-register with a `describe`/`it` runner IF one is later added
 *       (vitest/jest), via a runtime feature-probe on `globalThis` (no import of
 *       runner globals, so no type/lint breakage today), and
 *   (c) can be invoked directly via the exported `runAtelierCatalogContract()`.
 *
 * Playwright will NOT collect this file (its `testDir` is `./e2e`), so it is
 * inert during the e2e run.
 */

import { atelierCatalog, ATELIER_CATALOG_ID } from './atelierCatalog';

/** The trusted allowlist — must match the Python `ATELIER_CATALOG_COMPONENTS`. */
const EXPECTED_COMPONENTS = ['Card', 'Column', 'Row', 'Text', 'Divider', 'List'] as const;

/** Minimal, dependency-free assertion (no node:assert / chai needed). */
function assert(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(`[atelierCatalog contract] ${message}`);
  }
}

/**
 * The full static contract. Throws on the first violation. Exported so a runner,
 * a CI script, or another module can invoke it directly.
 */
export function runAtelierCatalogContract(): void {
  // (a) The catalog id is the canonical, byte-identical cross-track constant.
  assert(
    atelierCatalog.id === ATELIER_CATALOG_ID,
    `catalog.id (${atelierCatalog.id}) must equal ATELIER_CATALOG_ID (${ATELIER_CATALOG_ID})`
  );
  assert(
    ATELIER_CATALOG_ID ===
      'https://atelier.autonomous-agent.dev/a2ui/catalogs/design-system/v1.json',
    'ATELIER_CATALOG_ID drifted from the canonical cross-track value'
  );

  // (b) The catalog exposes EXACTLY the 6 trusted component types — the security
  //     perimeter. `.components` is a ReadonlyMap<string, …> keyed by name.
  const keys = Array.from(atelierCatalog.components.keys()).sort();
  const expected = [...EXPECTED_COMPONENTS].sort();
  assert(
    keys.length === expected.length && keys.every((k, i) => k === expected[i]),
    `catalog.components keys [${keys.join(', ')}] must be exactly [${expected.join(', ')}]`
  );

  // (c) Each component's registered `.name` matches its map key (no silent rename).
  for (const name of EXPECTED_COMPONENTS) {
    const impl = atelierCatalog.components.get(name);
    assert(impl !== undefined, `component "${name}" must be registered in the catalog`);
    assert(impl!.name === name, `component "${name}" has a mismatched .name (${impl!.name})`);
    assert(typeof impl!.render === 'function', `component "${name}" must expose a render function`);
    assert(impl!.schema !== undefined, `component "${name}" must expose a schema`);
  }

  // (d) NO extra (untrusted) component types leaked into the allowlist.
  for (const key of keys) {
    assert(
      (EXPECTED_COMPONENTS as readonly string[]).includes(key),
      `unexpected component "${key}" in the catalog — only the 6 trusted types are allowed`
    );
  }
}

// --- Runner-agnostic auto-registration -------------------------------------
// If a `describe`/`it` test runner (vitest/jest) is present at load time, register
// the contract as a proper test case. Otherwise this module is import-inert (the
// e2e covers the DOM assertions). We probe `globalThis` so we neither import nor
// type-reference runner globals — keeping `tsc`/`eslint` green without a runner.
type TestFn = (name: string, fn: () => void) => void;
type DescribeFn = (name: string, fn: () => void) => void;
const g = globalThis as unknown as { describe?: DescribeFn; it?: TestFn; test?: TestFn };
const registerTest = g.it ?? g.test;
if (typeof g.describe === 'function' && typeof registerTest === 'function') {
  g.describe('atelierCatalog (G4 static contract)', () => {
    registerTest(
      'id equals ATELIER_CATALOG_ID and exposes exactly the 6 trusted components',
      () => {
        runAtelierCatalogContract();
      }
    );
  });
}
