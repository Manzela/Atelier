# `atelier-build-2026` Readiness Assessment — 2026-05-21

**Assessed by:** Antigravity (R6-03)
**Principal:** `manzela@tngshopper.com`
**Date:** 2026-05-21T17:19Z

## Checklist

| #   | Check                 | Status     | Details                                                                                                                                                                                                                        |
| --- | --------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | Project exists        | ❌ FAIL    | `gcloud projects describe atelier-build-2026` returned permission error or 404. The project either does not exist or the current principal (`manzela@tngshopper.com`) does not have `resourcemanager.projects.get` permission. |
| 2   | Billing enabled       | ⬜ BLOCKED | Cannot check — project not accessible                                                                                                                                                                                          |
| 3   | Required APIs enabled | ⬜ BLOCKED | Cannot check — project not accessible                                                                                                                                                                                          |
| 4   | IAM policy sane       | ⬜ BLOCKED | Cannot check — project not accessible                                                                                                                                                                                          |

## Required APIs (per spec §2.3)

When the project is created, these APIs must be enabled:

- `aiplatform.googleapis.com` (Vertex AI)
- `run.googleapis.com` (Cloud Run)
- `bigquery.googleapis.com` (Trajectory store)
- `cloudtrace.googleapis.com` (OTel sink)
- `secretmanager.googleapis.com` (API keys)
- `firestore.googleapis.com` (State store — if used)
- `artifactregistry.googleapis.com` (Container images)
- `cloudbuild.googleapis.com` (CI image build)
- `iam.googleapis.com`
- `logging.googleapis.com`
- `monitoring.googleapis.com`
- `pubsub.googleapis.com`
- `compute.googleapis.com` (VPC)

## Verdict

**NOT READY.** Project must be created by Daniel before migration scripts 03-06 can execute.
See `audit/migration/atelier-build-2026-daniel-action-checklist.md` for required actions.
