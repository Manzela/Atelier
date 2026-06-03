# 0025. Generation latency — concurrent judging now, specialist model-routing deferred

**Status:** Accepted (2026-06-03)
**Date:** 2026-06-03
**Decision-makers:** Daniel Manzela
**Relates to:** complements ADR-0001 (wrap-don't-fork); references AT-024 (served-model pin), AT-097 (concurrent N3d judging).

## Context and problem statement

A full `/v1/generate` run takes roughly 20-30 minutes end-to-end (measured: 1373 s
local, 1824 s on staging). The question is whether that wall-clock is a defect to
optimize before submission or an inherent property of the pipeline depth, and which
levers are safe to pull.

The runtime decomposes as:

- **N3a — DDLC specialist pipeline.** A six-role `SequentialAgent`
  (UXResearcher -> IAFlowDesigner -> Wireframer -> UIDesigner -> InteractionDesigner ->
  TokenGenerator). Every specialist resolves the same served model
  (`resolve_model_id()` -> `gemini-2.5-pro`, AT-024) and runs strictly after the
  previous one, because each consumes the prior's output through session-state keys
  (`SPECIALIST_OUTPUT_KEYS`). The order is a data dependency, not an incidental
  sequence.
- **N3c -> N3d -> N4.** Deterministic gates (cheap), then D-O-R-A-V consensus over
  every gate-passing candidate across five axes, then best-pick.
- **N3e fixer loop.** Up to `max_iterations` rounds; each non-converging round
  re-runs the full N3a pipeline with a fixer-amended prompt. Convergence short-circuits
  the loop (the local run converged at iteration 3).

## Decision drivers

- The win condition is **output quality**, not wall-clock (memory: prioritize win over
  deadline/budget). A latency change that risks convergence quality is a net loss.
- The served model is **operator-pinned** (`gemini-2.5-pro`, GA, AT-024). Changing the
  model surface is not a silent code edit.
- The product is an **asynchronous, progress-streaming** design agent: the Studio renders
  per-iteration D-O-R-A-V scores and candidate events throughout the run, so the latency
  is observed as visible progress, not a frozen spinner.
- `<eval_delta_required>` — any change to the generation path must show no eval regression,
  and each live validation run is itself 20-30 minutes.

## Decision

**Ship the one safe, high-impact optimization; defer the quality-risking one with a clear,
evidenced trigger.**

1. **Concurrent N3d judging (done, AT-097).** The dominant parallelizable cost — judging
   each gate-passing candidate across five axes — runs on a `ThreadPoolExecutor`
   (`orchestrator/runner.py`), cutting N3d wall-clock from the sum of per-candidate
   judging to roughly the slowest single candidate. Order is preserved via
   `zip(..., strict=True)` so selection and token accounting are identical to serial.

2. **Specialist model-routing (deferred).** The remaining lever is routing the five
   _intermediate_ specialists (everything except the UIDesigner, which is the only role
   that emits the gated HTML) to a faster model such as `gemini-2.5-flash`, keeping Pro
   for the UIDesigner. This is **not** landed pre-submission because:
   - it changes the model surface, which is operator-pinned (AT-024);
   - the intermediate artifacts feed the UIDesigner, so a weaker model can degrade the
     final design — this needs a live eval-delta to confirm no convergence regression,
     and the win condition is quality;
   - the runtime is acceptable for an async, progress-streaming agent.

   **Trigger to revisit:** an operator-approved model-pin change plus a green eval-delta
   on the calibration golden set, after submission.

3. **The sequential specialist order and the fixer loop are not parallelized.** Both are
   genuine data dependencies (each specialist consumes the prior's session-state output;
   each fixer round consumes the prior round's gate failures). Parallelizing either would
   break the DDLC contract.

## Consequences

- No code change in this ADR; it records the analysis so the latency item is closed in the
  decision log rather than re-derived each session.
- The model-routing optimization is captured with a concrete trigger, so it is actionable
  post-submission without re-investigation.
