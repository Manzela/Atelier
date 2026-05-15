# 0002. Cloud Run jobs for runtime, not Agent Engine

**Status:** Accepted
**Date:** 2026-05-14
**Decision-makers:** Daniel Manzela (+ Claude Opus 4.7 MAX as builder)

## Context

Atelier needs a runtime to host the convergence loops. Three Google-native options:

1. **Vertex AI Agent Engine** (renamed under GEAP umbrella Apr 23 2026) — managed runtime; auto-scaling; first-class ADK integration; per-request billing
2. **Cloud Run** (jobs + services) — managed serverless containers; longer execution time; per-vCPU-second billing; scale-to-zero
3. **GKE Autopilot** — managed Kubernetes; fixed pricing per pod-hour; complex but flexible

Atelier's runtime characteristics that matter:

- A single convergence session can run **minutes to hours** (K=6 candidates × multi-judge × iterative fixer × multi-surface campaign)
- A single campaign can span **multiple sessions over days**
- Cost is **dominated by Sessions billing** ($0.25 per 1,000 stored events) — Google's "Standard Agent" benchmark (10 QPS, 5s/req, 2 vCPU/5 GiB) costs **$43,241/mo on Agent Engine, with Sessions alone costing $19,440/mo**
- Cold-start matters less than long-job efficiency

## Decision

**We will run the Atelier agent runtime on Cloud Run jobs**, not Agent Engine. Agent Engine provides Sessions, Memory Bank, A2A endpoint, and Agent Builder console as services we *call*.

Specifically:
- **Atelier API** (FastAPI) → Cloud Run service (request/response, auto-scale, low-latency)
- **Atelier Agent runtime** (the convergence loops) → Cloud Run jobs (long-running, scale-to-zero, billed per vCPU-second)
- **Sessions** (hot UI state) → Vertex AI Agent Engine Sessions (capped writes — we only persist node boundaries + final convergence state; trajectory captures go to Firestore + BigQuery)
- **Memory Bank** (cross-session preferences) → Vertex AI Memory Bank (managed, LLM-extracts memories)
- **A2A endpoint** → Vertex AI Agent Engine's A2A surface

## Consequences

### Positive

- Cost compression: Cloud Run jobs at $0.0864/vCPU-hr + $0.0090/GiB-hr beats Agent Engine's per-request billing for minutes-to-hours sessions
- Agent Engine Sessions billing capped (only persist node boundaries) — avoids the $19K/mo Sessions trap at modest scale
- Cloud Run jobs scale-to-zero; no idle cost when no campaigns are running
- Cloud Run supports up to 24-hour execution per job (Atelier campaigns rarely exceed 6 hours)
- Cloud Run has CMEK support (Agent Engine doesn't yet); keeps a path open for regulated tenants without a re-platforming
- We still get all GEAP benefits (Memory Bank, A2A, IAM Conditions) via service-to-service calls

### Negative

- Two compute substrates instead of one (Cloud Run + Agent Engine for state) — slightly more ops surface
- Lose Agent Engine's auto-scaling-per-request (we manage Cloud Run job concurrency manually)
- Cloud Run jobs don't have first-class ADK integration like Agent Engine does — we wrap ADK Runner in a Cloud Run job entrypoint ourselves

### Neutral

- This pattern is documented as supported by Google in [adk-docs #742](https://github.com/google/adk-docs/issues/742) and Google's own labs ([from-code-to-cloud](https://cloud.google.com/blog/topics/developers-practitioners/from-code-to-cloud-three-labs-for-deploying-your-ai-agent))

## Alternatives considered

### Option A: Run on Agent Engine for runtime + Sessions

- Pros: One platform, first-class ADK integration, auto-scaling-per-request
- Cons: Per-request runtime model is wrong for minutes-to-hours sessions; Sessions billing is dominant cost lever; no CMEK
- Why rejected: Cost projection at modest scale ($43K/mo Standard Agent benchmark) is unacceptable; CMEK gap blocks regulated tenants permanently

### Option B: Run on GKE Autopilot

- Pros: Maximum flexibility, predictable pricing per pod-hour, native CMEK
- Cons: Significant ops overhead (Kubernetes operations, networking, scaling configuration); slower iteration during 3-week sprint
- Why rejected: Ops complexity not justified at MVP scale; revisit if Cloud Run jobs prove insufficient

## References

- [PRD §6.2 Cluster Bv3 production stack](../superpowers/specs/2026-05-14-atelier-prd.md)
- [adk-docs #742](https://github.com/google/adk-docs/issues/742) — Cloud Run vs Agent Engine discussion
- [Google Cloud labs: from-code-to-cloud](https://cloud.google.com/blog/topics/developers-practitioners/from-code-to-cloud-three-labs-for-deploying-your-ai-agent)
- [Vertex AI Agent Engine pricing](https://cloud.google.com/products/gemini-enterprise-agent-platform/pricing)
- [Cloud Run pricing](https://cloud.google.com/run/pricing)
