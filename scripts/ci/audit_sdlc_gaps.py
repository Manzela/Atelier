"""Audit script for SDLC gaps RR-01 through RR-05."""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Add project root to sys.path for imports
sys.path.append(str(Path.cwd() / "atelier-core/src"))

from atelier.models.model_armor_callbacks import _INJECTION_PATTERNS
from atelier.optimize.dreaming_module import _JUSTIFICATION_PATTERN, _PRAISE_PATTERN


def audit_rr01_chromium_sandbox():
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


def audit_rr02_prompt_injection():
    """Verify prompt injection patterns."""
    print("Auditing RR-02: Prompt Injection...")

    required = ["DAN mode", "jailbreak", "unrestricted AI"]
    found = set()
    for pattern in _INJECTION_PATTERNS:
        for req in required:
            # Normalize regex pattern for simple string matching or use re
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


def audit_rr03_ci_gates():
    """Verify CI/CD gates."""
    print("Auditing RR-03: CI/CD Gates...")
    path = Path(".github/workflows/ci.yml")
    if not path.exists():
        print(f"  Error: {path} not found")
        return False

    content = path.read_text()
    if "security:" in content and "security" in content.split("ci-success:")[1]:
        print("  PASS: Security job found and required by ci-success gate.")
        return True
    print("  FAIL: Security job missing or not required by ci-success.")
    return False


def audit_rr04_sycophancy():
    """Verify anti-sycophancy patterns."""
    print("Auditing RR-04: Sycophancy...")

    praise_regex = _PRAISE_PATTERN.pattern
    justification_regex = _JUSTIFICATION_PATTERN.pattern

    if "spectacular" in praise_regex and "compliance" in justification_regex:
        print("  PASS: Hardened sycophancy patterns found.")
        return True
    print("  FAIL: Sycophancy patterns not hardened.")
    return False


def audit_rr05_circuit_breaker():
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


def main():
    results = [
        audit_rr01_chromium_sandbox(),
        audit_rr02_prompt_injection(),
        audit_rr03_ci_gates(),
        audit_rr04_sycophancy(),
        audit_rr05_circuit_breaker(),
    ]

    if all(results):
        print("\nSDLC Audit: ALL GAPS RESOLVED.")
        sys.exit(0)
    else:
        print("\nSDLC Audit: FAILURES DETECTED.")
        sys.exit(1)


if __name__ == "__main__":
    main()
