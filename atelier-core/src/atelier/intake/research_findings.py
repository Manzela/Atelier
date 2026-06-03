"""AT-025 WRAI grounded research — synthesis into a frozen ResearchFindings.

The web-research report (N14, :mod:`atelier.intake.web_research`) and the
domain-scoped standards packs (:mod:`atelier.intake.standards_extractor`) are
synthesized here into a single immutable :class:`ResearchFindings` object,
frozen pre-SIGN-OFF and threaded into the generator anchor so its tokens, layout
hints, and applicable standards demonstrably seed downstream output.

Four guarantees this module enforces (PRD §6 R8, §3.5):

    1. Every finding and every applicable standard carries a citation + trust.
    2. An under-specified brief in a recognizable domain yields the domain's
       Tier-1 standards as proposed defaults — "what the user doesn't know they
       don't know" surfaced before scope-lock.
    3. A reference URL's palette / layout signal is extracted into a
       machine-readable :class:`ReferenceExtract` that the UI Designer + Token
       Generator consume via :meth:`ResearchFindings.seed_blob`.
    4. An injection attempt on the research path is acknowledged
       (``armor_verdict = BLOCKED``) and the grounding query is skipped, but
       ``available`` stays ``True`` — research-unavailable NEVER blocks intake
       (fail-soft, R8).

PRD Reference: §6.1 (WRAI), §6 R8 (Model-Armor-sanitized research), §3.5 (standards)
ADR Reference: 0011 (trust lattice + append-and-supersede), 0021 (standards packs)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, unquote, urlparse

from atelier.intake.standards_extractor import (
    ApplicableStandard,
    infer_domain,
    load_standards_pack,
)
from atelier.models.model_armor_callbacks import detect_injection

if TYPE_CHECKING:
    from atelier.intake.web_research import WebResearchReport

logger = logging.getLogger(__name__)

#: Hex color literal (``#rgb`` / ``#rrggbb`` / ``#rrggbbaa``). Used to mine a
#: palette signal out of a reference URL (query value or inline).
_HEX_COLOR_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")

#: Query keys a reference URL may carry to declare a palette / layout / type hint.
_PALETTE_KEYS = ("palette", "colors", "color")
_LAYOUT_KEYS = ("layout", "grid")
_TYPE_KEYS = ("type", "font", "typeface", "typography")

#: Cap on extracted palette entries — a reference seed is a hint, not a full
#: design system; the Token Generator owns the canonical palette.
_MAX_PALETTE = 8


class ArmorVerdict(StrEnum):
    """Outcome of the Model-Armor scan on the research path (R8).

    - ``CLEAN``: the brief carried no injection marker; grounding ran (or was
      simply empty) normally.
    - ``BLOCKED``: an injection imperative was detected; the grounding query was
      skipped and acknowledged. Intake still proceeds (``available`` stays True).
    - ``UNAVAILABLE``: grounding was attempted but failed/degraded (fail-soft);
      standards still apply, intake still proceeds.
    """

    CLEAN = "clean"
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class Finding:
    """A single trusted web-research finding, citation- and trust-bearing.

    Attributes:
        claim: A short summary of what the source contributes (title + snippet).
        citation_url: The source URL (never empty — un-cited results are dropped).
        source_domain: The source's domain (provenance at a glance).
        trust_score: Domain trust score in ``[0.0, 1.0]``.
    """

    claim: str
    citation_url: str
    source_domain: str
    trust_score: float


@dataclass(frozen=True)
class ReferenceExtract:
    """Lightweight design signal mined from the brief's reference artifacts.

    These are HINTS that seed the UI Designer + Token Generator (not a binding
    design system). Empty fields are valid — a brief with no reference URL yields
    an all-empty extract and the pipeline proceeds unchanged.

    Attributes:
        palette: Hex color literals extracted from reference URLs.
        type: Typography / typeface hints extracted from reference URLs.
        layout: A layout hint (e.g. ``"split"``, ``"grid"``) or ``None``.
        source_urls: The reference URLs the signal was mined from.
    """

    palette: list[str] = field(default_factory=list)
    type: list[str] = field(default_factory=list)
    layout: str | None = None
    source_urls: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ResearchFindings:
    """Immutable WRAI synthesis frozen pre-SIGN-OFF and threaded into the anchor.

    Attributes:
        queries: The research queries that were considered (empty when skipped).
        findings: Trusted web findings, each cited + trust-scored.
        applicable_standards: Domain Tier-1 standards (cross-cutting + overlay),
            each cited + trust-scored, sorted by trust descending.
        reference_extract: Palette / type / layout mined from reference URLs.
        armor_verdict: The research-path Model-Armor verdict (R8).
        available: Whether research is available to downstream consumers. ALWAYS
            ``True`` after synthesis — a blocked/unavailable research path is
            acknowledged via ``armor_verdict`` but never blocks intake (fail-soft).
        domain: The inferred project-type domain (or ``None``).
    """

    queries: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    applicable_standards: list[ApplicableStandard] = field(default_factory=list)
    reference_extract: ReferenceExtract = field(default_factory=ReferenceExtract)
    armor_verdict: ArmorVerdict = ArmorVerdict.CLEAN
    available: bool = True
    domain: str | None = None

    def proposed_defaults(self) -> list[ApplicableStandard]:
        """Standards strong enough to propose as silent defaults (cited provenance).

        Returns the domain-scoped Tier-1 standards (the cross-cutting substrate is
        always-on and not "proposed"), highest-trust first. AT-030 owns the gate
        decision logic that turns these into asks vs. silent-with-citation; this
        method only surfaces the candidates.
        """
        return [s for s in self.applicable_standards if s.domain != "global"]

    def seed_blob(self) -> str:
        """A deterministic, machine-readable seed the generator anchor injects.

        Carries the reference palette/layout/type and the top applicable standards
        so the UI Designer + Token Generator demonstrably consume the research
        (acceptance A). Sorted/ordered deterministically so re-injection is
        byte-stable across iterations (R4 anchor discipline).
        """
        ref = self.reference_extract
        lines = ["--- RESEARCH SEED (AT-025) ---"]
        if ref.palette:
            lines.append("reference_palette: " + ", ".join(ref.palette))
        if ref.type:
            lines.append("reference_type: " + ", ".join(ref.type))
        if ref.layout:
            lines.append(f"reference_layout: {ref.layout}")
        for std in self.applicable_standards[:8]:
            lines.append(f"standard[{std.standard_id}|trust={std.trust_score:.2f}]: {std.rule}")
        return "\n".join(lines)


def _extract_reference_signal(reference_urls: list[str]) -> ReferenceExtract:
    """Mine palette / type / layout hints from reference URLs (lightweight parse).

    A real (not hard-coded) heuristic: it reads declarative query params
    (``palette=``, ``layout=``, ``type=``) and any inline hex literals from the
    URL. This is intentionally cheap and offline — a full visual scrape of the
    reference site is a heavier, separately-gated capability; this seeds the
    palette/layout signal the generator anchor needs without a network call.

    Args:
        reference_urls: The brief's reference artifact URLs.

    Returns:
        A ReferenceExtract (all-empty when no signal is present).
    """
    palette: list[str] = []
    types: list[str] = []
    layout: str | None = None
    used_urls: list[str] = []

    for raw_url in reference_urls:
        if not isinstance(raw_url, str) or not raw_url.strip():
            continue
        # Parse BEFORE percent-decoding: a palette value carries ``%23`` for ``#``,
        # and decoding the whole URL first would let an unescaped ``#`` be read as
        # the fragment delimiter and silently drop every query param after it.
        parsed = urlparse(raw_url)
        if not (parsed.scheme and parsed.netloc):
            # Not a URL (e.g. a local file path reference) — skip; only URLs carry
            # the query-param design signal this lightweight parser reads.
            continue
        used_urls.append(raw_url)
        # parse_qs percent-decodes each value, so ``%23112233`` -> ``#112233``.
        params = parse_qs(parsed.query)

        for key in _PALETTE_KEYS:
            for value in params.get(key, []):
                palette.extend(_HEX_COLOR_RE.findall(value))
        # Inline hex anywhere in the fully-decoded URL (e.g. ...?bg=%23112233).
        palette.extend(_HEX_COLOR_RE.findall(unquote(raw_url)))

        for key in _TYPE_KEYS:
            types.extend(v.strip() for v in params.get(key, []) if v.strip())

        if layout is None:
            for key in _LAYOUT_KEYS:
                hits = [v.strip() for v in params.get(key, []) if v.strip()]
                if hits:
                    layout = hits[0]
                    break

    # De-duplicate while preserving order (palette/type), capped.
    palette = list(dict.fromkeys(c.lower() for c in palette))[:_MAX_PALETTE]
    types = list(dict.fromkeys(types))[:_MAX_PALETTE]
    return ReferenceExtract(
        palette=palette,
        type=types,
        layout=layout,
        source_urls=used_urls,
    )


def _findings_from_report(report: WebResearchReport) -> list[Finding]:
    """Project the trusted web results into citation-bearing Findings.

    Only ``top_results`` (tier-1 / tier-2) become findings, and only those with a
    real source URL — every finding MUST carry a citation + trust score
    (acceptance D). Denied / unknown-domain results never surface here.
    """
    findings: list[Finding] = []
    for r in report.top_results:
        citation = r.url or (f"https://{r.domain}" if r.domain else "")
        if not citation.startswith("http"):
            continue
        claim = (r.title or r.snippet or r.domain or "").strip()
        findings.append(
            Finding(
                claim=claim or r.domain,
                citation_url=citation,
                source_domain=r.domain,
                trust_score=r.trust_score,
            )
        )
    return findings


def synthesize_findings(
    brief_text: str,
    report: WebResearchReport,
    reference_urls: list[str],
) -> ResearchFindings:
    """Synchronous core of :func:`research_synthesizer` (no network I/O).

    Pure and offline: injection scan + standards load + reference parse. Exposed
    separately so the deterministic generator anchor (R4) can re-derive the same
    frozen findings — and thus the same byte-stable :meth:`ResearchFindings.seed_blob`
    — synchronously, including after an AT-031 sign-off halt/resume, without an
    extra checkpoint field and without an event loop.

    See :func:`research_synthesizer` for the full contract.
    """
    injection_hit = detect_injection(brief_text)
    if injection_hit is not None:
        # R8 fail-soft: acknowledge the block, drop the (untrusted) grounding
        # findings, but keep intake alive — standards still apply and the
        # pipeline proceeds. This mirrors the model-boundary guard's behavior.
        logger.warning(
            "AT-025 research path blocked an injection attempt (fail-soft): pattern=%s",
            injection_hit,
        )
        armor_verdict = ArmorVerdict.BLOCKED
        findings: list[Finding] = []
    else:
        armor_verdict = ArmorVerdict.CLEAN
        findings = _findings_from_report(report)

    domain = infer_domain(brief_text)
    applicable_standards = load_standards_pack(domain)
    reference_extract = _extract_reference_signal(reference_urls)

    return ResearchFindings(
        queries=list(dict.fromkeys(r.query for r in report.results)),
        findings=findings,
        applicable_standards=applicable_standards,
        reference_extract=reference_extract,
        armor_verdict=armor_verdict,
        available=True,
        domain=domain,
    )


async def research_synthesizer(
    brief_text: str,
    report: WebResearchReport,
    reference_urls: list[str],
) -> ResearchFindings:
    """Synthesize WRAI report + standards + reference signal into ResearchFindings.

    The single entry point the runner calls after N14. It:

      1. Scans the brief on the research path (R8): an injection imperative sets
         ``armor_verdict = BLOCKED`` and the grounding findings are dropped — but
         ``available`` stays ``True`` so intake is NOT blocked (fail-soft).
      2. Infers the project-type domain and loads its Tier-1 standards
         (cross-cutting substrate + domain overlay), each cited + trust-scored.
      3. Mines a palette / layout / type signal from the reference URLs.

    This function performs NO network I/O itself — the grounding queries already
    ran in :func:`atelier.intake.web_research.research_brief` (N14); the report is
    passed in. Standards loading and reference parsing are offline and cannot
    fail the pipeline (a missing pack degrades to the cross-cutting substrate).

    Args:
        brief_text: The raw brief text.
        report: The N14 web-research report (may be empty).
        reference_urls: The brief's reference artifact URLs.

    Returns:
        A frozen ResearchFindings. ``available`` is always ``True``.
    """
    return synthesize_findings(brief_text, report, reference_urls)
