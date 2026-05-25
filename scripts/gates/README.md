# Phase 1 Gate Runner

## Invocation

```bash
./scripts/gates/phase_1_gate.sh
```

## Exit Codes

| Code | Meaning                               |
| ---- | ------------------------------------- |
| 0    | All gates pass — `READY-TO-TAG`       |
| 1    | At least one gate failed — `BLOCKING` |
| 2    | Script error (internal fault)         |

## Gate Inventory

The script wires all gates from the spec (§4.3 + §13.1):

| Gate | Source  | Description                            | Type           |
| ---- | ------- | -------------------------------------- | -------------- |
| 01   | §4.3 #1 | Surface converges end-to-end           | Infrastructure |
| 02   | §4.3 #2 | Cloud Run deployment working           | Infrastructure |
| 03   | §4.3 #3 | OTel + Cloud Trace functional          | Infrastructure |
| 04   | §4.3 #4 | BigQuery trajectory ingest             | Infrastructure |
| 05   | §4.3 #5 | 50/484 WebGen-Bench subset             | Test           |
| 06   | §4.3 #6 | README + ROADMAP + first 5 ADRs        | Documentation  |
| 07   | §4.3 #7 | Cost ≤ $1,200                          | Financial      |
| 08   | §13.1   | Orphan-zero (05_verify_no_orphans.py)  | Migration      |
| 09   | §13.1   | gcloud asset search returns empty      | Migration      |
| 10   | §13.1   | terraform plan zero drift              | Infrastructure |
| 11   | §13.1   | CI green 3 consecutive                 | CI             |
| 12   | §13.1   | No --no-verify in past 24h             | Governance     |
| 13   | §13.1   | pytest tests/eval/ no regression       | Test           |
| 14   | §13.1   | jq evidence_tests type check           | Schema         |
| 15   | §13.1   | jq passes+evidence check               | Schema         |
| 16   | §13.1   | features.json schema validation        | Schema         |
| 17   | §13.1   | §18-§21 protocol modules mypy --strict | Type safety    |
| 18   | §13.1   | ADR 0027-0030 at least one committed   | Documentation  |

## Rationale

Per §13.1: "All must be machine-verified — no human attestation accepted."
This script is the single source of truth for Phase 1 Gate readiness.
Run it before any `git tag -a v0.1.0-phase-1-gate` operation.

## Current State

Most infrastructure gates (01-04, 07, 08, 09, 10) will FAIL because `atelier-build-2026` is not yet created. This is expected. The script's correctness (structure, logic, exit codes) is what's verified — not the gate results.
