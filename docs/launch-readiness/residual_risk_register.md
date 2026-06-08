# Residual Risk Register

This document tracks all accepted operational, security, safety, and compliance risks for the **Atelier Autonomous Design Agent** prior to go-live. Every item here has been reviewed, has an associated mitigation strategy, and requires named acceptance by the respective stakeholders.

---

## Risk Matrix Summary

| Risk ID   | Risk Category | Description                                                                            | Likelihood | Impact | Severity   | Status   | Named Owner      |
| --------- | ------------- | -------------------------------------------------------------------------------------- | ---------- | ------ | ---------- | -------- | ---------------- |
| **RR-01** | Security      | Chromium launched with `--no-sandbox` option in production containers to run axe-core. | Medium     | Medium | **Medium** | Resolved | Security Lead    |
| **RR-02** | Safety        | Prompt injection patterns bypassed by novel or obfuscated user briefs.                 | Low        | Low    | **Low**    | Resolved | Safety Lead      |
| **RR-03** | Reliability   | Heuristic evaluation stubs diverge from live browser metrics (Lighthouse CI).          | Low        | Medium | **Low**    | Resolved | Engineering Lead |
| **RR-04** | Alignment     | Anti-sycophancy reward heuristic is bypassed by subtle model brown-nosing.             | Medium     | Low    | **Low**    | Resolved | Safety Lead      |
| **RR-05** | FinOps        | Sudden API usage spikes by malicious or bugged users exhausting project billing.       | Low        | Medium | **Medium** | Resolved | Product Owner    |

---

## Detailed Risk Register

### RR-01: Chromium Sandbox Exclusion in Production Container

- **Context:** The automated accessibility gate ([axe_core.py](file:///Users/danielmanzela/Professional%20Profile/Atelier/.worktrees/audit-e2e/atelier-core/src/atelier/gates/axe_core.py)) relies on headless Chromium. Inside rootless Docker containers, Chromium cannot run with the sandbox enabled without requiring `SYS_ADMIN` kernel privileges, which raises container escape risks.
- **Mitigation:** Chromium is executed with `--no-sandbox` only when running inside the production container environment.
- **Resolution:**
  1. The production container has been hardened to run as a non-root user (`appuser`) with a read-only filesystem.
  2. A dedicated `security` job has been added to the CI/CD pipeline, running `bandit`, `semgrep`, and `trivy` to detect vulnerabilities and misconfigurations in the container image and codebase.
  3. Strict environment checks in `axe_core.py` ensure the flag is only applied in production.
- **Residual Risk:** Negligible.
- **Acceptance:** Resolved.

---

### RR-02: Prompt Injection Guard Obfuscation Bypass

- **Context:** The model boundary before-callbacks ([model_armor_callbacks.py](file:///Users/danielmanzela/Professional%20Profile/Atelier/.worktrees/audit-e2e/atelier-core/src/atelier/models/model_armor_callbacks.py)) use a compiled regex pattern set to catch natural-language overrides.
- **Mitigation:** Fail-closed client-side filter + server-side Model Armor.
- **Resolution:**
  1. Expanded the injection pattern set in `model_armor_callbacks.py` to include novel and obfuscated vectors (e.g., DAN mode, unrestricted AI scenarios).
  2. Added unit tests for the expanded pattern set in `test_sdlc_remediations.py`.
- **Residual Risk:** Low.
- **Acceptance:** Resolved.

---

### RR-03: Offline Heuristic Stubs Diverging from Live Metrics

- **Context:** Offline verification utilizes stub gates to estimate scores.
- **Mitigation:** Real browser checks in CI/CD.
- **Resolution:**
  1. Enforced a strictly blocking `ci-success` gate that requires all real-browser tests to pass.
  2. Added the `security` audit job as a required gate for release.
- **Residual Risk:** Low.
- **Acceptance:** Resolved.

---

### RR-04: Sycophancy Soft Heuristic Gaming

- **Context:** Soft heuristic penalizes sycophantic behavior.
- **Mitigation:** Combined with deterministic structured checks.
- **Resolution:**
  1. Hardened the anti-sycophancy patterns in `dreaming_module.py` with an expanded set of praise and justification tokens.
  2. Added verification tests in `test_sdlc_remediations.py` to ensure robust penalty application.
- **Residual Risk:** Low.
- **Acceptance:** Resolved.

---

### RR-05: Sudden API billing spikes

- **Context:** Malicious or buggy clients could trigger numerous agent cycles.
- **Mitigation:** Token caps and tier limits.
- **Resolution:**
  1. Verified the process-wide circuit breaker in `UsageCounterStore` is correctly called in the pre-flight check of every run.
  2. Firestore-backed per-user lifetime caps are strictly enforced per tier.
- **Residual Risk:** Low.
- **Acceptance:** Resolved.
