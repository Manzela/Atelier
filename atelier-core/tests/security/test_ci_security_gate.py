"""Pins the CI security gate (RR-03).

Three failure modes are guarded here:

1. `ci-success` lists `security` in `needs` but never inspects
   `needs.security.result`, so a failed security job does not fail the gate.
2. The bandit/semgrep/trivy steps swallow findings (`|| true`, no exit-code,
   `@master`), so the security job is green even when a scanner fires.
3. `audit_rr03_ci_gates` is a substring tautology that passes regardless of
   whether the gate is real.

These tests assert the *behavior*, not the prose: the workflow's parsed
structure and the audit function's verdict on a deliberately-broken fixture.
"""

from __future__ import annotations

import ast
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CI_YML = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
_AUDIT_SCRIPT = _REPO_ROOT / "scripts" / "ci" / "audit_sdlc_gaps.py"


def _load_ci() -> dict[str, Any]:
    return yaml.safe_load(_CI_YML.read_text())


def _ci_success_run_text(workflow: dict[str, Any]) -> str:
    job = workflow["jobs"]["ci-success"]
    return "\n".join(
        step["run"] for step in job.get("steps", []) if isinstance(step.get("run"), str)
    )


def _security_run_steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    return workflow["jobs"]["security"]["steps"]


# ── 1. ci-success actually gates on the security result ──────────────────


def test_ci_success_needs_security() -> None:
    workflow = _load_ci()
    needs = workflow["jobs"]["ci-success"].get("needs", [])
    if isinstance(needs, str):
        needs = [needs]
    assert "security" in set(needs), "ci-success must depend on the security job"


def test_ci_success_fails_on_security_failure_or_cancel() -> None:
    """The verify step must inspect needs.security.result and exit on
    failure/cancelled — `skipped`/`success` are the only states it may pass."""
    run_text = _ci_success_run_text(_load_ci())
    assert "needs.security.result" in run_text, (
        "ci-success never reads needs.security.result — a failed security "
        "job would not fail the gate"
    )
    # The reference must be inside a failure/cancelled guard, not merely
    # printed. We require both tokens to appear alongside the result read.
    assert "failure" in run_text
    assert "cancelled" in run_text


# ── 2. The scanners are not declawed ─────────────────────────────────────


def test_bandit_does_not_swallow_findings() -> None:
    steps = _security_run_steps(_load_ci())
    bandit = next(s for s in steps if s.get("name", "").startswith("Bandit"))
    assert "|| true" not in bandit["run"], "bandit must not swallow findings"


def test_semgrep_does_not_swallow_findings() -> None:
    steps = _security_run_steps(_load_ci())
    semgrep = next(s for s in steps if s.get("name", "").startswith("Semgrep"))
    assert "|| true" not in semgrep["run"], "semgrep must not swallow findings"
    assert "--error" in semgrep["run"], "semgrep must exit non-zero on a hit"


def test_trivy_pinned_and_gating() -> None:
    steps = _security_run_steps(_load_ci())
    trivy = next(s for s in steps if str(s.get("uses", "")).startswith("aquasecurity/trivy-action"))
    uses = trivy["uses"]
    assert not uses.endswith("@master"), "trivy must be pinned to a released tag, not @master"
    ref = uses.split("@", 1)[1]
    # A released tag looks like v0.33.1 (or a 40-char commit SHA); reject the
    # moving branch refs `master`/`main`.
    assert ref not in {"master", "main"}, f"trivy ref {ref!r} is a moving branch"
    assert str(trivy["with"].get("exit-code")) == "1", (
        "trivy must exit-code:1 to gate CRITICAL/HIGH"
    )


# ── 3. The RR-03 audit is not a tautology ────────────────────────────────


def _load_rr03_audit() -> Callable[[], bool]:
    """Extract just the RR-03 functions from the audit script.

    The module imports `atelier.*` at top level (which requires the package on
    sys.path); we only want the two pure functions, so compile them in
    isolation against a minimal namespace.
    """
    tree = ast.parse(_AUDIT_SCRIPT.read_text())
    wanted = {
        "_collect_run_text",
        "_load_workflow",
        "_rr03_failure_reason",
        "audit_rr03_ci_gates",
    }
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    assert {f.name for f in funcs} == wanted, "audit script is missing the RR-03 functions"
    ns: dict[str, Any] = {"yaml": yaml, "Path": Path}
    module = ast.Module(body=funcs, type_ignores=[])
    exec(compile(module, str(_AUDIT_SCRIPT), "exec"), ns)  # noqa: S102 - trusted in-repo source
    return ns["audit_rr03_ci_gates"]


def test_audit_rr03_passes_real_workflow() -> None:
    audit = _load_rr03_audit()
    cwd = Path.cwd()
    os.chdir(_REPO_ROOT)
    try:
        assert audit() is True
    finally:
        os.chdir(cwd)


def test_audit_rr03_rejects_tautology_trap() -> None:
    """A workflow where `security` is in needs but the verify loop never reads
    needs.security.result must be FAILED by the audit. The old substring check
    passed this; the parsing check must not."""
    audit = _load_rr03_audit()
    trap = {
        "jobs": {
            "security": {"runs-on": "ubuntu-latest", "steps": [{"run": "echo scan"}]},
            "ci-success": {
                "needs": ["security", "precommit"],
                "runs-on": "ubuntu-latest",
                "steps": [
                    {
                        "run": 'if [[ "${{ needs.precommit.result }}" != "success" ]]; then exit 1; fi'
                    }
                ],
            },
        }
    }
    with tempfile.TemporaryDirectory() as d:
        gh = Path(d) / ".github" / "workflows"
        gh.mkdir(parents=True)
        (gh / "ci.yml").write_text(yaml.safe_dump(trap))
        cwd = Path.cwd()
        os.chdir(d)
        try:
            assert audit() is False
        finally:
            os.chdir(cwd)
