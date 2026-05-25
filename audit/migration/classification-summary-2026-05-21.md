# Migration Classification Summary — 2026-05-21

**Source:** `audit/migration/inventory-i-for-ai-2026-05-21.json`
**Output:** `audit/migration/classification-2026-05-21.json`
**Classifier:** `scripts/migration/02_classify.py`

## Disposition Summary

| Disposition       | Count   |
| ----------------- | ------- |
| LEAVE_NON_ATELIER | 158     |
| MIGRATE           | 1       |
| DECOMMISSION      | 0       |
| **Total**         | **159** |

## MIGRATE Items (1)

| Kind    | Name                                                | Rationale            |
| ------- | --------------------------------------------------- | -------------------- |
| secrets | `projects/85113401879/secrets/atelier-geap-api-key` | Atelier-owned secret |

## LEAVE_NON_ATELIER Breakdown

| Resource Type     | Count | Notes                                                           |
| ----------------- | ----- | --------------------------------------------------------------- |
| gcs_buckets       | 50    | TNG Shopper / fetch infrastructure                              |
| secrets           | 45    | Non-Atelier secrets                                             |
| bigquery_datasets | 24    | Analytics datasets                                              |
| service_accounts  | 16    | Various SAs                                                     |
| artifact_registry | 7     | Container repos                                                 |
| cloud_run         | 6     | fetch-bing, fetch-ga4, fetch-gsc, stream-ga4, firestore exports |
| pubsub_topics     | 6     | Messaging infrastructure                                        |
| firestore         | 4     | Firestore databases                                             |

## DECOMMISSION Items (0)

No resources classified for decommission. The `i-for-ai` project has zero idle Vertex AI endpoints (already cleaned up).

## UNKNOWN Dispositions

**None.** All 159 resources have explicit dispositions.

## Observations

1. **Atelier footprint in `i-for-ai` is minimal** — only 1 secret (`atelier-geap-api-key`).
2. The bulk of `i-for-ai` resources (GCS buckets, BQ datasets, Cloud Run services) belong to TNG Shopper infrastructure, NOT Atelier.
3. Migration to `atelier-build-2026` is effectively a **greenfield setup** with one secret to migrate.
4. The `is_atelier_owned()` heuristic matches on `atelier`, `webgen`, `consensus`, `dpo-judge` tokens. No false positives detected in manual review.
