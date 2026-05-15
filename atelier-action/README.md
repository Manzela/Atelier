# Atelier Design QA — GitHub Action

Run Atelier convergence on UI files changed in your PR. Post a verdict comment with per-axis scores + suggested fixes.

## Status

**Phase 0** — `action.yml` scaffolded; implementation (TypeScript build → `dist/index.js`) is a Phase 3 deliverable (Jun 1).

Will be published to GitHub Marketplace at v1.0.0 release on 2026-06-03.

## Usage (post-publication)

```yaml
# .github/workflows/atelier.yml
name: Design QA
on:
  pull_request:
    paths:
      - '**/*.html'
      - '**/*.jsx'
      - '**/*.tsx'
      - '**/*.css'

jobs:
  atelier:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: Manzela/atelier-action@v1
        with:
          api-key: ${{ secrets.ATELIER_API_KEY }}
          convergence-bar: 'production' # or 'ship-it' or 'perfectionist'
          comment-on-pr: 'true'
          fail-on-non-convergence: 'false' # set true to enforce as PR gate
```

## See also

- [Atelier PRD §5 — N9 Open Eval Adapters](../docs/superpowers/specs/2026-05-14-atelier-prd.md)
- [Get an API key](https://atelier.dev/settings/api-keys)
