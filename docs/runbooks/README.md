# Runbooks

Operational procedures for running, recovering, and supporting Atelier in production.

## Status

**Phase 0** — runbook index scaffolded; individual runbooks populated as Phase 1+ ships them.

## Index

| Runbook                                      | When to use                                                      | Status        |
| -------------------------------------------- | ---------------------------------------------------------------- | ------------- |
| [recovery.md](recovery.md)                   | Stack is broken; panic was invoked; restore from snapshot        | 📝 Phase 1 D7 |
| [on-call.md](on-call.md)                     | Alert routing, escalation matrix, common-incident playbook       | 📝 Phase 2 W2 |
| [deployment.md](deployment.md)               | Deploy a new version to staging or prod                          | 📝 Phase 1 D7 |
| [incident-response.md](incident-response.md) | A user or panel reports a security or major operational issue    | 📝 Phase 2 W3 |
| [customer-support.md](customer-support.md)   | A user reports a problem via in-product, email, or GitHub Issues | 📝 Phase 3    |

## Conventions

Every runbook:

- States its prerequisites at the top
- Lists steps in order with expected output for each
- Has a clear "pass criteria" or "expected end state"
- Says what to do if a step fails (link to recovery.md or escalate to on-call)

## Phase acceptance runbooks (sprint-specific)

| Runbook                | When                | Acceptance criteria                                                                        |
| ---------------------- | ------------------- | ------------------------------------------------------------------------------------------ |
| `phase1-acceptance.md` | End of D7 (May 21)  | 1-surface end-to-end + Cloud Run staging deploy + CI green + 50/484 WebGen-Bench passing   |
| `phase2-acceptance.md` | End of D14 (May 28) | 12-surface autonomous campaign + WebGen-Bench full ≥ 51 + 5 beta tenants signed in         |
| `phase3-acceptance.md` | End of D20 (Jun 3)  | All 13 novel contributions evidenced + 32 pre-launch artifacts live + G4S submission filed |
