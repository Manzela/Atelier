# Core Web Vitals SLO + Lighthouse lab gate (AT-013)

Atelier gates the **Lighthouse lab proxies** and records the **field p75 SLO** as
the production target. These are deliberately distinct: a freshly generated page
has **no CrUX field data**, so the field CWV thresholds cannot be a build-time
pass condition — only the lab proxies can be asserted at gate time.

## Field SLO (p75, the production target — NOT gated at build)

| Metric | p75 target | Notes                                                                                      |
| ------ | ---------- | ------------------------------------------------------------------------------------------ |
| LCP    | ≤ 2.5 s    | Largest Contentful Paint                                                                   |
| INP    | ≤ 200 ms   | Interaction to Next Paint — **replaced FID on 2024-03-12**; no FID-era thresholds are used |
| CLS    | ≤ 0.1      | Cumulative Layout Shift                                                                    |

## Lab gate (`lighthouserc.json`, asserted via `@lhci/cli` — real LHCI syntax)

Lighthouse measures **lab** metrics on a synthetic load; it does not produce a
lab INP, so **Total Blocking Time (TBT) is the lab proxy for INP/responsiveness**.
The committed `lighthouserc.json` asserts (LHCI `assert.assertions`,
`maxNumericValue` — not an inline `--assert` string):

| Lighthouse audit           | assertion         | mirrors field   |
| -------------------------- | ----------------- | --------------- |
| `largest-contentful-paint` | ≤ 2500 ms (error) | LCP             |
| `total-blocking-time`      | ≤ 200 ms (error)  | INP (lab proxy) |
| `cumulative-layout-shift`  | ≤ 0.1 (error)     | CLS             |
| `categories:accessibility` | ≥ 0.90 (error)    | —               |
| `categories:performance`   | ≥ 0.90 (warn)     | —               |

The pure-Python **WCAG 2.2 AA contrast oracle**
(`atelier.gates.contrast.check_wcag_contrast`) gates contrast deterministically
and offline (complementing real axe-core, AT-011); **APCA is advisory and not
gated**.

**Execution:** `npm run lhci` invokes `@lhci/cli` via pinned `npx`. The live run
against the served final candidate is exercised in the AT-110 production-readiness
walkthrough; this commit lands the config, the gate, and the SLO of record.
Source: Lighthouse is a lab proxy, not the CWV pass condition; INP replaced FID
(web.dev / Chrome, 2024-03-12).
