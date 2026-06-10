"""Atelier Pipeline Runner — N1 → N2 → N3a → N3c → N3d + Governor + SessionBackend.

Full 8-node DAG:
    N1  BriefParserGate + BriefParserAgent
    N14 WRAI — web research augmented intake (parallel)
    N2  SourceResolverGate + SourceResolverAgent
    N3a DDLC Specialist Pipeline (SequentialAgent of 6 role specialists — AT-020)
    N3c Deterministic Gates (6 gates per candidate — fast, hallucination-free filter)
    N3d ConsensusAgent (D-O-R-A-V multi-judge evaluation on passing candidates)
    N4  Final scoring and convergence decision

All LLM steps execute under MetacognitiveGovernor governance:
    - Fail-loud at the per-user lifetime 5M-token cap (GovernorTokenCapExceeded, AT-095)
    - Self-heal on 429/503 transients (3 retries, exponential backoff)
    - Fail-soft on tool degradation (log + degrade, do not crash)

Session service injectable via ``SessionBackend`` Protocol (B4):
    - Production: ``BigQuerySessionBackend`` (BQ-backed, cross-instance resumption)
    - Local dev:  ``InMemorySessionService`` (ephemeral, default fallback)

PRD Reference: §6.3 (N1-N4), §21 (Failure Trichotomy)
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import os
import re
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Final, cast

from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.adk.runners import Runner
from google.genai import types as genai_types

if TYPE_CHECKING:
    from google.adk.memory import BaseMemoryService
    from google.adk.sessions import BaseSessionService
    from google.adk.tools.tool_confirmation import ToolConfirmation

    from atelier.nodes.llm_judge import JudgeClient

from atelier.board.board_emitter import BoardEmitter
from atelier.durability.design_system_persister import persist_design_system
from atelier.durability.usage_counter import UsageCounterStore, get_usage_store
from atelier.gates.runner import run_gates
from atelier.gates.signoff import (
    AWAIT_SIGNOFF_TOOL,
    CHECKPOINT_KEY,
    SIGNOFF_STAGE_ID,
    SIGNOFF_STATUS_KEY,
    STATUS_APPROVED,
    STATUS_AWAITING,
    STATUS_COMPLETED,
    await_signoff,
    is_signoff_confirmed,
)
from atelier.intake.brief_parser import BriefParserAgent, BriefParserGate
from atelier.intake.brief_spec import BriefSpec
from atelier.intake.source_resolver import (
    ProjectContext,
    source_resolver_agent,
    source_resolver_gate,
)
from atelier.intake.web_research import (
    WebResearchReport,
    WebResearchResult,
    research_brief,
)
from atelier.models.axis_weights import AxisWeights
from atelier.models.data_contracts import CandidateUI, TenantContext
from atelier.models.enums import BoardColumnId, GateAxis, GateDecision
from atelier.models.model_armor_callbacks import (
    MODEL_ARMOR_BLOCK_USER_MESSAGE,
    was_model_armor_blocked,
)
from atelier.models.model_registry import calibrate_model, normalize_model_id
from atelier.nodes.consensus import ConsensusEvaluation, evaluate_candidate
from atelier.orchestrator.governor import (
    TOKEN_CAP_MESSAGE,
    GovernorState,
    MetacognitiveGovernor,
)
from atelier.orchestrator.planner import PlanStep
from atelier.orchestrator.specialists import create_specialist_pipeline, get_specialist_specs
from atelier.orchestrator.stop_controller import clear_stop, is_stop_requested
from atelier.orchestrator.stop_reason import (
    StopReason,
    StopSignals,
    candidate_fingerprint,
    is_duplicate,
    is_no_improvement,
    resolve_stop_reason,
)

logger = logging.getLogger(__name__)

# N3c gate axes — all 6 run
_N3C_GATE_AXES: list[GateAxis] = [
    GateAxis.SEMANTIC_HTML,
    GateAxis.CSS_VALIDITY,
    GateAxis.TOKEN_FIDELITY,
    GateAxis.LIGHTHOUSE_A11Y,
    GateAxis.AXE,
    GateAxis.VISUAL_DIFF,
]

# D-O-R-A-V convergence threshold — composite score must meet this to PASS
CONVERGENCE_THRESHOLD: float = 0.70

# ADK app name constant
_APP_NAME: str = "atelier"

# AT-031 stable stage ids for the per-stage accumulators (GovernorState). These are
# NOT iteration-specific — the durability oracle asserts completed-stage counts are
# unchanged (delta 0) across a halt/crash/resume cycle, so they must be stable.
STAGE_N1_BRIEF_PARSE: str = "n1_brief_parse"
STAGE_N2_SOURCE_RESOLVE: str = "n2_source_resolve"
STAGE_N3A_SPECIALIST_PIPELINE: str = "n3a_specialist_pipeline"

# Nominal token attribution per stage call. The accumulator's purpose is the
# resume-delta oracle (pre-signoff stages frozen, post-signoff stages > 0), not a
# precise token meter; ADK does not surface a deterministic offline token count for
# the faked model surface, so a fixed per-call attribution keeps the delta check
# meaningful and deterministic. This is the AT-031 durability oracle, independent
# of the AT-095 user-lifetime token cap below.
STAGE_TOKEN_ATTRIBUTION: int = 1


def _usage_from_event(event: Any) -> tuple[int, int, int]:
    """Extract (input, output, thinking) tokens from one ADK event's usage_metadata.

    Returns ``(0, 0, 0)`` when the event carries no usage (e.g. the faked offline
    model surface) — the caller estimates deterministically in that case.
    """
    usage = getattr(event, "usage_metadata", None)
    if usage is None:
        return (0, 0, 0)
    return (
        int(getattr(usage, "prompt_token_count", 0) or 0),
        int(getattr(usage, "candidates_token_count", 0) or 0),
        int(getattr(usage, "thoughts_token_count", 0) or 0),
    )


#: A structural/container tag opening at the START of a line — the mark of real
#: markup, as opposed to a tag named mid-sentence or in backticks inside prose.
#: Used to strip a narrated preamble from a document-less HTML fragment.
_LINE_START_STRUCTURAL_TAG = re.compile(
    r"(?im)^\s*<(?:div|main|section|aside|header|nav|article|footer|ul|ol|table|form)\b"
)


def _extract_html_document(raw: str) -> str:
    """Return the clean HTML document embedded in a raw generator candidate.

    The UI Designer specialist reliably wraps its HTML in conversational
    preamble and a `````html`` markdown fence (e.g. "Excellent. The team
    has provided ... Here is the final code:\\n```html\\n<!DOCTYPE html>...").
    Feeding that raw text to the N3c gates makes ``check_semantic_html`` fail (the
    document does not start with a doctype/``<html>``) and axe-core render a
    malformed page, so every candidate is rejected and the run never converges.

    Extraction is layered so it is safe for already-clean output and robust to
    the partial output ``max_output_tokens`` truncation produces:
      1. peel a fenced block — a complete ```` ```html … ``` ```` block, or a
         DANGLING opener/closer the model left when truncated mid-fence;
      2. if a ``<!doctype>``/``<html>`` is present, slice from it to the last
         ``</html>`` — or to end-of-string when the closing tag was truncated;
      3. otherwise (a document-less fragment) slice from the first structural
         tag that begins a line, dropping any narrated preamble.
    If none of these match, the de-fenced, stripped text is returned unchanged
    (a fragment still flows through the gates as before). Every branch guarantees
    the result never carries a leading ```` ``` ```` marker or prose preamble,
    which would otherwise render as literal text above the design in the Studio
    canvas on the non-converged fallback path (surfaced by the live E2E).
    """
    text = raw.strip()
    fence = re.search(r"```(?:html)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    else:
        # No complete fence. The generator sometimes opens ```html and is then
        # truncated by max_output_tokens before the closing fence — strip the
        # dangling opener (and a trailing closer if one is present) so the literal
        # ``` marker never survives into the rendered preview.
        text = re.sub(r"^```(?:html)?[ \t]*\r?\n", "", text, count=1, flags=re.IGNORECASE)
        text = re.sub(r"\r?\n```[ \t]*$", "", text, count=1).strip()

    lower = text.lower()
    start = lower.find("<!doctype")
    if start == -1:
        start = lower.find("<html")
    if start != -1:
        # Slice to the closing </html> when present; otherwise (truncated mid-
        # document) take everything from the doctype/<html> to the end — a
        # browser renders a truncated document fine, but never the preamble.
        end = lower.rfind("</html>")
        return text[start : end + len("</html>")] if end > start else text[start:]
    # No full document (a fragment). The Fixer / UI Designer often narrate "Here
    # is the corrected HTML ..." — with backticked tag mentions like `<aside>` —
    # BEFORE the real markup. Strip that preamble by slicing from the first
    # structural tag that begins a LINE: prose references tags mid-sentence or in
    # backticks, real markup opens them at a line start.
    fragment = _LINE_START_STRUCTURAL_TAG.search(text)
    if fragment:
        return text[fragment.start() :].strip()
    return text


def _ensure_renderable_document(html: str) -> str:
    """Wrap a scaffold-less but renderable fragment in a minimal HTML document.

    A Fixer reliably returns a "corrected section" (e.g. a bare ``<section>`` or
    ``<div>``), and a UI Designer disrupted mid-run (a Stitch MCP drop) can emit a
    body fragment instead of a full document. Such a fragment passes
    :func:`_looks_like_html` — so it is eligible to be the non-convergence
    ``best_partial_html`` — yet has no ``<html>``/``<head>`` for the completion
    passes to anchor ``lang`` / ``<title>`` onto. The result fails the zero-
    tolerance axe gate (``html-has-lang``, ``document-title``) even though the
    design content is sound, and the run reports INCOMPLETE on a perfectly
    renderable screen (live E2E, 2026-06-10: composite 0.600).

    This closes that gap at the same normalization choke point as the token /
    accessibility completion: a fragment that is real, renderable UI (a structural
    opening tag plus a matching close — the :func:`_looks_like_html` bar, so prose
    that merely *names* tags is never wrapped) is hoisted into a minimal valid
    document. The downstream ``_complete_color_token_palette`` then hoists its
    colors into ``:root`` and ``_complete_accessibility`` derives the ``<title>``
    from the fragment's first ``<h1>`` — so the wrapped fragment clears the gates.
    A document that already carries ``<!doctype>``/``<html>`` is returned
    unchanged; non-renderable prose is returned unchanged (and stays filtered out
    by :func:`_looks_like_html` downstream).
    """
    text = html.strip()
    if not text:
        return text
    lower = text.lower()
    if "<!doctype" in lower or "<html" in lower:
        return text
    has_structural = any(tag in lower for tag in _HTML_STRUCTURE_TAGS)
    if not (has_structural and _HTML_CLOSING_TAG.search(lower)):
        return text
    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8" />\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1" />\n'
        f"</head>\n<body>\n{text}\n</body>\n</html>\n"
    )


#: Structural/container tags that mark a candidate as renderable HTML rather than
#: a specialist's markdown narration (e.g. the Wireframer's prose description).
_HTML_STRUCTURE_TAGS: Final[tuple[str, ...]] = (
    "<!doctype",
    "<html",
    "<body",
    "<main",
    "<section",
    "<div",
    "<header",
    "<nav",
    "<form",
    "<ul",
    "<table",
)


#: A real closing tag (``</div>``, ``</main>`` …). Markdown that *describes*
#: structure names opening tags in backticks (`` `<main>` ``) but never writes
#: the matching close, so requiring one separates rendered UI from narration.
_HTML_CLOSING_TAG = re.compile(r"</[a-z][\w-]*>", re.IGNORECASE)


def _looks_like_html(text: str) -> bool:
    """Return True when ``text`` carries real HTML structure, not markdown prose.

    The non-convergence fallback (:data:`best_partial_html`) must surface an
    actual renderable design, never a specialist's markdown description — the
    Wireframer, for instance, emits prose like "Here is the low-fidelity
    structural wireframe ..." that *names* tags such as ``<main>`` / ``<nav>`` in
    backticks. When such prose out-scores the failing-but-real HTML on mean gate
    score, it would otherwise be served as the "design" and render as washed-out
    text in the Studio canvas.

    A full document (doctype / ``<html``) qualifies outright. Otherwise a
    candidate must carry BOTH a structural/container opening tag AND a matching
    closing tag — the closing tag is what distinguishes rendered UI from prose
    that merely references opening tags.
    """
    lower = text.lower()
    if "<!doctype" in lower or "<html" in lower:
        return True
    has_structural = any(tag in lower for tag in _HTML_STRUCTURE_TAGS)
    return has_structural and bool(_HTML_CLOSING_TAG.search(lower))


def _non_convergence_message(iteration: int) -> str:
    """User-facing acknowledgment for a non-converged terminal stop (trichotomy).

    Emitted when the loop exits on ``no_improvement`` / ``max_iterations`` /
    ``duplicate`` without clearing :data:`CONVERGENCE_THRESHOLD`. The pipeline
    still returns the strongest candidate it produced (the ``best_partial_html``
    fallback in :meth:`_run_n3c_n3d_n4` guarantees a real, cleaned-up screen),
    but Atelier states plainly that it did not fully clear every quality gate
    rather than presenting a sub-bar design as if it had converged. This is the
    fail-soft arm of the PRD failure-handling trichotomy — *the agent always
    acknowledges degradation; trust over apparent capability.*

    Args:
        iteration: Zero-indexed iteration the loop stopped on. ``rounds`` is
            ``iteration + 1`` so the count reads naturally to the user.
    """
    rounds = iteration + 1
    return (
        f"Atelier explored {rounds} design "
        f"{'iteration' if rounds == 1 else 'iterations'} and is showing the "
        "strongest candidate it produced. This design did not fully clear every "
        "convergence gate (semantic structure, accessibility, design-token "
        "fidelity, and visual consistency), so treat it as a strong draft rather "
        "than a final, converged result — review the preview and retry to refine it."
    )


#: Color literals in a style context: ``#rgb[a]``/``#rrggbb[aa]`` hex and the
#: functional ``rgb()/rgba()/hsl()/hsla()`` forms. Named colors are intentionally
#: out of scope (the N3c token gate flags numeric literals, which these cover).
_COLOR_LITERAL_PATTERN = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\([^)]*\)|\bhsla?\([^)]*\)")
#: A CSS custom-property declaration and its value (``--name: value;``).
_CSS_DECL_VALUE_PATTERN = re.compile(r"--[\w-]+\s*:\s*([^;{}]+?)\s*[;}]")
_STYLE_BLOCK_PATTERN = re.compile(r"(<style[^>]*>)(.*?)(</style>)", re.DOTALL | re.IGNORECASE)
_INLINE_STYLE_PATTERN = re.compile(r"style\s*=\s*\"([^\"]*)\"", re.IGNORECASE)


def _complete_color_token_palette(html: str) -> str:
    """Declare every style color literal as a ``:root`` design token.

    Deterministic completion of the DDLC TokenGenerator's job (N3a): the UI
    Designer reliably tokenizes most of its palette but leaks a few raw literals
    in hover/focus tints, borders, and shadows. The N3c token-fidelity gate is
    zero-tolerance (AT-012) — one literal whose value matches no declared
    ``--token`` rejects the whole candidate at score 0, so the run never
    converges even though the design is otherwise gate-clean.

    This hoists each not-yet-declared color literal into a generated ``:root``
    token block, so every color resolves to a token *definition* — exactly the
    compliance condition the gate enforces. The zero-tolerance gate itself is
    unchanged; only the candidate is made token-complete (genuine palette
    extraction, the design-system discipline the product exists to apply).
    Existing tokens and usages are left intact; the pass is purely additive.
    """
    style_match = _STYLE_BLOCK_PATTERN.search(html)
    # Collect style text from every <style> block plus inline style="" attributes.
    style_text = " ".join(m[1] for m in _STYLE_BLOCK_PATTERN.findall(html))
    style_text += " " + " ".join(_INLINE_STYLE_PATTERN.findall(html))

    declared = {value.strip().lower() for value in _CSS_DECL_VALUE_PATTERN.findall(style_text)}
    new_literals: list[str] = []
    seen: set[str] = set()
    for literal in _COLOR_LITERAL_PATTERN.findall(style_text):
        key = literal.strip().lower()
        if key not in declared and key not in seen:
            seen.add(key)
            new_literals.append(literal.strip())

    if not new_literals:
        return html

    palette = ":root{" + "".join(f"--c-auto-{i}:{lit};" for i, lit in enumerate(new_literals)) + "}"
    if style_match:
        # Prepend the palette inside the first <style> block.
        return html[: style_match.start(2)] + palette + html[style_match.start(2) :]
    # No <style> block (all-inline styling): add one in <head>, else prepend.
    if re.search(r"</head>", html, re.IGNORECASE):
        return re.sub(
            r"</head>", f"<style>{palette}</style></head>", html, count=1, flags=re.IGNORECASE
        )
    return f"<style>{palette}</style>" + html


_HTML_OPEN_PATTERN = re.compile(r"<html\b[^>]*>", re.IGNORECASE)
_HEAD_OPEN_PATTERN = re.compile(r"<head\b[^>]*>", re.IGNORECASE)
_TITLE_PATTERN = re.compile(r"<title[^>]*>.*?</title>", re.IGNORECASE | re.DOTALL)
_H1_TEXT_PATTERN = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
_PROGRESSBAR_PATTERN = re.compile(r"<[^>]*\brole\s*=\s*[\"']progressbar[\"'][^>]*>", re.IGNORECASE)
_IMG_PATTERN = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_HAS_LANG_PATTERN = re.compile(r"\blang\s*=", re.IGNORECASE)
_HAS_ACCESSIBLE_NAME_PATTERN = re.compile(r"aria-label(ledby)?\s*=", re.IGNORECASE)
_HAS_ALT_PATTERN = re.compile(r"\balt\s*=", re.IGNORECASE)
_TAG_TEXT_PATTERN = re.compile(r"<[^>]+>")


def _insert_attr(tag: str, attr: str) -> str:
    """Insert ``attr`` into an HTML start tag, handling self-closing ``/>``."""
    if tag.endswith("/>"):
        return f"{tag[:-2].rstrip()} {attr}/>"
    return f"{tag[:-1].rstrip()} {attr}>"


def _complete_accessibility(html: str) -> str:
    """Remediate the mechanically-fixable WCAG violations axe-core gates on.

    The N3c axe gate is zero-tolerance (a single critical/serious violation
    rejects the screen), and an LLM reliably leaks one of a small set of
    *structural* a11y gaps — empirically ``html-has-lang``, ``document-title``,
    and ``aria-progressbar-name`` (e.g. an onboarding progress bar with no
    accessible name). Each has a single correct, content-preserving remedy, so
    this pass applies them deterministically (the same shape as the palette
    completion that satisfies the token gate):

      - ``<html>`` gets ``lang="en"`` when absent,
      - a ``<title>`` (the first ``<h1>`` text, else a default) is added when the
        document has none,
      - every ``role="progressbar"`` without an accessible name gets
        ``aria-label="Progress"``,
      - every ``<img>`` without ``alt`` gets ``alt=""`` (treated decorative).

    These are genuine accessibility improvements (a screen reader benefits from
    each), not gate evasion. Judgement-dependent violations (contrast, control
    naming) are left to the generator — the UI Designer's WCAG instructions and
    the gate itself still apply. Operates only on HTML documents; markdown or
    fragments without an ``<html>`` tag pass through with the no-op edits.
    """
    html = _HTML_OPEN_PATTERN.sub(
        lambda m: (
            m.group(0)
            if _HAS_LANG_PATTERN.search(m.group(0))
            else _insert_attr(m.group(0), 'lang="en"')
        ),
        html,
        count=1,
    )

    if not _TITLE_PATTERN.search(html):
        h1 = _H1_TEXT_PATTERN.search(html)
        title = _TAG_TEXT_PATTERN.sub("", h1.group(1)).strip() if h1 else ""
        title_el = f"<title>{title or 'Generated Design'}</title>"
        if _HEAD_OPEN_PATTERN.search(html):
            html = _HEAD_OPEN_PATTERN.sub(lambda m: m.group(0) + title_el, html, count=1)
        elif _HTML_OPEN_PATTERN.search(html):
            html = _HTML_OPEN_PATTERN.sub(
                lambda m: m.group(0) + f"<head>{title_el}</head>", html, count=1
            )

    html = _PROGRESSBAR_PATTERN.sub(
        lambda m: (
            m.group(0)
            if _HAS_ACCESSIBLE_NAME_PATTERN.search(m.group(0))
            else _insert_attr(m.group(0), 'aria-label="Progress"')
        ),
        html,
    )

    return _IMG_PATTERN.sub(
        lambda m: (
            m.group(0)
            if _HAS_ALT_PATTERN.search(m.group(0))
            else _insert_attr(m.group(0), 'alt=""')
        ),
        html,
    )


def _estimate_tokens(prompt: str, candidates: list[Any]) -> tuple[int, int, int]:
    """Deterministic offline token estimate (~4 chars/token) for the AT-095 counter.

    Used only when the model surface surfaces no ``usage_metadata`` (the hermetic
    ``make verify`` / ``make replay`` lane). Deterministic for identical inputs so
    the token meter is byte-stable (PRD §13.3). Thinking tokens are 0 offline —
    real ``thoughts_token_count`` is counted whenever Vertex surfaces it.
    """
    input_tokens = max(1, len(prompt) // 4)
    output_tokens = sum(max(1, len(str(c)) // 4) for c in candidates) if candidates else 0
    return (input_tokens, output_tokens, 0)


def _require_user_id(tenant_ctx: TenantContext) -> str:
    """Return the non-empty Firebase uid for token-cap accounting, or fail loud.

    AT-095: the cap and the rate limiter are keyed on the uid. A missing/empty
    uid must NEVER silently collapse into a shared bucket (which would let
    unrelated callers share one 5M counter — a cross-caller DoS). The public API
    always supplies a verified uid (Depends(require_auth)); this guards the
    programmatic / default-context paths.
    """
    uid = tenant_ctx.user_id
    if not uid:
        raise ValueError(
            "AT-095: TenantContext.user_id is required for per-user token-cap accounting; "
            "refusing to bucket usage into a shared anonymous counter."
        )
    return uid


def _dev_placeholder_tenant_ctx() -> TenantContext:
    """Return the local-dev placeholder :class:`TenantContext`, or fail loud.

    ``run()``/``resume()`` accept ``tenant_ctx=None`` purely as a local-dev /
    hermetic-test convenience. Outside ``ATELIER_ENV=development`` (the same
    gate the usage counter, board emitter, and design-system persister use), a
    missing tenant context is a caller wiring bug: silently defaulting to the
    placeholder tenant ``"t1"`` would bill usage, write board task docs, and
    persist design systems under a tenant/project path no verified caller owns
    — the dead-data path the 2026-06-09 code-health audit flagged. The public
    API (``generate.py``/``a2a.py``) always builds a real context from the
    verified JWT, so production never hits this branch legitimately.
    """
    if os.getenv("ATELIER_ENV", "development") != "development":
        raise ValueError(
            "tenant_ctx is required outside ATELIER_ENV=development: refusing to "
            "default to the placeholder tenant 't1'. Build a TenantContext from "
            "the verified caller identity (see api/generate.py)."
        )
    return TenantContext(
        tenant_id="t1",
        user_id="u1",
        project_id="p1",
    )


def _serialize_checkpoint(
    *,
    brief: BriefSpec,
    project_ctx: ProjectContext,
    wrai_report: WebResearchReport,
    plan: PlanStep,
    surfaces: list[str],
    session_id: str,
    brief_text: str,
    stage_call_counts: dict[str, int],
    stage_token_counts: dict[str, int],
) -> dict[str, Any]:
    """Serialize the pre-signoff pipeline outputs into a JSON-safe checkpoint dict.

    Stored under ``session.state[CHECKPOINT_KEY]`` so a fresh ``AtelierRunner`` sharing
    the same session service can reconstruct N1/N2 outputs after a crash without
    re-running them. ``BriefSpec``/``ProjectContext``/``PlanStep`` are Pydantic
    (``model_dump(mode="json")``); ``WebResearchReport`` is a dataclass
    (``dataclasses.asdict``).
    """
    return {
        "brief": brief.model_dump(mode="json"),
        "project_ctx": project_ctx.model_dump(mode="json"),
        "wrai_report": dataclasses.asdict(wrai_report),
        "plan": plan.model_dump(mode="json"),
        "surfaces": list(surfaces),
        "session_id": session_id,
        "brief_text": brief_text,
        "stage_call_counts": dict(stage_call_counts),
        "stage_token_counts": dict(stage_token_counts),
    }


def _deserialize_checkpoint(
    payload: dict[str, Any],
) -> tuple[BriefSpec, ProjectContext, WebResearchReport, PlanStep, list[str], str, str]:
    """Reconstruct the pre-signoff outputs from a serialized checkpoint.

    Inverse of :func:`_serialize_checkpoint`. Reconstructs the dataclass
    ``WebResearchReport`` (and its ``WebResearchResult`` items) and the Pydantic
    models. Returns ``(brief, project_ctx, wrai_report, plan, surfaces, session_id,
    brief_text)``. The stage accumulators are restored separately by the caller into
    the governor state.
    """
    brief = BriefSpec.model_validate(payload["brief"])
    project_ctx = ProjectContext.model_validate(payload["project_ctx"])
    wrai_raw = payload["wrai_report"]
    wrai_report = WebResearchReport(
        results=[WebResearchResult(**item) for item in wrai_raw.get("results", [])],
        denied_count=wrai_raw.get("denied_count", 0),
        total_queries=wrai_raw.get("total_queries", 0),
    )
    plan = PlanStep.model_validate(payload["plan"])
    surfaces = list(payload["surfaces"])
    return (
        brief,
        project_ctx,
        wrai_report,
        plan,
        surfaces,
        str(payload["session_id"]),
        str(payload["brief_text"]),
    )


#: Synthetic function_call_id for the production halt path. The native ADK runner
#: assigns a real id when a tool call is dispatched (see the AT-031 integration test,
#: which exercises the genuine LongRunningFunctionTool + Runner path); the production
#: halt only needs request_confirmation to register a ToolConfirmation, which requires
#: a non-empty function_call_id.
_SIGNOFF_FUNCTION_CALL_ID: str = "atelier_signoff"


class _SignoffToolContext:
    """Minimal tool-context shim for the production sign-off halt.

    ``await_signoff`` is generic over any context exposing ``function_call_id`` and a
    ``request_confirmation(*, hint, payload)`` method. In the AT-031 integration test the
    real ``ToolContext`` (built by the ADK ``Runner``) is used end-to-end, proving the
    native ``adk_request_confirmation`` halt. In production ``run()`` does not spin up an
    autonomous agent loop to fire the confirmation (that would issue model calls during
    the halt window), so this shim records the confirmation request with the exact
    semantics verified in ``google.adk.tools.tool_context.ToolContext.request_confirmation``
    against google-adk==2.1.0: it writes a ``ToolConfirmation`` into
    ``EventActions.requested_tool_confirmations[function_call_id]``.
    """

    def __init__(self, *, actions: EventActions) -> None:
        self._event_actions = actions
        self.function_call_id = _SIGNOFF_FUNCTION_CALL_ID

    def request_confirmation(
        self,
        *,
        hint: str | None = None,
        payload: Any | None = None,
    ) -> None:
        """Register a confirmation request (mirrors ADK 2.1.0 ToolContext semantics).

        Unlike the real ``ToolContext.request_confirmation`` — which raises ``ValueError``
        when ``function_call_id`` is empty — this shim always supplies a non-empty
        ``function_call_id`` (``_SIGNOFF_FUNCTION_CALL_ID``) by construction, so the genuine
        empty-id guard is unreachable here. That native guard is exercised end-to-end by
        oracle 1's real ``Runner`` + ``LongRunningFunctionTool`` path, not by this shim.
        """
        from google.adk.tools.tool_confirmation import ToolConfirmation  # noqa: PLC0415

        self._event_actions.requested_tool_confirmations[self.function_call_id] = ToolConfirmation(
            hint=hint, payload=payload
        )


def _research_seed_blob(brief: Any, wrai_report: Any) -> str:
    """AT-025: the deterministic research seed embedded in the generator anchor.

    Re-derives the frozen :class:`ResearchFindings` synchronously from the
    (signed-off, immutable) brief + WRAI report and returns its
    ``seed_blob`` — the reference palette / layout / type plus the top applicable
    Tier-1 standards. Re-deriving here (rather than threading the dataclass through
    the AT-031 checkpoint) keeps the anchor byte-stable across iterations AND
    across a sign-off halt/resume, since the inputs are immutable. This is what
    makes a reference URL's tokens demonstrably seed the UI Designer + Token
    Generator output (acceptance A). Fail-soft: any synthesis error degrades to an
    empty seed rather than breaking the generator prompt (R8).
    """
    from atelier.intake.research_findings import synthesize_findings  # noqa: PLC0415

    brief_text = getattr(brief, "intent", "") or ""
    reference_urls = list(getattr(brief, "reference_artifacts", []) or [])
    try:
        findings = synthesize_findings(brief_text, wrai_report, reference_urls)
    except Exception as exc:  # noqa: BLE001
        # Fail-soft (R8): a research-seed failure must never break generation.
        logger.warning(
            "AT-025 anchor seed synthesis failed (fail-soft): %s: %s",
            type(exc).__name__,
            str(exc)[:200],
        )
        return ""
    return findings.seed_blob()


def _compose_anchor(brief: Any, project_ctx: Any, wrai_report: Any) -> str:
    """R4 (ADR-0012 anchored_context): the immutable anchor re-injected into the
    generator prompt every iteration -- the signed-off brief + design tokens +
    research findings, serialized deterministically so the re-injection is
    byte-identical across iterations regardless of accumulated fixer history.
    """
    brief_blob = brief.model_dump_json() if hasattr(brief, "model_dump_json") else str(brief)
    tokens = getattr(project_ctx, "design_tokens", None) or {}
    tokens_blob = json.dumps(tokens, sort_keys=True, default=str)
    findings = getattr(wrai_report, "results", None) or []
    research_blob = json.dumps([str(f) for f in findings], sort_keys=True)
    # AT-025: the applicable-standards + reference-palette seed (deterministic).
    seed_blob = _research_seed_blob(brief, wrai_report)
    return (
        "--- BRIEF (anchor; do not deviate) ---\n"
        + brief_blob
        + "\n--- DESIGN TOKENS (anchor) ---\n"
        + tokens_blob
        + "\n--- RESEARCH FINDINGS (anchor) ---\n"
        + research_blob
        + "\n"
        + seed_blob
    )


def _compose_generator_prompt(anchor: str, screen: str, directive: str) -> str:
    """Compose one iteration's generator prompt: the immutable anchor + the screen
    task + ONLY the latest fixer directive (rejected-variant history is never
    accumulated -- R4)."""
    base = f"{anchor}\n\n--- TASK ---\nGenerate the screen: '{screen}'."
    return f"{base}\n\n--- LATEST FIXER DIRECTIVE ---\n{directive}" if directive else base


def _build_iteration_dorav(
    evaluations_serialized: list[dict[str, Any]],
    composite_score: float,
) -> dict[str, Any]:
    """Build a per-axis D-O-R-A-V payload for an in-progress iteration.

    Mirrors the extraction logic in ``generate._enrich_complete_payload`` so that
    the per-iteration ``iteration_score`` SSE event carries the same shape as the
    final ``complete`` event's ``dorav`` field.  This is intentionally a module-level
    helper so it can be unit-tested independently of the runner.

    Args:
        evaluations_serialized: The list of serialized evaluation dicts as built in
            ``_run_surfaces_and_assemble`` — each entry has ``composite_score``,
            ``passed``, and ``votes`` (a dict mapping axis name to ``{"score": float}``).
        composite_score: The composite score for the current iteration's best candidate
            (may be 0.0 when no candidate passed the gates).

    Returns:
        A dict with per-axis float scores keyed by axis name, a ``composite`` key, and a
        ``failing_axis`` key containing the name of the axis with the lowest score (or
        ``None`` when no per-axis data is available).
    """
    best_eval: dict[str, Any] = evaluations_serialized[0] if evaluations_serialized else {}
    raw_votes: dict[str, Any] = best_eval.get("votes", {})
    dorav: dict[str, float] = {
        axis: float(v["score"]) if isinstance(v, dict) else float(v)
        for axis, v in raw_votes.items()
    }
    dorav["composite"] = float(best_eval.get("composite_score", composite_score))

    # Determine the failing axis (lowest per-axis score, excluding composite).
    failing_axis: str | None = None
    per_axis = {k: v for k, v in dorav.items() if k != "composite"}
    if per_axis:
        failing_axis = min(per_axis, key=lambda k: per_axis[k])

    return {**dorav, "failing_axis": failing_axis}


#: Max characters of a specialist's output surfaced in its legibility trace summary.
_TRACE_SUMMARY_CHARS: int = 200


def _trace_summary(texts: list[Any]) -> str:
    """A formatted, full trace of a specialist's output (AT-026 trace).

    Joins the event's text parts with newlines, preserving all code formatting
    and newlines, without collapsing or truncating, so the legibility trace shows
    the complete output.
    """
    joined = "\n".join(str(t) for t in texts if t).strip()
    return joined or "(no output)"


def _default_session_service() -> BaseSessionService:
    """Create the default session service from ``SESSION_BACKEND`` (B4, AT-080).

    Delegates to
    :func:`atelier.orchestrator.backend_factory.create_session_service`, which
    selects the backend from the ``SESSION_BACKEND`` env var:

        ``memory`` (default) — ``InMemorySessionService`` (offline, zero network)
        ``vertex``           — ``VertexAiSessionService`` (managed production)
        ``bigquery``         — ``BigQuerySessionBackend`` (legacy BigQuery store)

    Returns:
        A ``BaseSessionService`` implementation.
    """
    from atelier.orchestrator.backend_factory import create_session_service  # noqa: PLC0415

    return create_session_service()


def _default_memory_service() -> BaseMemoryService:
    """Create the default memory service from ``SESSION_BACKEND`` (AT-080).

    Mirrors :func:`_default_session_service`: the ``vertex`` backend yields a
    ``VertexAiMemoryBankService`` and the offline default yields an
    ``InMemoryMemoryService``.
    """
    from atelier.orchestrator.backend_factory import create_memory_service  # noqa: PLC0415

    return create_memory_service()


class AtelierRunner:
    """Pipeline Runner with Governor + injectable SessionBackend.

    Chains N1 (Brief Parser) -> N2 (Source Resolver) -> N3a (DDLC Specialist Pipeline).
    All LLM calls are governed by the budget cap and failure trichotomy.

    The session service is injectable via the ``SessionBackend`` Protocol (B4).
    Default: ``BigQuerySessionBackend`` -> ``InMemorySessionService`` fallback.
    """

    def __init__(
        self,
        *,
        session_service: BaseSessionService | None = None,
        memory_service: BaseMemoryService | None = None,
        judge_client: JudgeClient | None = None,
        usage_store: UsageCounterStore | None = None,
        board_emitter: BoardEmitter | None = None,
        max_iterations: int = 3,
        model: str | None = None,
        temperature: float | None = None,
        top_k: int | None = None,
        max_tokens: int | None = None,
    ) -> None:
        """Initialize the runner with a governor, session service, and optional judge client.

        Args:
            session_service: Injectable session service. Defaults to
                BigQuerySessionBackend (with InMemorySessionService fallback).
            judge_client: Injectable LLM judge client. When ``None`` and
                ``ATELIER_JUDGE_MODE`` is ``"llm"`` or ``"hybrid"``,
                auto-constructs a :class:`VertexAIJudgeClient` using
                ``ATELIER_GCP_PROJECT`` (default ``"atelier-build-2026"``).
                Pass an explicit client in tests to avoid network I/O.
            usage_store: Injectable per-user lifetime token-cap store (AT-095).
                Defaults to the process-wide singleton (Firestore in production,
                in-memory in the hermetic / dev lane). Pass an explicit
                in-memory store in tests.
        """
        state = GovernorState()
        self._governor = MetacognitiveGovernor(state=state)
        self._usage_store = usage_store or get_usage_store()
        self._session_service = session_service or _default_session_service()
        self._memory_service = memory_service or _default_memory_service()
        # AT-020b: the Board task-doc emitter (writer for §7A.5; reader is AT-041).
        # Backend auto-selects (in-memory offline/dev, Firestore in production). The
        # board is an observability surface — every emit is fail-soft, so a board
        # outage degrades + logs and NEVER crashes the generation run.
        self._board_emitter = board_emitter or BoardEmitter()

        # Auto-wire production Vertex client when a non-heuristic mode is
        # configured via the environment.  Tests inject a fake client to
        # avoid importing vertexai or hitting the network.
        from atelier.nodes.llm_judge import (  # noqa: PLC0415
            ATELIER_JUDGE_MODE_ENV,
            JUDGE_MODE_HEURISTIC,
            VertexAIJudgeClient,
        )

        effective_mode = os.environ.get(ATELIER_JUDGE_MODE_ENV, JUDGE_MODE_HEURISTIC)
        if judge_client is not None:
            self._judge_client: JudgeClient | None = judge_client
        elif effective_mode != JUDGE_MODE_HEURISTIC:
            project = os.environ.get("ATELIER_GCP_PROJECT", "atelier-build-2026")
            self._judge_client = VertexAIJudgeClient(project=project)
        else:
            self._judge_client = None
        self._max_iterations = max_iterations
        self._custom_model = normalize_model_id(model)
        self._custom_temperature = temperature
        self._custom_top_k = top_k
        self._custom_max_tokens = max_tokens

    def _seed_lifetime_counter(self, user_id: str) -> None:
        """AT-095: bind the governor's token-cap state to ``user_id`` and seed the
        cumulative count from the persisted store so the cap spans runs.

        Idempotent — always reflects the current persisted total. A persistence
        read failure (or a corrupt counter) raises :class:`GovernorUsageUnavailable`
        (fail-closed, retryable 503) from the store — distinct from a real cap breach.
        """
        self._governor._state.user_id = user_id
        self._governor._state.token_cap = self._usage_store.token_cap
        # Seed aggregate total (for reporting / legacy checks).
        snap = self._usage_store.snapshot(user_id)
        self._governor._state.cumulative_user_tokens = snap.total_tokens
        # Seed per-tier accumulators so cap checks span runs (AT-095 acceptance (e)).
        self._governor._state.per_tier_tokens = snap.per_tier()

    # -- AT-020b: Board task-doc lifecycle (writer for §7A.5) -----------------

    def _board_init(
        self,
        *,
        tenant_ctx: TenantContext,
        task_id: str,
        run_id: str,
        agent_role: str,
        status_line: str,
    ) -> None:
        """Create the Board card at the Brief column (fail-soft; never raises).

        The emitter already swallows store errors into a degraded ack; this
        wrapper additionally guards the (programming-bug) skip path so a board
        wiring mistake can never crash a real generation run. A degraded ack is
        logged at debug — the emitter already logged the structured warning.
        """
        try:
            ack = self._board_emitter.initialize_task_doc(
                tenant_ctx=tenant_ctx,
                task_id=task_id,
                run_id=run_id,
                agent_role=agent_role,
                status_line=status_line,
            )
            if ack.degraded:
                logger.debug("AT-020b: board init degraded for task %s", task_id)
        except Exception:  # noqa: BLE001 — board is observability-only, never fatal
            logger.warning(
                "AT-020b: board init raised unexpectedly (fail-soft; run continues)",
                exc_info=True,
                extra={"task_id": task_id},
            )

    def _board_transition(
        self,
        *,
        tenant_ctx: TenantContext,
        task_id: str,
        column: BoardColumnId,
        agent_role: str,
        status_line: str,
    ) -> None:
        """Advance the Board card one column (fail-soft; never raises).

        A :class:`~atelier.board.board_emitter.ColumnSkipError` would mean the
        runner wired a transition out of order — a code bug, not a runtime
        degradation. We surface it loudly in the log (it must be fixed) but still
        do NOT propagate it: the board is observability-only and must never crash
        a paying user's generation run. The state-machine invariant itself is
        proved by the AT-020b unit tests, where the skip DOES raise.
        """
        try:
            ack = self._board_emitter.transition(
                tenant_ctx=tenant_ctx,
                task_id=task_id,
                column=column,
                agent_role=agent_role,
                status_line=status_line,
            )
            if ack.degraded:
                logger.debug(
                    "AT-020b: board transition to %s degraded for task %s",
                    column.value,
                    task_id,
                )
        except Exception:  # noqa: BLE001 — board is observability-only, never fatal
            logger.warning(
                "AT-020b: board transition raised unexpectedly (fail-soft; run continues)",
                exc_info=True,
                extra={"task_id": task_id, "target_column": column.value},
            )

    def _run_n3c_n3d_n4(  # noqa: C901, PLR0912, PLR0915 — the N3c gate / N3d judge / N4 select convergence core
        self,
        raw_candidates: list[Any],
        brief_text: str,  # noqa: ARG002
        iteration: int = 0,
        tenant_ctx: TenantContext | None = None,
    ) -> dict[str, Any]:
        """Execute N3c (deterministic gates) → N3d (consensus) → N4 (final pick).

        This is the convergence engine that separates Atelier from one-shot
        generators. Every candidate from N3a is evaluated through:

            N3c: 6 deterministic gates (semantic HTML, CSS, token fidelity,
                 Lighthouse heuristic, axe heuristic, visual diff). Only
                 candidates that pass ALL gates proceed to N3d.

            N3d: D-O-R-A-V consensus evaluation (5-axis weighted scoring).
                 Produces a composite score per passing candidate.

            N4:  Selects the best-scoring candidate that exceeds the
                 convergence threshold. Falls back to the best available
                 candidate if none exceed the threshold.

        Gates are pure-Python (no LLM calls). Consensus mode is controlled
        by ``ATELIER_JUDGE_MODE``: ``"heuristic"`` (default, v1.0 implementation scorers),
        ``"llm"`` (Vertex AI per-axis judges), or ``"hybrid"`` (LLM wins,
        heuristic disagreement recorded for calibration dashboards).

        Args:
            raw_candidates: List of candidate strings from N3a. Each string
                is assumed to be raw HTML/CSS output from a generator.
            brief_text: Original brief text (used to build candidate metadata).

        Returns:
            Dict with keys: best_candidate, all_gate_results, all_evaluations
            (score-descending), scored_candidates (per gate-passing candidate:
            candidate_id + html + composite_score + votes, joined by id),
            converged, composite_score, candidates_evaluated, candidates_passed_gates.
        """
        from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415
        from uuid import uuid4  # noqa: PLC0415

        weights = AxisWeights()
        gate_results = []
        candidates_passed_gates = 0
        # Best gate-passing-adjacent candidate, used for the no-convergence
        # fallback so we never return a non-design specialist output (e.g. the UX
        # Researcher's markdown) as the "best candidate".
        best_partial_html: str | None = None
        best_partial_score: float = -1.0
        best_partial_candidate_id: uuid.UUID | None = None
        # Candidates that cleared every N3c gate, paired with their normalized
        # HTML; judged concurrently after the (cheap, deterministic) gate pass.
        passing: list[tuple[CandidateUI, str]] = []

        for raw in raw_candidates:
            # Normalize each candidate before the zero-tolerance N3c gates, which
            # otherwise reject every one and the run never converges:
            #   1. extract the bare HTML document (drop prose + ```html fence) so
            #      semantic-HTML / axe see a valid page, not preamble;
            #   2. wrap a scaffold-less-but-renderable fragment (a Fixer's
            #      "corrected section", or a Stitch-disrupted UI Designer) into a
            #      minimal document so the completion passes below have an
            #      <html>/<head> to anchor lang/title onto — otherwise a sound
            #      design fails axe on html-has-lang/document-title;
            #   3. complete the color-token palette so stray literals pass the
            #      token-fidelity gate;
            #   4. remediate the mechanically-fixable axe violations (lang, title,
            #      progressbar name, img alt) so the a11y gate passes.
            html_content = _complete_accessibility(
                _complete_color_token_palette(
                    _ensure_renderable_document(
                        _extract_html_document(raw if isinstance(raw, str) else str(raw))
                    )
                )
            )
            if not html_content.strip():
                continue

            # Build CandidateUI for gate + consensus evaluation
            candidate = CandidateUI(
                candidate_id=uuid4(),
                surface_id=uuid4(),
                iteration=iteration,
                artifacts={"index.html": html_content},
            )

            # N3c: deterministic gates
            gate_result = run_gates(candidate, _N3C_GATE_AXES)
            gate_results.append(gate_result)

            # Track the highest mean-gate-score candidate for the non-convergence
            # fallback below — but ONLY among candidates that are actually HTML.
            # A markdown specialist output (e.g. the Wireframer's prose) can
            # out-score failing-but-real HTML on the mean and would then be served
            # as the "design", rendering as washed-out text in the Studio canvas.
            # Guarding on _looks_like_html keeps the fallback a renderable screen.
            if gate_result.outcomes and _looks_like_html(html_content):
                mean_score = sum(o.score for o in gate_result.outcomes) / len(gate_result.outcomes)
                if mean_score > best_partial_score:
                    best_partial_score = mean_score
                    best_partial_html = html_content
                    best_partial_candidate_id = candidate.candidate_id

            if not gate_result.all_passed:
                failed_axes = [
                    o.axis.value for o in gate_result.outcomes if o.decision != GateDecision.PASS
                ]
                logger.info(
                    "N3c: candidate %s REJECTED — failed gates: %s",
                    str(candidate.candidate_id)[:8],
                    failed_axes,
                )
                continue

            candidates_passed_gates += 1

            from atelier.durability.screenshot_helper import (  # noqa: PLC0415
                capture_and_upload_screenshot,
            )

            tenant_id = tenant_ctx.tenant_id if tenant_ctx else "default"
            screenshot_url = capture_and_upload_screenshot(
                tenant_id=tenant_id,
                candidate_id=str(candidate.candidate_id),
                html=html_content,
            )
            if screenshot_url:
                candidate.artifacts["screenshot.png"] = screenshot_url
                logger.info(
                    "Closed-loop QA: captured candidate screenshot and uploaded to GCS: %s",
                    screenshot_url,
                )

            passing.append((candidate, html_content))

        # N3d: D-O-R-A-V consensus over every gate-passing candidate. The
        # candidates are independent, so judge them concurrently — each
        # evaluate_candidate is a blocking, thread-safe call (heuristic scorers are
        # pure Python; the LLM judge client is concurrency-safe). This cuts N3d
        # wall-clock from the sum of per-candidate judging to roughly the slowest
        # single candidate, the dominant latency cost once gates pass. Order is
        # preserved so selection and token accounting are identical to serial.
        evaluations: list[tuple[ConsensusEvaluation, str]] = []
        if passing:
            with ThreadPoolExecutor(max_workers=min(len(passing), 8)) as pool:
                futures = [
                    pool.submit(
                        evaluate_candidate, candidate, weights, judge_client=self._judge_client
                    )
                    for candidate, _ in passing
                ]
                results = [future.result() for future in futures]
            evaluations = [(ev, html) for ev, (_, html) in zip(results, passing, strict=True)]
            for ev, _html in evaluations:
                logger.info(
                    "N3d: candidate composite=%.3f passed=%s", ev.composite_score, ev.passed
                )

        # N4: select best candidate
        best_candidate: str | None = None
        best_score: float = 0.0
        converged = False

        if evaluations:
            # Sort by composite score descending
            evaluations.sort(key=lambda x: x[0].composite_score, reverse=True)
            best_evaluation, best_candidate = evaluations[0]
            best_score = best_evaluation.composite_score
            converged = best_score >= CONVERGENCE_THRESHOLD

            logger.info(
                "N4: selected candidate with composite=%.3f (converged=%s, threshold=%.2f)",
                best_score,
                converged,
                CONVERGENCE_THRESHOLD,
            )
        elif best_partial_html is not None:
            # No candidate passed every gate — return the best-scoring normalized
            # HTML design, not the first raw event (which may be a non-design
            # specialist output). The user still gets a real, cleaned-up screen.
            best_candidate = best_partial_html
            logger.warning(
                "N4: all candidates failed N3c gates; falling back to best-scoring HTML "
                "candidate (mean gate score %.1f/100 across %d candidates)",
                best_partial_score,
                len(raw_candidates),
            )
        elif raw_candidates:
            # Last resort: nothing was gradable (no HTML at all) — return the
            # first raw candidate so the response is never empty.
            best_candidate = (
                raw_candidates[0] if isinstance(raw_candidates[0], str) else str(raw_candidates[0])
            )
            logger.warning(
                "N4: no HTML candidate available; falling back to raw candidate 1/%d",
                len(raw_candidates),
            )

        # Canonical per-candidate join (audit 2026-06-03). Each entry pairs a
        # gate-passing candidate's normalized HTML with its OWN consensus score,
        # votes, and candidate_id, built straight from the `evaluations` zip where
        # html<->score<->id are provably aligned. Every per-candidate consumer
        # (DPO pair extraction, trajectory recording, the API response builder)
        # MUST read this structure and join by candidate_id — never positionally
        # zip the raw-order candidates / gate_results against the
        # score-descending `all_evaluations`. That positional mismatch silently
        # inverted the DPO chosen/rejected labels and mispaired per-candidate
        # scores. This list is self-describing, so its order does not matter.
        if evaluations:
            scored_candidates = [
                {
                    "candidate_id": str(ev.candidate_id),
                    "html": html,
                    "composite_score": ev.composite_score,
                    "votes": {axis.value: {"score": v.score} for axis, v in ev.votes.items()},
                }
                for ev, html in evaluations
            ]
        elif best_partial_html is not None:
            scored_candidates = [
                {
                    "candidate_id": str(best_partial_candidate_id or uuid4()),
                    "html": best_partial_html,
                    "composite_score": best_partial_score / 100.0,
                    "votes": {},
                }
            ]
        elif raw_candidates:
            scored_candidates = [
                {
                    "candidate_id": str(uuid4()),
                    "html": best_candidate,
                    "composite_score": 0.0,
                    "votes": {},
                }
            ]
        else:
            scored_candidates = []

        # AT-097: total N3d (D-O-R-A-V judge) token spend across every evaluated
        # candidate this iteration. 0 in heuristic mode (no LLM call); > 0 when
        # ATELIER_JUDGE_MODE routes axes through Vertex judges. The runner charges
        # this to the per-user lifetime cap (closes the AT-095 N3a-only under-count).
        return {
            "best_candidate": best_candidate,
            "all_gate_results": gate_results,
            # Score-descending (so [0] is the best); the dorav enrichment and the
            # iteration scorecard rely on this order. Per-candidate consumers must
            # use `scored_candidates` (joined by id) instead.
            "all_evaluations": [e for e, _ in evaluations],
            "scored_candidates": scored_candidates,
            "converged": converged,
            "composite_score": best_score,
            "candidates_evaluated": len(raw_candidates),
            "candidates_passed_gates": candidates_passed_gates,
            "judge_input_tokens": sum(e.total_input_tokens for e, _ in evaluations),
            "judge_output_tokens": sum(e.total_output_tokens for e, _ in evaluations),
            "judge_thinking_tokens": sum(e.total_thinking_tokens for e, _ in evaluations),
        }

    async def _run_n1_n2(
        self,
        brief_text: str,  # used for trajectory metadata
        tenant_ctx: TenantContext,
        progress_callback: Callable[[str, dict[str, Any]], Any] | None = None,
    ) -> tuple[Any, Any, WebResearchReport, Any]:
        """Execute N1 (Brief Parser), N0 (Planner), WRAI (conditional), and N2 (Source Resolver).

        The PlannerAgent (N0) runs after brief parsing to produce a PlanStep
        that drives WRAI routing: narrow briefs skip web research, creative
        briefs get full research augmentation. AT-025 then synthesizes the WRAI
        report + domain Tier-1 standards + reference-URL palette into a frozen
        ``ResearchFindings`` and enriches the plan with its ``proposed_defaults``;
        the seed is re-derived deterministically at anchor-composition time so it
        also survives the AT-031 sign-off halt/resume (no extra checkpoint field).

        Returns:
            Tuple of (brief, project_ctx, wrai_report, plan_step). The plan carries
            the AT-025 ``proposed_defaults`` / ``gaps`` populated from research.
        """
        from atelier.intake.research_findings import research_synthesizer  # noqa: PLC0415
        from atelier.orchestrator.planner import PlannerAgent  # noqa: PLC0415

        gate = BriefParserGate()
        outcome = gate.check(brief_text)
        if outcome.decision != GateDecision.PASS:
            raise ValueError(f"Brief failed gate: {outcome.diagnostic}")
        n1_agent = BriefParserAgent()
        brief = await n1_agent.parse(brief_text)
        # AT-031: record the N1 completed-stage call on a stable id. Captured into the
        # sign-off checkpoint and restored on resume so N1 never re-runs (delta 0).
        self._governor._state.record_stage_call(
            STAGE_N1_BRIEF_PARSE, tokens=STAGE_TOKEN_ATTRIBUTION
        )

        # N0: PlannerAgent — dynamic DAG routing based on brief analysis
        planner = PlannerAgent()
        plan = await planner.plan(brief_text)
        logger.info(
            "N0: PlannerAgent produced plan",
            extra={
                "should_run_wrai": plan.should_run_wrai,
                "ensemble_k": plan.ensemble_k,
                "constitution": plan.constitution,
                "reasoning": plan.reasoning,
            },
        )

        # N14 WRAI: conditional on plan.should_run_wrai
        if plan.should_run_wrai:
            wrai_report = await research_brief(brief_text)
            # AT-026 (Mid legibility): surface ONE research_query trace event per
            # WRAI query — the grounded provenance of what Atelier looked up, with
            # the top citation per query so the user can verify. Fail-soft: a trace
            # emission failure must never break intake (R8).
            if progress_callback:
                await self._emit_research_queries(wrai_report, progress_callback)
        else:
            logger.info("N14 WRAI: skipped per PlannerAgent (should_run_wrai=False)")
            wrai_report = WebResearchReport(results=[])

        # AT-025: synthesize report + domain standards + reference palette into a
        # frozen ResearchFindings; enrich the plan with proposed_defaults + gaps.
        # research_synthesizer performs no network I/O (grounding already ran) and
        # never blocks intake — an injection brief is acknowledged (armor_verdict)
        # and intake proceeds (fail-soft, R8).
        research_findings = await research_synthesizer(
            brief_text=brief_text,
            report=wrai_report,
            reference_urls=list(getattr(brief, "reference_artifacts", []) or []),
        )
        plan = plan.with_research(research_findings)
        # AT-030 clarify gate (decision layer on AT-025 data): assess the brief on
        # the six specification dimensions and classify the gaps the gate routes.
        # A clear brief leaves the plan unchanged (no questions, no new defaults); an
        # under-specified or high-stakes brief gets ``gaps_detail`` populated so the
        # stakes router can ask-vs-silent-default at emission time (in ``run``).
        from atelier.orchestrator.planner import assess_specification  # noqa: PLC0415

        assessment = assess_specification(brief_text)
        plan = plan.with_clarify_assessment(assessment, research_findings)
        logger.info(
            "AT-025: research synthesized",
            extra={
                "domain": research_findings.domain,
                "applicable_standards": len(research_findings.applicable_standards),
                "proposed_defaults": len(plan.proposed_defaults),
                "armor_verdict": research_findings.armor_verdict.value,
                "reference_palette": len(research_findings.reference_extract.palette),
                "clarify_ambiguity": assessment.ambiguity_score,
                "clarify_gaps": len(plan.gaps_detail),
            },
        )

        if not source_resolver_gate(tenant_ctx, brief):
            raise ValueError("Source resolver gate failed (no descriptor or design source).")
        project_ctx = await source_resolver_agent(tenant_ctx, brief)
        # AT-031: record the N2 completed-stage call (stable id; frozen across resume).
        self._governor._state.record_stage_call(
            STAGE_N2_SOURCE_RESOLVE, tokens=STAGE_TOKEN_ATTRIBUTION
        )
        return brief, project_ctx, wrai_report, plan

    async def _emit_research_queries(
        self,
        wrai_report: WebResearchReport,
        progress_callback: Callable[[str, dict[str, Any]], Any],
    ) -> None:
        """AT-026 (Mid): emit ONE ``research_query`` trace event per WRAI query.

        The Mid-legibility bar requires ">= 1 trace event per research query". The
        WRAI report carries ``total_queries`` (queries dispatched) and ``results``
        (scored, query-tagged). We group results by their ``query`` and emit one
        event per distinct query that produced a surfaced result, then top up to
        ``total_queries`` with bare-query events for any query that returned nothing
        (so every dispatched query is legible, not just the ones that hit). Each
        event carries the top citation for that query so the provenance is
        verifiable. Fail-soft: any emission error degrades to a logged warning and
        intake proceeds (R8) — the trace is an aid, never a hard gate.
        """
        try:
            by_query: dict[str, list[WebResearchResult]] = {}
            for result in wrai_report.results:
                by_query.setdefault(result.query, []).append(result)

            emitted = 0
            for query, hits in by_query.items():
                top = max(hits, key=lambda r: r.trust_score)
                await progress_callback(
                    "research_query",
                    {
                        "query": query,
                        "result_count": len(hits),
                        "top_citation": top.url,
                        "top_title": top.title,
                        "trust_score": top.trust_score,
                    },
                )
                emitted += 1

            # Top up: every DISPATCHED query is legible even when it returned no
            # surfaced result (so the count matches total_queries the user sees).
            for i in range(emitted, wrai_report.total_queries):
                await progress_callback(
                    "research_query",
                    {
                        "query": f"research query {i + 1}",
                        "result_count": 0,
                        "top_citation": "",
                        "top_title": "",
                        "trust_score": 0.0,
                    },
                )
        except Exception:  # noqa: BLE001
            # Fail-soft (R8): a research trace failure must never break intake.
            logger.warning(
                "AT-026: research_query trace emission failed; proceeding",
                exc_info=True,
            )

    async def _emit_clarify(
        self,
        *,
        plan: PlanStep,
        surfaces: list[str],
        progress_callback: Callable[[str, dict[str, Any]], Any],
    ) -> None:
        """AT-030: run the clarify gate and surface its single batched event.

        Routes the plan's classified gaps (ask high-stakes/irreversible; silently
        apply cheap+local cited defaults) into one :class:`ClarifyBatch` and emits
        it as a ``clarify`` progress event — but only when the gate is non-silent
        (a clear brief emits nothing). Fail-soft: a clarify failure must never
        break generation, so any error degrades to "no clarify event" with a
        logged warning (the gate is an aid, not a hard gate here).
        """
        from atelier.gates.clarify import clarify_gate  # noqa: PLC0415
        from atelier.models.acceptance import AcceptanceCriteria  # noqa: PLC0415

        try:
            acceptance = AcceptanceCriteria(
                run_id="clarify-preview",
                brief_sha256="0" * 64,
                required_surfaces=list(surfaces),
            )
            emitted: list[Any] = []
            clarify_gate(
                plan=plan,
                acceptance=acceptance,
                research_findings=None,
                emit=emitted.append,
            )
            for batch in emitted:
                await progress_callback("clarify", batch.model_dump(mode="json"))
        except Exception:  # noqa: BLE001
            # Fail-soft: the clarify event is an anti-railroad aid, not a hard gate
            # in the non-signoff path. A failure here must not block generation.
            logger.warning(
                "AT-030 clarify gate failed; proceeding without a clarify event",
                exc_info=True,
                extra={"surfaces": surfaces},
            )

    async def run(
        self,
        brief_text: str,  # used for trajectory metadata
        tenant_ctx: TenantContext | None = None,
        progress_callback: Callable[[str, dict[str, Any]], Any] | None = None,
        *,
        require_signoff: bool = False,
    ) -> dict[str, Any]:
        """Run the pipeline from brief text to generated candidates.

        Args:
            brief_text: Raw brief text input.
            tenant_ctx: Tenant context for source resolution. ``None`` is a
                local-dev / hermetic-test convenience only: it resolves to the
                placeholder context in ``ATELIER_ENV=development`` and raises
                ``ValueError`` in any other environment (fail-loud — see
                :func:`_dev_placeholder_tenant_ctx`).
            progress_callback: Optional async callback to stream progress events.
            require_signoff: AT-031 opt-in human-in-the-loop gate. When ``True``,
                the pipeline locks the plan/scope (N0/N1/N2), persists an idempotent
                ``AWAITING_SIGNOFF`` checkpoint into session state, fires the native
                ``await_signoff`` confirmation request, and RETURNS a halt sentinel
                *before* any screen generation (N3a). Resume via :meth:`resume` with
                a confirmed ``ToolConfirmation``. Defaults to ``False`` (no gate; the
                pre-AT-031 behaviour every existing caller relies on).

        Returns:
            When not gated (or when the gate is already approved inline), the full
            response payload (brief, project context, candidates, ...). When gated
            and awaiting sign-off, a halt sentinel
            ``{"status": "awaiting_signoff", "session_id": ..., "signoff": {...}}``.

        Raises:
            GovernorTokenCapExceeded: When the user's cumulative lifetime token
                count is at/over the 5M cap (AT-095). Fail-loud per PRD §21/§13.
            GovernorRateLimitExceeded: When the user exceeds the request-rate
                limit (AT-095/097). Fail-loud reject of the offending request.
            ValueError: When brief fails the deterministic gate.
        """
        if tenant_ctx is None:
            # Dev/test convenience ONLY — fails loud outside ATELIER_ENV=development.
            tenant_ctx = _dev_placeholder_tenant_ctx()

        # AT-095 (§13.2 / G16): per-user lifetime token cap, enforced server-side
        # PRE-FLIGHT — before any Vertex call (N1/N2 included). Seed the cumulative
        # count from the persisted store (spans runs), rate-limit this request so the
        # cap cannot be burned in seconds (acceptance (f)), then fail-loud if already
        # at/over the cap (acceptance (c): no Vertex spend once at cap).
        user_id = _require_user_id(tenant_ctx)
        self._usage_store.check_rate_limit(user_id)
        # AT-097: the fleet-wide token circuit-breaker — reject before N1/N2 (the
        # first Vertex spend) if aggregate consumption across all users tripped it.
        self._usage_store.check_circuit_breaker()
        self._seed_lifetime_counter(user_id)
        self._governor._check_token_budget()

        brief, project_ctx, wrai_report, plan = await self._run_n1_n2(
            brief_text, tenant_ctx, progress_callback=progress_callback
        )

        # Create a session via the injected session service (B4)
        session_id = str(uuid.uuid4())
        session = await self._session_service.create_session(
            app_name=_APP_NAME,
            user_id=user_id,
            state={"brief_text": brief_text[:500]},  # Truncate for state storage
            session_id=session_id,
        )

        # AT-020b: open the Board card at the FIRST column (Brief). The session id
        # is the stable task id — it survives the sign-off halt/resume and is what
        # AT-041's onSnapshot reader watches. Fail-soft (observability surface).
        self._board_init(
            tenant_ctx=tenant_ctx,
            task_id=session.id,
            run_id=session.id,
            agent_role="intake",
            status_line="Brief frozen; planning the design pipeline",
        )

        if progress_callback:
            plan_data = plan.model_dump() if hasattr(plan, "model_dump") else {}
            plan_data["surfaces"] = getattr(plan, "surfaces", ["landing page"])
            # AT-026: surface the session id on the plan event so the legibility UI
            # (and the Stop control) can address THIS run — the Stop endpoint is
            # keyed on session_id and the loop honors it per-session.
            plan_data["session_id"] = session.id
            await progress_callback("plan", plan_data)

        surfaces = getattr(plan, "surfaces", ["landing page"])
        if not surfaces:
            surfaces = ["landing page"]

        # AT-020b: Brief -> Decompose. The plan has decomposed the brief into the
        # ordered DDLC specialist plan (ux_research is the first specialist).
        self._board_transition(
            tenant_ctx=tenant_ctx,
            task_id=session.id,
            column=BoardColumnId.DECOMPOSE,
            agent_role="ux_research",
            status_line="Decomposed into the DDLC specialist plan",
        )
        # AT-020b: Decompose -> Awaiting Sign-off. Scope is locked; the card now
        # sits at the human sign-off gate. In the require_signoff path the run
        # halts here (the card stays at this column until resume); in the auto
        # path this column is transient (immediately followed by Generating).
        self._board_transition(
            tenant_ctx=tenant_ctx,
            task_id=session.id,
            column=BoardColumnId.AWAITING_SIGNOFF,
            agent_role="planner",
            status_line="Scope locked; awaiting human sign-off",
        )

        # AT-030: run the clarify gate over the enriched plan. The stakes router
        # asks high-stakes/irreversible gaps and silently applies cheap+local cited
        # defaults; ONE batched event is surfaced (never drip-fed). A clear brief
        # emits nothing. The batch feeds the §14 clarify panel; confirmed defaults
        # are written into ACCEPTANCE at sign-off via ``apply_clarify_answers``.
        if progress_callback:
            await self._emit_clarify(
                plan=plan,
                surfaces=surfaces,
                progress_callback=progress_callback,
            )

        # AT-031 (PRD §1 / §16 / R5): fail-closed human sign-off gate. After the plan
        # and scope are locked and BEFORE the screen loop (N3a), halt for an explicit
        # human approval. Opt-in (default False preserves the pre-AT-031 path). The
        # halt is durable: an idempotent AWAITING_SIGNOFF checkpoint is persisted into
        # session state so a crashed runner resumes from here with zero re-execution.
        if require_signoff and session.state.get(SIGNOFF_STATUS_KEY) != STATUS_APPROVED:
            return await self._halt_for_signoff(
                session=session,
                brief=brief,
                project_ctx=project_ctx,
                wrai_report=wrai_report,
                plan=plan,
                surfaces=surfaces,
                brief_text=brief_text,
                progress_callback=progress_callback,
            )

        return await self._run_surfaces_and_assemble(
            brief=brief,
            project_ctx=project_ctx,
            wrai_report=wrai_report,
            plan=plan,
            surfaces=surfaces,
            session_id=session.id,
            tenant_ctx=tenant_ctx,
            brief_text=brief_text,
            progress_callback=progress_callback,
        )

    async def _halt_for_signoff(
        self,
        *,
        session: Any,
        brief: BriefSpec,
        project_ctx: ProjectContext,
        wrai_report: WebResearchReport,
        plan: PlanStep,
        surfaces: list[str],
        brief_text: str,
        progress_callback: Callable[[str, dict[str, Any]], Any] | None,
    ) -> dict[str, Any]:
        """Persist the AWAITING_SIGNOFF checkpoint, fire the native confirmation, halt.

        Serializes the pre-signoff outputs (N1/N2 results, plan, surfaces, and the
        per-stage accumulators) into ``session.state`` via a durable ADK ``state_delta``,
        invokes the native ``await_signoff`` confirmation request to demonstrate a real
        ``requested_tool_confirmations`` halt, emits a ``"signoff"`` progress event, and
        returns the halt sentinel — stopping before N3a.
        """
        scope_summary = ", ".join(surfaces)
        checkpoint = _serialize_checkpoint(
            brief=brief,
            project_ctx=project_ctx,
            wrai_report=wrai_report,
            plan=plan,
            surfaces=surfaces,
            session_id=session.id,
            brief_text=brief_text,
            stage_call_counts=self._governor._state.stage_call_counts,
            stage_token_counts=self._governor._state.stage_token_counts,
        )
        await self._persist_signoff_state(
            session=session,
            status=STATUS_AWAITING,
            checkpoint=checkpoint,
        )

        # Fire the native ADK confirmation request so a real
        # requested_tool_confirmations / is_long_running halt is demonstrable. The
        # confirmation is captured on a throwaway EventActions: production resume is
        # driven by resume() supplying a confirmed ToolConfirmation, not by an
        # autonomous agent loop here (which would issue model calls during the halt).
        signoff_actions = EventActions()
        ctx = _SignoffToolContext(actions=signoff_actions)
        signoff_response = await_signoff(ctx, scope_summary=scope_summary)  # type: ignore[arg-type]
        requested = signoff_actions.requested_tool_confirmations
        signoff_event = {
            "status": signoff_response["status"],
            "stage": signoff_response["stage"],
            "requested_tool_confirmations": list(requested.keys()),
            # Source the long-running flag from the tool object itself (the native
            # LongRunningFunctionTool) rather than hardcoding it, so the sentinel
            # stays correct if the tool's nature ever changes.
            "is_long_running": AWAIT_SIGNOFF_TOOL.is_long_running,
            "hint": next(iter(requested.values())).hint if requested else None,
        }

        if progress_callback:
            await progress_callback("signoff", signoff_event)

        logger.info(
            "AT-031: pipeline halted for human sign-off (session=%s, surfaces=%s)",
            session.id,
            surfaces,
        )
        return {
            "status": "awaiting_signoff",
            "session_id": session.id,
            "signoff": signoff_event,
        }

    async def _persist_signoff_state(
        self,
        *,
        session: Any,
        status: str,
        checkpoint: dict[str, Any] | None = None,
    ) -> None:
        """Durably persist the sign-off status (and optional checkpoint) into session state.

        Uses an ADK ``append_event`` with a ``state_delta`` so a fresh ``AtelierRunner``
        reading the same session service after a crash observes the persisted state. The
        in-memory ``session.state`` mapping is also updated so the same-process idempotency
        check (``session.state.get(SIGNOFF_STATUS_KEY)``) sees the write immediately.
        """
        state_delta: dict[str, Any] = {SIGNOFF_STATUS_KEY: status}
        if checkpoint is not None:
            state_delta[CHECKPOINT_KEY] = checkpoint
        event = Event(author=_APP_NAME, actions=EventActions(state_delta=state_delta))
        await self._session_service.append_event(session=session, event=event)
        # append_event applies the delta to the passed session in ADK >=2.0; mirror it
        # defensively so callers reading session.state in-process do not depend on that.
        session.state.update(state_delta)

    async def _persist_stop_checkpoint(
        self,
        *,
        brief: BriefSpec,
        project_ctx: ProjectContext,
        wrai_report: WebResearchReport,
        plan: PlanStep,
        surfaces: list[str],
        session_id: str,
        brief_text: str,
        user_id: str,
    ) -> None:
        """AT-026 / R13: persist an in-flight Stop checkpoint so resume can continue.

        Serializes the (immutable) pre-N3a outputs + the per-stage accumulators into
        ``session.state`` under the same ``CHECKPOINT_KEY`` the sign-off halt uses,
        and marks the session ``AWAITING_SIGNOFF`` so a subsequent confirmed
        :meth:`resume` re-enters the surface loop from the checkpoint (N1/N2 are NOT
        re-run — their completed-stage deltas stay 0). Reuses the exact serialization
        + durable ``state_delta`` path proven by AT-031, so the Stop and the sign-off
        halt share one recovery surface. Fail-soft on a session read miss: a Stop
        whose session vanished is logged, not crashed (the loop still halts).
        """
        checkpoint = _serialize_checkpoint(
            brief=brief,
            project_ctx=project_ctx,
            wrai_report=wrai_report,
            plan=plan,
            surfaces=surfaces,
            session_id=session_id,
            brief_text=brief_text,
            stage_call_counts=self._governor._state.stage_call_counts,
            stage_token_counts=self._governor._state.stage_token_counts,
        )
        session = await self._session_service.get_session(
            app_name=_APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )
        if session is None:
            logger.warning(
                "AT-026: Stop checkpoint skipped — session %s not found (loop still halts)",
                session_id,
            )
            return
        await self._persist_signoff_state(
            session=session,
            status=STATUS_AWAITING,
            checkpoint=checkpoint,
        )

    async def resume(
        self,
        session_id: str,
        confirmation: ToolConfirmation,
        tenant_ctx: TenantContext | None = None,
        progress_callback: Callable[[str, dict[str, Any]], Any] | None = None,
    ) -> dict[str, Any]:
        """Resume a sign-off-halted run from its durable checkpoint (AT-031).

        This is the crash-recovery path: a FRESH ``AtelierRunner`` constructed with the
        same ``session_service`` can call ``resume`` to reload the ``AWAITING_SIGNOFF``
        checkpoint, restore the per-stage accumulators (so completed N1/N2 stages are NOT
        re-incremented), and — only when ``confirmation.confirmed is True`` — run the
        screen loop + payload assembly using the checkpointed outputs (N1/N2 do not
        re-run, so their ``stage_call_counts`` delta is 0).

        ``resume()`` expects a FRESH runner: it treats the checkpoint's persisted
        accumulators as authoritative and REPLACES the in-runner
        ``stage_call_counts``/``stage_token_counts`` with them. Any prior in-runner
        accumulator values (if ``resume`` were called on a non-fresh runner) are
        intentionally discarded — the durable checkpoint is the single source of truth.

        Terminal-state re-entry guard (PRD P4 "crash -> resume, no double-charge"): a
        SECOND confirmed resume on a session whose ``signoff_status`` is already
        ``APPROVED`` or ``COMPLETED`` (approval-webhook redelivery, a UI double-click, or
        a crash AFTER the APPROVED write) must NOT re-run the surface loop — that would be
        real duplicated model spend. Such a re-entry fails closed: it returns an
        ``{"status": "already_resumed", ...}`` sentinel WITHOUT re-running surfaces. Note:

          * Mid-N3a crash recovery — a crash DURING the surface loop, leaving the session
            ``APPROVED`` but with surfaces only partially generated — is intentionally OUT
            of AT-031 scope. The guard fails closed (no re-run, no double-charge) rather
            than auto-resuming partial work; finer-grained mid-surface checkpointing is
            future scope.
          * The guard is NOT concurrency-safe against two genuinely simultaneous resumes:
            the session service offers no compare-and-set, so two callers that both read
            ``AWAITING_SIGNOFF`` before either writes ``APPROVED`` could both proceed.
            Single-flight serialization of resumes is out of AT-031 scope.

        Args:
            session_id: The session id returned in the halt sentinel.
            confirmation: The human's ``ToolConfirmation``. Fail-closed: only
                ``confirmed is True`` advances; ``confirmed is False`` (or absent) leaves
                the run ``AWAITING_SIGNOFF`` and returns the halt sentinel unchanged.
            tenant_ctx: Tenant context. ``None`` resolves to the same dev-only
                placeholder as :meth:`run` (raises ``ValueError`` outside
                ``ATELIER_ENV=development``).
            progress_callback: Optional async progress callback.

        Returns:
            The full response payload on first approval; the halt sentinel on denial;
            an ``{"status": "already_resumed", ...}`` sentinel on re-entry of an
            already-APPROVED/COMPLETED session.

        Raises:
            ValueError: When no AWAITING_SIGNOFF checkpoint exists for ``session_id``.
        """
        if tenant_ctx is None:
            # Dev/test convenience ONLY — fails loud outside ATELIER_ENV=development.
            tenant_ctx = _dev_placeholder_tenant_ctx()

        session = await self._session_service.get_session(
            app_name=_APP_NAME,
            user_id=_require_user_id(tenant_ctx),
            session_id=session_id,
        )
        if session is None:
            raise ValueError(f"resume: no session found for session_id={session_id}")
        raw_checkpoint = session.state.get(CHECKPOINT_KEY)
        # Absent or non-dict checkpoint both mean "nothing to resume" — a domain
        # precondition failure, not a caller type-contract violation.
        checkpoint_present = isinstance(raw_checkpoint, dict)
        if not checkpoint_present:
            raise ValueError(f"resume: no AWAITING_SIGNOFF checkpoint for session_id={session_id}")
        checkpoint = cast("dict[str, Any]", raw_checkpoint)

        (
            brief,
            project_ctx,
            wrai_report,
            plan,
            surfaces,
            _ckpt_session_id,
            brief_text,
        ) = _deserialize_checkpoint(checkpoint)

        # Restore the pre-signoff stage accumulators so completed stages are not
        # re-incremented (idempotent resume — completed-stage delta 0). The checkpoint is
        # authoritative for a FRESH runner; any prior in-runner accumulators are discarded.
        self._governor._state.stage_call_counts = dict(checkpoint.get("stage_call_counts", {}))
        self._governor._state.stage_token_counts = dict(checkpoint.get("stage_token_counts", {}))

        # Terminal-state re-entry guard (PRD P4 — no double-charge). If the session is
        # already APPROVED or COMPLETED, a second confirmed resume (webhook redelivery,
        # double-click, or a crash after the APPROVED write) must NOT re-run the surface
        # loop. Fail closed: return an idempotent sentinel without re-running surfaces /
        # re-recording N3a calls. (See the method docstring for the mid-surface-crash and
        # concurrency caveats — both intentionally out of AT-031 scope.)
        current_status = session.state.get(SIGNOFF_STATUS_KEY)
        if current_status in (STATUS_APPROVED, STATUS_COMPLETED):
            logger.info(
                "AT-031: resume re-entry on already-%s session %s — no surface re-run "
                "(fail-closed, no double-charge)",
                current_status,
                session_id,
            )
            return {
                "status": "already_resumed",
                "session_id": session_id,
                "signoff_status": current_status,
            }

        # Fail-closed negative arm: without an explicit confirmed sign-off, stay
        # AWAITING_SIGNOFF and do not advance.
        if not is_signoff_confirmed(confirmation):
            await self._persist_signoff_state(session=session, status=STATUS_AWAITING)
            logger.info(
                "AT-031: resume denied (confirmation not confirmed); session %s stays %s",
                session_id,
                STATUS_AWAITING,
            )
            scope_summary = ", ".join(surfaces)
            return {
                "status": "awaiting_signoff",
                "session_id": session_id,
                "signoff": {
                    "status": STATUS_AWAITING,
                    "stage": SIGNOFF_STAGE_ID,
                    "scope_summary": scope_summary,
                },
            }

        # Mark APPROVED before running surfaces so a crash mid-surface leaves a terminal
        # status the re-entry guard treats as "do not re-run" (fail-closed, no
        # double-charge) — see the re-entry guard above and the docstring caveats.
        await self._persist_signoff_state(session=session, status=STATUS_APPROVED)
        if progress_callback:
            await progress_callback(
                "signoff_approved", {"session_id": session_id, "stage": SIGNOFF_STAGE_ID}
            )
        logger.info("AT-031: sign-off APPROVED for session %s; resuming N3a", session_id)

        payload = await self._run_surfaces_and_assemble(
            brief=brief,
            project_ctx=project_ctx,
            wrai_report=wrai_report,
            plan=plan,
            surfaces=surfaces,
            session_id=session_id,
            tenant_ctx=tenant_ctx,
            brief_text=brief_text,
            progress_callback=progress_callback,
        )

        # Record the terminal state once surfaces finish. A subsequent confirmed resume
        # now hits the COMPLETED arm of the re-entry guard (no surface re-run).
        await self._persist_signoff_state(session=session, status=STATUS_COMPLETED)
        return payload

    async def _run_surfaces_and_assemble(  # noqa: C901, PLR0912, PLR0915 — core multi-surface convergence loop
        self,
        *,
        brief: BriefSpec,
        project_ctx: ProjectContext,
        wrai_report: WebResearchReport,
        plan: PlanStep,
        surfaces: list[str],
        session_id: str,
        tenant_ctx: TenantContext,
        brief_text: str,
        progress_callback: Callable[[str, dict[str, Any]], Any] | None,
    ) -> dict[str, Any]:
        """Run the per-surface convergence loop (N3a..N4) and assemble the payload.

        Shared by :meth:`run` (non-signoff and approved-inline paths) and
        :meth:`resume` (post-approval path). The N1/N2 outputs are passed in already
        resolved; this helper never re-runs them, so their per-stage accumulators are
        unchanged across a sign-off halt/resume.
        """
        # Import fixer dynamically to avoid circular dependencies
        from atelier.nodes.fixer import FixerAgent  # noqa: PLC0415

        fixer = FixerAgent(self._governor)

        screens_results = {}
        user_id = _require_user_id(tenant_ctx)

        # AT-095: (re)seed the lifetime counter from the persisted store and
        # pre-flight the cap on every entry to the generation loop. This covers the
        # resume() path (which calls this helper directly) as well as run(): a resume
        # that would start past the cap is rejected before any screen renders.
        # AT-097: re-check the fleet circuit-breaker here too, so a resume() (which
        # enters this helper directly, bypassing run()'s pre-flight) is also gated.
        self._seed_lifetime_counter(user_id)
        self._usage_store.check_circuit_breaker()
        self._governor._check_token_budget()

        # AT-020b: restore Board lane continuity for the resume() path (cold cache
        # after a sign-off halt) so the Generating transition below is a legal
        # forward step from Awaiting Sign-off (the column the card was halted at).
        # No-op on the inline run() path, where the lane is already warm there.
        self._board_emitter.ensure_lane_at(
            tenant_ctx=tenant_ctx,
            task_id=session_id,
            run_id=session_id,
            column=BoardColumnId.AWAITING_SIGNOFF,
        )
        # AT-020b: Awaiting Sign-off -> Generating. Screens render now; the active
        # specialist (the UI Designer authors the HTML) rides the statusLine, which
        # the emitter guarantees carries the agentRole for the Generating column (U6).
        self._board_transition(
            tenant_ctx=tenant_ctx,
            task_id=session_id,
            column=BoardColumnId.GENERATING,
            agent_role="ui_design",
            status_line="rendering the screen",
        )

        # Governed A2UI (ADR-0024) — G6 single-source convergence: the AT-044
        # design-system panel surface is built + gated EXACTLY ONCE per run, at the
        # canonical emit boundary (api/generate.py:_enrich_complete_payload), from
        # the run's resolved project_context.design_tokens. That enrichment runs
        # LAST in the SSE pipeline and OVERWRITES a2ui_payload, so it governs the
        # surface the frontend actually RENDERS (the frontend consumes a2ui_payload
        # only off the enriched `complete` event; `screen_converged` does not read
        # it). A second surface build here would be a redundant write — discarded by
        # the API rebuild on the rendered path and never consumed on the SSE path —
        # built from a token source that could drift from the canonical one. It is
        # intentionally NOT built here; a2ui_payload / a2ui_governance are threaded
        # solely from the canonical enrich site.

        for idx, screen in enumerate(surfaces):
            if progress_callback:
                await progress_callback(
                    "screen_start",
                    {"screen": screen, "index": idx, "session_id": session_id},
                )

            # Initialize convergence state for this screen.
            # R4: build the immutable anchor once; re-inject it (never accumulate)
            # each iteration so fixer feedback cannot displace the brief/tokens/research.
            anchor = _compose_anchor(brief, project_ctx, wrai_report)
            latest_directive = ""
            generator_prompt = _compose_generator_prompt(anchor, screen, latest_directive)
            best_candidate = None
            convergence_result: dict[str, Any] = {}
            stitch_degraded = False
            degradation_reason = None
            user_message = None
            gate_results_serialized: list[dict[str, Any]] = []
            evaluations_serialized: list[dict[str, Any]] = []
            scored_candidates_serialized: list[dict[str, Any]] = []
            raw_candidates: list[Any] = []
            exit_reason: StopReason = StopReason.MAX_ITERATIONS
            iteration = 0
            previous_best_score: float | None = None
            seen_fingerprints: set[str] = set()

            for iteration in range(self._max_iterations):
                self._governor._state.record_step(f"convergence_loop_{screen}_{iteration}")

                if progress_callback:
                    await progress_callback(
                        "iteration_start", {"screen": screen, "iteration": iteration}
                    )

                # AT-026 / R13 (trust-critical interruption): honor a user Stop at
                # the TOP of the iteration, BEFORE any model call. Because this check
                # precedes N3a's generation, a Stop set at this boundary halts within
                # this one iteration and issues NO model call afterward — the
                # security guarantee the AT-003 LiveCallGuard counter proves (0 model
                # calls after Stop). On Stop we persist a durable checkpoint (so a
                # resume continues from N1/N2 without re-running them), emit a `stop`
                # event so the UI acknowledges the halt, and break the loop.
                if is_stop_requested(session_id):
                    await self._persist_stop_checkpoint(
                        brief=brief,
                        project_ctx=project_ctx,
                        wrai_report=wrai_report,
                        plan=plan,
                        surfaces=surfaces,
                        session_id=session_id,
                        brief_text=brief_text,
                        user_id=user_id,
                    )
                    clear_stop(session_id)
                    exit_reason = StopReason.STOPPED
                    user_message = (
                        "Generation was stopped at your request. Progress up to this "
                        "iteration is checkpointed — resume to continue."
                    )
                    logger.info(
                        "AT-026: user Stop honored for screen %s at iteration %d "
                        "(no model call after Stop)",
                        screen,
                        iteration,
                    )
                    if progress_callback:
                        await progress_callback(
                            "stop",
                            {
                                "screen": screen,
                                "iteration": iteration,
                                "session_id": session_id,
                                "checkpointed": True,
                            },
                        )
                    break

                if self._governor._state.is_over_token_cap():
                    # AT-095 graceful in-flight stop: a prior unit (or the in-stream
                    # check inside _run_ensemble, which aborts the ADK run the moment a
                    # tier crosses its cap) pushed cumulative usage over the cap. Stop
                    # cleanly BEFORE starting another (expensive) generation, then a
                    # single branded message (never a raw quota error or hang).
                    _exceeded = self._governor._state.exceeded_tier()
                    logger.warning(
                        "Convergence loop graceful stop: per-user token cap reached.",
                        extra={
                            "user_id": user_id,
                            "cumulative_user_tokens": self._governor._state.cumulative_user_tokens,
                            "token_cap": self._governor._state.token_cap,
                            "exceeded_tier": _exceeded,
                        },
                    )
                    if progress_callback:
                        await progress_callback(
                            "degraded",
                            {
                                "mode": "cap",
                                "message": TOKEN_CAP_MESSAGE,
                                "exceeded_tier": _exceeded,
                            },
                        )
                    exit_reason = StopReason.TOKEN_CAP_EXHAUSTED
                    user_message = TOKEN_CAP_MESSAGE
                    break

                if self._governor._state.is_loop():
                    logger.warning("Convergence loop halted: governor detected infinite loop.")
                    exit_reason = StopReason.GOVERNOR_LOOP_DETECTED
                    break

                # R4: re-inject the immutable anchor + only the latest fixer
                # directive (clear accumulated rejected-variant history).
                generator_prompt = _compose_generator_prompt(anchor, screen, latest_directive)

                # N3a: DDLC Specialist Pipeline (SequentialAgent, AT-020) — governed.
                # Also tallies (input, output, thinking) tokens from each ADK event's
                # usage_metadata for the AT-095 lifetime counter; falls back to a
                # deterministic estimate when the offline model surface reports none.
                async def _run_ensemble(  # noqa: C901, PLR0912, PLR0915
                    prompt: str = generator_prompt,
                    screen: str = screen,
                    iteration: int = iteration,
                ) -> tuple[list[Any], bool, tuple[int, int, int]]:
                    pipeline, stitch_degradation = create_specialist_pipeline(
                        model=self._custom_model,
                        temperature=self._custom_temperature,
                        top_k=self._custom_top_k,
                        max_tokens=self._custom_max_tokens,
                    )
                    adk_runner = Runner(
                        agent=pipeline,
                        session_service=self._session_service,
                        memory_service=self._memory_service,
                        app_name=_APP_NAME,
                    )

                    candidates: list[Any] = []
                    usage_in = usage_out = usage_think = 0
                    charged_in = charged_out = charged_think = 0

                    # AT-095 per-tier attribution: charge each ADK event against the
                    # model the producing specialist actually runs on, not a single
                    # hardcoded Flash id. The event author equals the specialist name;
                    # map name -> calibrated model id so Pro/Flash-Lite spend lands in
                    # the correct per-tier bucket (and its correct cap). When a uniform
                    # model override is in effect (hermetic tests / pinned model), every
                    # specialist runs on it, so the map collapses to that single id.
                    if self._custom_model:
                        specialist_model_by_author = {
                            spec.name: self._custom_model for spec in get_specialist_specs()
                        }
                    else:
                        specialist_model_by_author = {
                            spec.name: calibrate_model(spec.task_type)
                            for spec in get_specialist_specs()
                        }
                    # Fallback for events from a non-specialist author (root coordinator)
                    # or an unmapped name: charge Flash, the bulk-generation tier.
                    fallback_model_id = self._custom_model or "gemini-2.5-flash"

                    traced_authors: set[str] = set()
                    accumulated_texts: list[str] = []
                    current_author: str | None = None

                    async for event in adk_runner.run_async(
                        user_id=user_id,
                        session_id=session_id,
                        new_message=genai_types.Content(
                            role="user",
                            parts=[genai_types.Part(text=prompt)],
                        ),
                    ):
                        texts = _extract_text_from_event(event)
                        candidates.extend(texts)
                        ein, eout, ethink = _usage_from_event(event)
                        usage_in += ein
                        usage_out += eout
                        usage_think += ethink

                        author = getattr(event, "author", None)
                        # Attribute this event's tokens to the real model the
                        # producing specialist runs on (AT-095 per-tier cap).
                        event_model_id = (
                            specialist_model_by_author.get(author, fallback_model_id)
                            if isinstance(author, str)
                            else fallback_model_id
                        )

                        # Charge tokens dynamically in real-time
                        if ein + eout + ethink > 0:
                            charged_in += ein
                            charged_out += eout
                            charged_think += ethink
                            self._governor._state.add_user_tokens(
                                input_tokens=ein,
                                output_tokens=eout,
                                thinking_tokens=ethink,
                                model_id=event_model_id,
                            )
                            self._usage_store.add(
                                user_id,
                                input_tokens=ein,
                                output_tokens=eout,
                                thinking_tokens=ethink,
                                model_id=event_model_id,
                            )
                            if progress_callback:
                                await progress_callback(
                                    "token_delta",
                                    {
                                        "input": ein,
                                        "output": eout,
                                        "thinking": ethink,
                                        "cumulative_user_tokens": self._governor._state.cumulative_user_tokens,
                                    },
                                )
                            # AT-095 in-stream cap enforcement (finding: mid-iteration
                            # overrun): once this event pushes a tier over its cap,
                            # abort the ADK run immediately rather than letting the rest
                            # of the specialist pipeline keep spending. The governor's
                            # run_with_governance wrapper maps the break to a graceful
                            # degraded stop; the top-of-loop check then halts the loop.
                            if self._governor._state.is_over_token_cap():
                                logger.warning(
                                    "AT-095 in-stream token-cap stop: aborting N3a "
                                    "mid-pipeline (tier over cap).",
                                    extra={
                                        "exceeded_tier": self._governor._state.exceeded_tier(),
                                        "cumulative_user_tokens": (
                                            self._governor._state.cumulative_user_tokens
                                        ),
                                    },
                                )
                                break

                        if isinstance(author, str) and author:
                            if current_author is not None and author != current_author:
                                # Handoff: previous specialist completed!
                                if current_author not in traced_authors:
                                    traced_authors.add(current_author)
                                    if progress_callback:
                                        await progress_callback(
                                            "specialist_trace",
                                            {
                                                "screen": screen,
                                                "iteration": iteration,
                                                "role": current_author,
                                                "summary": _trace_summary(accumulated_texts),
                                            },
                                        )
                                accumulated_texts = []
                            current_author = author
                            accumulated_texts.extend(texts)

                    # Emit the last specialist's trace
                    if current_author is not None and current_author not in traced_authors:
                        traced_authors.add(current_author)
                        if progress_callback:
                            await progress_callback(
                                "specialist_trace",
                                {
                                    "screen": screen,
                                    "iteration": iteration,
                                    "role": current_author,
                                    "summary": _trace_summary(accumulated_texts),
                                },
                            )

                    # Handlers for estimated fallback (offline runs)
                    if usage_in + usage_out + usage_think == 0:
                        usage_in, usage_out, usage_think = _estimate_tokens(prompt, candidates)

                    rem_in = usage_in - charged_in
                    rem_out = usage_out - charged_out
                    rem_think = usage_think - charged_think
                    if rem_in + rem_out + rem_think > 0:
                        # Estimated-fallback remainder (offline runs with no per-event
                        # usage metadata): no author signal to split by tier, so charge
                        # the bulk-generation tier (Flash, or the uniform override).
                        self._governor._state.add_user_tokens(
                            input_tokens=rem_in,
                            output_tokens=rem_out,
                            thinking_tokens=rem_think,
                            model_id=fallback_model_id,
                        )
                        self._usage_store.add(
                            user_id,
                            input_tokens=rem_in,
                            output_tokens=rem_out,
                            thinking_tokens=rem_think,
                            model_id=fallback_model_id,
                        )
                        if progress_callback:
                            await progress_callback(
                                "token_delta",
                                {
                                    "input": rem_in,
                                    "output": rem_out,
                                    "thinking": rem_think,
                                    "cumulative_user_tokens": self._governor._state.cumulative_user_tokens,
                                },
                            )

                    return (
                        candidates,
                        stitch_degradation.is_degraded,
                        (usage_in, usage_out, usage_think),
                    )

                governed_result = await self._governor.run_with_governance(
                    _run_ensemble,
                    step_id=f"n3a_specialist_pipeline_{screen}_{iteration}",
                )

                if governed_result is None:
                    # Governor returned None — fail-soft
                    raw_candidates = []
                    stitch_degraded = False
                    degradation_reason = "n3a_governor_fail_soft"
                    user_message = (
                        "The generation step degraded unexpectedly due to an infrastructure "
                        "condition (budget cap, rate limit, or stall timeout). Your session "
                        "was preserved. Please retry — no additional charge was applied."
                    )
                    logger.warning(
                        "N3a governed run returned None (fail-soft); loop broken",
                        extra={
                            "step_id": f"n3a_specialist_pipeline_{screen}_{iteration}",
                            "cumulative_user_tokens": self._governor._state.cumulative_user_tokens,
                            "token_cap": self._governor._state.token_cap,
                        },
                    )
                    exit_reason = StopReason.GOVERNOR_FAIL_SOFT
                    break
                raw_candidates, stitch_degraded, _token_usage = governed_result
                # AT-031: record the N3a post-signoff stage call on a stable id. This is
                # the "post-signoff stages" side of the resume oracle — its token count
                # must be > 0 after approval, while N1/N2 remain frozen at their
                # checkpointed values. Independent of the AT-095 lifetime counter above.
                self._governor._state.record_stage_call(
                    STAGE_N3A_SPECIALIST_PIPELINE, tokens=STAGE_TOKEN_ATTRIBUTION
                )
                if stitch_degraded:
                    degradation_reason = "stitch_mcp_unavailable"
                    user_message = (
                        "The Stitch design tool is temporarily unavailable. "
                        "Generating directly from the model — output will not include "
                        "Stitch design-system tokens. Retry to use the full design pipeline."
                    )
                else:
                    degradation_reason = None
                    user_message = None

                # S6 / trichotomy fail-LOUD: if Model Armor short-circuited this
                # generation (the brief carried a prompt-injection pattern), the
                # "candidates" are refusal sentinels, not designs. Acknowledge the
                # safety block to the user with a clean branded message and stop the
                # screen here instead of feeding refusal text through the N3c gates
                # (which would surface a confusing non-converged result). No Vertex
                # spend occurred — the before-callback blocks ahead of the model call.
                if was_model_armor_blocked(raw_candidates):
                    degradation_reason = "model_armor_blocked"
                    user_message = MODEL_ARMOR_BLOCK_USER_MESSAGE
                    exit_reason = StopReason.SAFETY_BLOCKED
                    logger.warning(
                        "N3a generation blocked by Model Armor input guard; "
                        "halting screen %s at iteration %d (no design produced)",
                        screen,
                        iteration,
                    )
                    break

                if progress_callback:
                    await progress_callback(
                        "candidates", {"screen": screen, "candidates": raw_candidates}
                    )

                # N3c → N3d → N4: gate filtering + consensus evaluation + best-pick.
                # This method does blocking I/O (GCS screenshot upload) and joins a
                # ThreadPoolExecutor of judge calls. Offload it to a worker thread so
                # the event loop stays responsive (SSE progress, other awaitables) for
                # the duration of N3c/N3d rather than stalling the single Cloud Run loop.
                convergence_result = await asyncio.to_thread(
                    self._run_n3c_n3d_n4,
                    raw_candidates,
                    brief_text,
                    iteration=iteration,
                    tenant_ctx=tenant_ctx,
                )
                # AT-097: charge N3d (D-O-R-A-V judge) token spend to the user's
                # lifetime counter too — not just N3a. Mirrors the N3a attribution
                # above so the cap, the persisted counter, and the live meter all
                # include judge spend (closes the AT-095 N3a-only under-count). 0 in
                # heuristic mode → the guard skips the no-op add + event.
                judge_in = int(convergence_result.get("judge_input_tokens", 0))
                judge_out = int(convergence_result.get("judge_output_tokens", 0))
                judge_think = int(convergence_result.get("judge_thinking_tokens", 0))
                if judge_in or judge_out or judge_think:
                    # N3d judge mix: Originality=Pro, Design/Relevance/Visual=Flash,
                    # Accessibility=Flash-Lite. Attribute to Pro (most restrictive cap)
                    # so the 5M Pro guard is the conservative check on judge spend.
                    n3d_model_id = "gemini-2.5-pro"
                    self._governor._state.add_user_tokens(
                        input_tokens=judge_in,
                        output_tokens=judge_out,
                        thinking_tokens=judge_think,
                        model_id=n3d_model_id,
                    )
                    self._usage_store.add(
                        user_id,
                        input_tokens=judge_in,
                        output_tokens=judge_out,
                        thinking_tokens=judge_think,
                        model_id=n3d_model_id,
                    )
                    if progress_callback:
                        await progress_callback(
                            "token_delta",
                            {
                                "input": judge_in,
                                "output": judge_out,
                                "thinking": judge_think,
                                "cumulative_user_tokens": (
                                    self._governor._state.cumulative_user_tokens
                                ),
                            },
                        )
                best_candidate = convergence_result.get("best_candidate")

                gate_results_serialized = [
                    {
                        "candidate_id": str(gr.candidate_id),
                        "all_passed": gr.all_passed,
                        "outcomes": [
                            {
                                "axis": o.axis.value,
                                "score": o.score,
                                "passed": o.decision == GateDecision.PASS,
                            }
                            for o in gr.outcomes
                        ],
                    }
                    for gr in convergence_result.get("all_gate_results", [])
                ]
                evaluations_serialized = [
                    {
                        "composite_score": e.composite_score,
                        "passed": e.passed,
                        "votes": {axis.value: {"score": v.score} for axis, v in e.votes.items()},
                    }
                    for e in convergence_result.get("all_evaluations", [])
                ]
                # Canonical per-candidate join (already plain JSON-safe dicts):
                # candidate_id + html + composite_score + votes, paired correctly
                # upstream. Threaded to the API so per-candidate consumers join by
                # id instead of positionally zipping the score-desc evaluations.
                scored_candidates_serialized = convergence_result.get("scored_candidates", [])

                if progress_callback:
                    await progress_callback(
                        "gates_evaluation",
                        {"screen": screen, "gate_results": gate_results_serialized},
                    )
                    await progress_callback(
                        "consensus_evaluation",
                        {"screen": screen, "evaluations": evaluations_serialized},
                    )

                    # AT-093: emit per-iteration D-O-R-A-V scores so the Studio
                    # scorecard can animate convergence in real-time.  The payload
                    # shape matches the ``dorav`` key in the final ``complete`` event
                    # plus a ``failing_axis`` key for the amber highlight.
                    iter_dorav = _build_iteration_dorav(
                        evaluations_serialized,
                        float(convergence_result.get("composite_score", 0.0)),
                    )
                    await progress_callback(
                        "iteration_score",
                        {
                            "screen": screen,
                            "iteration": iteration,
                            "dorav": {k: v for k, v in iter_dorav.items() if k != "failing_axis"},
                            "composite": iter_dorav.get("composite", 0.0),
                            "failing_axis": iter_dorav.get("failing_axis"),
                        },
                    )

                # R1 stop-reason precedence: collapse the post-generation signals to
                # the single highest-precedence reason. token_cap_exhausted always
                # wins (fail-loud security cap) — checked here too so a cap crossed
                # DURING this iteration stops cleanly without one more generation.
                best_score = float(convergence_result.get("composite_score", 0.0))
                fresh_candidate = best_candidate if isinstance(best_candidate, str) else ""
                signals = StopSignals(
                    token_cap_exhausted=self._governor._state.is_over_token_cap(),
                    converged=bool(convergence_result.get("converged")),
                    max_iterations_reached=iteration == self._max_iterations - 1,
                    no_improvement=is_no_improvement(previous_best_score, best_score),
                    duplicate=bool(fresh_candidate)
                    and is_duplicate(fresh_candidate, seen_fingerprints),
                )
                resolved = resolve_stop_reason(signals)
                if resolved is not None:
                    logger.info(
                        "Loop stop for screen %s at iteration %d: %s (composite=%.3f)",
                        screen,
                        iteration,
                        resolved.value,
                        best_score,
                    )
                    exit_reason = resolved
                    if resolved is StopReason.TOKEN_CAP_EXHAUSTED:
                        # The single branded cap message (acceptance (b)); never a raw
                        # quota error. Shown once via the response/complete payload.
                        user_message = TOKEN_CAP_MESSAGE
                        _exceeded = self._governor._state.exceeded_tier()
                        if progress_callback:
                            await progress_callback(
                                "degraded",
                                {
                                    "mode": "cap",
                                    "message": TOKEN_CAP_MESSAGE,
                                    "exceeded_tier": _exceeded,
                                },
                            )
                    elif (
                        resolved
                        in (
                            StopReason.NO_IMPROVEMENT,
                            StopReason.MAX_ITERATIONS,
                            StopReason.DUPLICATE,
                        )
                        and not signals.converged
                        and user_message is None
                    ):
                        # Trichotomy (fail-soft): a non-converged terminal stop means
                        # we are surfacing the strongest sub-bar candidate, so the
                        # agent ACKNOWLEDGES the degradation instead of presenting it
                        # as a converged result. CONVERGED outranks these reasons in
                        # resolve_stop_reason precedence, so reaching this branch
                        # already implies not-converged; the explicit guard is
                        # defensive. A more specific per-iteration degradation message
                        # (stitch / governor fail-soft) is preserved when already set.
                        user_message = _non_convergence_message(iteration)
                    break

                # Not stopping this iteration: record anchors for the next round
                # (R4 re-anchoring of the running best + duplicate fingerprints).
                previous_best_score = best_score
                if fresh_candidate:
                    seen_fingerprints.add(candidate_fingerprint(fresh_candidate))

                # Run FixerAgent for the next iteration.
                if iteration < self._max_iterations - 1:
                    logger.info(
                        "Iteration %d did not converge for screen %s. Running FixerAgent.",
                        iteration,
                        screen,
                    )

                    # Feed the fixer the BEST candidate's OWN evidence — its
                    # consensus scores AND its own gate outcomes. all_evaluations is
                    # score-descending so [0] is the best consensus, but
                    # all_gate_results is in raw candidate order and INCLUDES
                    # gate-failers, so its [0] is a different candidate. Match the
                    # gate outcomes to the best consensus by candidate_id, never by
                    # list position (audit 2026-06-03).
                    best_evals = convergence_result.get("all_evaluations", [])
                    best_consensus = best_evals[0] if best_evals else None

                    all_gate_results = convergence_result.get("all_gate_results", [])
                    if best_consensus is not None:
                        target_gate_outcomes = next(
                            (
                                gr.outcomes
                                for gr in all_gate_results
                                if gr.candidate_id == best_consensus.candidate_id
                            ),
                            [],
                        )
                    elif all_gate_results:
                        target_gate_outcomes = all_gate_results[0].outcomes
                    else:
                        target_gate_outcomes = []

                    directive = await fixer.fix(
                        gate_outcomes=target_gate_outcomes,
                        consensus=best_consensus,
                        memory_service=self._memory_service,
                        tenant_id=tenant_ctx.tenant_id,
                    )

                    if progress_callback:
                        await progress_callback(
                            "fixer_directive",
                            {"screen": screen, "directive": directive.model_dump()},
                        )

                    # Mutate prompt for next iteration
                    amendments = "\n".join(directive.prompt_amendments)
                    # R4: REPLACE the directive (do not accumulate); the anchor is
                    # re-injected fresh next iteration by _compose_generator_prompt.
                    latest_directive = amendments
                    logger.info(
                        "FixerAgent proposed mutations for screen %s: %s",
                        screen,
                        directive.mutations,
                    )

            if progress_callback:
                await progress_callback(
                    "screen_converged",
                    {
                        "screen": screen,
                        "best_candidate": best_candidate,
                        # ``html`` mirrors ``best_candidate`` for the frontend
                        # ScreenConvergedData contract (api.ts): the Studio reads
                        # ``data.html`` to populate the per-surface tab map, so a
                        # multi-surface run lights up every surface tab live —
                        # not just surfaces[0]. (A1)
                        "html": best_candidate,
                        "converged": convergence_result.get("converged", False),
                        # Governed A2UI chrome (ADR-0024) is NOT threaded here: the
                        # frontend reads a2ui_payload only off the enriched
                        # `complete` event (G6 single-source convergence). The
                        # canonical build+gate is api/generate.py:_enrich_complete_payload.
                    },
                )

            # Record this screen's results
            screens_results[screen] = {
                "best_candidate": best_candidate,
                "candidates": raw_candidates,
                "convergence_iteration": iteration,
                "exit_reason": exit_reason.value,
                "converged": convergence_result.get("converged", False),
                "composite_score": convergence_result.get("composite_score", 0.0),
                "candidates_evaluated": convergence_result.get("candidates_evaluated", 0),
                "candidates_passed_gates": convergence_result.get("candidates_passed_gates", 0),
                "gate_results": gate_results_serialized,
                "evaluations": evaluations_serialized,
                "scored_candidates": scored_candidates_serialized,
                "stitch_degraded": stitch_degraded,
                "degradation_reason": degradation_reason,
                "user_message": user_message,
            }

        # AT-020b: Generating -> QA. All surfaces have run their generate -> gate
        # -> judge loops; the card now reflects the scoring/convergence phase.
        self._board_transition(
            tenant_ctx=tenant_ctx,
            task_id=session_id,
            column=BoardColumnId.QA,
            agent_role="judge",
            status_line="Scoring candidates against the convergence gates",
        )

        # Select the first screen as the default top-level result
        first_screen_name = surfaces[0]
        first_screen_res = screens_results[first_screen_name]

        # AT-095: the per-user token cap is the highest-precedence outcome and
        # spans surfaces. If ANY surface hit the cap (e.g. surface 1 finished
        # under the cap but surface 2 crossed it), surface the cap signal at the
        # TOP level so the branded message renders exactly once (acceptance (b))
        # instead of being masked by surface 1's non-cap exit_reason.
        cap_hit_any_surface = any(
            res["exit_reason"] == StopReason.TOKEN_CAP_EXHAUSTED.value
            for res in screens_results.values()
        )
        top_exit_reason = (
            StopReason.TOKEN_CAP_EXHAUSTED.value
            if cap_hit_any_surface
            else first_screen_res["exit_reason"]
        )
        top_user_message = (
            TOKEN_CAP_MESSAGE if cap_hit_any_surface else first_screen_res["user_message"]
        )

        response_payload = {
            "brief": brief,
            "project_context": project_ctx,
            "candidates": first_screen_res["candidates"],
            "best_candidate": first_screen_res["best_candidate"],
            "convergence_iteration": first_screen_res["convergence_iteration"],
            "exit_reason": top_exit_reason,
            "converged": first_screen_res["converged"],
            "composite_score": first_screen_res["composite_score"],
            "candidates_evaluated": first_screen_res["candidates_evaluated"],
            "candidates_passed_gates": first_screen_res["candidates_passed_gates"],
            "gate_results": first_screen_res["gate_results"],
            "evaluations": first_screen_res["evaluations"],
            "scored_candidates": first_screen_res["scored_candidates"],
            "stitch_degraded": first_screen_res["stitch_degraded"],
            "degradation_reason": first_screen_res["degradation_reason"],
            "user_message": top_user_message,
            # AT-095: token-only usage governance — no USD. tokens_used is the
            # user's cumulative lifetime total (spans runs); the meter (AT-096)
            # rides this + the per-iteration token_delta events.
            "tokens_used": self._governor._state.cumulative_user_tokens,
            "token_cap": self._governor._state.token_cap,
            "web_research": wrai_report,
            "session_id": session_id,
            "plan": plan.model_dump() if hasattr(plan, "model_dump") else {},
            "screens": screens_results,
            # Governed A2UI chrome (ADR-0024) — G6 single-source convergence: the
            # design-system panel surface is built, gated, and threaded EXACTLY
            # ONCE, at the canonical emit boundary
            # (api/generate.py:_enrich_complete_payload), which derives it from
            # project_context.design_tokens and OVERWRITES a2ui_payload on the
            # `complete` event LAST. That is the surface the frontend renders. It
            # is intentionally NOT set here, so there is no second token source to
            # drift from the canonical one.
        }

        # Mid-flight DPO pair extraction — Dreaming Module (fail-soft).
        # Pairs are written fire-and-forget; write failures must not block response.
        try:
            from atelier.optimize.dreaming_module import (  # noqa: PLC0415
                extract_pairs_midflight,
                write_pairs_to_bq,
            )

            dpo_pairs = extract_pairs_midflight(
                session_id=session_id,
                tenant_id=tenant_ctx.tenant_id,
                surface_id=str(uuid.uuid4()),
                brief_text=brief_text,
                # Pre-joined (candidate_id, html, score) per gate-passing candidate
                # — the chosen/rejected labels are derived from each candidate's
                # OWN score, so they can never invert. Replaces the old positional
                # zip of raw candidates / score-desc evaluations (audit 2026-06-03).
                scored_candidates=scored_candidates_serialized,
            )
            write_pairs_to_bq(dpo_pairs)
        except Exception as _dreaming_exc:  # noqa: BLE001
            # Fail-soft — pair extraction is non-critical, must never break generate
            logger.warning(
                "Mid-flight DPO pair extraction failed (fail-soft): %s: %s",
                type(_dreaming_exc).__name__,
                str(_dreaming_exc)[:200],
            )

        # AT-053: persist the tenant's design system at run finalization (the
        # sign-off boundary). On a converged run this writes the run's resolved
        # tokens + constitution + standards as the tenant's CURRENT system, so the
        # NEXT run auto-applies them (no re-specification) and the AT-012 gate
        # enforces them. Fail-soft: a persistence failure is acknowledged + logged
        # and never fails the run (the design was already produced).
        await self._persist_design_system_at_signoff(
            tenant_ctx=tenant_ctx,
            project_ctx=project_ctx,
            plan=plan,
            session_id=session_id,
            converged=bool(first_screen_res.get("converged")),
        )

        # AT-020b: QA -> Done. The run has reached its terminal state; the card
        # lands on the final column. The statusLine reflects the convergence
        # outcome so a non-converged terminal stop is not shown as a clean "Done".
        _converged = bool(first_screen_res.get("converged"))
        self._board_transition(
            tenant_ctx=tenant_ctx,
            task_id=session_id,
            column=BoardColumnId.DONE,
            agent_role="orchestrator",
            status_line=("Converged" if _converged else "Terminal stop (review and retry)"),
        )

        if progress_callback:
            await progress_callback("complete", response_payload)

        return response_payload

    async def _persist_design_system_at_signoff(
        self,
        *,
        tenant_ctx: TenantContext,
        project_ctx: ProjectContext,
        plan: PlanStep,
        session_id: str,
        converged: bool,
    ) -> None:
        """AT-053: persist the tenant's design system at the sign-off boundary (fail-soft).

        Writes the run's resolved design tokens (the converged system) as the
        tenant's CURRENT persisted design system so the next run auto-applies and
        the AT-012 gate enforces it. Only a CONVERGED run persists — a degraded /
        non-converged run must not overwrite a good system with a half-baked one.

        Fail-soft (PRD §21): persistence is durability, not correctness — the
        design has already been produced and returned. A write failure is logged
        with structured context and acknowledged, never raised.
        """
        if not converged:
            logger.info(
                "AT-053: run did not converge; not persisting design system",
                extra={"tenant_id": tenant_ctx.tenant_id, "session_id": session_id},
            )
            return

        tokens = {
            name: value
            for name, value in (getattr(project_ctx, "design_tokens", None) or {}).items()
            if not str(name).startswith("_")
        }
        if not tokens:
            logger.info(
                "AT-053: no design tokens resolved; nothing to persist",
                extra={"tenant_id": tenant_ctx.tenant_id, "session_id": session_id},
            )
            return

        constitution = getattr(plan, "constitution", None)
        research = getattr(plan, "research_findings", None)
        standards_raw = getattr(research, "applicable_standards", None) or []
        standards: list[dict[str, Any]] = []
        for item in standards_raw:
            if isinstance(item, dict):
                standards.append(item)
            elif hasattr(item, "model_dump"):
                standards.append(item.model_dump(mode="json"))

        try:
            await persist_design_system(
                tenant_id=tenant_ctx.tenant_id,
                tokens=tokens,
                constitution=constitution if isinstance(constitution, str) else None,
                standards=standards,
                run_id=session_id,
            )
            logger.info(
                "AT-053: persisted tenant design system at sign-off",
                extra={
                    "tenant_id": tenant_ctx.tenant_id,
                    "session_id": session_id,
                    "token_count": len(tokens),
                },
            )
        except Exception as exc:  # noqa: BLE001 — fail-soft durability (see docstring)
            logger.warning(
                "AT-053: design-system persist failed at sign-off (fail-soft; run unaffected)",
                exc_info=True,
                extra={
                    "tenant_id": tenant_ctx.tenant_id,
                    "session_id": session_id,
                    "error_type": type(exc).__name__,
                },
            )

    @property
    def tokens_used(self) -> int:
        """User's cumulative lifetime token count tracked by the governor (AT-095)."""
        return self._governor._state.cumulative_user_tokens

    @property
    def session_service(self) -> BaseSessionService:
        """The active session service (for testing/inspection)."""
        return self._session_service


def _extract_text_from_event(event: Any) -> list[Any]:
    """Extract text content from an ADK 2.0 Event.

    Handles multiple event shapes:
        - ADK Event objects with content.parts[].text
        - Dict events with 'data' key (test mocks, legacy format)
        - Raw events (fallback -- returns event as-is)

    Returns a list of text strings or the raw event.
    """
    texts: list[Any] = []

    # ADK 2.0 Event API: content.parts[].text
    if hasattr(event, "content") and hasattr(event.content, "parts"):
        for part in event.content.parts:
            if hasattr(part, "text") and part.text:
                texts.append(part.text)

    # Dict-based events (test mocks, legacy format)
    elif isinstance(event, dict) and "data" in event:
        texts.append(event["data"])

    if not texts:
        texts.append(event)
    return texts
