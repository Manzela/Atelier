# Atelier Architecture Diagram

> Full system architecture for the Google for Startups AI Agents Challenge 2026 submission.

## System Overview

```mermaid
graph TB
    subgraph "User Layer"
        U["User / Designer"]
        DASH["Firebase Hosting<br/>Bench + Replay + Auth"]
    end

    subgraph "Auth Layer"
        FB["Firebase Auth<br/>Google SSO"]
        IAP["Cloud IAP<br/>Identity-Aware Proxy"]
    end

    subgraph "API Layer — Cloud Run"
        API["FastAPI<br/>POST /v1/generate<br/>GET /v1/replay<br/>GET /v1/account/usage"]
    end

    subgraph "Pipeline — 8-Node DAG"
        N1["N1: Brief Parser<br/>ADK LlmAgent"]
        N14["N14: WRAI<br/>Vertex Search Grounding"]
        N2["N2: Source Resolver<br/>DESIGN.md Parser"]
        N3A["N3a: Generator Ensemble<br/>ADK ParallelAgent K=3<br/>Stitch MCP"]
        N3C["N3c: Deterministic Gates<br/>6 gates: HTML, CSS, a11y,<br/>performance, visual-diff"]
        N3D["N3d: Consensus Judge<br/>D-O-R-A-V 5-axis scoring<br/>Bayesian weighted"]
        N4["N4: Best Pick<br/>κ=0.70 convergence gate"]
    end

    subgraph "Self-Improving DPO Flywheel"
        TR["Trajectory Recorder<br/>BQ streaming insert"]
        MINER["DPO Pair Miner<br/>mine_pairs from BQ"]
        TUNER["GeneratorTuner<br/>tune + evaluate_and_promote"]
        VERTEX["Vertex AI Tuning<br/>gemini-2.5-flash DPO<br/>β=0.1 epochs=3"]
    end

    subgraph "Memory & Sessions"
        BQS["BigQuery Session Backend<br/>ADK BaseSessionService"]
        EPIC["Episodic Memory<br/>BQ session_events"]
    end

    subgraph "Observability"
        OTEL["OTel Spans<br/>15-attribute schema"]
        CT["Cloud Trace"]
        CL["Cloud Logging"]
        BENCH["Bench Dashboard<br/>bench.atelier.autonomous-agent.dev"]
    end

    subgraph "GCP Infrastructure"
        CR["Cloud Run<br/>atelier-api-staging"]
        BQ[("BigQuery<br/>atelier_trajectories")]
        SM["Secret Manager<br/>API keys + tokens"]
        KMS["Cloud KMS<br/>Per-tenant encryption"]
        CF["Cloudflare<br/>DNS + CDN + DDoS"]
    end

    U --> DASH
    DASH --> FB
    FB --> IAP
    IAP --> API
    API --> N1
    N1 --> N14
    N14 --> N2
    N2 --> N3A
    N3A --> N3C
    N3C --> N3D
    N3D --> N4
    N4 --> TR
    TR --> BQ
    MINER --> BQ
    TUNER --> MINER
    TUNER --> VERTEX
    VERTEX --> N3A
    API --> BQS
    BQS --> BQ
    N3D --> EPIC
    EPIC --> BQ
    API --> OTEL
    OTEL --> CT
    OTEL --> CL
    BQ --> BENCH
    CF --> DASH
    CF --> API
    SM --> N3A
    KMS --> BQ
```

## Technology Stack

| Layer           | Technology                    | Purpose                             |
| --------------- | ----------------------------- | ----------------------------------- |
| Agent Framework | Google ADK 2.0                | Orchestration, evaluation, sessions |
| Models          | Gemini 2.5 Flash + 3 Pro      | Generation, judgment, DPO tuning    |
| API             | FastAPI on Cloud Run          | REST API + auth middleware          |
| Auth            | Firebase Auth + Cloud IAP     | Google SSO + proxy security         |
| Storage         | BigQuery                      | Trajectories, sessions, DPO pairs   |
| Hosting         | Firebase Hosting + Cloudflare | Dashboards + CDN                    |
| Tuning          | Vertex AI PREFERENCE_TUNING   | DPO fine-tuning pipeline            |
| Observability   | Cloud Trace + Cloud Logging   | OTel spans + structured logs        |
| Secrets         | Secret Manager + KMS          | Keys + per-tenant encryption        |
| Eval            | ADK golden_set.json           | tool_trajectory + rubric scoring    |

## Data Flow

1. **Request**: User submits a design brief through the Firebase-hosted dashboard or API
2. **Authentication**: Firebase Auth verifies Google SSO token → Cloud IAP enforces ingress policy
3. **Pipeline**: FastAPI routes to the 8-node DAG: N1 parses the brief, N14 enriches with web research, N2 resolves source context, N3a generates K=3 candidates via Stitch MCP
4. **Quality gates**: N3c runs 6 deterministic gates (fast, hallucination-free filter) → N3d runs D-O-R-A-V multi-judge consensus on surviving candidates
5. **Convergence**: N4 selects the best candidate if composite score ≥ 0.70 (κ threshold)
6. **Recording**: TrajectoryRecorder streams the full trajectory to BigQuery for DPO pair extraction
7. **Self-improvement**: The DPO Pair Miner extracts preference pairs from accumulated trajectories → GeneratorTuner submits tuning jobs to Vertex AI → promoted adapters feed back into N3a
