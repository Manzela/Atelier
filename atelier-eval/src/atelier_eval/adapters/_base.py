"""Base types for all eval adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class EvalResult:
    """Result of evaluating a single benchmark task."""

    task_id: str
    passed: bool
    score: float  # 0.0-1.0
    error: str | None  # None on pass
    metadata: dict[str, str | float | int]


class EvalAdapter(Protocol):
    """All adapters implement this. Stateless — no I/O in __init__."""

    def load_tasks(self, data_dir: str) -> list[str]:
        """Load task IDs from a local dataset directory."""
        ...

    def evaluate(self, task_id: str, generated_output: str) -> EvalResult:
        """Evaluate a single task against the generated output."""
        ...

    def aggregate(self, results: list[EvalResult]) -> dict[str, float]:
        """Aggregate individual results into summary metrics."""
        ...
