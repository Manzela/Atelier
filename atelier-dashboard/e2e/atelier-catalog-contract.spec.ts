/**
 * ADR-0024 / P0.4 (G4) — A2UI catalog allowlist contract, EXECUTED.
 *
 * `src/components/a2ui/atelierCatalog.test.tsx` defines the trusted-component
 * allowlist contract (the A2UI security perimeter: exactly Card/Column/Row/Text/
 * Divider/List, no untrusted type leaks in) but is collected by NO runner — this
 * project has no vitest/jest, and Playwright's `testDir` is `./e2e`, so a
 * `*.test.tsx` under `src/` never runs. The contract therefore asserted nothing.
 *
 * This spec invokes the exported `runAtelierCatalogContract()` so the allowlist
 * contract actually executes in CI (`npm run test:e2e`). A regression that adds an
 * untrusted component type to the catalog — an XSS/injection surface for the A2UI
 * renderer — now fails the suite. The contract reads only catalog METADATA
 * (component keys, names, schema presence, render typeof) and touches no DOM, so
 * it runs as a plain node-side assertion inside the Playwright worker.
 */
import { test } from '@playwright/test';
import { runAtelierCatalogContract } from '../src/components/a2ui/atelierCatalog.test';

test.describe('A2UI catalog allowlist contract (G4)', () => {
  test('catalog id and the exact 6-component trusted allowlist hold', () => {
    // Throws on the first violation; an uncaught throw fails the test.
    runAtelierCatalogContract();
  });
});
