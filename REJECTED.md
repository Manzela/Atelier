# REJECTED.md — Failed approaches & dead ends

> Long-term memory of approaches we've tried that didn't work. Future sessions read this before re-attempting anything. Pattern from AutonomousAgent SESSION-COMPLETE doc + Karpathy LLM-wiki convention.

> **Auto-injected into every Claude Code session.** When tempted by an approach not currently in the codebase, check this file first.

---

## Format

Each rejected approach gets a dated entry:

```markdown
### YYYY-MM-DD — <short title>

**Approach attempted**: <what we tried>
**Where in the code (if any)**: <git SHA or branch — useful for "show me what this looked like">
**Why it failed**: <root cause + symptoms observed>
**What we did instead**: <chosen alternative + reference>
**When to revisit (if ever)**: <conditions under which this might become viable>
**Related ADR/issue**: <link>
```

---

## Rejected approaches

_(Populated as the sprint reveals dead ends. Initial state: empty.)_

### Reserved entries (pre-emptively documented from research synthesis)

These are approaches the research has already shown will fail; documented here so we don't accidentally try them.

### 2026-05-14 — Use Langfuse for prompt/trace observability

**Approach attempted**: Self-host Langfuse on GKE Autopilot for production-grade prompt + trace UI.
**Where in the code**: Initial Cluster B v1 design (pre-v2 unification).
**Why it failed (preempted)**: Cloud Trace + Cloud Monitoring + Cloud Logging + Vertex AI Studio Tracing UI + Atelier Dashboard cover ~95% of Langfuse functionality. Adding Langfuse adds a stateful service to operate, splits observability across two stacks, doubles auth/RBAC surface, and **conflicts with the "Use of Google Cloud" judging criterion**.
**What we did instead**: Google-native observability stack only. Per [ADR 0006](docs/decisions/0006-google-native-stack-no-langfuse.md).
**When to revisit**: Never — the architectural choice is locked.

### 2026-05-14 — Run Atelier on Vertex AI Agent Engine for runtime

**Approach attempted**: Deploy the Atelier agent runtime directly to Agent Engine (managed runtime).
**Why it failed (preempted)**: Agent Engine's per-request runtime model is wrong for our use case. Convergence loops run minutes-to-hours per session. Sessions billing alone would cost $19K/mo at Google's published Standard Agent benchmark (10 QPS / 5s/req / 2vCPU/5GiB). Cold-start on every invocation. No warm-pool primitive.
**What we did instead**: **Cloud Run jobs** for runtime, with Agent Engine providing Sessions, Memory Bank, A2A endpoint as services we _call_. Per [ADR 0002](docs/decisions/0002-cloud-run-not-agent-engine-for-runtime.md). Confirmed in adk-docs #742 and Google's own labs.
**When to revisit**: When Agent Engine adds long-job billing or warm-pool primitive.

### 2026-05-14 — Fork agent-dag-pipeline as the base codebase

**Approach attempted**: Fork the user's `agent-dag-pipeline` repo as Atelier's starting point; modify internals to retarget from retail-product enrichment to UI/UX.
**Why it failed (preempted)**: Per AutonomousAgent ADR 0001 lineage, **wrap-don't-fork** preserves upgrade paths and avoids merge friction. Forking breaks the ability to consume upstream improvements; doubles maintenance burden; misaligns governance.
**What we did instead**: Consume `agent-dag-pipeline` via `pip install agent-dag-pipeline==<pinned-version>` in `requirements.lock`. Subclass public APIs without modifying upstream source. Per [ADR 0001](docs/decisions/0001-wrap-dont-fork-inheritance-model.md).
**When to revisit**: Only if upstream is abandoned; even then, prefer hard-fork as a separate repo over modifying inline.

### 2026-05-14 — Use Statsig or GrowthBook for feature flags + A/B testing

**Approach attempted**: Self-host Statsig (or use GrowthBook) for progressive rollouts and A/B testing.
**Why it failed (preempted)**: We already have Firebase via Identity Platform. **Firebase Remote Config + A/B Testing** covers the same use cases natively. Adding Statsig duplicates an existing capability and breaks the unified-stack principle.
**What we did instead**: Firebase Remote Config + A/B Testing. Per [ADR 0006](docs/decisions/0006-google-native-stack-no-langfuse.md).
**When to revisit**: If Firebase A/B Testing proves insufficient for advanced experimentation (e.g., contextual bandits) — not in MVP scope.

### 2026-05-14 — Use PostHog for product analytics

**Approach attempted**: Self-host PostHog for funnels, retention, NPS prompts.
**Why it failed (preempted)**: We're already in BigQuery for trajectories. **Firebase Analytics + GA4 + BigQuery Export + Looker Studio** covers funnels, retention, NPS. PostHog is a parallel data store we don't need.
**What we did instead**: Firebase Analytics + GA4 + BigQuery Export. Per [ADR 0006](docs/decisions/0006-google-native-stack-no-langfuse.md).
**When to revisit**: If we need PostHog-specific session-replay or feature usage heatmaps that GA4 doesn't provide.

### 2026-05-14 — Use GKE Autopilot for self-hosted vLLM Multi-LoRA serving

**Approach attempted**: Run our own vLLM cluster with `--enable-lora` on GKE Autopilot for per-project judge LoRA serving.
**Why it failed (preempted)**: **Vertex AI Endpoints with Multi-Tuning Manager** is the managed equivalent. Same S-LoRA-style adapter swap, no K8s ops, model-registry-versioned, Workload Identity Federation auth.
**What we did instead**: Vertex AI Endpoints + Multi-Tuning. Predibase/Together LoRAX as managed fallback. Per [PRD §10 inheritance map].
**When to revisit**: If Vertex AI Endpoints proves insufficient for adapter count > 10K (S-LoRA paper's claim) — measure before deciding.

### 2026-05-14 — Use LiteLLM as the production model proxy

**Approach attempted**: LiteLLM Proxy as the per-tenant cost-routing + virtual-keys layer.
**Why it failed (preempted)**: We're 100% Vertex/Gemini in MVP — multi-provider routing is YAGNI. **Apigee AI Gateway** is the first-class ADK integration with the same per-tenant rate-limit + cost router + Sanitize policies (Model Armor) primitives. Adding LiteLLM duplicates Apigee + isn't on-rubric for "Use of Google Cloud."
**What we did instead**: Apigee AI Gateway only. Per [ADR 0006](docs/decisions/0006-google-native-stack-no-langfuse.md).
**When to revisit**: If we need OpenAI/Anthropic fallback in production; LiteLLM can be added as a sidecar later without touching the agent code.

---

_(Future entries get appended here as the sprint reveals new dead ends. Each entry is permanent; we never delete REJECTED.md content — only annotate "When to revisit" if circumstances change.)_
