"""WebGen-Bench 50-task subset evaluation harness.

Phase 1 Gate criterion §4.3 #5: pipeline must produce non-error output
for each of the 50 deterministically selected WebGen-Bench tasks.

Source: https://github.com/mnluzimu/WebGen-Bench
Benchmark: 101 total tasks, 647 test cases
Subset: 50 tasks selected by SHA-256 sort of task ID, first 50

NOTE: The spec references "50/484 WebGen-Bench subset" but the actual
benchmark has 101 tasks (484 is the Design2Code dataset). The 50-task
subset from the real 101 is used here. See the eval-harness handoff notes.

Coverage honesty: the per-task pipeline assertion is an explicit SKIP, not an
xfail. The WebGen-Bench corpus (per-task briefs/expected output) is not vendored
into this repo, so the live N1->N4 invocation cannot run hermetically here; the
wiring lands in D17. An unconditional ``pytest.xfail`` would report 50 green
"xfailed" results that assert nothing about the pipeline, which over-credits
coverage to a reader counting test cases. A SKIP makes the un-run state explicit.
The subset-integrity test below DOES run by default and guards the headline
"50-task WebGen-Bench" claim against silent corpus drift.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_TASK_IDS_PATH = Path(__file__).parent / "webgen_50_task_ids.json"
_IDS: list[str] = json.loads(_TASK_IDS_PATH.read_text(encoding="utf-8"))


def test_webgen_subset_integrity() -> None:
    """The headline "50-task WebGen-Bench" subset is exactly 50 unique task IDs.

    This runs by default and fails loudly on corpus drift — a truncated,
    duplicated, or empty selection would silently weaken the benchmark claim
    while the per-task harness (skipped below) shows nothing. Each ID must be a
    non-empty string so the (future) live harness has a real task to dispatch.
    """
    assert isinstance(_IDS, list), "webgen_50_task_ids.json must be a JSON list"
    assert len(_IDS) == 50, f"WebGen subset must hold exactly 50 task IDs, found {len(_IDS)}"
    assert len(set(_IDS)) == 50, "WebGen subset task IDs must be unique (no duplicates)"
    assert all(isinstance(task_id, str) and task_id.strip() for task_id in _IDS), (
        "every WebGen task ID must be a non-empty string"
    )


@pytest.mark.skip(
    reason="WebGen-Bench corpus not vendored; live N1->N4 per-task wiring lands in D17 (§22.3)"
)
@pytest.mark.parametrize("task_id", _IDS)
def test_webgen_task(task_id: str) -> None:
    """Phase 1 Gate: pipeline must produce non-error output for this task.

    Skipped until the WebGen-Bench corpus is vendored and the live pipeline is
    wired (D17). Kept parametrized so the eventual wiring lights up all 50 tasks.
    """
    raise AssertionError("unreachable: skipped until the WebGen-Bench harness is wired (D17)")
