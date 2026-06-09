"""Eval runner — orchestrates benchmark execution across adapters.

Usage:
    runner = EvalRunner(data_dir="atelier-eval/data")
    results = runner.run_design2code(generated_outputs)
    scoreboard.publish(results)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atelier_eval.adapters._base import EvalResult


@dataclass
class EvalRunner:
    """Coordinates benchmark evaluation across multiple adapters.

    Dispatches generated outputs to the Design2Code, Web2Code, ScreenSpot, and
    WebGen-Bench adapters, collects their per-task results, and aggregates them
    into a single scoreboard summary.
    """

    data_dir: str
    results: list[EvalResult] = field(default_factory=list)

    def run_design2code(
        self,
        generated_outputs: dict[str, str],
    ) -> list[EvalResult]:
        """Run Design2Code evaluation on generated outputs."""
        from atelier_eval.adapters.design2code import (  # noqa: PLC0415
            evaluate_design2code_visual_similarity,
            load_design2code_tasks,
        )

        tasks = load_design2code_tasks(self.data_dir)
        results: list[EvalResult] = []
        for task in tasks:
            if task.task_id in generated_outputs:
                result = evaluate_design2code_visual_similarity(
                    task=task,
                    generated_html=generated_outputs[task.task_id],
                    data_dir=self.data_dir,
                )
                results.append(result)
        self.results.extend(results)
        return results

    def run_web2code(
        self,
        generated_outputs: dict[str, str],
    ) -> list[EvalResult]:
        """Run Web2Code evaluation on generated outputs."""
        from atelier_eval.adapters.web2code import (  # noqa: PLC0415
            evaluate_web2code_visual_similarity,
            load_web2code_tasks,
        )

        tasks = load_web2code_tasks(self.data_dir)
        results: list[EvalResult] = []
        for task in tasks:
            if task.task_id in generated_outputs:
                result = evaluate_web2code_visual_similarity(
                    task=task,
                    generated_html=generated_outputs[task.task_id],
                    data_dir=self.data_dir,
                )
                results.append(result)
        self.results.extend(results)
        return results

    def run_screenspot(
        self,
        predicted_bboxes: dict[str, list[float]],
    ) -> list[EvalResult]:
        """Run ScreenSpot grounding evaluation."""
        from atelier_eval.adapters.screenspot import (  # noqa: PLC0415
            evaluate_screenspot_grounding,
            load_screenspot_tasks,
        )

        tasks = load_screenspot_tasks(self.data_dir)
        results: list[EvalResult] = []
        for task in tasks:
            if task.task_id in predicted_bboxes:
                result = evaluate_screenspot_grounding(
                    task=task,
                    predicted_bbox=predicted_bboxes[task.task_id],
                )
                results.append(result)
        self.results.extend(results)
        return results

    def run_webgen_bench(
        self,
        generated_outputs: dict[str, str],
    ) -> list[EvalResult]:
        """Run WebGen-Bench evaluation on generated outputs."""
        from atelier_eval.adapters.webgen_bench import (  # noqa: PLC0415
            evaluate_webgen_bench,
            load_webgen_bench_tasks,
        )

        tasks = load_webgen_bench_tasks(self.data_dir)
        results: list[EvalResult] = []
        for task in tasks:
            if task.task_id in generated_outputs:
                result = evaluate_webgen_bench(
                    task=task,
                    generated_html=generated_outputs[task.task_id],
                    data_dir=self.data_dir,
                )
                results.append(result)
        self.results.extend(results)
        return results

    def summary(self) -> dict[str, float]:
        """Return aggregate pass rate and mean score."""
        if not self.results:
            return {"pass_rate": 0.0, "mean_score": 0.0}
        passed = sum(1 for r in self.results if r.passed)
        mean_score = sum(r.score for r in self.results) / len(self.results)
        return {
            "pass_rate": passed / len(self.results),
            "mean_score": mean_score,
        }
