from __future__ import annotations

import re
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRUBBER_CONFIG = _REPO_ROOT / "config" / "scrubber-patterns.yaml"


def test_scrubber_patterns_yaml_valid() -> None:
    with _SCRUBBER_CONFIG.open() as f:
        data = yaml.safe_load(f)
    assert "patterns" in data
    assert len(data["patterns"]) == 6


def test_google_api_key_pattern_matches() -> None:
    with _SCRUBBER_CONFIG.open() as f:
        pattern = yaml.safe_load(f)["patterns"]["google_api_key"]["pattern"]
    assert re.search(pattern, "AIzaSyB" + "X" * 32)


def test_jwt_pattern_matches() -> None:
    with _SCRUBBER_CONFIG.open() as f:
        pattern = yaml.safe_load(f)["patterns"]["jwt_token"]["pattern"]
    synthetic_jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    assert re.search(pattern, synthetic_jwt)
