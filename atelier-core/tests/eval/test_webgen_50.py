"""WebGen-Bench 50-task subset evaluation harness.

Phase 1 Gate criterion §4.3 #5: pipeline must produce non-error output
for each of the 50 deterministically selected WebGen-Bench tasks.

Source: https://github.com/mnluzimu/WebGen-Bench
Benchmark: 101 total tasks, 647 test cases
Subset: 50 tasks selected by SHA-256 sort of task ID, first 50

NOTE: The spec references "50/484 WebGen-Bench subset" but the actual
benchmark has 101 tasks (484 is the Design2Code dataset). The 50-task
subset from the real 101 is used here. See R6-06 handoff notes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_TASK_IDS_PATH = Path(__file__).parent / "webgen_50_task_ids.json"
_IDS: list[str] = json.loads(_TASK_IDS_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("task_id", _IDS)
def test_webgen_task(task_id: str) -> None:
    """Phase 1 Gate: pipeline must produce non-error output for this task.

    Currently XFAILs — full wiring lands in §22.3 D17.
    """
    pytest.xfail(f"WebGen-Bench harness not yet wired to live pipeline (task {task_id})")
