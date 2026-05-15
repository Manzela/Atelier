# atelier-dashboard

Live observability dashboard + time-machine iteration tree UI for Atelier.

Visual heritage: matches `pipeline-observatory` aesthetic — Apple-Grade typography, hairlines, restraint. Vanilla approach where possible (Tailwind via CDN), React + WebSocket for the live event stream.

## Features

- **Live campaign view** — surfaces queued / in-flight / converged with dependency graph
- **Time-machine iteration tree** — every iteration is a navigable node; fork from any candidate (N5 EvoDesign visualization)
- **Multi-axis judge scoreboard** — per-axis scores + confidence intervals (DEMAS-D Provenance highlights)
- **Cost meter** — per-tenant + per-session budget burn live
- **A2UI render preview** — the converged design rendered side-by-side in React + Flutter + Lit + Angular hosts

## Status

**Phase 0** — repo scaffold complete; dashboard is a Phase 2 deliverable (W2, May 22-28).

## Quick start (post-Phase-2)

```bash
npm install
npm run dev          # http://localhost:5173
npm run build
npm run typecheck
npm run test
```

## See also

- [Atelier PRD §6 System architecture](../docs/superpowers/specs/2026-05-14-atelier-prd.md)
- [pipeline-observatory](https://manzela.github.io/pipeline-observatory/) — visual heritage reference
