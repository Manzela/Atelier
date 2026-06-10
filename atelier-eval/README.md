# atelier-eval

The Atelier evaluation suite — benchmark adapters, golden sets, and the public scoreboard infrastructure.

## Subpackages

```
src/atelier_eval/
├── adapters/             # N9 Open Eval Adapters
│   ├── webgen_bench.py   # WebGen-Bench (101 tasks / 647 test cases)
│   ├── design2code.py    # Stanford NAACL 2025 — Design2Code (484 webpages)
│   ├── web2code.py       # NeurIPS 2024 — Web2Code (1,198 screenshots)
│   ├── screenspot.py     # ScreenSpot benchmark
│   └── frontendbench.py  # FrontendBench (arXiv 2506.13832)
├── golden_sets/
│   ├── calibration.json  # Frozen 100-task calibration set (recalibration weekly)
│   └── adversarial.json  # Held-out 50-task adversarial set (pre-release)
├── runner.py             # Eval runner: pytest-style + ADK eval integration
├── scoreboard.py         # N11 — publishes results to atelier.autonomous-agent.dev/bench
└── calibration_dashboard.py  # N8 — publishes drift to atelier.autonomous-agent.dev/calibration
```

## Status

**Phase 0** — repo scaffold complete; eval suite is a Phase 2 deliverable (W2 May 22-28).

## Quick start (post-Phase-2)

```bash
pip install -e ".[dev]"
pytest tests/ -v                          # adapter unit tests
python -m atelier_eval.runner --suite webgen_bench --subset 50  # subset
python -m atelier_eval.runner --suite webgen_bench               # full 101-task suite
python -m atelier_eval.calibration_dashboard --update --alert-on-drift
```

## See also

- [Atelier PRD §16 — 10× outcome checklist](../docs/superpowers/specs/2026-05-14-atelier-prd.md)
- [Eval methodology](../docs/eval/methodology.md)
- [Public scoreboard](https://atelier.autonomous-agent.dev/bench)
- [Public calibration drift dashboard](https://atelier.autonomous-agent.dev/calibration)
