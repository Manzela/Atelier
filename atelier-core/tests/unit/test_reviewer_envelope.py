"""AT-102 acceptance oracle — Reviewer DONE-evidence envelope + CI gate.

PRD v2.2 §12 E10 / §8A acceptance criteria exercised:

1. ``ReviewerEnvelope`` model: valid parses, missing field -> ValidationError,
   extra field -> ValidationError (``extra='forbid'``).
2. Verify script: exits 1 when no envelope file present.
3. Verify script: exits 0 when envelope matches mocked re-run (happy path).
4. **Anti-fabrication core**: exits 1 (auto-REJECT) when envelope claims
   ``pytest_exit=0`` but the independent re-run returns non-zero.
5. Exits 1 when a ``files_touched_sha`` entry is tampered.
6. Exits 2 on the 3rd consecutive REJECTED entry (non-convergence).

Tests are non-vacuous: the anti-fabrication test (4) seeds a DONE envelope
with a lying ``pytest_exit=0`` value, monkeypatches the subprocess re-run to
return 1, and asserts the gate catches the lie and returns exit 1.

All subprocess and make-command calls are monkeypatched so the tests are
fast, hermetic, and do not shell out.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from atelier.models.reviewer_envelope import EnvelopeVerificationResult, ReviewerEnvelope
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Load the gate script as a module (not installed — load from path)
# ---------------------------------------------------------------------------

_GATE_PATH = Path(__file__).resolve().parents[3] / "scripts" / "ci" / "verify_reviewer_envelope.py"


def _load_gate_module():  # type: ignore[return]
    spec = importlib.util.spec_from_file_location("verify_reviewer_envelope", _GATE_PATH)
    assert spec is not None, f"Gate script not found at {_GATE_PATH}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules["verify_reviewer_envelope"] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_gate = _load_gate_module()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write_envelope(repo_root: Path, data: dict[str, Any]) -> None:
    (repo_root / ".reviewer-envelope.json").write_text(json.dumps(data), encoding="utf-8")


_VALID_ENVELOPE: dict[str, Any] = {
    "schema_version": 1,
    "verdict": "DONE",
    "pytest_exit": 0,
    "mypy_exit": 0,
    "eval_delta_vs_head1": None,
    "files_touched_sha": {},
}


# ===========================================================================
# Section 1 — ReviewerEnvelope Pydantic model
# ===========================================================================


class TestReviewerEnvelopeModel:
    """Pydantic model validation invariants."""

    def test_valid_done_envelope(self) -> None:
        env = ReviewerEnvelope(
            verdict="DONE",
            pytest_exit=0,
            mypy_exit=0,
            eval_delta_vs_head1=None,
            files_touched_sha={"src/foo.py": "abc123"},
        )
        assert env.verdict == "DONE"
        assert env.schema_version == 1
        assert env.files_touched_sha == {"src/foo.py": "abc123"}

    def test_valid_rejected_envelope(self) -> None:
        env = ReviewerEnvelope(
            verdict="REJECTED",
            pytest_exit=1,
            mypy_exit=0,
        )
        assert env.verdict == "REJECTED"

    def test_missing_verdict_raises(self) -> None:
        with pytest.raises(ValidationError):
            ReviewerEnvelope(pytest_exit=0, mypy_exit=0)  # type: ignore[call-arg]

    def test_missing_pytest_exit_raises(self) -> None:
        with pytest.raises(ValidationError):
            ReviewerEnvelope(verdict="DONE", mypy_exit=0)  # type: ignore[call-arg]

    def test_missing_mypy_exit_raises(self) -> None:
        with pytest.raises(ValidationError):
            ReviewerEnvelope(verdict="DONE", pytest_exit=0)  # type: ignore[call-arg]

    def test_extra_field_raises(self) -> None:
        """extra='forbid' — unknown fields must be rejected."""
        with pytest.raises(ValidationError):
            ReviewerEnvelope(
                verdict="DONE",
                pytest_exit=0,
                mypy_exit=0,
                unknown_field="surprise",  # type: ignore[call-arg]
            )

    def test_invalid_verdict_raises(self) -> None:
        with pytest.raises(ValidationError):
            ReviewerEnvelope(
                verdict="MAYBE",  # type: ignore[arg-type]
                pytest_exit=0,
                mypy_exit=0,
            )

    def test_frozen(self) -> None:
        """Envelope is immutable after construction."""
        env = ReviewerEnvelope(verdict="DONE", pytest_exit=0, mypy_exit=0)
        with pytest.raises(Exception):
            env.verdict = "REJECTED"  # type: ignore[misc]

    def test_schema_version_default(self) -> None:
        env = ReviewerEnvelope(verdict="DONE", pytest_exit=0, mypy_exit=0)
        assert env.schema_version == 1

    def test_eval_delta_nullable(self) -> None:
        env = ReviewerEnvelope(
            verdict="DONE",
            pytest_exit=0,
            mypy_exit=0,
            eval_delta_vs_head1=0.05,
        )
        assert env.eval_delta_vs_head1 == pytest.approx(0.05)

    def test_roundtrip_json(self) -> None:
        env = ReviewerEnvelope(
            verdict="DONE",
            pytest_exit=0,
            mypy_exit=0,
            files_touched_sha={"a.py": "deadbeef"},
        )
        recovered = ReviewerEnvelope.model_validate_json(env.model_dump_json())
        assert recovered == env


class TestEnvelopeVerificationResult:
    """EnvelopeVerificationResult model."""

    def test_valid_passed(self) -> None:
        r = EnvelopeVerificationResult(passed=True)
        assert r.mismatch_reasons == []
        assert r.rejection_streak == 0

    def test_valid_failed_with_reasons(self) -> None:
        r = EnvelopeVerificationResult(
            passed=False,
            mismatch_reasons=["pytest_exit mismatch"],
            rejection_streak=2,
        )
        assert not r.passed
        assert len(r.mismatch_reasons) == 1

    def test_extra_field_raises(self) -> None:
        with pytest.raises(ValidationError):
            EnvelopeVerificationResult(passed=True, bogus="x")  # type: ignore[call-arg]


# ===========================================================================
# Section 2 — Gate script: no envelope -> exit 1
# ===========================================================================


class TestGateNoEnvelope:
    def test_missing_envelope_returns_1(self, tmp_path: Path) -> None:
        """No .reviewer-envelope.json -> gate must exit 1."""
        code = _gate.run_gate(tmp_path)
        assert code == 1


# ===========================================================================
# Section 3 — Gate script: valid DONE envelope + mocked re-run -> exit 0
# ===========================================================================


class TestGateHappyPath:
    def test_valid_done_envelope_exits_0(self, tmp_path: Path) -> None:
        """Happy path: DONE envelope, re-runs return 0, SHAs match -> exit 0."""
        file_a = tmp_path / "src" / "foo.py"
        file_a.parent.mkdir(parents=True)
        file_a.write_bytes(b"# real content\n")

        envelope: dict[str, Any] = {
            **_VALID_ENVELOPE,
            "files_touched_sha": {"src/foo.py": _sha256(b"# real content\n")},
        }
        _write_envelope(tmp_path, envelope)

        with (
            patch.object(_gate, "_rerun_pytest", return_value=0),
            patch.object(_gate, "_rerun_mypy", return_value=0),
        ):
            code = _gate.run_gate(tmp_path)

        assert code == 0


# ===========================================================================
# Section 4 — Anti-fabrication core (THE oracle test for AT-102)
#
# Seed a fabricated DONE envelope claiming pytest_exit=0.
# Monkeypatch the re-run to return exit 1.
# Gate MUST catch the lie and return exit 1 (auto-REJECT).
# ===========================================================================


class TestGateAntiFabrication:
    def test_fabricated_pytest_exit_is_caught(self, tmp_path: Path) -> None:
        """CRITICAL: fabricated pytest_exit=0 in envelope, real re-run=1 -> exit 1.

        This is the verification-asymmetry core of AT-102: the CI gate does NOT
        trust the Reviewer's claimed exit code; it re-runs pytest independently
        and rejects if the result disagrees.
        """
        _write_envelope(tmp_path, _VALID_ENVELOPE)  # claims pytest_exit=0

        with (
            patch.object(_gate, "_rerun_pytest", return_value=1),  # <-- lie caught here
            patch.object(_gate, "_rerun_mypy", return_value=0),
        ):
            code = _gate.run_gate(tmp_path)

        assert code == 1, (
            "Gate failed to catch fabricated pytest_exit=0; "
            "independent re-run returned 1 but gate did not auto-reject."
        )

    def test_fabricated_mypy_exit_is_caught(self, tmp_path: Path) -> None:
        """Fabricated mypy_exit=0 in envelope, real re-run=1 -> exit 1."""
        _write_envelope(tmp_path, _VALID_ENVELOPE)  # claims mypy_exit=0

        with (
            patch.object(_gate, "_rerun_pytest", return_value=0),
            patch.object(_gate, "_rerun_mypy", return_value=1),  # <-- lie caught here
        ):
            code = _gate.run_gate(tmp_path)

        assert code == 1

    def test_fabricated_eval_exit_is_caught(self, tmp_path: Path) -> None:
        """When eval_delta_vs_head1 is non-None, a failing re-run causes exit 1."""
        envelope_with_eval = {**_VALID_ENVELOPE, "eval_delta_vs_head1": 0.02}
        _write_envelope(tmp_path, envelope_with_eval)

        with (
            patch.object(_gate, "_rerun_pytest", return_value=0),
            patch.object(_gate, "_rerun_mypy", return_value=0),
            patch.object(_gate, "_rerun_eval", return_value=1),  # <-- re-run fails
        ):
            code = _gate.run_gate(tmp_path)

        assert code == 1

    def test_eval_not_rerun_when_null(self, tmp_path: Path) -> None:
        """When eval_delta_vs_head1 is None, verify-eval is NOT re-run."""
        _write_envelope(tmp_path, _VALID_ENVELOPE)  # eval_delta_vs_head1 = None

        with (
            patch.object(_gate, "_rerun_pytest", return_value=0),
            patch.object(_gate, "_rerun_mypy", return_value=0),
            patch.object(_gate, "_rerun_eval", side_effect=AssertionError("must not run")),
        ):
            code = _gate.run_gate(tmp_path)

        assert code == 0


# ===========================================================================
# Section 5 — SHA-256 tamper detection
# ===========================================================================


class TestGateTamperDetection:
    def test_tampered_sha_causes_exit_1(self, tmp_path: Path) -> None:
        """File on disk has different content from the SHA in the envelope -> exit 1."""
        real_file = tmp_path / "src" / "changed.py"
        real_file.parent.mkdir(parents=True)
        real_file.write_bytes(b"# modified after signing\n")

        # Envelope was signed against different content
        envelope: dict[str, Any] = {
            **_VALID_ENVELOPE,
            "files_touched_sha": {
                "src/changed.py": _sha256(b"# original content at signing time\n")
            },
        }
        _write_envelope(tmp_path, envelope)

        with (
            patch.object(_gate, "_rerun_pytest", return_value=0),
            patch.object(_gate, "_rerun_mypy", return_value=0),
        ):
            code = _gate.run_gate(tmp_path)

        assert code == 1

    def test_missing_file_in_touched_sha_causes_exit_1(self, tmp_path: Path) -> None:
        """File listed in files_touched_sha does not exist on disk -> exit 1."""
        envelope: dict[str, Any] = {
            **_VALID_ENVELOPE,
            "files_touched_sha": {"src/deleted.py": "abc123"},
        }
        _write_envelope(tmp_path, envelope)

        with (
            patch.object(_gate, "_rerun_pytest", return_value=0),
            patch.object(_gate, "_rerun_mypy", return_value=0),
        ):
            code = _gate.run_gate(tmp_path)

        assert code == 1

    def test_matching_sha_does_not_block(self, tmp_path: Path) -> None:
        """SHA matches exactly -> no tamper -> gate passes (exit 0)."""
        content = b"# stable content\n"
        real_file = tmp_path / "src" / "stable.py"
        real_file.parent.mkdir(parents=True)
        real_file.write_bytes(content)

        envelope: dict[str, Any] = {
            **_VALID_ENVELOPE,
            "files_touched_sha": {"src/stable.py": _sha256(content)},
        }
        _write_envelope(tmp_path, envelope)

        with (
            patch.object(_gate, "_rerun_pytest", return_value=0),
            patch.object(_gate, "_rerun_mypy", return_value=0),
        ):
            code = _gate.run_gate(tmp_path)

        assert code == 0


# ===========================================================================
# Section 6 — REJECTED verdict and non-convergence (3x streak -> exit 2)
# ===========================================================================


class TestGateRejectedAndStreak:
    def test_rejected_verdict_exits_1(self, tmp_path: Path) -> None:
        """Envelope with verdict=REJECTED -> gate exits 1 (merge blocked)."""
        envelope: dict[str, Any] = {**_VALID_ENVELOPE, "verdict": "REJECTED"}
        _write_envelope(tmp_path, envelope)
        code = _gate.run_gate(tmp_path)
        assert code == 1

    def test_first_rejection_writes_calibration_log(self, tmp_path: Path) -> None:
        """First REJECTED entry is written to .reviewer-calibration-log.json."""
        envelope: dict[str, Any] = {**_VALID_ENVELOPE, "verdict": "REJECTED"}
        _write_envelope(tmp_path, envelope)
        _gate.run_gate(tmp_path)

        log_path = tmp_path / ".reviewer-calibration-log.json"
        assert log_path.exists()
        entries = json.loads(log_path.read_text())
        assert len(entries) == 1
        assert entries[0]["verdict"] == "REJECTED"

    def test_three_consecutive_rejections_exits_2(self, tmp_path: Path) -> None:
        """3 consecutive REJECTED entries in calibration log -> gate exits 2 (NON_CONVERGENCE).

        This is the non-convergence surface per PRD §8A: after 3 REJECTED cycles
        the gate escalates rather than silently cycling.
        """
        # Pre-seed two rejections so the NEXT run is the 3rd
        pre_log = [
            {"verdict": "REJECTED", "reasons": ["reviewer returned REJECTED verdict"]},
            {"verdict": "REJECTED", "reasons": ["reviewer returned REJECTED verdict"]},
        ]
        (tmp_path / ".reviewer-calibration-log.json").write_text(
            json.dumps(pre_log), encoding="utf-8"
        )

        envelope: dict[str, Any] = {**_VALID_ENVELOPE, "verdict": "REJECTED"}
        _write_envelope(tmp_path, envelope)

        code = _gate.run_gate(tmp_path)
        assert code == 2, (
            "Gate must return exit 2 (NON_CONVERGENCE) on the 3rd consecutive REJECTED. "
            f"Actual exit code: {code}"
        )

    def test_streak_resets_after_done(self, tmp_path: Path) -> None:
        """A DONE-passing run after prior rejections resets the streak — no exit 2."""
        # Pre-seed two rejections
        pre_log = [
            {"verdict": "REJECTED", "reasons": ["reviewer returned REJECTED verdict"]},
            {"verdict": "REJECTED", "reasons": ["reviewer returned REJECTED verdict"]},
        ]
        (tmp_path / ".reviewer-calibration-log.json").write_text(
            json.dumps(pre_log), encoding="utf-8"
        )

        # Now a successful DONE run — must NOT exit 2 because streak resets on DONE
        _write_envelope(tmp_path, _VALID_ENVELOPE)

        with (
            patch.object(_gate, "_rerun_pytest", return_value=0),
            patch.object(_gate, "_rerun_mypy", return_value=0),
        ):
            code = _gate.run_gate(tmp_path)

        assert code == 0

    def test_auto_reject_counts_toward_streak(self, tmp_path: Path) -> None:
        """Auto-REJECTED entries (fabricated envelope) count toward the streak."""
        # Pre-seed two auto-REJECTs
        pre_log = [
            {"verdict": "auto-REJECTED", "reasons": ["pytest_exit mismatch"]},
            {"verdict": "auto-REJECTED", "reasons": ["pytest_exit mismatch"]},
        ]
        (tmp_path / ".reviewer-calibration-log.json").write_text(
            json.dumps(pre_log), encoding="utf-8"
        )

        # Third auto-REJECT -> exit 2
        _write_envelope(tmp_path, _VALID_ENVELOPE)  # claims pytest_exit=0

        with (
            patch.object(_gate, "_rerun_pytest", return_value=1),  # <-- lie caught
            patch.object(_gate, "_rerun_mypy", return_value=0),
        ):
            code = _gate.run_gate(tmp_path)

        assert code == 2


# ===========================================================================
# Section 7 — Envelope parse errors
# ===========================================================================


class TestGateParseErrors:
    def test_malformed_json_exits_1(self, tmp_path: Path) -> None:
        (tmp_path / ".reviewer-envelope.json").write_text("{ not valid json", encoding="utf-8")
        code = _gate.run_gate(tmp_path)
        assert code == 1

    def test_missing_required_field_exits_1(self, tmp_path: Path) -> None:
        broken = {k: v for k, v in _VALID_ENVELOPE.items() if k != "pytest_exit"}
        _write_envelope(tmp_path, broken)
        code = _gate.run_gate(tmp_path)
        assert code == 1

    def test_extra_field_exits_1(self, tmp_path: Path) -> None:
        """extra='forbid' enforced by the parse layer as well."""
        extra = {**_VALID_ENVELOPE, "surprise_field": "value"}
        _write_envelope(tmp_path, extra)
        code = _gate.run_gate(tmp_path)
        assert code == 1

    def test_invalid_verdict_exits_1(self, tmp_path: Path) -> None:
        bad = {**_VALID_ENVELOPE, "verdict": "MAYBE"}
        _write_envelope(tmp_path, bad)
        code = _gate.run_gate(tmp_path)
        assert code == 1


# ===========================================================================
# Section 8 — Calibration log helper unit tests
# ===========================================================================


class TestCalibrationLogHelpers:
    def test_empty_log_streak_is_0(self) -> None:
        assert _gate._consecutive_rejections([]) == 0

    def test_all_rejected_returns_full_streak(self) -> None:
        entries = [{"verdict": "REJECTED"}] * 3
        assert _gate._consecutive_rejections(entries) == 3

    def test_streak_breaks_on_done(self) -> None:
        entries = [
            {"verdict": "DONE"},
            {"verdict": "REJECTED"},
            {"verdict": "REJECTED"},
        ]
        assert _gate._consecutive_rejections(entries) == 2

    def test_auto_rejected_counted(self) -> None:
        entries = [{"verdict": "auto-REJECTED"}, {"verdict": "auto-REJECTED"}]
        assert _gate._consecutive_rejections(entries) == 2

    def test_mixed_stop_on_non_rejected(self) -> None:
        entries = [
            {"verdict": "REJECTED"},
            {"verdict": "DONE"},  # <-- breaks trailing streak
            {"verdict": "REJECTED"},
        ]
        assert _gate._consecutive_rejections(entries) == 1

    def test_load_missing_log_returns_empty(self, tmp_path: Path) -> None:
        result = _gate._load_calibration_log(tmp_path / "nonexistent.json")
        assert result == []

    def test_load_corrupt_log_returns_empty(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("not json", encoding="utf-8")
        result = _gate._load_calibration_log(bad)
        assert result == []
