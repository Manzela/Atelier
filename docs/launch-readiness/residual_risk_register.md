# Residual Risk Register

This document tracks all accepted operational, security, safety, and compliance risks for the **Atelier Autonomous Design Agent** prior to go-live. Every item here has been reviewed, has an associated mitigation strategy, and requires named acceptance by the respective stakeholders.

---

## Risk Matrix Summary

| Risk ID   | Risk Category | Description                                                                            | Likelihood | Impact | Severity   | Status   | Named Owner      |
| --------- | ------------- | -------------------------------------------------------------------------------------- | ---------- | ------ | ---------- | -------- | ---------------- |
| **RR-01** | Security      | Chromium launched with `--no-sandbox` option in production containers to run axe-core. | Medium     | Medium | **Medium** | Accepted | Security Lead    |
| **RR-02** | Safety        | Prompt injection patterns bypassed by novel or obfuscated user briefs.                 | Low        | Low    | **Low**    | Accepted | Safety Lead      |
| **RR-03** | Reliability   | Heuristic evaluation stubs diverge from live browser metrics (Lighthouse CI).          | Low        | Medium | **Low**    | Accepted | Engineering Lead |
| **RR-04** | Alignment     | Anti-sycophancy reward heuristic is bypassed by subtle model brown-nosing.             | Medium     | Low    | **Low**    | Accepted | Safety Lead      |
| **RR-05** | FinOps        | Sudden API usage spikes by malicious or bugged users exhausting project billing.       | Low        | Medium | **Medium** | Accepted | Product Owner    |

---

## Detailed Risk Register

### RR-01: Chromium Sandbox Exclusion in Production Container

- **Context:** The automated accessibility gate ([axe_core.py](file:///Users/danielmanzela/Professional%20Profile/Atelier/.worktrees/audit-e2e/atelier-core/src/atelier/gates/axe_core.py)) relies on headless Chromium. Inside rootless Docker containers, Chromium cannot run with the sandbox enabled without requiring `SYS_ADMIN` kernel privileges, which raises container escape risks.
- **Mitigation:** Chromium is executed with `--no-sandbox` only when running inside the production container environment. The blast radius is strictly contained because:
  1. The container runs as a non-root, read-only user.
  2. The HTML/CSS rendered by the browser is generated locally by the agent (it does not parse arbitrary, untrusted third-party user input).
- **Residual Risk:** A compromised agent model generating exploit payloads could target browser engine vulnerabilities.
- **Acceptance:** Accepted by the Security Lead.

---

### RR-02: Prompt Injection Guard Obfuscation Bypass

- **Context:** The model boundary before-callbacks ([model_armor_callbacks.py](file:///Users/danielmanzela/Professional%20Profile/Atelier/.worktrees/audit-e2e/atelier-core/src/atelier/models/model_armor_callbacks.py)) use a compiled regex pattern set to catch natural-language overrides. Obfuscated or multi-turn injection vectors may bypass the regex.
- **Mitigation:**
  1. The regex is a fast, fail-closed client-side filter. The primary defense-in-depth is the server-side, managed Google Cloud Model Armor template in `us-central1` which scans all inputs.
  2. The agent executes in a sandboxed execution thread and cannot access host APIs, databases, or issue HTTP requests.
- **Residual Risk:** Adversarial briefs could trigger model refusal or divert the specialist pipeline, leading to invalid code output.
- **Acceptance:** Accepted by the Safety Lead.

---

### RR-03: Offline Heuristic Stubs Diverging from Live Metrics

- **Context:** Offline verification utilizes stub gates (e.g. `check_lighthouse_stub`, `check_visual_diff_stub`) to estimate scores. These are browser-free proxies to keep offline checks fast and hermetic.
- **Mitigation:**
  1. Real browser checks (via `check_axe` running actual Chromium) are executed in CI/CD and production environments.
  2. A live golden-path walkthrough test (`test_production_readiness.py`) runs against the deployed stack on every release.
- **Residual Risk:** An optimization regression that passes heuristic stubs but fails real metrics in production.
- **Acceptance:** Accepted by the Engineering Lead.

---

### RR-04: Sycophancy Soft Heuristic Gaming

- **Context:** The dreaming module ([dreaming_module.py](file:///Users/danielmanzela/Professional%20Profile/Atelier/.worktrees/audit-e2e/atelier-core/src/atelier/optimize/dreaming_module.py)) penalizes sycophantic behavior using a soft heuristic (e.g., searching for specific praise tokens). A model could learn to bypass this penalty by rephrasing sycophantic statements.
- **Mitigation:** The anti-sycophancy penalty is combined with deterministic structured checks (Semantic HTML, WCAG contrast) that cannot be gamed by verbal strategies.
- **Residual Risk:** Model tuning updates may drift toward sycophantic/yes-man behavior in narrative critiques.
- **Acceptance:** Accepted by the Safety Lead.

---

### RR-05: Sudden API billing spikes

- **Context:** Malicious or buggy clients could bypass standard front-end rate limits and trigger numerous agent cycles, causing Vertex AI pricing charges.
- **Mitigation:**
  1. Token caps are enforced at the orchestrator level (`governor.py`) on every request, backed by Firestore.
  2. Tier limits are hardcoded: Pro 5M, Flash 15M, Flash-Lite 60M.
- **Residual Risk:** Multiple registered users exhausting their individual tiers simultaneously, raising total billing.
- **Acceptance:** Accepted by the Product Owner and FinOps Lead.
