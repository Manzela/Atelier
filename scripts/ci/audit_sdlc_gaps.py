"""Audit script for SDLC gaps RR-01 through RR-05.

Each ``audit_rrNN_*`` function returns True (PASS) or False (FAIL).  Any
unhandled exception inside an audit function is caught in ``main()`` and
reported as a FAIL so that a single import error cannot prevent the remaining
checks from running.

Run from the repository root:

    python scripts/ci/audit_sdlc_gaps.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

# Resolve atelier-core early so the per-check imports below can succeed whether
# the script is invoked from the repo root or from scripts/ci/.
_ATELIER_SRC = Path(__file__).parents[2] / "atelier-core" / "src"
if str(_ATELIER_SRC) not in sys.path:
    sys.path.insert(0, str(_ATELIER_SRC))


def audit_rr01_chromium_sandbox() -> bool:
    """Verify Chromium sandbox configuration."""
    print("Auditing RR-01: Chromium Sandbox...")
    path = Path("atelier-core/src/atelier/gates/axe_core.py")
    if not path.exists():
        print(f"  Error: {path} not found")
        return False

    content = path.read_text()
    if 'os.getenv("ATELIER_ENV") == "production"' in content and "--no-sandbox" in content:
        print("  PASS: Production environment check and --no-sandbox flag found.")
        return True
    print("  FAIL: Production environment check or --no-sandbox flag missing.")
    return False


def audit_rr02_prompt_injection() -> bool:
    """Verify prompt injection patterns."""
    print("Auditing RR-02: Prompt Injection...")

    from atelier.models.model_armor_callbacks import _INJECTION_PATTERNS  # noqa: PLC0415

    required = ["DAN mode", "jailbreak", "unrestricted AI"]
    found = set()
    for pattern in _INJECTION_PATTERNS:
        for req in required:
            clean_pattern = (
                pattern.replace(r"\s+", " ").replace("(?:a|an) ", "").replace(r"(?:your\s+)?", "")
            )
            if req.lower() in clean_pattern.lower() or re.search(pattern, req, re.IGNORECASE):
                found.add(req)

    missing = set(required) - found
    if not missing:
        print(f"  PASS: All required patterns found: {list(found)}")
        return True
    print(f"  FAIL: Missing patterns: {missing}")
    print(f"  Current patterns: {_INJECTION_PATTERNS}")
    return False


def _collect_run_text(job: dict) -> str:
    """Concatenate every step's ``run:`` body in a parsed workflow job."""
    parts: list[str] = []
    for step in job.get("steps", []) or []:
        if isinstance(step, dict) and isinstance(step.get("run"), str):
            parts.append(step["run"])
    return "\n".join(parts)


def _load_workflow(path: Path) -> tuple[dict | None, str | None]:
    """Parse a workflow file, returning ``(workflow, error_reason)``."""
    if not path.exists():
        return None, f"{path} not found"
    try:
        return (yaml.safe_load(path.read_text()) or {}), None
    except yaml.YAMLError as exc:
        return None, f"ci.yml is not valid YAML: {exc}"


def _rr03_failure_reason(path: Path) -> str | None:
    """Return the first reason the RR-03 gate is unsound, or None if sound.

    The security job is only a real gate if ``ci-success`` BOTH lists it in
    ``needs`` AND its verify step actually inspects ``needs.security.result``.
    Substring-matching the file passes even when the verify loop ignores the
    security result, so parse the YAML and assert the dependency and the result
    reference explicitly.
    """
    workflow, error = _load_workflow(path)
    if error is not None:
        return error

    jobs = workflow.get("jobs", {})
    ci_success = jobs.get("ci-success")
    if "security" not in jobs:
        return "no `security` job defined in ci.yml."
    if not isinstance(ci_success, dict):
        return "no `ci-success` job defined in ci.yml."

    needs = ci_success.get("needs", [])
    if isinstance(needs, str):
        needs = [needs]
    if "security" not in set(needs or []):
        return "ci-success does not list `security` in needs."

    if "needs.security.result" not in _collect_run_text(ci_success):
        return (
            "ci-success never inspects needs.security.result — "
            "a failed security job would not fail the gate."
        )

    return None


def audit_rr03_ci_gates() -> bool:
    """Verify CI/CD gates (security job is a real gate, not a tautology)."""
    print("Auditing RR-03: CI/CD Gates...")
    reason = _rr03_failure_reason(Path(".github/workflows/ci.yml"))
    if reason is not None:
        print(f"  FAIL: {reason}")
        return False
    print("  PASS: ci-success requires `security` and gates on needs.security.result.")
    return True


def audit_rr04_sycophancy() -> bool:
    """Verify anti-sycophancy reward behaves correctly (behavioral, not tautological).

    Calls ``apply_anti_sycophancy_reward`` directly:
      - Unjustified praise must be penalised (score multiplied by < 1.0).
      - Justified praise must be preserved (score unchanged).
    """
    print("Auditing RR-04: Sycophancy...")

    try:
        from atelier.optimize.dreaming_module import (  # noqa: PLC0415
            apply_anti_sycophancy_reward,
        )
    except ImportError as exc:
        print(f"  FAIL: Could not import apply_anti_sycophancy_reward: {exc}")
        return False

    base_score = 1.0

    # Unjustified praise: should be penalised (result < base_score).
    unjustified = "This design looks spectacular and brilliant!"
    penalised = apply_anti_sycophancy_reward(unjustified, base_score)
    if penalised >= base_score:
        print(
            f"  FAIL: Unjustified praise was NOT penalised "
            f"(got {penalised}, expected < {base_score})."
        )
        return False

    # Justified praise: compliance/spec reference should preserve the score.
    justified = "This design is spectacular — it satisfies WCAG 2.1 AA compliance."
    preserved = apply_anti_sycophancy_reward(justified, base_score)
    if preserved < base_score:
        print(
            f"  FAIL: Justified praise was incorrectly penalised "
            f"(got {preserved}, expected {base_score})."
        )
        return False

    print(
        f"  PASS: Unjustified praise penalised ({penalised:.3f}), "
        f"justified praise preserved ({preserved:.3f})."
    )
    return True


def audit_rr05_circuit_breaker() -> bool:
    """Verify circuit breaker call."""
    print("Auditing RR-05: Circuit Breaker...")
    path = Path("atelier-core/src/atelier/orchestrator/runner.py")
    if not path.exists():
        print(f"  Error: {path} not found")
        return False

    content = path.read_text()
    if "self._usage_store.check_circuit_breaker()" in content:
        print("  PASS: Circuit breaker call found in runner.")
        return True
    print("  FAIL: Circuit breaker call missing in runner.")
    return False


def main() -> None:
    audit_fns = [
        audit_rr01_chromium_sandbox,
        audit_rr02_prompt_injection,
        audit_rr03_ci_gates,
        audit_rr04_sycophancy,
        audit_rr05_circuit_breaker,
    ]

    results: list[bool] = []
    for fn in audit_fns:
        try:
            results.append(fn())
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL: {fn.__name__} raised an unexpected exception: {exc}")
            results.append(False)

    if all(results):
        print("\nSDLC Audit: ALL GAPS RESOLVED.")
        sys.exit(0)
    else:
        print("\nSDLC Audit: FAILURES DETECTED.")
        sys.exit(1)


if __name__ == "__main__":
    main()
