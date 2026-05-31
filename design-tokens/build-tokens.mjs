// Atelier DTCG → multi-platform token fan-out (AT-050, PRD §7A.7).
// Style Dictionary v4 (ESM). Consumes the DTCG `tokens.json` ($value/$type,
// auto-detected) and emits CSS custom properties, a Tailwind-consumable JS
// module, Swift, and Kotlin (Compose) — the §7A.7 handoff bundle's code outputs.
// Run: `npm run build:tokens` (node >= 20). API verified via context7:
// new StyleDictionary(config) + await buildAllPlatforms().
import StyleDictionary from 'style-dictionary';

const sd = new StyleDictionary({
  source: ['design-tokens/tokens.json'],
  platforms: {
    css: {
      transformGroup: 'css',
      buildPath: 'design-tokens/build/css/',
      files: [{ destination: 'variables.css', format: 'css/variables' }],
    },
    tailwind: {
      transformGroup: 'js',
      buildPath: 'design-tokens/build/tailwind/',
      files: [{ destination: 'tokens.js', format: 'javascript/es6' }],
    },
    swift: {
      transformGroup: 'ios-swift',
      buildPath: 'design-tokens/build/swift/',
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
      buildPath: 'design-tokens/build/kotlin/',
      files: [
        {
          destination: 'AtelierTokens.kt',
          format: 'compose/object',
          options: { className: 'AtelierTokens', packageName: 'dev.atelier.tokens' },
        },
      ],
    },
  },
});

await sd.buildAllPlatforms();
