# atelier-eval

The Atelier evaluation suite — benchmark adapters, calibration golden sets, and public scoreboard infrastructure.

## Packages

```
src/atelier_eval/
├── adapters/
│   ├── webgen_bench.py          # WebGen-Bench (NeurIPS 2025, 101 tasks)
│   ├── design2code.py           # Design2Code (Stanford NAACL 2025, 484 webpages)
│   ├── web2code.py              # Web2Code (NeurIPS 2024, 1,198 screenshots)
│   ├── screenspot.py            # ScreenSpot visual grounding benchmark
│   └── frontendbench.py         # FrontendBench (arXiv 2506.13832, 148 tasks)
├── metrics/
│   ├── lighthouse.py            # Core Web Vitals extraction (LCP, CLS, INP)
│   └── visual_similarity.py     # SSIM perceptual similarity for visual quality
├── golden_sets/
│   ├── calibration.json         # 100-task calibration set (weekly recalibration)
│   └── adversarial.json         # 50-task held-out adversarial set (pre-release only)
├── runner.py                    # Evaluation runner with pytest-style parametrization
├── scoreboard.py                # Publishes results to bench.atelier.dev
└── calibration_dashboard.py     # Publishes calibration drift to calibration.atelier.dev
```

## Status

The package scaffold, adapter stubs, and Core Web Vitals metrics module are complete. Full dataset wiring and live benchmark runs ship in Milestone 2. See [ROADMAP.md](../ROADMAP.md) for the delivery plan.

## Quick start

```bash
pip install -e ".[dev]"
pytest tests/ -v

# Run the WebGen-Bench 50-task CI subset
python -m atelier_eval.runner --suite webgen_bench --subset 50

# Run the full WebGen-Bench suite (requires dataset download)
python -m atelier_eval.runner --suite webgen_bench

# Update and check calibration dashboard
python -m atelier_eval.calibration_dashboard --update --alert-on-drift
```

## Benchmark coverage

| Benchmark     | Source              | Tasks | Metric                          |
| ------------- | ------------------- | ----- | ------------------------------- |
| WebGen-Bench  | NeurIPS 2025        | 101   | Pass rate vs reference          |
| Design2Code   | Stanford NAACL 2025 | 484   | SSIM visual similarity          |
| Web2Code      | NeurIPS 2024        | 1,198 | GPT-4V rendering fidelity       |
| ScreenSpot    | —                   | —     | Visual grounding accuracy       |
| FrontendBench | arXiv 2506.13832    | 148   | Puppeteer interaction pass rate |

## See also

- [Evaluation methodology](../docs/eval/methodology.md)
- [Public scoreboard](https://bench.atelier.dev)
- [Calibration drift dashboard](https://calibration.atelier.dev)
