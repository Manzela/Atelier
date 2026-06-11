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
    _complete_accessibility,
    _complete_color_token_palette,
    _ensure_renderable_document,
    _extract_html_document,
    _looks_like_html,
)


def _normalize(raw: str) -> str:
    """The exact gate-prep chain the runner applies to each raw candidate."""
    return _complete_accessibility(
        _complete_color_token_palette(_ensure_renderable_document(_extract_html_document(raw)))
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

    def test_strips_narrated_preamble_from_document_less_fragment(self) -> None:
        # Live regression: the Fixer narrates before a fragment (no <html> wrapper)
        # and references tags in backticks. The preamble must NOT survive into the
        # canvas; extraction slices from the first line-start structural tag.
        raw = (
            "Here is the corrected HTML and CSS for the Project Board screen.\n\n"
            "The code now correctly uses `<aside>`, `<main>`, and `<nav>`:\n\n"
            '<div class="board"><aside>nav</aside><main>cols</main></div>'
        )
        out = _extract_html_document(raw)
        assert out.startswith('<div class="board">')
        assert "Here is the corrected" not in out
        assert "`<aside>`" not in out  # the backticked prose mention is gone

    def test_strips_dangling_open_fence_on_truncated_document(self) -> None:
        # Live regression: max_output_tokens truncates mid-fence — an opening
        # ```html with a <!DOCTYPE doc but no closing </html> or ```. The literal
        # ```html must not render above the design in the canvas.
        raw = (
            '```html\n<!DOCTYPE html>\n<html lang="en"><head>'
            "<title>Board</title></head><body><main>cols"
        )
        out = _extract_html_document(raw)
        assert out.startswith("<!DOCTYPE html>")
        assert "```" not in out

    def test_truncated_full_document_without_close_is_kept_from_doctype(self) -> None:
        # A truncated document (no </html>) must still be sliced from the doctype,
        # never returned with whatever preamble preceded it.
        raw = "Here is the code:\n<!DOCTYPE html>\n<html><body><main>partial"
        out = _extract_html_document(raw)
        assert out.startswith("<!DOCTYPE html>")
        assert "Here is the code" not in out


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

    def test_declares_single_quoted_inline_literal_as_token(self) -> None:
        # RC-1c: the N3c token gate scans BOTH quote styles for inline-style color
        # literals, but the palette completer's _INLINE_STYLE_PATTERN matched only
        # double-quoted style="" — so a single-quoted style='' color leaked past
        # un-hoisted and the design failed the zero-tolerance token gate even
        # after normalization (one recurring N3c convergence-trap contributor).
        doc = (
            "<!DOCTYPE html><html lang='en'><head></head>"
            "<body><div style='border:1px solid #13a7c2'>x</div></body></html>"
        )
        out = _complete_color_token_palette(doc)
        assert "--c-auto-0:#13a7c2" in out.replace(" ", "")

    def test_single_quoted_inline_literal_flips_token_gate(self) -> None:
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

        raw = (
            "<!DOCTYPE html><html lang='en'><head><title>t</title></head>"
            "<body><div style='border:1px solid #13a7c2'>x</div></body></html>"
        )
        # The single-quoted inline literal is off-token -> zero-tolerance reject ...
        assert token_gate(_extract_html_document(raw)) == "reject"
        # ... and palette completion now hoists it to a declared token -> pass.
        assert token_gate(_complete_color_token_palette(_extract_html_document(raw))) == "pass"

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


@pytest.mark.unit
class TestCompleteAccessibility:
    """Deterministic remediation of the mechanically-fixable axe violations.

    Regression guard for the convergence-reliability finding: the N3c axe gate is
    zero-tolerance and the generator reliably leaks html-has-lang / document-title
    / aria-progressbar-name. Each has one correct, content-preserving remedy.
    """

    def test_adds_lang_when_missing(self) -> None:
        out = _complete_accessibility("<html><head><title>T</title></head><body>x</body></html>")
        assert 'lang="en"' in out

    def test_preserves_existing_lang(self) -> None:
        out = _complete_accessibility('<html lang="fr"><head><title>T</title></head><body/></html>')
        assert 'lang="fr"' in out
        assert out.count("lang=") == 1

    def test_adds_title_from_h1_when_missing(self) -> None:
        out = _complete_accessibility(
            '<html lang="en"><head></head><body><h1>My Screen</h1></body></html>'
        )
        assert "<title>My Screen</title>" in out

    def test_adds_default_title_when_no_h1(self) -> None:
        out = _complete_accessibility('<html lang="en"><head></head><body><p>x</p></body></html>')
        assert "<title>Generated Design</title>" in out

    def test_creates_head_for_title_when_absent(self) -> None:
        out = _complete_accessibility('<html lang="en"><body><h1>Hi</h1></body></html>')
        assert "<title>Hi</title>" in out
        assert "<head>" in out.lower()

    def test_names_unnamed_progressbar(self) -> None:
        out = _complete_accessibility(
            '<html lang="en"><head><title>T</title></head><body><div role="progressbar"></div></body></html>'
        )
        assert 'aria-label="Progress"' in out

    def test_preserves_named_progressbar(self) -> None:
        html = '<html lang="en"><head><title>T</title></head><body><div role="progressbar" aria-label="Step 1 of 3"></div></body></html>'
        assert _complete_accessibility(html) == html

    def test_adds_alt_to_img_including_self_closing(self) -> None:
        out = _complete_accessibility(
            '<html lang="en"><head><title>T</title></head><body><img src="a.png"><img src="b.png"/></body></html>'
        )
        # Both imgs get alt, and the self-closing one stays well-formed.
        assert out.count("alt=") == 2
        assert "/ alt" not in out
        assert 'alt=""/>' in out.replace(" ", "")

    def test_is_idempotent(self) -> None:
        once = _complete_accessibility(
            '<html><head></head><body><h1>X</h1><img src="a"><div role="progressbar"></div></body></html>'
        )
        assert _complete_accessibility(once) == once

    def test_fully_compliant_doc_unchanged(self) -> None:
        doc = '<html lang="en"><head><title>Ok</title></head><body><main>ok</main></body></html>'
        assert _complete_accessibility(doc) == doc


@pytest.mark.unit
class TestLooksLikeHtml:
    """The non-convergence fallback must never serve markdown prose as a design.

    Regression: on the live Linear-app E2E the Wireframer's markdown out-scored
    the failing-but-real HTML on mean gate score and was rendered as washed-out
    text in the Studio canvas. _looks_like_html gates the fallback selection.
    """

    def test_rejects_wireframer_markdown_prose(self) -> None:
        # Verbatim shape of the live regression: prose that *names* structural
        # tags (`<main>`, `<nav>`) in backticks but never writes a closing tag.
        markdown = (
            "Here is the low-fidelity structural wireframe for the **Project Board** "
            "screen.\n\n### 1. Overall Screen Layout (`App Shell`)\n\n"
            "*   **`<aside>` (Sidebar Navigation):** A fixed-width vertical region.\n"
            "*   **`<main>` (Main Content Area):** The primary content region.\n"
            "*   **`<nav>`:** A vertically stacked list of navigation items."
        )
        # Contains `<main>`/`<nav>` substrings yet no closing tag -> not a design.
        assert _looks_like_html(markdown) is False

    def test_accepts_full_document(self) -> None:
        assert _looks_like_html("<!DOCTYPE html><html><body><main>x</main></body></html>")

    def test_accepts_structural_fragment(self) -> None:
        assert _looks_like_html('<div class="board"><section>col</section></div>')

    def test_accepts_nav_and_form_containers(self) -> None:
        assert _looks_like_html("<nav>links</nav>")
        assert _looks_like_html('<form action="/x"></form>')

    def test_rejects_plain_text(self) -> None:
        assert _looks_like_html("just a sentence with no markup at all.") is False

    def test_case_insensitive(self) -> None:
        assert _looks_like_html("<MAIN>X</MAIN>")


@pytest.mark.unit
class TestEnsureRenderableDocument:
    """A scaffold-less but renderable fragment (e.g. a Fixer's 'corrected
    section', or a UI Designer disrupted mid-run by a Stitch MCP failure) must be
    wrapped into a minimal HTML document BEFORE the completion passes run.

    Live regression (2026-06-10 E2E): a fixer-style fragment passed
    ``_looks_like_html`` (so it was eligible as ``best_partial_html``) but the
    completion passes could not anchor ``lang``/``<title>`` onto an ``<html>``/
    ``<head>`` that did not exist, so axe rejected it (html-has-lang,
    document-title) and the run reported INCOMPLETE at composite 0.600 despite
    the design content being sound.
    """

    def test_full_document_is_unchanged(self) -> None:
        assert _ensure_renderable_document(_DOC) == _DOC

    def test_document_with_html_tag_is_unchanged(self) -> None:
        doc = "<html><body><main>x</main></body></html>"
        assert _ensure_renderable_document(doc) == doc

    def test_prose_is_not_wrapped(self) -> None:
        # Markdown narration must stay unwrapped so _looks_like_html still
        # rejects it as a non-design (never serve prose as a wrapped "document").
        prose = "Here is the layout. The `<main>` region holds the content."
        out = _ensure_renderable_document(prose)
        assert "<html" not in out.lower()

    def test_renderable_fragment_is_wrapped_into_a_document(self) -> None:
        frag = '<section class="hero"><h1>Aurora</h1><p>Analytics</p></section>'
        out = _ensure_renderable_document(frag)
        low = out.lower()
        assert "<html" in low
        assert "lang=" in low
        assert frag in out  # fragment content preserved verbatim in the body

    def test_wrap_flips_the_scaffold_caused_gate_failures(self) -> None:
        # The decisive assertion, scoped to exactly what the missing scaffold
        # broke: the live run's Acceptance Verdict failed on axe (html-has-lang,
        # document-title) and token-fidelity (:root). After the wrap step both
        # flip to PASS for a renderable fixer-style fragment. (semantic-html /
        # visual-diff are out of scope: a bare section legitimately lacks the
        # page landmarks — that is correct gate behavior, not this bug.)
        # Contrast-safe palette (white on deep indigo ≈ 12:1, white on dark red
        # ≈ 7:1, both clear WCAG AA) so the ONLY thing under test is the
        # scaffold flip — not a genuine contrast violation.
        fragment = (
            "Here is the corrected hero section with improved contrast:\n\n"
            '<section class="hero" style="background:#2A2F4F;color:#ffffff;padding:64px">\n'
            "  <h1>Aurora — B2B Analytics for Retail</h1>\n"
            "  <p>Real-time dashboards, anomaly alerts, forecast accuracy.</p>\n"
            '  <a href="#demo" style="background:#A01010;color:#ffffff">Request a demo</a>\n'
            "</section>"
        )
        html = _normalize(fragment)
        low = html.lower()
        assert "<html" in low
        assert "lang=" in low
        assert "<title" in low
        assert ":root" in low
        candidate = CandidateUI(
            candidate_id=__import__("uuid").uuid4(),
            surface_id=__import__("uuid").uuid4(),
            iteration=0,
            artifacts={"index.html": html},
        )
        outcomes = {o.axis.value: o for o in run_gates(candidate, _N3C_GATE_AXES).outcomes}
        assert outcomes["axe"].decision.name == "PASS", outcomes["axe"].diagnostic
        assert outcomes["token-fidelity"].decision.name == "PASS", outcomes[
            "token-fidelity"
        ].diagnostic

    def test_unwrapped_fragment_fails_the_same_gates(self) -> None:
        # Red-state guard: WITHOUT the wrap step, the identical fragment fails the
        # exact two gates the wrap fixes — proving the wrap is load-bearing.
        fragment = (
            '<section class="hero" style="background:#2A2F4F;color:#ffffff">'
            "<h1>Aurora</h1><p>x</p></section>"
        )
        unwrapped = _complete_accessibility(
            _complete_color_token_palette(_extract_html_document(fragment))
        )
        candidate = CandidateUI(
            candidate_id=__import__("uuid").uuid4(),
            surface_id=__import__("uuid").uuid4(),
            iteration=0,
            artifacts={"index.html": unwrapped},
        )
        outcomes = {o.axis.value: o for o in run_gates(candidate, _N3C_GATE_AXES).outcomes}
        assert outcomes["axe"].decision.name != "PASS"

    def test_full_document_still_converges_through_the_chain(self) -> None:
        # Guard: wrapping must not regress the full-document path.
        full = (
            '```html\n<!DOCTYPE html>\n<html lang="en">\n<head><meta charset="utf-8">'
            "<title>Aurora</title>\n<style>:root{--c-primary:#2A2F4F;--c-bg:#F8F7F4}"
            "body{background:var(--c-bg);color:var(--c-primary)}</style></head>\n"
            '<body><header><h1>Aurora</h1></header><nav><a href="#m">Skip</a></nav>'
            '<main id="m"><section><article><h2>Hi</h2><p>x</p></article></section></main>'
            "<footer><small>f</small></footer></body>\n</html>\n```"
        )
        candidate = CandidateUI(
            candidate_id=__import__("uuid").uuid4(),
            surface_id=__import__("uuid").uuid4(),
            iteration=0,
            artifacts={"index.html": _normalize(full)},
        )
        assert run_gates(candidate, _N3C_GATE_AXES).all_passed
