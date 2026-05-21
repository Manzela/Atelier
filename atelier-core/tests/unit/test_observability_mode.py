"""Tests for atelier.observability mode flag (C14/M13)."""

from __future__ import annotations

import os
import warnings
from unittest import mock

from atelier.observability import (
    get_observability_mode,
    is_dev_mode,
    is_prod_mode,
)


class TestObservabilityMode:
    """Tests for ATELIER_OBSERVABILITY_MODE env var handling."""

    def test_default_is_dev(self) -> None:
        """Without env var, mode defaults to 'dev'."""
        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ATELIER_OBSERVABILITY_MODE", None)
            assert get_observability_mode() == "dev"

    def test_dev_mode_explicit(self) -> None:
        """Explicit 'dev' value is accepted."""
        with mock.patch.dict(os.environ, {"ATELIER_OBSERVABILITY_MODE": "dev"}):
            assert get_observability_mode() == "dev"
            assert is_dev_mode() is True
            assert is_prod_mode() is False

    def test_prod_mode(self) -> None:
        """Explicit 'prod' value switches to production."""
        with mock.patch.dict(os.environ, {"ATELIER_OBSERVABILITY_MODE": "prod"}):
            assert get_observability_mode() == "prod"
            assert is_dev_mode() is False
            assert is_prod_mode() is True

    def test_case_insensitive(self) -> None:
        """Mode check is case-insensitive."""
        with mock.patch.dict(os.environ, {"ATELIER_OBSERVABILITY_MODE": "PROD"}):
            assert get_observability_mode() == "prod"

    def test_whitespace_stripped(self) -> None:
        """Leading/trailing whitespace is stripped."""
        with mock.patch.dict(os.environ, {"ATELIER_OBSERVABILITY_MODE": "  dev  "}):
            assert get_observability_mode() == "dev"

    def test_unrecognized_value_warns_and_defaults(self) -> None:
        """Unrecognized value emits warning and falls back to dev."""
        with (
            mock.patch.dict(os.environ, {"ATELIER_OBSERVABILITY_MODE": "staging"}),
            warnings.catch_warnings(record=True) as w,
        ):
            warnings.simplefilter("always")
            result = get_observability_mode()
            assert result == "dev"
            assert len(w) == 1
            assert "staging" in str(w[0].message)
