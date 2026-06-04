"""Tests for tiered model routing and per-tier token cap enforcement.

Covers:
    - calibrate_model() returns the right model ID per task type
    - model_tier_for_id() correctly identifies Flash / Flash-Lite / Pro
    - TASK_MODEL_ROUTING covers every TaskType
    - GovernorState.add_user_tokens() accumulates per-tier correctly
    - GovernorState.exceeded_tier() / is_over_token_cap() fires on the right tier
    - GovernorTokenCapExceeded carries the exceeded_tier field
    - MetacognitiveGovernor._check_token_budget() raises on tier breach
    - UsageSnapshot.per_tier() returns the correct tier dict
    - UsageCounterStore.add(model_id=...) writes per-tier fields in memory backend
"""

from __future__ import annotations

import os

import pytest
from atelier.durability.usage_counter import UsageCounterStore
from atelier.models.model_registry import (
    DEFAULT_GEMINI_MODEL_ID,
    GEMINI_FLASH_LITE_MODEL_ID,
    GEMINI_FLASH_MODEL_ID,
    TASK_MODEL_ROUTING,
    TIER_TOKEN_CAPS,
    TaskType,
    calibrate_model,
    model_tier_for_id,
)
from atelier.orchestrator.governor import (
    TIER_TOKEN_CAPS as GOV_TIER_CAPS,
)
from atelier.orchestrator.governor import (
    GovernorState,
    GovernorTokenCapExceeded,
    MetacognitiveGovernor,
)

# ---------------------------------------------------------------------------
# model_registry — routing table coverage
# ---------------------------------------------------------------------------


def test_task_model_routing_covers_all_task_types() -> None:
    """Every TaskType must have an explicit entry in TASK_MODEL_ROUTING."""
    missing = [t for t in TaskType if t not in TASK_MODEL_ROUTING]
    assert not missing, f"TaskTypes without routing: {missing}"


def test_calibrate_model_pro_tasks() -> None:
    """Pro-tier tasks must resolve to the Pro model ID."""
    for task in (TaskType.PLANNER, TaskType.JUDGE_ORIGINALITY, TaskType.CLARIFY):
        assert calibrate_model(task) == DEFAULT_GEMINI_MODEL_ID, task


def test_calibrate_model_flash_tasks() -> None:
    """Flash-tier tasks must resolve to the Flash model ID."""
    flash_tasks = (
        TaskType.UX_RESEARCH,
        TaskType.IA_FLOW,
        TaskType.WIREFRAME,
        TaskType.UI_DESIGN,
        TaskType.INTERACTION,
        TaskType.WEB_RESEARCH,
        TaskType.FIXER,
        TaskType.JUDGE_DESIGN,
        TaskType.JUDGE_RELEVANCE,
        TaskType.JUDGE_VISUAL,
    )
    for task in flash_tasks:
        assert calibrate_model(task) == GEMINI_FLASH_MODEL_ID, task


def test_calibrate_model_flash_lite_tasks() -> None:
    """Flash-Lite tasks must resolve to the Flash-Lite model ID."""
    for task in (
        TaskType.BRIEF_PARSE,
        TaskType.TOKEN_GEN,
        TaskType.COPY_EDITOR,
        TaskType.JUDGE_ACCESSIBILITY,
    ):
        assert calibrate_model(task) == GEMINI_FLASH_LITE_MODEL_ID, task


def test_calibrate_model_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """GEMINI_MODEL_ID env var overrides ALL calibrated models."""
    monkeypatch.setenv("GEMINI_MODEL_ID", "gemini-2.5-pro-test")
    for task in TaskType:
        assert calibrate_model(task) == "gemini-2.5-pro-test"


def test_model_tier_for_id_pro() -> None:
    assert model_tier_for_id("gemini-2.5-pro") == "pro"
    assert model_tier_for_id("gemini-3-pro") == "pro"
    assert model_tier_for_id("unknown-model") == "pro"


def test_model_tier_for_id_flash() -> None:
    assert model_tier_for_id("gemini-2.5-flash") == "flash"
    assert model_tier_for_id("gemini-3-flash") == "flash"


def test_model_tier_for_id_flash_lite() -> None:
    assert model_tier_for_id("gemini-2.5-flash-lite") == "flash_lite"
    assert model_tier_for_id("gemini-2.5-flash-lite-preview-09-2025") == "flash_lite"


def test_tier_caps_match_governor_and_registry() -> None:
    """TIER_TOKEN_CAPS in model_registry and governor must be identical."""
    assert TIER_TOKEN_CAPS == GOV_TIER_CAPS


# ---------------------------------------------------------------------------
# GovernorState — per-tier accumulation and cap enforcement
# ---------------------------------------------------------------------------


def test_add_user_tokens_accumulates_per_tier() -> None:
    state = GovernorState()
    state.add_user_tokens(input_tokens=1000, output_tokens=500, model_id="gemini-2.5-flash")
    assert state.per_tier_tokens["flash"] == 1500
    assert state.cumulative_user_tokens == 1500

    state.add_user_tokens(input_tokens=200, output_tokens=300, model_id="gemini-2.5-pro")
    assert state.per_tier_tokens["pro"] == 500
    assert state.cumulative_user_tokens == 2000

    state.add_user_tokens(input_tokens=100, model_id="gemini-2.5-flash-lite")
    assert state.per_tier_tokens["flash_lite"] == 100


def test_add_user_tokens_no_model_id_no_tier_entry() -> None:
    state = GovernorState()
    state.add_user_tokens(input_tokens=999)
    assert state.per_tier_tokens == {}
    assert state.cumulative_user_tokens == 999


def test_exceeded_tier_none_when_under_caps() -> None:
    state = GovernorState()
    state.add_user_tokens(input_tokens=100, model_id="gemini-2.5-pro")
    assert state.exceeded_tier() is None
    assert not state.is_over_token_cap()


def test_exceeded_tier_pro_when_over_pro_cap() -> None:
    state = GovernorState()
    pro_cap = TIER_TOKEN_CAPS["pro"]
    state.add_user_tokens(input_tokens=pro_cap, model_id="gemini-2.5-pro")
    assert state.exceeded_tier() == "pro"
    assert state.is_over_token_cap()


def test_exceeded_tier_flash_when_over_flash_cap() -> None:
    state = GovernorState()
    flash_cap = TIER_TOKEN_CAPS["flash"]
    state.add_user_tokens(input_tokens=flash_cap, model_id="gemini-2.5-flash")
    assert state.exceeded_tier() == "flash"
    assert state.is_over_token_cap()


def test_exceeded_tier_flash_lite_when_over_flash_lite_cap() -> None:
    state = GovernorState()
    fl_cap = TIER_TOKEN_CAPS["flash_lite"]
    state.add_user_tokens(input_tokens=fl_cap, model_id="gemini-2.5-flash-lite")
    assert state.exceeded_tier() == "flash_lite"
    assert state.is_over_token_cap()


def test_is_over_token_cap_legacy_fallback() -> None:
    """When all per_tier_tokens values are zero, falls back to cumulative >= token_cap."""
    state = GovernorState(token_cap=100)
    state.add_user_tokens(input_tokens=100)  # no model_id → no tier attribution
    # per_tier_tokens is empty → legacy aggregate path fires
    assert state.is_over_token_cap()


def test_is_over_token_cap_all_tiers_zero_seeds_legacy_path() -> None:
    """When per_tier_tokens is seeded with all-zeros (from store snapshot on new user),
    the legacy aggregate check must still apply correctly."""
    state = GovernorState(token_cap=100)
    # Simulate _seed_lifetime_counter for a user whose tier fields are all zero
    state.per_tier_tokens = {"pro": 0, "flash": 0, "flash_lite": 0}
    state.cumulative_user_tokens = 100  # at cap
    # All-zero tier dict → any(v > 0 ...) is False → legacy path fires
    assert state.is_over_token_cap()


def test_governor_check_token_budget_raises_with_tier() -> None:
    """_check_token_budget must raise GovernorTokenCapExceeded with exceeded_tier set."""
    gov = MetacognitiveGovernor()
    pro_cap = TIER_TOKEN_CAPS["pro"]
    gov._state.add_user_tokens(input_tokens=pro_cap, model_id="gemini-2.5-pro")
    with pytest.raises(GovernorTokenCapExceeded) as exc_info:
        gov._check_token_budget()
    assert exc_info.value.exceeded_tier == "pro"
    assert exc_info.value.cap_tokens == pro_cap


# ---------------------------------------------------------------------------
# UsageCounterStore — per-tier write/read in memory backend
# ---------------------------------------------------------------------------


def test_usage_store_add_with_model_id_updates_tier_fields() -> None:
    store = UsageCounterStore(backend="memory")
    uid = "test-tier-user"
    store.add(uid, input_tokens=1000, output_tokens=500, model_id="gemini-2.5-flash")
    snap = store.snapshot(uid)
    assert snap.tier_flash_tokens == 1500
    assert snap.tier_pro_tokens == 0
    assert snap.total_tokens == 1500


def test_usage_store_add_pro_tier() -> None:
    store = UsageCounterStore(backend="memory")
    uid = "test-pro-user"
    store.add(uid, input_tokens=200, output_tokens=300, model_id="gemini-2.5-pro")
    snap = store.snapshot(uid)
    assert snap.tier_pro_tokens == 500
    assert snap.tier_flash_tokens == 0


def test_usage_store_add_flash_lite_tier() -> None:
    store = UsageCounterStore(backend="memory")
    uid = "test-fl-user"
    store.add(uid, input_tokens=100, model_id="gemini-2.5-flash-lite")
    snap = store.snapshot(uid)
    assert snap.tier_flash_lite_tokens == 100


def test_usage_snapshot_per_tier_dict() -> None:
    store = UsageCounterStore(backend="memory")
    uid = "per-tier-dict"
    store.add(uid, input_tokens=1000, model_id="gemini-2.5-pro")
    store.add(uid, input_tokens=2000, model_id="gemini-2.5-flash")
    snap = store.snapshot(uid)
    tier_dict = snap.per_tier()
    assert tier_dict == {"pro": 1000, "flash": 2000, "flash_lite": 0}


def test_usage_store_add_without_model_id_no_tier_fields() -> None:
    store = UsageCounterStore(backend="memory")
    uid = "no-tier-user"
    store.add(uid, input_tokens=500)
    snap = store.snapshot(uid)
    assert snap.total_tokens == 500
    assert snap.tier_pro_tokens == 0
    assert snap.tier_flash_tokens == 0
    assert snap.tier_flash_lite_tokens == 0
