"""Regression tests for RR-04 (anti-sycophancy lexicon) and RR-31 (idempotent
DPO writes) in the Dreaming Module.

These pin two defects that the prior implementation shipped:

* RR-04: the anti-sycophancy praise detector was a 12-phrase allowlist, so any
  flattery synonym outside that list ("gorgeous", "stunning", "nails it", ...)
  escaped the penalty and the unjustified-praise winner biased the DPO signal.
* RR-31: ``write_pairs_to_bq`` streamed rows with no ``insertId``, so a retried
  or re-emitted request duplicated DPO pairs in BigQuery.
"""

from __future__ import annotations

import pytest
from atelier.optimize.dreaming_module import (
    ANTI_SYCOPHANCY_PENALTY,
    ExtractedPair,
    _dpo_row_id,
    apply_anti_sycophancy_reward,
    write_pairs_to_bq,
)

# ---------------------------------------------------------------------------
# RR-04 — anti-sycophancy lexicon must penalise praise synonyms, not just the
# original 12-phrase allowlist.
# ---------------------------------------------------------------------------

# Synonyms / idioms the old 12-phrase allowlist missed. Each is unjustified
# praise and MUST be down-weighted.
_UNJUSTIFIED_PRAISE = [
    "<h1>This is gorgeous and bold.</h1>",
    "<h1>Absolutely stunning work here.</h1>",
    "<p>This design is beautiful.</p>",
    "<p>Top notch, really.</p>",
    "<p>This nails it.</p>",
    "<p>Chef's kiss on this one.</p>",
    "<p>That layout is breathtaking.</p>",
    "<p>Flawless execution.</p>",
    "<p>Truly impressive composition.</p>",
    "<p>So clean and slick.</p>",
    "<p>This is spot on.</p>",
    "<p>A real masterpiece.</p>",
]


@pytest.mark.parametrize("response", _UNJUSTIFIED_PRAISE)
def test_unjustified_praise_synonyms_are_penalised(response: str) -> None:
    """Each flattery synonym outside the original allowlist is down-weighted."""
    penalised = apply_anti_sycophancy_reward(chosen_response=response, chosen_score=0.90)
    assert penalised == pytest.approx(0.90 * ANTI_SYCOPHANCY_PENALTY)


def test_justified_praise_synonym_is_not_penalised() -> None:
    """Praise WITH justification is untouched even for the broadened lexicon."""
    response = "<p>This is gorgeous because it clears the WCAG AA contrast ratio.</p>"
    assert apply_anti_sycophancy_reward(
        chosen_response=response, chosen_score=0.90
    ) == pytest.approx(0.90)


def test_neutral_factual_response_is_not_penalised() -> None:
    """A response with no praise sentiment at all keeps its full score."""
    response = "<p>The header uses a 16px grid and a 4.6:1 contrast ratio.</p>"
    assert apply_anti_sycophancy_reward(
        chosen_response=response, chosen_score=0.90
    ) == pytest.approx(0.90)


def test_intensifier_plus_adjective_is_penalised() -> None:
    """Bare 'intensifier + positive adjective' flattery is caught."""
    response = "<p>Really clean and very polished.</p>"
    penalised = apply_anti_sycophancy_reward(chosen_response=response, chosen_score=0.80)
    assert penalised == pytest.approx(0.80 * ANTI_SYCOPHANCY_PENALTY)


# ---------------------------------------------------------------------------
# RR-31 — DPO pair writes are idempotent: identical content yields a stable
# insertId so a retry does not duplicate the row.
# ---------------------------------------------------------------------------


def _pair(*, surface_id: str = "surf", chosen: str = "<h1>A</h1>") -> ExtractedPair:
    return ExtractedPair(
        surface_id=surface_id,
        tenant_id="tenant",
        session_id="sess-1",
        prompt="brief",
        chosen_response=chosen,
        rejected_response="<h1>B</h1>",
        chosen_score=0.9,
        rejected_score=0.7,
        margin=0.2,
        node_name="N3a.generator",
        iteration=0,
        extracted_at="2026-06-09T00:00:00+00:00",
    )


def test_row_id_is_stable_across_fresh_surface_ids() -> None:
    """The insertId is content-derived, so the per-emit uuid4 surface_id does
    NOT change it — the dedup key survives the runner's fresh-uuid behaviour."""
    a = _dpo_row_id(_pair(surface_id="11111111-1111-1111-1111-111111111111"))
    b = _dpo_row_id(_pair(surface_id="22222222-2222-2222-2222-222222222222"))
    assert a == b


def test_row_id_differs_when_candidate_content_differs() -> None:
    """Genuinely different pairs get different insertIds (no false dedup)."""
    a = _dpo_row_id(_pair(chosen="<h1>A</h1>"))
    b = _dpo_row_id(_pair(chosen="<h1>DIFFERENT</h1>"))
    assert a != b


def test_write_passes_deterministic_row_ids_to_bq() -> None:
    """``write_pairs_to_bq`` supplies content-derived row_ids to insert_rows_json
    so BigQuery streaming inserts deduplicate retries."""

    class _CapturingClient:
        def __init__(self) -> None:
            self.row_ids: list[str] | None = None

        def insert_rows_json(
            self,
            table: str,
            rows: list[dict[str, object]],
            *,
            row_ids: list[str] | None = None,
        ) -> list[dict[str, object]]:
            self.row_ids = row_ids
            return []

    pair = _pair()
    client = _CapturingClient()
    written = write_pairs_to_bq([pair], bq_client=client)

    assert written == 1
    assert client.row_ids == [_dpo_row_id(pair)]
    # A re-run with the same content produces the SAME insertId → BQ dedups it.
    client2 = _CapturingClient()
    write_pairs_to_bq([_pair()], bq_client=client2)
    assert client2.row_ids == client.row_ids
