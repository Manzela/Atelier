/**
 * P0 (delete-mock-views) — StitchClientShell credibility/security contract.
 *
 * Pins the removal of three fabricated GCP-console mock views (IAM, Billing,
 * Model Registry) that shipped hardcoded, audience-misleading data — most
 * critically a FABRICATED "API key" minted live from the real Firebase ID token
 * (`at_live_${user.token.substring(0, 32)}`, a token-handling smell) and a
 * hardcoded "~200,000 tokens consumed (4.0%)" billing meter. Deleting them
 * closes both the overclaim/credibility risk and the token-exfiltration smell.
 *
 * RUNNER NOTE (verified): this project has NO unit-test runner installed — no
 * vitest, no jest, no @testing-library/react (see package.json; the only test
 * tooling is `@playwright/test` with `testDir: './e2e'`). Following the existing
 * `a2ui/atelierCatalog.test.tsx` precedent, this file holds a STATIC source
 * contract written runner-AGNOSTIC so it:
 *   (a) typechecks under the existing `tsc --noEmit` and lints clean under
 *       `eslint src/` (imports only Node built-ins — no uninstalled deps),
 *   (b) auto-registers with a `describe`/`it` runner IF one is later added
 *       (vitest/jest), via a runtime feature-probe on `globalThis`, and
 *   (c) can be invoked directly via the exported `runStitchShellSecurityContract()`.
 *
 * Playwright will NOT collect this file (its `testDir` is `./e2e`), so it is
 * inert during the e2e run.
 *
 * The contract reads the component's own source at test time, so it FAILS if any
 * of the deleted blocks (or the fabricated key) are ever reintroduced.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

/** Minimal, dependency-free assertion (no node:assert / chai needed). */
function assert(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(`[StitchClientShell security contract] ${message}`);
  }
}

/**
 * The full static contract. Throws on the first violation. Exported so a runner,
 * a CI script, or another module can invoke it directly.
 */
export function runStitchShellSecurityContract(): void {
  const source = readFileSync(join(__dirname, 'StitchClientShell.tsx'), 'utf8');

  // (a) The fabricated API key — minted from the live Firebase token — is gone.
  //     This is the token-handling smell; its presence is a hard fail.
  assert(
    !source.includes('at_live_'),
    'fabricated "at_live_" API key (minted from the Firebase token) must not appear in the source'
  );
  assert(
    !/user\.token\.substring/.test(source),
    'user.token must not be sliced into a displayed/"copied" credential'
  );

  // (b) The hardcoded billing meter ("~200,000 tokens consumed (4.0%)") is gone.
  assert(
    !/200,000 tokens consumed/.test(source),
    'hardcoded "200,000 tokens consumed (4.0%)" mock meter must not appear in the source'
  );
  assert(
    !/Approximately 200,000 tokens/.test(source),
    'hardcoded mock consumption copy must not appear in the source'
  );

  // (c) The three mock views are removed from the DashboardView union — the only
  //     reachable view is 'generate'.
  assert(
    /type DashboardView = 'generate';/.test(source),
    "DashboardView union must collapse to exactly 'generate' (no iam/billing/models)"
  );

  // (d) No render branch or nav handler references the deleted views.
  for (const v of ['iam', 'billing', 'models'] as const) {
    assert(
      !new RegExp(`view === '${v}'`).test(source),
      `no "view === '${v}'" render branch may remain`
    );
    assert(
      !new RegExp(`setView\\('${v}'\\)`).test(source),
      `no "setView('${v}')" nav handler may remain`
    );
  }
}

// --- Runner-agnostic auto-registration -------------------------------------
// If a `describe`/`it` test runner (vitest/jest) is present at load time, register
// the contract as a proper test case. Otherwise this module is import-inert. We
// probe `globalThis` so we neither import nor type-reference runner globals —
// keeping `tsc`/`eslint` green without a runner.
type TestFn = (name: string, fn: () => void) => void;
type DescribeFn = (name: string, fn: () => void) => void;
const g = globalThis as unknown as { describe?: DescribeFn; it?: TestFn; test?: TestFn };
const registerTest = g.it ?? g.test;
if (typeof g.describe === 'function' && typeof registerTest === 'function') {
  g.describe('StitchClientShell (P0 delete-mock-views contract)', () => {
    registerTest(
      'no fabricated API key, no mock billing meter, no iam/billing/models views',
      () => {
        runStitchShellSecurityContract();
      }
    );
  });
}
