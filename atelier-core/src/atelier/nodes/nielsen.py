"""Nielsen-10 usability-heuristic presence oracle — AT-022 (PRD v2.2 §12 E2 / R6).

The Nielsen critic votes **PRESENCE only**: for each of Nielsen Norman Group's ten
usability heuristics, the oracle decides whether a *violation is present* in a
candidate UI — it never assigns or acts on **severity**. Severity is a human gate
(``<no_llm_severity_authority>`` / R6); the deterministic gates (AT-010/012/013) and
the D-O-R-A-V judges (AT-021) are what gate convergence. This oracle is **advisory**:
its findings feed the §3.9 "D-O-R-A-V + Nielsen" scorecard and the Fixer's narrative,
and never block convergence by themselves.

Design — a **≥2/3 deterministic vote** (mirrors the AT-021 deterministic-oracle /
narrative-critic split):

* Each heuristic has **three independent deterministic detectors ("voters")**, each
  looking for a *different* concrete signal of that heuristic's violation in the
  rendered HTML/CSS.
* A heuristic violation is **PRESENT iff ≥2 of its 3 voters fire**
  (:data:`PRESENCE_VOTE_THRESHOLD` of :data:`VOTERS_PER_HEURISTIC`). The ≥2/3 rule
  is load-bearing: a single incidental signal (1/3) cannot trip a heuristic, so the
  finding must be corroborated — the same robustness an LLM-judge ensemble buys with
  three judges, achieved deterministically so the result is testable and reproducible.

Because the vote is deterministic, the AT-022 discrimination arm is a real oracle: a
fixture that violates a heuristic fires the ≥2/3 vote for *that* heuristic, and a
clean, well-built page fires none — and a naive all-ABSENT (or all-PRESENT) stub fails
the discrimination tests. The detectors are general-purpose usability predicates
(missing live regions, placeholder-only inputs, non-standard controls, missing input
constraints, …), not fixture-keyed string matches.

The LLM ``NielsenHeuristicCritic`` in :mod:`atelier.nodes.critique_panel` is the
*narrative* layer (qualitative critique text for the Fixer); this module is the
*structured presence authority* behind it.

PRD Reference: §12 AT-022, R6 (``<no_llm_severity_authority>``), §3.2 (QA panel).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from uuid import UUID

    from atelier.models.data_contracts import CandidateUI

#: Voters evaluated per heuristic, and the votes required to call a violation PRESENT.
VOTERS_PER_HEURISTIC: Final[int] = 3
PRESENCE_VOTE_THRESHOLD: Final[int] = 2  # ≥2 of 3

# Detector thresholds (named so the ≥2/3 vote is not a wall of magic numbers).
_MIN_FORM_INPUTS: Final[int] = 2  # ≥2 fields ⇒ a multi-field form (accelerators expected)
_COMPLEX_FORM_INPUTS: Final[int] = 3  # ≥3 fields ⇒ a complex task (assistance/help expected)
_MAX_DISTINCT_COLORS: Final[int] = 12  # H8: palette beyond this reads as cluttered
_MAX_DISTINCT_FONT_SIZES: Final[int] = 8  # H8: type-scale beyond this reads as cluttered
_MAX_CTAS: Final[int] = 12  # H8: simultaneous calls-to-action beyond this overwhelm


class NielsenHeuristic(StrEnum):
    """Nielsen Norman Group's ten general usability heuristics (1994, rev. 2020)."""

    VISIBILITY_OF_SYSTEM_STATUS = "visibility_of_system_status"
    MATCH_SYSTEM_AND_REAL_WORLD = "match_system_and_real_world"
    USER_CONTROL_AND_FREEDOM = "user_control_and_freedom"
    CONSISTENCY_AND_STANDARDS = "consistency_and_standards"
    ERROR_PREVENTION = "error_prevention"
    RECOGNITION_RATHER_THAN_RECALL = "recognition_rather_than_recall"
    FLEXIBILITY_AND_EFFICIENCY = "flexibility_and_efficiency_of_use"
    AESTHETIC_AND_MINIMALIST = "aesthetic_and_minimalist_design"
    HELP_RECOGNIZE_DIAGNOSE_RECOVER = "help_recognize_diagnose_recover_errors"
    HELP_AND_DOCUMENTATION = "help_and_documentation"


@dataclass(frozen=True)
class HeuristicVerdict:
    """Per-heuristic presence verdict — PRESENCE only, never severity (R6).

    Attributes:
        heuristic: Which Nielsen heuristic this verdict concerns.
        present: ``True`` iff ≥2/3 voters fired (a violation is present).
        votes: How many of the three voters fired (0-3).
        voters_fired: Names of the deterministic detectors that fired — the
            one-line "locator" of why the heuristic was flagged. There is
            deliberately **no severity field**: severity is a human decision.
    """

    heuristic: NielsenHeuristic
    present: bool
    votes: int
    voters_fired: tuple[str, ...]


@dataclass(frozen=True)
class NielsenReport:
    """The full Nielsen-10 presence report for one candidate (advisory).

    Attributes:
        candidate_id: UUID of the evaluated candidate.
        verdicts: One :class:`HeuristicVerdict` per heuristic, in canonical
            :class:`NielsenHeuristic` order.
    """

    candidate_id: UUID
    verdicts: tuple[HeuristicVerdict, ...]

    @property
    def violations(self) -> tuple[NielsenHeuristic, ...]:
        """Heuristics whose violation is PRESENT (≥2/3 vote), in canonical order."""
        return tuple(v.heuristic for v in self.verdicts if v.present)

    @property
    def any_violation(self) -> bool:
        """Whether any heuristic's violation is present."""
        return any(v.present for v in self.verdicts)

    def by_heuristic(self, heuristic: NielsenHeuristic) -> HeuristicVerdict:
        """Return the verdict for ``heuristic`` (raises ``KeyError`` if absent)."""
        for verdict in self.verdicts:
            if verdict.heuristic == heuristic:
                return verdict
        raise KeyError(heuristic)


# ---------------------------------------------------------------------------
# Artifact extraction — lowercased views the detectors read (stdlib re only,
# matching the deterministic-gate convention; no HTML-parser dependency).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Doc:
    """Pre-extracted, lowercased views of a candidate's artifacts."""

    html: str  # all *.html artifacts joined, lowercased (tags + attributes)
    css: str  # *.css artifacts + <style> blocks + inline style= values, lowercased
    text: str  # user-visible text (script/style stripped, tags removed), lowercased


_STYLE_BLOCK_RE: Final = re.compile(r"<style\b[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)
_INLINE_STYLE_RE: Final = re.compile(r"""style\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.IGNORECASE)
_NON_RENDERED_RE: Final = re.compile(
    r"<(script|style|template)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)
_TAG_RE: Final = re.compile(r"<[^>]+>")
_WS_RE: Final = re.compile(r"\s+")


def _extract(candidate: CandidateUI) -> _Doc:
    html_parts = [
        content
        for name, content in candidate.artifacts.items()
        if name.lower().endswith((".html", ".htm"))
    ]
    if not html_parts:  # fall back to any artifact that looks like markup
        html_parts = [content for content in candidate.artifacts.values() if "<" in content]
    html_raw = "\n".join(html_parts)

    css_parts = [
        content for name, content in candidate.artifacts.items() if name.lower().endswith(".css")
    ]
    css_parts += [match.group(1) for match in _STYLE_BLOCK_RE.finditer(html_raw)]
    css_parts += [
        (match.group(1) or match.group(2)) for match in _INLINE_STYLE_RE.finditer(html_raw)
    ]

    rendered = _NON_RENDERED_RE.sub(" ", html_raw)
    text = _WS_RE.sub(" ", _TAG_RE.sub(" ", rendered)).strip()

    return _Doc(html=html_raw.lower(), css="\n".join(css_parts).lower(), text=text.lower())


# ---------------------------------------------------------------------------
# Shared predicates
# ---------------------------------------------------------------------------

_INPUT_RE: Final = re.compile(r"<input\b[^>]*>", re.IGNORECASE)
_BUTTON_RE: Final = re.compile(r"<button\b([^>]*)>(.*?)</button>", re.IGNORECASE | re.DOTALL)
_ROLE_DIALOG_RE: Final = re.compile(r"role\s*=\s*['\"]?dialog")
_ROLE_STATUS_RE: Final = re.compile(r"role\s*=\s*['\"]?(alert|status)")
_ROLE_BUTTON_RE: Final = re.compile(r"role\s*=\s*['\"]?button")
_NAV_RE: Final = re.compile(r"<nav\b|role\s*=\s*['\"]?navigation")
_COLOR_RE: Final = re.compile(r"#[0-9a-f]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)", re.IGNORECASE)
_FONT_SIZE_RE: Final = re.compile(r"font-size\s*:\s*([^;}]+)")
_GUIDANCE_RE: Final = re.compile(
    r"\b(try again|please|check|make sure|enter a|enter your|must be|required|"
    r"is invalid|valid|contact|unable to|highlighted|correct)\b"
)
_BARE_CODE_RE: Final = re.compile(
    r"\b(error|err|code|status|exception)\s*:?\s*\d{2,4}\b|\b\d{3}\s+(error|status)\b"
)
_HELP_WORD_RE: Final = re.compile(r"\b(help|faq|support|documentation|tutorial|knowledge base)\b")
_DESTRUCTIVE_RE: Final = re.compile(
    r"\b(delete|remove|deactivate|erase|wipe|destroy|permanently)\b"
)
_CONSTANT_TOKEN_RE: Final = re.compile(r"\b[a-z]{2,}_[a-z0-9_]{2,}\b")
_FIELD_HINTS: Final = ("email", "e-mail", "phone", "url", "zip", "postal", "credit card")


def _has_action_controls(html: str) -> bool:
    return ("<button" in html) or ("<form" in html) or ("<input" in html)


def _has_help_affordance(doc: _Doc) -> bool:
    return bool(_HELP_WORD_RE.search(doc.text)) or "/docs" in doc.html or "learn more" in doc.text


def _has_input_hints(html: str) -> bool:
    return (
        "aria-describedby" in html
        or "title=" in html
        or "<small" in html
        or "<details" in html
        or "tooltip" in html
    )


def _has_error_region(html: str) -> bool:
    return (
        bool(_ROLE_STATUS_RE.search(html))
        or "aria-invalid" in html
        or re.search(r"class\s*=\s*['\"][^'\"]*error", html) is not None
    )


def _fired(*pairs: tuple[str, bool]) -> tuple[str, ...]:
    """Collect the names of the voters whose boolean signal fired."""
    return tuple(name for name, signal in pairs if signal)


# ---------------------------------------------------------------------------
# Per-heuristic detectors — each returns the names of the voters that fired.
# ---------------------------------------------------------------------------


def _h1_visibility(doc: _Doc) -> tuple[str, ...]:
    """H1 Visibility of system status: actions exist but give no feedback."""
    if not _has_action_controls(doc.html):
        return ()
    has_live = bool(_ROLE_STATUS_RE.search(doc.html)) or "aria-live" in doc.html
    has_loading = any(
        token in doc.html
        for token in ("aria-busy", "<progress", "progressbar", "spinner", "loading", "skeleton")
    ) or any(token in doc.html for token in ("toast", "snackbar"))
    has_feedback_copy = any(
        token in doc.text
        for token in ("saved", "saving", "please wait", "loading", "updating", "success", "done")
    )
    return _fired(
        ("no_live_region", not has_live),
        ("no_loading_affordance", not has_loading),
        ("no_feedback_copy", not has_feedback_copy),
    )


def _h2_real_world(doc: _Doc) -> tuple[str, ...]:
    """H2 Match the real world: developer jargon / machine tokens in visible copy."""
    placeholder = any(
        token in doc.text
        for token in (
            "lorem ipsum",
            "todo",
            "fixme",
            "placeholder",
            "your text here",
            "sample text",
            "dummy text",
        )
    )
    machine_token = (
        any(
            re.search(rf"\b{re.escape(token)}\b", doc.text)
            for token in ("undefined", "null", "nan")
        )
        or "[object object]" in doc.text
    )
    system_code = (
        bool(re.search(r"\b(err[_ ]?code|exception|stack ?trace|traceback)\b", doc.text))
        or bool(_BARE_CODE_RE.search(doc.text))
        or bool(_CONSTANT_TOKEN_RE.search(doc.text))
    )
    return _fired(
        ("developer_placeholder", placeholder),
        ("raw_machine_token", machine_token),
        ("system_error_code", system_code),
    )


def _h3_user_control(doc: _Doc) -> tuple[str, ...]:
    """H3 User control and freedom: no exit from modal / form / flow."""
    html = doc.html
    has_modal = bool(_ROLE_DIALOG_RE.search(html)) or "<dialog" in html or "aria-modal" in html
    has_form = "<form" in html
    if not (has_modal or has_form):
        return ()
    # The multiplication-sign and heavy-multiplication-x close glyphs are deliberate
    # literals: real close buttons render them, and we match them in the candidate's
    # HTML, so the ambiguous-homoglyph lint does not apply to this string.
    dismiss_tokens = ("close", "cancel", "dismiss", "&times;", "✕", "×", "no thanks")  # noqa: RUF001
    escape_tokens = (
        "cancel",
        "back",
        "undo",
        "&times;",
        "breadcrumb",
        ">home<",
        "close",
        "skip to",
    )
    has_dismiss = any(token in html for token in dismiss_tokens)
    has_cancel = any(token in html for token in ("cancel", "reset", "go back"))
    has_escape = any(token in html for token in escape_tokens)
    return _fired(
        ("modal_without_dismiss", has_modal and not has_dismiss),
        ("form_without_cancel", has_form and not has_cancel),
        ("no_escape_hatch", not has_escape),
    )


def _h4_consistency(doc: _Doc) -> tuple[str, ...]:
    """H4 Consistency and standards: non-standard / mixed interaction paradigms."""
    html = doc.html
    div_onclick = re.search(r"<(div|span)\b[^>]*\bonclick", html) is not None
    anchor_as_button = (
        re.search(r"<a\b[^>]*href\s*=\s*['\"]#['\"][^>]*onclick", html) is not None
        or re.search(r"<a\b[^>]*onclick[^>]*href\s*=\s*['\"]#['\"]", html) is not None
        or re.search(r"<a\b(?:(?!href)[^>])*onclick(?:(?!href)[^>])*>", html) is not None
    )
    mixed_paradigm = ("<button" in html) and (
        div_onclick or "href='#'" in html or 'href="#"' in html
    )
    return _fired(
        ("div_span_onclick", div_onclick),
        ("anchor_as_button", anchor_as_button),
        ("mixed_action_paradigm", mixed_paradigm),
    )


def _h5_error_prevention(doc: _Doc) -> tuple[str, ...]:
    """H5 Error prevention: data entry without constraints / destructive w/o confirm."""
    html = doc.html
    inputs = _INPUT_RE.findall(html)
    no_required = bool(inputs) and "required" not in html
    typed_missing = False
    for tag in inputs:
        if any(hint in tag for hint in _FIELD_HINTS):
            is_generic = (not re.search(r"type\s*=", tag)) or re.search(
                r"type\s*=\s*['\"]?text", tag
            ) is not None
            if is_generic and "pattern=" not in tag and "inputmode=" not in tag:
                typed_missing = True
                break
    destructive = bool(_DESTRUCTIVE_RE.search(doc.text))
    has_confirm = any(
        token in html
        for token in ("confirm", "are you sure", "<dialog", "data-confirm", "cannot be undone")
    ) or bool(_ROLE_DIALOG_RE.search(html))
    return _fired(
        ("inputs_without_required", no_required),
        ("typed_field_missing_type", typed_missing),
        ("destructive_without_confirm", destructive and not has_confirm),
    )


def _h6_recognition(doc: _Doc) -> tuple[str, ...]:
    """H6 Recognition over recall: hidden labels / unnamed icons / no nav state."""
    html = doc.html
    inputs = _INPUT_RE.findall(html)
    placeholder_only = (
        bool(inputs)
        and "placeholder=" in html
        and "<label" not in html
        and "aria-label" not in html
        and "aria-labelledby" not in html
    )
    icon_only = False
    for attrs, inner in _BUTTON_RE.findall(html):
        inner_text = _WS_RE.sub(" ", _TAG_RE.sub(" ", inner)).strip()
        if not inner_text and "aria-label" not in attrs and "title=" not in attrs:
            icon_only = True
            break
    has_nav = bool(_NAV_RE.search(html))
    nav_no_state = (
        has_nav
        and not any(token in html for token in ("aria-current", "aria-selected", "breadcrumb"))
        and re.search(r"class\s*=\s*['\"][^'\"]*(active|current|selected)", html) is None
    )
    return _fired(
        ("placeholder_only_inputs", placeholder_only),
        ("icon_only_button_no_name", icon_only),
        ("nav_without_current_state", nav_no_state),
    )


def _h7_flexibility(doc: _Doc) -> tuple[str, ...]:
    """H7 Flexibility and efficiency: no accelerators for repeated data entry."""
    html = doc.html
    n_inputs = len(_INPUT_RE.findall(html))
    no_autocomplete = n_inputs >= _MIN_FORM_INPUTS and "autocomplete=" not in html
    no_defaults = (
        n_inputs >= _MIN_FORM_INPUTS
        and "value=" not in html
        and "checked" not in html
        and "selected" not in html
    )
    no_assistance = (
        n_inputs >= _COMPLEX_FORM_INPUTS
        and "autocomplete=" not in html
        and "<datalist" not in html
        and "list=" not in html
        and "accesskey" not in html
    )
    return _fired(
        ("inputs_without_autocomplete", no_autocomplete),
        ("no_field_defaults", no_defaults),
        ("no_input_assistance", no_assistance),
    )


def _h8_minimalist(doc: _Doc) -> tuple[str, ...]:
    """H8 Aesthetic and minimalist design: palette / type-scale / CTA overload."""
    colors = {_WS_RE.sub("", c).lower() for c in _COLOR_RE.findall(doc.css)}
    font_sizes = {_WS_RE.sub("", m).lower() for m in _FONT_SIZE_RE.findall(doc.css)}
    n_ctas = doc.html.count("<button") + len(_ROLE_BUTTON_RE.findall(doc.html))
    return _fired(
        ("excessive_color_palette", len(colors) > _MAX_DISTINCT_COLORS),
        ("excessive_font_sizes", len(font_sizes) > _MAX_DISTINCT_FONT_SIZES),
        ("cta_overload", n_ctas > _MAX_CTAS),
    )


def _h9_error_recovery(doc: _Doc) -> tuple[str, ...]:
    """H9 Help users recover from errors: errors without actionable guidance."""
    html = doc.html
    region_no_guidance = _has_error_region(html) and not _GUIDANCE_RE.search(doc.text)
    bare_code = bool(_BARE_CODE_RE.search(doc.text))
    form_no_error_ui = "<form" in html and not (
        _has_error_region(html) or "aria-describedby" in html
    )
    return _fired(
        ("error_region_without_guidance", region_no_guidance),
        ("bare_error_code", bare_code),
        ("form_without_error_messaging", form_no_error_ui),
    )


def _h10_help(doc: _Doc) -> tuple[str, ...]:
    """H10 Help and documentation: no help affordances for a non-trivial task."""
    html = doc.html
    inputs = _INPUT_RE.findall(html)
    help_present = _has_help_affordance(doc)
    hints_present = _has_input_hints(html)
    no_help_link = not help_present
    inputs_without_hints = bool(inputs) and not hints_present
    complex_task_no_help = (
        "<form" in html
        and len(inputs) >= _COMPLEX_FORM_INPUTS
        and not help_present
        and not hints_present
    )
    return _fired(
        ("no_help_link", no_help_link),
        ("inputs_without_hints", inputs_without_hints),
        ("complex_task_no_help", complex_task_no_help),
    )


_DETECTORS: Final[dict[NielsenHeuristic, Callable[[_Doc], tuple[str, ...]]]] = {
    NielsenHeuristic.VISIBILITY_OF_SYSTEM_STATUS: _h1_visibility,
    NielsenHeuristic.MATCH_SYSTEM_AND_REAL_WORLD: _h2_real_world,
    NielsenHeuristic.USER_CONTROL_AND_FREEDOM: _h3_user_control,
    NielsenHeuristic.CONSISTENCY_AND_STANDARDS: _h4_consistency,
    NielsenHeuristic.ERROR_PREVENTION: _h5_error_prevention,
    NielsenHeuristic.RECOGNITION_RATHER_THAN_RECALL: _h6_recognition,
    NielsenHeuristic.FLEXIBILITY_AND_EFFICIENCY: _h7_flexibility,
    NielsenHeuristic.AESTHETIC_AND_MINIMALIST: _h8_minimalist,
    NielsenHeuristic.HELP_RECOGNIZE_DIAGNOSE_RECOVER: _h9_error_recovery,
    NielsenHeuristic.HELP_AND_DOCUMENTATION: _h10_help,
}

# Fail-loud invariant: every heuristic has a detector, in canonical order.
if tuple(_DETECTORS) != tuple(NielsenHeuristic):
    raise RuntimeError("Nielsen drift: _DETECTORS keys do not match NielsenHeuristic in order")


def evaluate_nielsen(candidate: CandidateUI) -> NielsenReport:
    """Evaluate the Nielsen-10 presence vote for one candidate (PRESENCE only, R6).

    For each heuristic, runs its three deterministic voters and records a violation
    as PRESENT iff ≥2 fired. The result is **advisory** — it carries no severity and
    never gates convergence (severity is a human decision).

    Args:
        candidate: The candidate UI to evaluate.

    Returns:
        A frozen :class:`NielsenReport` with one verdict per heuristic, in canonical
        :class:`NielsenHeuristic` order.
    """
    doc = _extract(candidate)
    verdicts: list[HeuristicVerdict] = []
    for heuristic in NielsenHeuristic:
        fired = _DETECTORS[heuristic](doc)
        verdicts.append(
            HeuristicVerdict(
                heuristic=heuristic,
                present=len(fired) >= PRESENCE_VOTE_THRESHOLD,
                votes=len(fired),
                voters_fired=fired,
            )
        )
    return NielsenReport(candidate_id=candidate.candidate_id, verdicts=tuple(verdicts))


__all__ = [
    "PRESENCE_VOTE_THRESHOLD",
    "VOTERS_PER_HEURISTIC",
    "HeuristicVerdict",
    "NielsenHeuristic",
    "NielsenReport",
    "evaluate_nielsen",
]
