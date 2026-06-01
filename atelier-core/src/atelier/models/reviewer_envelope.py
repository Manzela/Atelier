"""Reviewer DONE-evidence envelope model (AT-102, PRD v2.2 §12 E10 / §8A).

The Reviewer emits ``DONE`` only inside a JSON envelope it cannot cheaply
fabricate.  The CI gate (``scripts/ci/verify_reviewer_envelope.py``)
independently re-runs every named command and compares the re-run result
against the envelope's claimed values — any disagreement causes an
automatic REJECTION flagging the Reviewer for calibration.

Verification asymmetry (§8): the producer's self-reported confidence is
stripped from the Reviewer's context before it evaluates, so the Reviewer
cannot simply parrot the producer's numbers.

Design invariants (shared with all Atelier models):
    - ``ConfigDict(frozen=True, extra='forbid')`` — immutable, no drift
    - ``schema_version: int = 1`` — never decreases, fields never dropped
    - Pydantic v2 — ``model_dump_json()`` / ``model_validate_json()`` roundtrip
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReviewerEnvelope(BaseModel):
    """The Reviewer DONE-evidence envelope.

    Fields map 1-to-1 to the independently re-runnable CI checks:

    - ``verdict`` — DONE (merge candidate) or REJECTED (block + log).
    - ``pytest_exit`` — claimed ``pytest`` exit code (0 = all tests pass).
    - ``mypy_exit`` — claimed ``mypy --strict`` exit code (0 = type-clean).
    - ``eval_delta_vs_head1`` — eval delta against HEAD~1 (None when not
      applicable, e.g. no eval tests changed); the gate tolerates None but
      re-runs ``make verify-eval`` when the value is non-None.
    - ``files_touched_sha`` — mapping of changed-file paths to their
      SHA-256 digest at the time the Reviewer evaluated; the gate
      re-computes each digest from the checked-out file and rejects on
      any mismatch (tamper detection).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    verdict: Literal["DONE", "REJECTED"]
    pytest_exit: int = Field(ge=0)
    mypy_exit: int = Field(ge=0)
    eval_delta_vs_head1: float | None = None
    files_touched_sha: dict[str, str] = Field(default_factory=dict)


class EnvelopeVerificationResult(BaseModel):
    """Result returned by the gate's verification logic.

    ``passed`` is True iff the envelope was valid, verdict == DONE, and
    every re-run exit code + SHA-256 matched the claimed values.

    ``mismatch_reasons`` lists each field/path that disagreed.

    ``rejection_streak`` is the count of consecutive REJECTED (or
    auto-REJECTED) entries in ``.reviewer-calibration-log.json`` as of
    the moment the gate ran — surfaced to the caller so it can exit 2 on
    the 3rd.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    passed: bool
    mismatch_reasons: list[str] = Field(default_factory=list)
    rejection_streak: int = Field(default=0, ge=0)
