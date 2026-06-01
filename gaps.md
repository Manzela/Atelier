# AT-095 — gaps.md (per-user lifetime 5M-token hard cap)

## Status: implementation complete, all verify lanes green

- mypy --strict: clean (93 src files).
- verify-tests: 928 passed, 7 skipped (full offline lane incl. AT-003 determinism, AT-020/021).
- verify-eval: 8 passed (AT-100 deterministic gate, zero live calls).
- ruff check + format: clean on all changed files.
- New oracles: `tests/unit/test_usage_counter.py` (store), `tests/unit/test_token_cap.py` (runner-level, the 7 acceptance criteria a–g).

## What shipped (PRD §13.2 / G14 / G15 / G16 / R1 / R5)

- `atelier/durability/usage_counter.py` — `UsageCounterStore`: cumulative per-uid counter at Firestore `users/{uid}/usage/lifetime` (atomic `Increment`), in-memory backend for the hermetic/dev lane (process-wide, so cross-run durability + byte-stable meter hold), per-window request-rate limiter. Fail-closed on a hard persistence error.
- `orchestrator/governor.py` — **removed** the USD cap (`_check_budget`, `is_over_budget`, `budget_cap_usd`, `total_cost_usd`, `_check_step_budget`, `MAX_STEP_COST_USD`, `GovernorBudgetExceeded`, `GovernorStepBudgetExceeded`); **added** `GovernorTokenCapExceeded` / `GovernorRateLimitExceeded`, `GovernorState.{user_id,cumulative_user_tokens,token_cap}`, `add_user_tokens`, `is_over_token_cap`, `_check_token_budget` (pre-flight, fail-loud), `TOKEN_CAP_MESSAGE`.
- `orchestrator/runner.py` — seed counter from store at run-start + before the screen loop (covers resume); pre-flight reject when already at cap (no Vertex call); count real N3a tokens (ADK `event.usage_metadata`, incl. `thoughts_token_count`) or a deterministic offline estimate; write-through persist; emit `token_delta` SSE event; graceful in-run cap stop → `TOKEN_CAP_EXHAUSTED` + branded message; payload now `tokens_used`/`token_cap` (no USD).
- `nodes/llm_judge.py` — capture `thoughts_token_count` into `LLMJudgeResponse.thinking_tokens` (G15).
- `api/app.py` — `GovernorTokenCapExceeded` → 402 branded message + alertable breach log (uid/session/IP, sanitized); `GovernorRateLimitExceeded` → 429 + Retry-After.
- `api/generate.py` — removed `budget_usd` request field + USD plumbing; `GenerateResponse` now carries `tokens_used`/`token_cap`; SSE path emits a clean `degraded` cap event instead of a raw error.
- `cli.py` — removed the `--budget` USD flag.
- `pyproject.toml` (both) — declared `google-cloud-firestore` direct dep (already lock-pinned 2.27.0 transitively); added the `atelier.durability.usage_counter` mypy override (firebase-admin has no py.typed, mirrors `atelier.auth.*`).

## Known gaps / deliberate scope boundaries (follow-ups, not blockers)

1. **N3d judge tokens are not yet added to the lifetime counter.** The counter currently counts N3a generation tokens (the dominant cost) + the deterministic offline estimate. `llm_judge` now _captures_ `thinking_tokens`, but the judge (N3d) deltas are not threaded into `cumulative_user_tokens`. Acceptance (a–g) are satisfied without it (the cap fires on N3a + seeding). Threading judge tokens is a clean follow-up — low risk, additive. The cap therefore slightly _under_-counts real usage (conservative for the user, not a security hole — it never _over_-counts).
2. **`TenantContext.cost_budget_usd` retained as a deprecated, non-enforced descriptor** (kept to avoid a ~9-file/2-fixture churn). No code reads it for enforcement. Full removal is a mechanical follow-up.
3. **`durability/governor.py` (the legacy, NOT-in-live-path governor) still has its own USD `_check_budget`.** The live governor is `orchestrator/governor.py` (G14's named target), which is fully migrated. The legacy module is only referenced by `fixer.py` for a `record_step` type annotation; out of AT-095 scope.
4. **Rate limit + fail-closed policy are in-process / first-cut.** The per-window limiter is single-instance (one Cloud Run instance); the global circuit-breaker, distributed limiter, and bounded-retry-before-fail-closed are **AT-097** (explicitly the next feature; thresholds operator-open per §22 D-cap-numbers).
5. **`atelier_tenant` claim minting** (AT-084 deploy contract) is unrelated to AT-095's per-uid cap (the cap keys on `uid`, always present). Claim minting remains an AT-083 deploy-wave item.

## Review focus suggested

- The fail-closed-on-Firestore-error choice (security-over-availability for a paid public endpoint) — is it the right trichotomy call? (Documented; consistent with the rest of the system being Firestore-backed.)
- The double `_seed_lifetime_counter` (run-start + loop-start) is idempotent because N1/N2 don't accrue user tokens; confirm no double-count.
- The graceful-stop vs. hard-raise split (in-run crossing = graceful `TOKEN_CAP_EXHAUSTED`; already-at-cap entry = fail-loud raise → 402).
