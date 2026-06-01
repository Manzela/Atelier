# AT-095 hardening + USD dead-code sweep — gaps.md

## Status: complete, all gates green, adversarial review DONE (both lenses)

Post-merge verification-gate audit (4-lens) + the operator's zero-dead-code
mandate. Every fix-now finding addressed; every removal proven safe.

- mypy --strict: clean (92 src files; was 93 — `durability/governor.py` deleted).
- verify-tests: 934 passed, 7 skipped (full offline lane).
- verify-eval: 8 passed (AT-100). firestore-rules emulator: 19/19.
- ruff check + format: clean.

## Fixed (audit fix-now findings)

1. **[SEC] Honest fail-closed.** A transient Firestore outage / corrupt counter
   now raises `GovernorUsageUnavailable` → **HTTP 503 + Retry-After** + a
   retryable message, never the dishonest 402 "you reached your cap" (PRD §21).
2. **[SEC] Guarded parse.** A non-int counter value fails closed as
   `corrupt_counter` — never a raw 500, never a silent coerce-to-zero.
   `add()` no longer denies an already-committed charge on a post-write read blip.
3. **[CORRECTNESS] Multi-surface cap.** If the cap is crossed on a later surface,
   the top-level payload now surfaces the branded message exactly once.
4. **[OBSERVABILITY] SSE `which_cap` logging** — a Firestore outage is now
   alert-distinguishable from a real per-user cap breach.
5. **[HARDENING] Fail-loud on missing uid** — no silent shared "anonymous" bucket.

## Dead-code sweep (operator mandate: zero orphan/dead code)

- Deleted `atelier/durability/governor.py` (the legacy USD governor — fully
  unreferenced; verified zero live refs across src/tests/scripts/fixtures/docs).
- Removed `TenantContext.cost_budget_usd` / `cost_consumed_usd` (unread, non-enforced).
- Removed `StopReason.BUDGET_EXHAUSTED` (dead USD alias).
- Removed now-unused `Decimal` imports; refreshed `docs/architecture/govern-pillar.md`
  Governor section from the retired USD model to the token-only cap.

## Correctly deferred to AT-097 (auditors unanimous — conservative, no security exposure)

1. **N3d judge-token threading into the lifetime counter.** The counter currently
   counts N3a generation tokens (the dominant, always-present cost) + a
   deterministic offline estimate. Judge (N3d) tokens are captured at the
   `llm_judge` layer (`thinking_tokens`) but not threaded into
   `cumulative_user_tokens` (consensus.py returns no per-judge token totals to
   the runner). Direction of error is SAFE: the cap UNDER-counts real usage (fires
   slightly late) — it never over-counts (never wrongly locks out a paying user)
   and never fails open. When AT-097 lands, route `LLMJudgeResponse.{input,output,
thinking}_tokens` back through `evaluate_candidate` so the runner can
   `add_user_tokens` for N3d.
2. **Distributed rate-limiter + global circuit-breaker + concurrent-overshoot bound.**
   The per-window limiter is in-process (single Cloud Run instance); concurrent
   runs for one uid can overshoot the cap by a bounded ~one generation each.
   Thresholds are operator-open (§22 D-cap-numbers). This is the core of AT-097.

## Cross-component contract (unchanged, AT-083 deploy)

- The cap keys on the Firebase `uid` (always present), independent of the
  `atelier_tenant` claim minting (an AT-083 deploy-wave item).
