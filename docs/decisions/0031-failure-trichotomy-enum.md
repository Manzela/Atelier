# 0031. Failure Trichotomy Enum — Typed Failure Modes for External IO

**Status:** Accepted
**Date:** 2026-05-21
**Decision-makers:** Daniel Manzela (Principal Architect), Atelier sprint

## Context

CLAUDE.md §5 defines a failure-handling trichotomy (fail-loud, fail-soft, self-heal) used informally in every executor brief since R3. However, the trichotomy was enforced only by code review — no type-level enforcement existed, no grep could verify coverage, and the R4 audit (spec §23) found two callsites that silently swallowed gcloud errors without declaring their failure intent.

Spec §13.1 Gate g09 requires: "Failure trichotomy enum stamped on every external-IO callsite." Without a machine-verifiable decorator, this gate can not pass.

## Decision

Adopt a typed `FailureMode` enum (`FAIL_LOUD | FAIL_SOFT | SELF_HEAL`) and a `@failure_trichotomy(fail_mode=..., max_retries=N)` decorator in `atelier.runtime.failure`. Every function that performs external IO (gcloud, Vertex API, BigQuery, Secret Manager, etc.) MUST be decorated with `@failure_trichotomy`.

### `FailureMode` values

| Mode        | Behavior                                  | Retry                     | Use case                                         |
| ----------- | ----------------------------------------- | ------------------------- | ------------------------------------------------ |
| `FAIL_LOUD` | Raise immediately                         | No                        | Auth failures, missing projects, corrupted state |
| `FAIL_SOFT` | Log warning + return `None`               | No                        | Optional telemetry, missing CI jobs              |
| `SELF_HEAL` | Retry N times, then escalate to FAIL_LOUD | Yes (up to `max_retries`) | Transient gcloud 429/503, pip timeouts           |

### Decorator contract

```python
@failure_trichotomy(fail_mode=FailureMode.SELF_HEAL, max_retries=3)
def fetch_secret(project: str, name: str) -> str:
    ...
```

- `max_retries` is only meaningful for `SELF_HEAL`. For `FAIL_LOUD` and `FAIL_SOFT`, it is ignored.
- Negative `max_retries` raises `ValueError` at decoration time.
- The decorator stamps `_failure_mode` and `_max_retries` on the wrapper for introspection by audit tooling.

### Coverage verification

```bash
grep -rn "@failure_trichotomy" atelier-core/src/atelier/ | wc -l
```

The count must match the number of functions performing external IO. Gate g09 runs this as a machine check.

## Consequences

### Positive

- Every external-IO callsite declares its failure contract at the type level.
- `grep @failure_trichotomy` gives machine-verifiable coverage for Gate g09.
- Silent error suppression (bare `except: pass`) becomes structurally impossible — the decorator is the ONLY path to exception handling on IO callsites.

### Negative

- Decorator overhead (~2μs per call for FAIL_LOUD passthrough). Acceptable for IO-bound callsites where the IO itself is 10-1000ms.
- Requires discipline: every new IO callsite must add the decorator. Mitigation: pre-commit hook or CI lint.

### Neutral

- The decorator does not handle async functions (async support is a Phase 2 enhancement if needed).

## Alternatives considered

**Option A: `try/except` blocks with inline comments.**
Pros: no decorator overhead. Cons: R4 audit showed comments don't prevent silent swallowing; no machine verification. **Rejected — measured to fail.**

**Option B: A `Result[T, E]` monadic return type.**
Pros: type-safe error handling. Cons: requires every callsite to unwrap; Python's type system makes `Result` ergonomically painful vs. exceptions; alien to the existing codebase style. **Rejected — too heavy a refactor for the sprint.**

**Option C: Custom exception hierarchy only (no decorator).**
Pros: standard Python. Cons: doesn't enforce that every callsite declares a mode; bare `except` still compiles. **Rejected — doesn't close the enforcement gap.**

## References

- CLAUDE.md §5 (failure-handling trichotomy definition)
- Spec §13.1 Gate g09 (failure trichotomy enum stamped on every external-IO callsite)
- Spec §23 (R4 audit reconciliation — silent error suppression incidents)
- Implementation: `atelier-core/src/atelier/runtime/failure.py`
- Tests: `atelier-core/tests/unit/test_failure_trichotomy.py`
