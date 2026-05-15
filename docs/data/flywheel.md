# Data Flywheel — DPO + LoRA Self-Improvement

Atelier's per-project judge personalization (N3 PerJudge) implements the same 3-tier dataset curation pattern as `agent-dag-pipeline`'s flywheel, retargeted from product-content to UI/UX design diffs.

## 3-tier architecture

```
Production traffic
      ↓
[T1: production-baseline] ← all sessions, partitioned by tenant_id + project_id
      ↓ D-O-R-A-V composite ≥ 0.7 AND all deterministic gates pass
[T2: quality-approved] ← chosen examples (positive)
      ↓ D-O-R-A-V < 0.5 OR any deterministic gate fails
[T3: failure-cases] ← rejected examples (negative)
      ↓
DPO preference pairs (margin ≥ 0.15) → LoRA fine-tune (Vertex AI Tuning Manager)
      ↓
Per-project judge LoRA → Vertex AI Endpoints with Multi-Tuning (S-LoRA serving)
      ↓
Improved judge in next session
```

## Storage

- **T1-T3 raw**: BigQuery, partitioned by `DATE(ts)`, clustered by `tenant_id`. Per-subject KMS encryption (GDPR right-to-be-forgotten).
- **DPO pairs**: GCS bucket `gs://atelier-dpo-pairs/<tenant>/<project>/<date>/<batch>.jsonl.zst`. DVC tracks dataset versions.
- **LoRA artifacts**: Vertex AI Model Registry per project. Versioned by training run.

## Hebbian prompt mutator (between full retrains)

Fast runtime feedback before a full LoRA training cycle. Wraps `adk optimize` (GEPA):

| Failure pattern             | Mutation type      | Effect                                                                            |
| --------------------------- | ------------------ | --------------------------------------------------------------------------------- |
| `LIGHTHOUSE_A11Y_FAIL`      | APPEND_CONSTRAINT  | Adds "ARIA labels on iconic controls; alt text on images" to the Generator prompt |
| `TOKEN_DRIFT`               | APPEND_CONSTRAINT  | Adds "use only tokens from {project_design_md_path}" to the Generator prompt      |
| `BRAND_INCONSISTENT`        | BOOST_EXAMPLE      | Injects highest-scoring exemplar from this project's T2 set                       |
| `LOW_ORIGINALITY`           | ADJUST_TEMPERATURE | Increases LLM creativity (temperature 0.3 → 0.6)                                  |
| `MOTION_NO_REDUCED_VARIANT` | APPEND_CONSTRAINT  | Adds "prefers-reduced-motion alternate must exist; reveals fire once per session" |

## Training trigger

Per-project LoRA training is curriculum-based:

1. Monitor DPO pair count per project
2. When count ≥ 50 AND mean margin ≥ 0.20 → eligible for training
3. **First-project LoRA run is eval-only baseline** (per AutonomousAgent ADR 0005 lineage) — load base, score on suite, store baseline; only then train
4. Vertex AI tuning job submitted (LoRA rank=16, alpha=32, lr=2e-5)
5. Eval against held-out adversarial + calibration golden set
6. If eval improves ≥ 2% AND no axis regresses ≥ 5% → register checkpoint
7. Per-project judge swapped in via Vertex AI Endpoints with Multi-Tuning

## Reward signals (per limits.dpo_rewards.weights)

| Signal                   | Weight | Source                                           |
| ------------------------ | ------ | ------------------------------------------------ |
| `user_explicit_accept`   | 1.0    | User clicked "ship it"                           |
| `user_implicit_accept`   | 0.3    | User didn't reject within 24h                    |
| `judge_self_consistency` | 0.2    | Generator agreement with judge across iterations |
| `convergence_completion` | 0.5    | Session reached convergence vs timeout           |

Reward horizon: 8 iterations. Sessions < 3 iterations excluded from training.

## Anti-reward-hacking guard

10% of `user_explicit_accept` signal is **held out** from DPO training. Quarterly check: judge-train correlation vs judge-holdout correlation. Drop > 5% triggers fail-loud alert (per Strategy v2 reward-hacking defense).

## Privacy + compliance

- Trajectory data is **per-tenant isolated** via BigQuery authorized views + IAM Conditions
- GDPR right-to-be-forgotten: revoke per-subject KMS key → all rows opaque without delete
- 90-day hot retention; 11-month coldline; hard delete after 365 days
- Sample to 10% before RL training (preserve diversity vs over-fitting recent signal)

## See also

- [PRD §6.6 Self-Improvement Loop](../superpowers/specs/2026-05-14-atelier-prd.md)
- [ADR 0008 — Multi-judge Bayesian-weighted consensus](../decisions/0008-multi-judge-bayesian-consensus.md)
- [agent-dag-pipeline data flywheel](https://github.com/Manzela/agent-dag-pipeline/blob/main/docs/data_flywheel.md) — direct lineage
