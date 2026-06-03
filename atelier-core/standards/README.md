# Standards packs (seed corpus)

Seed artifacts for Atelier's "apply the domain's Tier-1 standards by default" feature (AT-025 / §3.5 / ADR-0021). The executor relocates these into `atelier-core/standards/` during the build. **Project-scoped, not global config** — only the cross-cutting pack is `scope: global`; every domain pack is loaded _only_ when the BriefSpec project-type matches, so a checkout standard never fires on a marketing page.

## Schema (one flat array of standard objects — no taxonomy, no ontology)

```
{ id, rule (<=140-char imperative), check, threshold, source_url, source_title, trust (0..1), year, scope }
```

- **`check`** routes the standard to its enforcer: `gate-axis:<axe|lighthouse-lab|token-fidelity>` → the Layer-1 deterministic gate; `judge` → the multi-axis critique panel; `manual` → human-on-the-loop review. A standard is not "stored prose" — its `check` field is how it becomes enforceable.
- **`trust`** seeds the WRAI trust score (1.0 = canonical body: w3.org / web.dev / developers.google.com).
- **`scope`** = `global` (cross-cutting) or the project-type key the pack applies to.

## WRAI lifecycle (ADR-0011)

WRAI refreshes packs by **append-and-supersede on `id`** — it overwrites a stale row or adds a new one (e.g. surfacing a WCAG criterion the user didn't know existed), and **never deletes**. This is how Atelier surfaces "what the user doesn't know they don't know" before scope-lock.

## Critical framing — Lighthouse is a LAB PROXY, not the Core Web Vitals pass condition

The binding CWV pass condition is **field data at the 75th percentile (CrUX)**: LCP ≤2.5s, INP ≤200ms, CLS ≤0.1. A freshly generated page has no field data at generation time, so the deterministic gate uses **Lighthouse-lab INP/TBT/LCP/CLS as the best available pre-deploy oracle**, while the pack records the p75 field thresholds as the SLO the proxy approximates. **INP replaced FID on 2024-03-12** — all FID-era language is retired. A perfect Lighthouse score does not by itself mean the page passes CWV.

## Packs

| File                                | scope              | source authority                       | trust seed |
| ----------------------------------- | ------------------ | -------------------------------------- | ---------- |
| `cross-cutting.standards.json`      | global             | W3C WCAG 2.2, web.dev/Google CWV, DTCG | 1.0        |
| `ecommerce-checkout.standards.json` | ecommerce-checkout | Baymard, evilmartians                  | 0.95       |
| `fintech-trust.standards.json`      | fintech            | practitioner + regulatory pointers     | 0.80       |
| `saas-dashboard.standards.json`     | saas-dashboard     | NN/g, TPGi                             | 0.85       |
| `marketing-landing.standards.json`  | marketing-landing  | NN/g, web.dev, CRO consensus           | 0.85       |

Jurisdiction-specific regulation (PSD3/PSR, Consumer Duty, US state law) is **confirmed by WRAI per-tenant, never hard-coded** — it is geography-bound and changes faster than any seed.
