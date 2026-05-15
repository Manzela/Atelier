# 0006. Google-native stack — no Langfuse, Statsig, PostHog, GKE-S-LoRA, LiteLLM

**Status:** Accepted
**Date:** 2026-05-14
**Decision-makers:** Daniel Manzela (+ Claude Opus 4.7 MAX as builder)

## Context

Initial architecture sketches (Cluster B v1) included popular OSS / 3rd-party tools where Google has native equivalents:

- Langfuse for prompt/trace observability
- Statsig (or GrowthBook) for feature flags + A/B testing
- PostHog for product analytics
- GKE Autopilot for self-hosted vLLM Multi-LoRA serving
- LiteLLM Proxy for cost routing + virtual keys

Each was technically defensible in isolation. But together they introduced **architectural sprawl**: 5 additional self-hosted services, 5 separate auth/RBAC surfaces, 5 separate ops surfaces, 5 separate observability hops.

Critical context: **the Google for Startups AI Agents Challenge 2026 explicitly judges on "Use of Google Cloud."** Running a parallel OSS observability stack alongside Google's native stack actively undermines that scoring axis.

## Decision

**Atelier ships on a unified Google-native stack.** Every layer that can be Google-native is Google-native. Two non-Google components total: Stripe (no Google billing platform) and Telegram (already owned from hermes-agent inheritance).

| Layer                              | Google-native                                                                                                        | Replaces                             |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------- | ------------------------------------ |
| Multi-agent orchestration          | ADK 2.0 Beta (`SequentialAgent`, `ParallelAgent`, `LoopAgent`, `MCPToolset`, `rubric_based_*_v1`, Skills for Agents) | Custom orchestrator                  |
| Cross-session memory               | `VertexAiMemoryBankService`                                                                                          | Custom MEMORY/SOUL persistence       |
| Pattern embeddings                 | Vertex Vector Search 2.0 + multimodal-embedding                                                                      | Self-hosted Chroma/FAISS             |
| Multi-axis evaluation              | `rubric_based_final_response_quality_v1` + `adk eval`                                                                | Custom eval harness                  |
| Prompt optimization                | `adk optimize` (GEPA)                                                                                                | Custom Hebbian mutator backend       |
| Replay testing                     | `adk conformance`                                                                                                    | Custom replay harness                |
| MCP integration                    | `MCPToolset`                                                                                                         | Custom MCP client wrapper            |
| Auth (multi-tenant public users)   | **Identity Platform**                                                                                                | Auth0 / Clerk / custom               |
| Per-tenant isolation               | **IAM Conditions on session resources**                                                                              | Custom RBAC                          |
| Cost / rate-limit / model routing  | **Apigee AI Gateway**                                                                                                | **LiteLLM Proxy**                    |
| Safety                             | **Model Armor** + **Gemini-as-judge plugin**                                                                         | Llama Prompt Guard 2                 |
| **Observability — traces**         | **Cloud Trace + OTel GenAI semconv**                                                                                 | **Langfuse**                         |
| **Observability — metrics + SLOs** | **Cloud Monitoring**                                                                                                 | Datadog / Grafana                    |
| **Observability — logs**           | **Cloud Logging**                                                                                                    | ELK / Loki                           |
| **Observability — prompt UI**      | **Vertex AI Studio Tracing UI + Atelier Dashboard**                                                                  | **Langfuse UI**                      |
| **Feature flags + A/B tests**      | **Firebase Remote Config + A/B Testing**                                                                             | **Statsig / GrowthBook**             |
| **Product analytics**              | **Firebase Analytics + GA4 + BigQuery Export + Looker Studio**                                                       | **PostHog**                          |
| Auth at edge                       | Identity Platform / Firebase Auth                                                                                    | —                                    |
| Per-IP rate limits                 | Cloud Armor                                                                                                          | —                                    |
| Hot UI state                       | Agent Engine Sessions (capped) + Firestore                                                                           | —                                    |
| Trajectory captures                | BigQuery + GCS coldline                                                                                              | —                                    |
| Per-tenant LoRA serving            | **Vertex AI Endpoints with Multi-Tuning**                                                                            | **GKE Autopilot S-LoRA self-hosted** |
| Tuning (SFT + DPO)                 | Vertex AI tuning jobs                                                                                                | Custom training pipeline             |
| Runtime hosting                    | Cloud Run jobs (per ADR 0002)                                                                                        | —                                    |
| Deployment                         | `adk deploy cloud_run --with_ui --a2a`                                                                               | Custom deploy scripts                |
| Secrets                            | Secret Manager + Cloud KMS for BYOK                                                                                  | sops + age (only for repo configs)   |
| Docs site hosting                  | **Firebase Hosting**                                                                                                 | Vercel / Netlify / GH Pages          |
| Status page                        | Self-built static on Firebase Hosting                                                                                | StatusPage.io                        |
| Alerting                           | Cloud Monitoring → Telegram + email                                                                                  | PagerDuty (defer to enterprise tier) |
| Compliance evidence                | Google's compliance reports + manual evidence                                                                        | Vanta (defer to month 6)             |
| Container registry                 | Artifact Registry                                                                                                    | Docker Hub / GHCR                    |
| CI/CD                              | GitHub Actions → Cloud Build → WIF → Cloud Run                                                                       | —                                    |

## Consequences

### Positive

- **Direct alignment with G4S "Use of Google Cloud" judging criterion** — the architecture diagram is the pitch slide
- One pager (Cloud Monitoring), one trace UI (Cloud Trace), one logging surface (Cloud Logging), one auth model (IAM + Identity Platform), one IaC stack (Terraform → GCP only), one bill, one quota model, one SLA contract
- No additional self-hosted stateful services to operate (no Langfuse on GKE, no Statsig backend, no PostHog backend)
- Cost compression: each native service is cheaper than its OSS equivalent at our scale
- Proves Google's GEAP + ADK + Memory Bank + A2UI stack can ship a production-grade self-improving agent — Atelier becomes a reference implementation Google can point at

### Negative

- Locked into Google for these capabilities (vendor concentration)
- If a Google service is degraded, parallel OSS would have provided a fallback (mitigated: most failures are transient and recover; Cloud Run multi-region failover available in Phase 2)
- Some Google services (Apigee, Vertex tuning) have steeper learning curves than their OSS equivalents — slower onboarding for new contributors

### Neutral

- This is a deliberate choice for the competition + first-product launch. Post-launch, if portability becomes a customer requirement, we can add OSS sidecars (e.g., LiteLLM for multi-provider routing) without rewriting the core

## Alternatives considered

### Option A: Best-of-breed OSS for each capability (Langfuse + Statsig + PostHog + GKE-S-LoRA + LiteLLM)

- Pros: Portability across cloud providers; no vendor lock-in for any single capability
- Cons: 5 additional self-hosted services; misaligns with G4S judging criterion; 5× ops surface
- Why rejected: Sprawl + criterion-misalignment outweigh portability benefit at MVP scale

### Option B: Best-of-breed managed SaaS (Langfuse Cloud + Statsig + PostHog Cloud + Modal + Portkey)

- Pros: No self-hosting; portable
- Cons: 5 additional billing accounts, 5 additional auth surfaces, still misaligns with G4S
- Why rejected: Same misalignment, plus higher cost than Google-native equivalents

## References

- [PRD §8 Tech stack (Google-native, sprawl-free)](../superpowers/specs/2026-05-14-atelier-prd.md)
- [REJECTED.md entries — Langfuse, Statsig, PostHog, GKE-S-LoRA, LiteLLM](../../REJECTED.md)
- [G4S 2025 judging criteria (inferred from public materials)](https://startup.google.com/programs/agents-challenge)
