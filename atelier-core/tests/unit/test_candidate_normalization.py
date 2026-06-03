"""Tests for N3a candidate normalization before the N3c gates.

The generator wraps its HTML in conversational preamble + a ```html fence and
leaks a few raw color literals; both make every candidate fail the deterministic
N3c gates, so the run never converges. ``_extract_html_document`` and
``_complete_color_token_palette`` normalize each candidate at the single
gate-prep choke point. These tests lock that behavior (the live regression was
candidates_passed_gates=0 on staging).
"""

import pytest
from atelier.gates.runner import run_gates
from atelier.models.data_contracts import CandidateUI
from atelier.orchestrator.runner import (
    _N3C_GATE_AXES,
    _complete_color_token_palette,
    _extract_html_document,
)

_DOC = (
    '<!DOCTYPE html>\n<html lang="en"><head><style>'
    ":root{--color-primary:#1a73e8}body{color:var(--color-primary);"
    "border:1px solid #E5E7EB}</style></head><body><main>Hi</main></body></html>"
)


@pytest.mark.unit
class TestExtractHtmlDocument:
    def test_strips_prose_and_markdown_fence(self) -> None:
        raw = (
            "Excellent. The team has provided all artifacts. Here is the final code:\n"
            "```html\n" + _DOC + "\n```"
        )
        out = _extract_html_document(raw)
        assert out.lstrip().lower().startswith("<!doctype")
        assert out.rstrip().lower().endswith("</html>")
        assert "Excellent" not in out
        assert "```" not in out

    def test_already_clean_html_is_unchanged(self) -> None:
        assert _extract_html_document(_DOC) == _DOC

    def test_html_without_doctype_is_extracted_from_html_tag(self) -> None:
        raw = "preamble\n```\n<html><body>x</body></html>\n```"
        assert _extract_html_document(raw) == "<html><body>x</body></html>"

    def test_fragment_without_document_returns_stripped_text(self) -> None:
        # No <html> document: return the de-fenced text rather than dropping it.
        assert (
            _extract_html_document("  <div>just a fragment</div>  ") == "<div>just a fragment</div>"
        )


@pytest.mark.unit
class TestCompleteColorTokenPalette:
    def test_declares_stray_literal_as_token(self) -> None:
        # #E5E7EB is used but not declared as a token; it must become one.
        out = _complete_color_token_palette(_DOC)
        assert "--c-auto-0:#E5E7EB" in out.replace(" ", "")
        # The existing token is preserved.
        assert "--color-primary:#1a73e8" in out.replace(" ", "")

    def test_no_change_when_every_literal_already_declared(self) -> None:
        doc = (
            "<!DOCTYPE html><html><head><style>"
            ":root{--a:#ffffff}body{color:var(--a)}</style></head><body>x</body></html>"
        )
        assert _complete_color_token_palette(doc) == doc

    def test_is_idempotent(self) -> None:
        once = _complete_color_token_palette(_DOC)
        assert _complete_color_token_palette(once) == once

    def test_injects_style_block_when_only_inline_colors(self) -> None:
        doc = '<!DOCTYPE html><html><head></head><body style="color:#abcdef">x</body></html>'
        out = _complete_color_token_palette(doc)
        assert "<style>" in out
        assert "#abcdef" in out.replace(" ", "")

    def test_normalization_flips_token_gate_reject_to_pass(self) -> None:
        """The precise contract: the leaked literal rejects, normalization fixes it.

        (Overall convergence also needs the other axes, which depend on document
        richness, not on this pass — exercised by the live E2E. Here we isolate
        the token-fidelity gate this normalizer is responsible for.)
        """
        from uuid import uuid4

        def token_gate(html: str) -> str:
            candidate = CandidateUI(
                candidate_id=uuid4(),
                surface_id=uuid4(),
                iteration=0,
                artifacts={"index.html": html},
            )
            outcome = next(
                o
                for o in run_gates(candidate, _N3C_GATE_AXES).outcomes
                if o.axis.value == "token-fidelity"
            )
            return str(outcome.decision.value)

        # Raw doc leaks #E5E7EB -> zero-tolerance reject.
        assert token_gate(_extract_html_document(_DOC)) == "reject"
        # After palette completion the literal is a declared token -> pass.
        assert token_gate(_complete_color_token_palette(_extract_html_document(_DOC))) == "pass"
