#!/usr/bin/env node
/**
 * check-a2ui-skew.mjs — @a2ui/web_core dependency-skew guard (G7, ADR-0024).
 *
 * WHY THIS EXISTS
 * ---------------
 * The dashboard intentionally carries TWO copies of `@a2ui/web_core`:
 *   - 0.9.2  hoisted to the workspace root (pulled up to satisfy
 *            `@a2ui/markdown-it@0.0.4`'s `^0.9.2`)
 *   - 0.10.0 nested under `@a2ui/react@0.10.0` (its paired core)
 *
 * The renderer in
 *   atelier-dashboard/src/components/a2ui/A2uiDesignSystemPanel.tsx
 * (see the "web_core version-bridge" note around lines 46-63) bridges that gap
 * with `as unknown as` casts. Those casts are runtime-safe ONLY because the
 * `SurfaceModel` / `Catalog` / `DataModel` declarations are byte-identical
 * across exactly 0.9.2 and 0.10.0. A drift to a THIRD version (e.g. a 0.11.0
 * bump of `@a2ui/react`, or `@a2ui/markdown-it` moving off `^0.9.2`) would
 * silently invalidate those nominal-only casts.
 *
 * Decision (ADR-0024): GUARD the skew, do NOT declare `@a2ui/web_core` directly.
 * npm cannot dedupe across the 0.9.2 / 0.10.0 major-pin gap, so a direct
 * declaration would only ADD a third coordinate, not collapse the pair. This
 * script makes the documented two-version invariant a machine-checked CI gate.
 *
 * CONTRACT (cross-track): the resolved `@a2ui/web_core` version SET must equal
 * EXACTLY {0.9.2, 0.10.0}. Any track that bumps `@a2ui/react`,
 * `@a2ui/markdown-it`, or `@a2ui/web_core` MUST update `EXPECTED_VERSIONS`
 * below in the same PR and re-verify the byte-identical-decls claim in the
 * version-bridge note.
 *
 * Stdlib-only ESM (node:child_process). No external dependencies.
 * Exit 0 on the expected pair; exit 1 with a structured diff on any drift.
 */

import { execFileSync } from 'node:child_process';

/**
 * The expected resolved version SET of `@a2ui/web_core` across the whole tree.
 * Keep in sync with package-lock.json and the version-bridge note in
 * A2uiDesignSystemPanel.tsx.
 */
const EXPECTED_VERSIONS = ['0.9.2', '0.10.0'];

/**
 * Which importer is expected to pull each version. Used only to make the
 * failure message actionable — it names which dependency drifted.
 * @type {Record<string, string>}
 */
const EXPECTED_IMPORTERS = {
  '0.9.2': '@a2ui/markdown-it (^0.9.2, hoisted to root)',
  '0.10.0': '@a2ui/react (0.10.0, nested)',
};

const TARGET_PACKAGE = '@a2ui/web_core';
const VERSION_BRIDGE_NOTE =
  'atelier-dashboard/src/components/a2ui/A2uiDesignSystemPanel.tsx (web_core version-bridge note, ~lines 46-63)';

/**
 * Run `npm ls @a2ui/web_core --json --all` and return the parsed JSON.
 *
 * `npm ls` exits non-zero whenever the tree has ANY extraneous/peer/missing
 * advisory — even when the queried package itself is fine — but it still emits
 * the dependency JSON on stdout. So we must read the JSON off the thrown
 * error's `.stdout` rather than relying on a zero exit code. We never silently
 * swallow: a genuine parse failure (no JSON anywhere) is logged with context
 * and re-thrown.
 *
 * @returns {Record<string, unknown>} parsed `npm ls` JSON tree
 */
function runNpmLs() {
  /** @type {string} */
  let stdout;
  try {
    stdout = execFileSync('npm', ['ls', TARGET_PACKAGE, '--json', '--all'], {
      encoding: 'utf8',
      maxBuffer: 64 * 1024 * 1024,
    });
  } catch (error) {
    // npm ls returned a non-zero exit (common: extraneous/peer advisories).
    // The dependency JSON is still on the error's stdout — recover it.
    const recovered =
      error && typeof error === 'object' && 'stdout' in error
        ? /** @type {{ stdout?: unknown }} */ (error).stdout
        : undefined;
    if (typeof recovered === 'string' && recovered.trim().length > 0) {
      stdout = recovered;
    } else {
      const reason = error instanceof Error ? error.message : String(error);
      console.error(
        `[check-a2ui-skew] FATAL: \`npm ls ${TARGET_PACKAGE} --json --all\` ` +
          `produced no parseable stdout. Underlying error: ${reason}`
      );
      throw error instanceof Error ? error : new Error(`npm ls failed: ${reason}`);
    }
  }

  try {
    return JSON.parse(stdout);
  } catch (parseError) {
    const reason = parseError instanceof Error ? parseError.message : String(parseError);
    console.error(
      `[check-a2ui-skew] FATAL: could not JSON.parse \`npm ls\` output. ` + `Reason: ${reason}`
    );
    console.error(`[check-a2ui-skew] First 500 chars of stdout:\n${stdout.slice(0, 500)}`);
    throw parseError instanceof Error ? parseError : new Error(`JSON.parse failed: ${reason}`);
  }
}

/**
 * Recursively walk an `npm ls --json` dependency tree, collecting every
 * resolved version of TARGET_PACKAGE keyed by the package name at that node.
 *
 * @param {unknown} node a node in the `npm ls` tree (has optional `.dependencies`)
 * @param {string | null} nodeName the package name of `node`, or null for the root
 * @param {Set<string>} found accumulator of resolved versions
 * @returns {void}
 */
function collectVersions(node, nodeName, found) {
  if (node === null || typeof node !== 'object') {
    return;
  }
  const record = /** @type {Record<string, unknown>} */ (node);

  if (nodeName === TARGET_PACKAGE && typeof record.version === 'string') {
    found.add(record.version);
  }

  const deps = record.dependencies;
  if (deps !== null && typeof deps === 'object') {
    for (const [childName, childNode] of Object.entries(
      /** @type {Record<string, unknown>} */ (deps)
    )) {
      collectVersions(childNode, childName, found);
    }
  }
}

/**
 * @param {string[]} arr
 * @returns {string[]} sorted unique copy
 */
function sortedUnique(arr) {
  return [...new Set(arr)].sort();
}

function main() {
  const tree = runNpmLs();

  /** @type {Set<string>} */
  const found = new Set();
  collectVersions(tree, null, found);

  const foundSorted = sortedUnique([...found]);
  const expectedSorted = sortedUnique(EXPECTED_VERSIONS);

  if (foundSorted.length === 0) {
    console.error(
      `[check-a2ui-skew] FAIL: no ${TARGET_PACKAGE} resolved in the tree. ` +
        `Expected exactly {${expectedSorted.join(', ')}}. ` +
        `Did the install run? See ${VERSION_BRIDGE_NOTE}.`
    );
    process.exit(1);
  }

  const matches =
    foundSorted.length === expectedSorted.length &&
    foundSorted.every((v, i) => v === expectedSorted[i]);

  if (matches) {
    console.log(
      `[check-a2ui-skew] OK: ${TARGET_PACKAGE} resolves to exactly ` +
        `{${foundSorted.join(', ')}} — the documented two-version bridge ` +
        `(0.9.2 ← @a2ui/markdown-it, 0.10.0 ← @a2ui/react) is intact.`
    );
    process.exit(0);
  }

  const unexpected = foundSorted.filter((v) => !expectedSorted.includes(v));
  const missing = expectedSorted.filter((v) => !foundSorted.includes(v));

  console.error(`[check-a2ui-skew] FAIL: ${TARGET_PACKAGE} version skew drift.`);
  console.error(`  expected set : {${expectedSorted.join(', ')}}`);
  console.error(`  resolved set : {${foundSorted.join(', ')}}`);
  if (unexpected.length > 0) {
    console.error(
      `  unexpected   : ${unexpected
        .map((v) => `${v} (importer unknown — investigate)`)
        .join(', ')}`
    );
  }
  if (missing.length > 0) {
    console.error(
      `  missing      : ${missing
        .map((v) => `${v} (was ${EXPECTED_IMPORTERS[v] ?? 'expected'})`)
        .join(', ')}`
    );
  }
  console.error(
    `  The \`as unknown as\` casts in the renderer are runtime-safe ONLY for ` +
      `the exact pair {${expectedSorted.join(', ')}}. If this drift is ` +
      `intentional, update EXPECTED_VERSIONS in this file AND re-verify the ` +
      `byte-identical-decls claim in:\n    ${VERSION_BRIDGE_NOTE}`
  );
  process.exit(1);
}

main();
