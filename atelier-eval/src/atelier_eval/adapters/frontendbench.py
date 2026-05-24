"""FrontendBench adapter — 148 frontend tasks (stub).

Dataset: https://github.com/nicholasgasior/FrontendBench
Paper: arXiv 2411.XXXXX (frontend code generation benchmark)

**Status: STUB** — FrontendBench data has not been publicly released.
This adapter provides type stubs only. Real implementation lands when
the dataset becomes available.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from atelier_eval.adapters._base import EvalResult

FRONTENDBENCH_TASK_COUNT: Final[int] = 148


@dataclass(frozen=True, slots=True)
class FrontendBenchTask:
    """A single FrontendBench task."""

    task_id: str
    prompt: str
    expected_elements: list[str]


def load_frontendbench_tasks(data_dir: str) -> list[FrontendBenchTask]:
    """Load FrontendBench tasks (STUB — dataset not released).

    Raises:
        NotImplementedError: Always, until dataset is released.
    """
    msg = (
        "FrontendBench dataset not yet publicly released. "
        "See https://github.com/nicholasgasior/FrontendBench"
    )
    raise NotImplementedError(msg)


def evaluate_frontendbench(
    *,
    task: FrontendBenchTask,
    generated_html: str,
) -> EvalResult:
    """Evaluate a FrontendBench task (STUB — dataset not released).

    Raises:
        NotImplementedError: Always, until dataset is released.
    """
    msg = "FrontendBench evaluation not yet implemented — dataset not released."
    raise NotImplementedError(msg)
