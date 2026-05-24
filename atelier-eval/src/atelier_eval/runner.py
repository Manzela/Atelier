"""Eval runner — orchestrates benchmark execution across adapters.

Usage (Phase 2):
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

    Phase 1 skeleton — real orchestration logic lands in Phase 2.
    """

    data_dir: str
    results: list[EvalResult] = field(default_factory=list)

    def run_design2code(
        self,
        generated_outputs: dict[str, str],
    ) -> list[EvalResult]:
        """Run Design2Code evaluation on generated outputs.

        Args:
            generated_outputs: Mapping of task_id → generated HTML string.

        Returns:
            List of EvalResult for each evaluated task.
        """
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
