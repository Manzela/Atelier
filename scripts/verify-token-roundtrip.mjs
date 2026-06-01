/**
 * AT-052: Token round-trip proof — code surfaces.
 *
 * Proves that a single change to design-tokens/tokens.json propagates to all
 * four Style Dictionary platform outputs (CSS, Tailwind, Swift, Kotlin).
 *
 * Strategy: deep-copy tokens.json, mutate color.primary.$value to the sentinel
 * #facade, build to a temp directory via the Style Dictionary JS API (never
 * overwriting design-tokens/build/), read each of the four outputs, and assert
 * the sentinel hex appears in each.  Exit 0 on success; exit 1 with per-file
 * diagnostics on failure.
 *
 * The sentinel (#facade) is greppable and does not collide with any token in
 * the real design system.  The script is intentionally non-vacuous: if you run
 * it against an unmodified tokens.json (without the mutation) the build will
 * contain the real #2563eb value — not #facade — and all four assertions will
 * fail.
 *
 * Run: node scripts/verify-token-roundtrip.mjs
 */

import StyleDictionary from 'style-dictionary';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// ---------------------------------------------------------------------------
// Sentinel: greppable value that must not appear in the real token set.
// ---------------------------------------------------------------------------

const SENTINEL_HEX = '#facade';

// Swift uses UIColor(red:green:blue:alpha:) with float components.
// #facade = 0xFA/0xCA/0xDE  →  250/255, 202/255, 222/255  ≈  0.980, 0.792, 0.871
// Match the FULL signature, not the red channel alone: the real token set already
// contains red:0.980 (colorSurfaceMuted has green:0.980), so a bare "0.980" match
// would be VACUOUS — it would pass even if color.primary never propagated. green:0.792
// and blue:0.871 are unique to the sentinel, so the full ordered signature proves
// color.primary specifically reached the Swift surface.
const SENTINEL_SWIFT_FRAGMENT = 'red: 0.980, green: 0.792, blue: 0.871';

// Kotlin/Compose: Color(0xffFACCADE)  — uppercase or lowercase depending on SD.
const SENTINEL_KOTLIN_FRAGMENT = 'facade'; // SD lowercases hex in compose output

// ---------------------------------------------------------------------------
// Resolve project root (the script may be called from any cwd).
// ---------------------------------------------------------------------------

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const TOKENS_SRC = path.join(ROOT, 'design-tokens', 'tokens.json');

let tempDir = null;

try {
  // -----------------------------------------------------------------------
  // 1. Load the real tokens.json and mutate a deep copy.
  // -----------------------------------------------------------------------

  const tokensRaw = fs.readFileSync(TOKENS_SRC, 'utf8');
  const tokens = JSON.parse(tokensRaw);

  // Deep-copy via round-trip serialization to avoid reference aliasing.
  const mutated = JSON.parse(tokensRaw);
  mutated.color.primary.$value = SENTINEL_HEX;

  // -----------------------------------------------------------------------
  // 2. Write the mutated tokens to a temp directory.
  // -----------------------------------------------------------------------

  tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'atelier-at052-'));
  const tempTokensPath = path.join(tempDir, 'tokens.json');
  const tempBuildPath = path.join(tempDir, 'build');
  fs.writeFileSync(tempTokensPath, JSON.stringify(mutated, null, 2));

  // -----------------------------------------------------------------------
  // 3. Build with the Style Dictionary JS API, mirroring build-tokens.mjs
  //    exactly (same platforms, transforms, formats, and options).
  // -----------------------------------------------------------------------

  const sd = new StyleDictionary({
    source: [tempTokensPath],
    platforms: {
      css: {
        transformGroup: 'css',
        buildPath: path.join(tempBuildPath, 'css') + path.sep,
        files: [{ destination: 'variables.css', format: 'css/variables' }],
      },
      tailwind: {
        transformGroup: 'js',
        buildPath: path.join(tempBuildPath, 'tailwind') + path.sep,
        files: [{ destination: 'tokens.js', format: 'javascript/es6' }],
      },
      swift: {
        transformGroup: 'ios-swift',
        buildPath: path.join(tempBuildPath, 'swift') + path.sep,
        files: [
          {
            destination: 'AtelierTokens.swift',
            format: 'ios-swift/class.swift',
            options: { className: 'AtelierTokens' },
          },
        ],
      },
      kotlin: {
        transformGroup: 'compose',
        buildPath: path.join(tempBuildPath, 'kotlin') + path.sep,
        files: [
          {
            destination: 'AtelierTokens.kt',
            format: 'compose/object',
            options: { className: 'AtelierTokens', packageName: 'dev.atelier.tokens' },
          },
        ],
      },
    },
    log: { verbosity: 'silent' },
  });

  await sd.buildAllPlatforms();

  // -----------------------------------------------------------------------
  // 4. Assert the sentinel value appears in each of the four outputs.
  // -----------------------------------------------------------------------

  const checks = [
    {
      label: 'CSS (variables.css)',
      file: path.join(tempBuildPath, 'css', 'variables.css'),
      needle: SENTINEL_HEX,
    },
    {
      label: 'Tailwind (tokens.js)',
      file: path.join(tempBuildPath, 'tailwind', 'tokens.js'),
      needle: SENTINEL_HEX,
    },
    {
      label: 'Swift (AtelierTokens.swift)',
      file: path.join(tempBuildPath, 'swift', 'AtelierTokens.swift'),
      needle: SENTINEL_SWIFT_FRAGMENT,
    },
    {
      label: 'Kotlin (AtelierTokens.kt)',
      file: path.join(tempBuildPath, 'kotlin', 'AtelierTokens.kt'),
      needle: SENTINEL_KOTLIN_FRAGMENT,
    },
  ];

  let allPassed = true;

  for (const { label, file, needle } of checks) {
    if (!fs.existsSync(file)) {
      console.error(`[AT-052] FAIL  ${label}: file not found at ${file}`);
      allPassed = false;
      continue;
    }
    const content = fs.readFileSync(file, 'utf8');
    const found = content.toLowerCase().includes(needle.toLowerCase());
    if (found) {
      console.log(`[AT-052] PASS  ${label}: sentinel "${needle}" found`);
    } else {
      console.error(`[AT-052] FAIL  ${label}: sentinel "${needle}" NOT found in output`);
      // Print the relevant line(s) for diagnostics.
      const lines = content.split('\n').filter((l) => l.toLowerCase().includes('colorprimary') || l.toLowerCase().includes('color-primary'));
      if (lines.length > 0) {
        console.error(`         relevant lines: ${lines.slice(0, 3).join(' | ')}`);
      }
      allPassed = false;
    }
  }

  if (allPassed) {
    console.log('\n[AT-052] OK — sentinel #facade propagated to all 4 code surfaces.');
    process.exit(0);
  } else {
    console.error('\n[AT-052] FAIL — propagation incomplete. See diagnostics above.');
    process.exit(1);
  }
} finally {
  // -----------------------------------------------------------------------
  // 5. Always clean up temp files, regardless of success or failure.
  // -----------------------------------------------------------------------

  if (tempDir !== null) {
    try {
      fs.rmSync(tempDir, { recursive: true, force: true });
    } catch {
      // Non-fatal: temp directory cleanup failure should not mask the real result.
      // The OS will reclaim the temp dir on next reboot.
    }
  }
}
