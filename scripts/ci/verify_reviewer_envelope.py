"""CI merge-gate: verify the Reviewer DONE-evidence envelope (AT-102).

This script is run by CI on every pull-request targeting ``main`` or a
``phase/*`` branch.  It enforces PRD v2.2 §12 E10 / §8A:

    "No envelope -> merge blocked"
    "Envelope disagrees with independent re-run -> auto-REJECT (flagged)"
    "3x consecutive REJECTED -> NON_CONVERGENCE surfaced to user"

Exit codes (the public contract; nothing else exits with these values):
    0  Envelope present, verdict DONE, re-run agrees on all fields.
    1  Merge blocked (missing envelope / parse error / REJECTED verdict /
       auto-REJECT because re-run disagrees / tampered SHA-256).
    2  Non-convergence: 3rd consecutive REJECTED entry in the calibration
       log — surface to user for manual intervention.

Usage (local):
    python scripts/ci/verify_reviewer_envelope.py

    The script resolves paths relative to the *repo root* (detected via
    ``git rev-parse --show-toplevel`` or the script's own ancestry).

Invariants:
    - stdlib only (subprocess, hashlib, json, pathlib, sys, logging).
    - <no_silent_error_suppression>: every caught exception is logged with
      context and either re-raised or turned into an exit-1 with reason.
    - All subprocess invocations use explicit timeout=300 and
      capture_output=True; non-zero exits are treated as the re-run
      disagreeing with the claimed exit code of 0.
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Logging — structured, no silent suppression
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s  %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("reviewer-envelope-gate")

# ---------------------------------------------------------------------------
# Repo-root discovery
# ---------------------------------------------------------------------------


def _find_repo_root() -> Path:
    """Return the git repo root, preferring ``git rev-parse`` over ancestry."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],  # noqa: S607 — controlled git command
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except Exception as exc:  # noqa: BLE001 — fallback is safe for repo discovery
        log.warning("git rev-parse failed (%s); falling back to ancestry.", exc)

    # Fallback: walk up from this script until we find a .git
    candidate = Path(__file__).resolve()
    for _ in range(10):
        candidate = candidate.parent
        if (candidate / ".git").exists():
            return candidate
    raise RuntimeError("Could not locate repo root: neither git nor .git ancestry worked.")


# ---------------------------------------------------------------------------
# Path constants (resolved lazily relative to repo root)
# ---------------------------------------------------------------------------

_ENVELOPE_FILENAME = ".reviewer-envelope.json"
_CALIBRATION_LOG_FILENAME = ".reviewer-calibration-log.json"
_NON_CONVERGENCE_STREAK = 3


# ---------------------------------------------------------------------------
# SHA-256 helpers
# ---------------------------------------------------------------------------


def sha256_of_file(path: Path) -> str:
    """Return the lowercase hex SHA-256 of *path*'s raw bytes."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Calibration log (rejection streak)
# ---------------------------------------------------------------------------


def _load_calibration_log(log_path: Path) -> list[dict[str, Any]]:
    """Load the calibration log JSON list; return [] on missing/corrupt."""
    if not log_path.exists():
        return []
    try:
        raw = log_path.read_bytes()
        data = json.loads(raw)
        if not isinstance(data, list):
            log.warning("Calibration log at %s is not a list; treating as empty.", log_path)
            return []
    except json.JSONDecodeError as exc:
        log.warning("Calibration log at %s is corrupt (%s); treating as empty.", log_path, exc)
        return []
    else:
        return data  # type: ignore[return-value]


def _consecutive_rejections(entries: list[dict[str, Any]]) -> int:
    """Count the TRAILING run of REJECTED / auto-REJECTED entries."""
    streak = 0
    for entry in reversed(entries):
        v = entry.get("verdict", "")
        if v in ("REJECTED", "auto-REJECTED"):
            streak += 1
        else:
            break
    return streak


def _append_calibration_entry(
    log_path: Path,
    verdict: str,
    reasons: list[str],
) -> int:
    """Append one entry to the calibration log; return the new streak count.

    The caller is responsible for checking whether the streak warrants exit 2.
    Writes are best-effort: a failure is logged but does NOT suppress the
    primary gate exit code (the envelope check takes priority).
    """
    entries = _load_calibration_log(log_path)
    entry: dict[str, Any] = {"verdict": verdict, "reasons": reasons}
    entries.append(entry)
    try:
        log_path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    except OSError:
        log.exception(
            "Could not write calibration log at %s. "
            "The rejection-streak counter will not persist for this run.",
            log_path,
        )
    return _consecutive_rejections(entries)


# ---------------------------------------------------------------------------
# Independent re-run helpers
# ---------------------------------------------------------------------------


def _run_command(cmd: list[str], cwd: Path) -> int:
    """Run *cmd* in *cwd*; return its exit code. Logs stdout+stderr on failure."""
    try:
        result = subprocess.run(  # noqa: S603 — CI gate, trusted commands
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except subprocess.TimeoutExpired:
        log.exception("Command %s timed out after 300 s.", cmd)
        return 124
    except OSError:
        log.exception("Command %s could not be launched.", cmd)
        return 1
    else:
        if result.returncode != 0:
            log.info(
                "Command %s exited %d.\nstdout:\n%s\nstderr:\n%s",
                cmd,
                result.returncode,
                result.stdout[-4000:],
                result.stderr[-4000:],
            )
        return result.returncode


def _rerun_pytest(repo_root: Path) -> int:
    """Re-run the ``make verify-tests`` lane; return the real exit code."""
    venv_python = repo_root / ".venv" / "bin" / "python"
    if not venv_python.exists():
        venv_python = Path(sys.executable)
    core_dir = repo_root / "atelier-core"
    return _run_command(
        [
            str(venv_python),
            "-m",
            "pytest",
            "tests/unit",
            "tests/integration/test_record_replay_determinism.py",
            "tests/integration/test_specialist_pipeline.py",
            "tests/integration/test_critique_panel_pipeline.py",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=core_dir,
    )


def _rerun_mypy(repo_root: Path) -> int:
    """Re-run mypy --strict on the core src; return the real exit code."""
    venv_python = repo_root / ".venv" / "bin" / "python"
    if not venv_python.exists():
        venv_python = Path(sys.executable)
    core_dir = repo_root / "atelier-core"
    return _run_command(
        [str(venv_python), "-m", "mypy", "--strict", "src"],
        cwd=core_dir,
    )


def _rerun_eval(repo_root: Path) -> int:
    """Re-run ``make verify-eval``; return the real exit code."""
    return _run_command(
        ["make", "verify-eval"],
        cwd=repo_root,
    )


# ---------------------------------------------------------------------------
# Envelope parsing (inline, stdlib-only — no pydantic in this script)
# ---------------------------------------------------------------------------

_VALID_VERDICTS = {"DONE", "REJECTED"}
_REQUIRED_FIELDS = frozenset(
    {"schema_version", "verdict", "pytest_exit", "mypy_exit", "files_touched_sha"}
)
_KNOWN_FIELDS = _REQUIRED_FIELDS | {"eval_delta_vs_head1"}


def _check_envelope_types(data: dict[str, Any]) -> None:
    """Raise TypeError for fields with wrong types (extracted to reduce complexity).

    Precondition: all required fields are present in *data*.
    """
    if not isinstance(data["pytest_exit"], int):
        raise TypeError("'pytest_exit' must be an integer.")
    if not isinstance(data["mypy_exit"], int):
        raise TypeError("'mypy_exit' must be an integer.")
    if not isinstance(data["files_touched_sha"], dict):
        raise TypeError("'files_touched_sha' must be a dict.")
    if not isinstance(data["schema_version"], int):
        raise TypeError("'schema_version' must be an integer.")
    eval_delta = data.get("eval_delta_vs_head1")
    if eval_delta is not None and not isinstance(eval_delta, (int, float)):
        raise TypeError("'eval_delta_vs_head1' must be a float or null.")


def _parse_envelope(raw: bytes) -> dict[str, Any]:
    """Parse + validate envelope JSON; raise ValueError/TypeError on schema violations."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Envelope is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise TypeError("Envelope must be a JSON object (dict), got list or scalar.")

    missing = _REQUIRED_FIELDS - data.keys()
    if missing:
        raise ValueError(f"Envelope missing required fields: {sorted(missing)}")

    extra = data.keys() - _KNOWN_FIELDS
    if extra:
        raise ValueError(f"Envelope has unexpected fields (extra='forbid'): {sorted(extra)}")

    # Type-check individual fields only after all required fields confirmed present
    _check_envelope_types(data)

    verdict = data["verdict"]
    if verdict not in _VALID_VERDICTS:
        raise ValueError(f"Envelope 'verdict' must be 'DONE' or 'REJECTED', got {verdict!r}.")

    return data


# ---------------------------------------------------------------------------
# SHA mismatch checks (extracted to reduce run_gate complexity)
# ---------------------------------------------------------------------------


def _check_sha_mismatches(
    repo_root: Path,
    files_touched: dict[str, str],
    mismatches: list[str],
) -> None:
    """Populate *mismatches* with any SHA-256 tamper or missing-file findings."""
    for rel_path, claimed_sha in files_touched.items():
        abs_path = repo_root / rel_path
        if not abs_path.exists():
            mismatches.append(f"files_touched_sha[{rel_path!r}]: file not found on disk")
            continue
        real_sha = sha256_of_file(abs_path)
        if real_sha != claimed_sha:
            mismatches.append(
                f"files_touched_sha[{rel_path!r}]: "
                f"claimed={claimed_sha[:12]}..., "
                f"re-computed={real_sha[:12]}..."
            )


def _escalate_if_converging(
    calibration_path: Path,
    verdict: str,
    mismatches: list[str],
) -> int:
    """Log calibration entry and return 2 on NON_CONVERGENCE, else 1."""
    streak = _append_calibration_entry(calibration_path, verdict, mismatches)
    if streak >= _NON_CONVERGENCE_STREAK:
        log.error(
            "NON_CONVERGENCE: %d consecutive REJECTED entries in calibration log. "
            "Manual intervention required — review the PR and reset the calibration "
            "log once the root cause is resolved.",
            streak,
        )
        return 2
    return 1


# ---------------------------------------------------------------------------
# Main gate logic
# ---------------------------------------------------------------------------


def run_gate(repo_root: Path) -> int:
    """Execute the gate; return the appropriate exit code (0, 1, or 2).

    This function is importable for unit testing.  The real ``main()``
    simply calls it with the detected repo root.
    """
    envelope_path = repo_root / _ENVELOPE_FILENAME
    calibration_path = repo_root / _CALIBRATION_LOG_FILENAME

    # 1. Envelope must be present
    if not envelope_path.exists():
        log.error(
            "merge blocked: no reviewer DONE-evidence envelope "
            "(.reviewer-envelope.json not found at repo root)"
        )
        return 1

    # 2. Parse + validate envelope schema
    try:
        raw = envelope_path.read_bytes()
        envelope = _parse_envelope(raw)
    except (ValueError, TypeError):
        log.exception("merge blocked: envelope schema invalid")
        return 1

    # 3. REJECTED verdict — block and log
    if envelope["verdict"] == "REJECTED":
        log.error(
            "merge blocked: Reviewer returned REJECTED verdict; "
            "the Reviewer did not approve this PR."
        )
        return _escalate_if_converging(
            calibration_path, "REJECTED", ["reviewer emitted REJECTED verdict"]
        )

    # 4. verdict == "DONE" — independently re-run every named check
    mismatches: list[str] = []

    real_pytest = _rerun_pytest(repo_root)
    claimed_pytest: int = envelope["pytest_exit"]
    if real_pytest != claimed_pytest:
        mismatches.append(f"pytest_exit: claimed={claimed_pytest}, re-run={real_pytest}")

    real_mypy = _rerun_mypy(repo_root)
    claimed_mypy: int = envelope["mypy_exit"]
    if real_mypy != claimed_mypy:
        mismatches.append(f"mypy_exit: claimed={claimed_mypy}, re-run={real_mypy}")

    claimed_eval: float | None = envelope.get("eval_delta_vs_head1")
    if claimed_eval is not None:
        real_eval = _rerun_eval(repo_root)
        if real_eval != 0:
            mismatches.append(
                f"eval (make verify-eval): expected exit 0, re-run returned {real_eval}"
            )

    files_touched: dict[str, str] = envelope["files_touched_sha"]
    _check_sha_mismatches(repo_root, files_touched, mismatches)

    # 5. Decide outcome
    if mismatches:
        for reason in mismatches:
            log.error("auto-REJECT: %s", reason)
        log.error(
            "merge blocked: envelope disagrees with independent re-run on %d field(s). "
            "Reviewer flagged for calibration.",
            len(mismatches),
        )
        return _escalate_if_converging(calibration_path, "auto-REJECTED", mismatches)

    log.info("Reviewer envelope verified: DONE — all re-run checks agree with claimed values.")
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Resolve repo root and delegate to ``run_gate``."""
    try:
        repo_root = _find_repo_root()
    except RuntimeError:
        log.exception("Cannot determine repo root")
        sys.exit(1)

    sys.exit(run_gate(repo_root))


if __name__ == "__main__":
    main()
