"""Unit tests for FailureMode enum + @failure_trichotomy decorator (§8, ADR 0031).

Tests the failure trichotomy contract:
- FAIL_LOUD: raises immediately, zero retries
- FAIL_SOFT: logs + returns sentinel, zero retries
- SELF_HEAL: retries up to max_retries, then escalates to FAIL_LOUD
"""

from __future__ import annotations

import logging

import pytest
from atelier.runtime.failure import FailureMode, failure_trichotomy

# ──────────────────────────────────────────────────────────────────────
# FAIL_LOUD tests
# ──────────────────────────────────────────────────────────────────────


class TestFailLoud:
    def test_fail_loud_propagates_exception(self) -> None:
        @failure_trichotomy(fail_mode=FailureMode.FAIL_LOUD)
        def always_fails() -> str:
            raise ConnectionError("gcloud auth failed")

        with pytest.raises(ConnectionError, match="gcloud auth failed"):
            always_fails()

    def test_fail_loud_no_retries(self) -> None:
        call_count = 0

        @failure_trichotomy(fail_mode=FailureMode.FAIL_LOUD)
        def counted_call() -> str:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            counted_call()
        assert call_count == 1, "FAIL_LOUD must not retry"

    def test_fail_loud_success_passthrough(self) -> None:
        @failure_trichotomy(fail_mode=FailureMode.FAIL_LOUD)
        def ok_call() -> str:
            return "success"

        assert ok_call() == "success"


# ──────────────────────────────────────────────────────────────────────
# FAIL_SOFT tests
# ──────────────────────────────────────────────────────────────────────


class TestFailSoft:
    def test_fail_soft_returns_none_on_exception(self) -> None:
        @failure_trichotomy(fail_mode=FailureMode.FAIL_SOFT)
        def flaky() -> str:
            raise TimeoutError("vertex 503")

        result = flaky()
        assert result is None

    def test_fail_soft_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        @failure_trichotomy(fail_mode=FailureMode.FAIL_SOFT)
        def flaky() -> str:
            raise TimeoutError("vertex 503")

        with caplog.at_level(logging.WARNING):
            flaky()

        assert any("FAIL_SOFT" in rec.message for rec in caplog.records)

    def test_fail_soft_success_passthrough(self) -> None:
        @failure_trichotomy(fail_mode=FailureMode.FAIL_SOFT)
        def ok_call() -> str:
            return "data"

        assert ok_call() == "data"

    def test_fail_soft_no_retries(self) -> None:
        call_count = 0

        @failure_trichotomy(fail_mode=FailureMode.FAIL_SOFT)
        def counted_call() -> str:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("boom")

        counted_call()
        assert call_count == 1, "FAIL_SOFT must not retry"


# ──────────────────────────────────────────────────────────────────────
# SELF_HEAL tests
# ──────────────────────────────────────────────────────────────────────


class TestSelfHeal:
    def test_self_heal_retries_then_succeeds(self) -> None:
        attempt = 0

        @failure_trichotomy(fail_mode=FailureMode.SELF_HEAL, max_retries=3)
        def heals_on_third() -> str:
            nonlocal attempt
            attempt += 1
            if attempt < 3:
                raise ConnectionError("transient")
            return "healed"

        assert heals_on_third() == "healed"
        assert attempt == 3

    def test_self_heal_exhausts_retries_then_raises(self) -> None:
        call_count = 0

        @failure_trichotomy(fail_mode=FailureMode.SELF_HEAL, max_retries=3)
        def always_fails() -> str:
            nonlocal call_count
            call_count += 1
            raise ConnectionError("persistent failure")

        with pytest.raises(ConnectionError, match="persistent failure"):
            always_fails()
        assert call_count == 3, "SELF_HEAL must retry exactly max_retries times"

    def test_self_heal_success_no_retry(self) -> None:
        call_count = 0

        @failure_trichotomy(fail_mode=FailureMode.SELF_HEAL, max_retries=3)
        def ok_call() -> str:
            nonlocal call_count
            call_count += 1
            return "instant"

        assert ok_call() == "instant"
        assert call_count == 1

    def test_self_heal_zero_retries_raises_immediately(self) -> None:
        """max_retries=0 means try once (initial call only), then raise."""
        call_count = 0

        @failure_trichotomy(fail_mode=FailureMode.SELF_HEAL, max_retries=0)
        def always_fails() -> str:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            always_fails()
        # max_retries=0 means no retries, just the initial attempt
        assert call_count == 1


# ──────────────────────────────────────────────────────────────────────
# Enum invariants
# ──────────────────────────────────────────────────────────────────────


class TestFailureModeEnum:
    def test_enum_has_three_members(self) -> None:
        assert len(FailureMode) == 3

    def test_enum_values(self) -> None:
        assert FailureMode.FAIL_LOUD.value == "fail_loud"
        assert FailureMode.FAIL_SOFT.value == "fail_soft"
        assert FailureMode.SELF_HEAL.value == "self_heal"

    def test_enum_is_str_enum(self) -> None:
        assert isinstance(FailureMode.FAIL_LOUD, str)


# ──────────────────────────────────────────────────────────────────────
# Decorator argument validation
# ──────────────────────────────────────────────────────────────────────


class TestDecoratorValidation:
    def test_invalid_max_retries_raises(self) -> None:
        with pytest.raises(ValueError, match="max_retries"):

            @failure_trichotomy(fail_mode=FailureMode.SELF_HEAL, max_retries=-1)
            def bad() -> None:
                pass

    def test_fail_loud_ignores_max_retries(self) -> None:
        """FAIL_LOUD never retries even if max_retries > 0."""
        call_count = 0

        @failure_trichotomy(fail_mode=FailureMode.FAIL_LOUD, max_retries=5)
        def always_fails() -> str:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            always_fails()
        assert call_count == 1
