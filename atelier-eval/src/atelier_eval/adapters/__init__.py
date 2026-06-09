"""Eval adapters — benchmark-specific task loaders and evaluators."""

from __future__ import annotations

from atelier_eval.adapters._base import EvalAdapter, EvalResult
from atelier_eval.adapters.design2code import (
    Design2CodeTask,
    evaluate_design2code_visual_similarity,
    load_design2code_tasks,
)
from atelier_eval.adapters.frontendbench import (
    FrontendBenchTask,
    evaluate_frontendbench,
    load_frontendbench_tasks,
)
from atelier_eval.adapters.screenspot import (
    ScreenSpotTask,
    evaluate_screenspot_grounding,
    load_screenspot_tasks,
)
from atelier_eval.adapters.web2code import (
    Web2CodeTask,
    evaluate_web2code_visual_similarity,
    load_web2code_tasks,
)
from atelier_eval.adapters.webgen_bench import (
    WebGenBenchTask,
    evaluate_webgen_bench,
    load_webgen_bench_tasks,
)

__all__ = [
    "Design2CodeTask",
    "EvalAdapter",
    "EvalResult",
    "FrontendBenchTask",
    "ScreenSpotTask",
    "Web2CodeTask",
    "WebGenBenchTask",
    "evaluate_design2code_visual_similarity",
    "evaluate_frontendbench",
    "evaluate_screenspot_grounding",
    "evaluate_web2code_visual_similarity",
    "evaluate_webgen_bench",
    "load_design2code_tasks",
    "load_frontendbench_tasks",
    "load_screenspot_tasks",
    "load_web2code_tasks",
    "load_webgen_bench_tasks",
]
