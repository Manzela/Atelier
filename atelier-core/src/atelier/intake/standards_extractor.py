"""AT-025 standards extraction — domain-scoped applicable-standards loader.

Atelier ships a seed corpus of Tier-1 design/accessibility/performance standards
under ``atelier-core/standards/`` (relocated from ``docs/standards/`` at build
time). Each pack is a flat array of standard objects:

    { id, rule, check, threshold, source_url, source_title, trust, year, scope }

The ``cross-cutting`` pack (``scope: global``) is the always-on substrate every
project type inherits (WCAG 2.2, Core Web Vitals, DTCG). Domain packs
(``saas-dashboard``, ``marketing-landing``, ``ecommerce-checkout``,
``fintech``) are loaded *only* when the brief's inferred project-type matches,
so a checkout standard never fires on a marketing page.

WRAI lifecycle (ADR-0011): packs refresh by **append-and-supersede on ``id``** —
a refreshed row overwrites a stale one or adds a new id; rows are NEVER deleted.
:func:`load_standards_pack` implements that merge for the static packs plus any
runtime overlay WRAI surfaces.

PRD Reference: §3.5 (apply the domain's Tier-1 standards by default), R8 (research)
ADR Reference: 0011 (domain trust lattice + append-and-supersede), 0021 (standards packs)
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pack location + domain routing
# ---------------------------------------------------------------------------

#: Directory holding the relocated ``*.standards.json`` packs. ``parents[3]`` is
#: the ``atelier-core/`` package root (src/atelier/intake/standards_extractor.py
#: → src/atelier/intake → src/atelier → src → atelier-core is parents[3] from the
#: file's resolved path: .../intake/standards_extractor.py).
STANDARDS_DIR: Final[Path] = Path(__file__).resolve().parents[3] / "standards"

#: The always-on global substrate pack stem.
_CROSS_CUTTING_STEM: Final[str] = "cross-cutting"

#: Recognized project-type domains → their pack file stem. The pack's ``scope``
#: field may differ from the routing key (e.g. ``fintech`` routes to
#: ``fintech-trust.standards.json`` whose scope is ``fintech``).
_DOMAIN_PACKS: Final[dict[str, str]] = {
    "saas-dashboard": "saas-dashboard",
    "marketing-landing": "marketing-landing",
    "ecommerce-checkout": "ecommerce-checkout",
    "fintech": "fintech-trust",
}

#: Ordered keyword → domain routing for :func:`infer_domain`. First match wins,
#: so more specific signals (checkout) are listed before broader ones (landing).
#: Lowercased substring match against the brief text.
_DOMAIN_KEYWORDS: Final[tuple[tuple[str, str], ...]] = (
    ("checkout", "ecommerce-checkout"),
    ("ecommerce", "ecommerce-checkout"),
    ("e-commerce", "ecommerce-checkout"),
    ("cart", "ecommerce-checkout"),
    ("payment", "ecommerce-checkout"),
    ("dashboard", "saas-dashboard"),
    ("analytics", "saas-dashboard"),
    ("kpi", "saas-dashboard"),
    ("admin panel", "saas-dashboard"),
    ("fintech", "fintech"),
    ("banking", "fintech"),
    ("transfer money", "fintech"),
    ("balance", "fintech"),
    ("wallet", "fintech"),
    ("landing", "marketing-landing"),
    ("hero", "marketing-landing"),
    ("cta", "marketing-landing"),
    ("conversion", "marketing-landing"),
)


# ---------------------------------------------------------------------------
# ApplicableStandard — the normalized, citation-bearing record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ApplicableStandard:
    """A single Tier-1 standard applicable to a brief, with citation + trust.

    Attributes:
        standard_id: Stable identifier (e.g. ``"wcag-1.4.3"``). The merge key for
            append-and-supersede.
        name: Human-readable source title (``source_title`` in the pack).
        rule: The imperative rule text (<=140 chars in the seed corpus).
        citation_url: The authoritative source URL (``source_url`` in the pack).
            Every standard MUST carry one — a rule with no citation is dropped.
        trust_score: Trust seed in ``[0.0, 1.0]`` (1.0 = canonical body).
        domain: ``"global"`` for the cross-cutting substrate, else the pack scope.
        check: Enforcer routing — ``gate-axis:<...>`` | ``judge`` | ``manual``.
        threshold: Optional threshold string (e.g. ``"4.5:1 / 3:1"``).
        year: Publication/last-review year (provenance).
    """

    standard_id: str
    name: str
    rule: str
    citation_url: str
    trust_score: float
    domain: str
    check: str = "judge"
    threshold: str | None = None
    year: int | None = None


# ---------------------------------------------------------------------------
# Pack loading
# ---------------------------------------------------------------------------


def _coerce_standard(raw: dict[str, Any], pack_scope: str) -> ApplicableStandard | None:
    """Normalize one raw pack row into an ApplicableStandard.

    Returns ``None`` (and logs a structured warning) when the row is missing a
    citation URL or a stable id — a standard with no provenance is unusable and
    is dropped rather than surfaced as an un-cited default (acceptance: every
    standard carries a citation + trust score).
    """
    standard_id = str(raw.get("id", "")).strip()
    citation_url = str(raw.get("source_url", "")).strip()
    rule = str(raw.get("rule", "")).strip()
    if not standard_id or not citation_url or not rule:
        logger.warning(
            "standards_extractor: dropping un-citeable standard row in pack=%s "
            "(id=%r, has_url=%s, has_rule=%s)",
            pack_scope,
            standard_id,
            bool(citation_url),
            bool(rule),
        )
        return None

    raw_trust = raw.get("trust", 0.5)
    try:
        trust_score = max(0.0, min(1.0, float(raw_trust)))
    except (TypeError, ValueError):
        logger.warning(
            "standards_extractor: non-numeric trust %r for %s; defaulting to 0.5",
            raw_trust,
            standard_id,
        )
        trust_score = 0.5

    scope = str(raw.get("scope", pack_scope)).strip() or pack_scope
    year_raw = raw.get("year")
    year = int(year_raw) if isinstance(year_raw, (int, float)) else None

    return ApplicableStandard(
        standard_id=standard_id,
        name=str(raw.get("source_title", standard_id)),
        rule=rule,
        citation_url=citation_url,
        trust_score=trust_score,
        domain=scope,
        check=str(raw.get("check", "judge")),
        threshold=(str(raw["threshold"]) if raw.get("threshold") is not None else None),
        year=year,
    )


@lru_cache(maxsize=16)
def _load_pack(stem: str) -> tuple[ApplicableStandard, ...]:
    """Load and normalize one ``*.standards.json`` pack by file stem (cached).

    Fail-soft: a missing or malformed pack logs a warning and returns an empty
    tuple — a research gap must never crash intake (R8). The cache holds the
    immutable normalized tuple so repeated lookups across a run are free.
    """
    path = STANDARDS_DIR / f"{stem}.standards.json"
    try:
        with path.open(encoding="utf-8") as fh:
            payload = json.load(fh)
    except FileNotFoundError:
        logger.warning("standards_extractor: pack not found: %s (research degraded)", path)
        return ()
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(
            "standards_extractor: failed to load pack %s (%s: %s); research degraded",
            path,
            type(exc).__name__,
            exc,
        )
        return ()

    pack_scope = str(payload.get("scope", stem))
    rows = payload.get("standards", [])
    if not isinstance(rows, list):
        logger.warning("standards_extractor: pack %s 'standards' is not a list; skipping", path)
        return ()

    coerced = [
        std
        for row in rows
        if isinstance(row, dict)
        for std in (_coerce_standard(row, pack_scope),)
        if std is not None
    ]
    return tuple(coerced)


def _merge_supersede(
    base: Iterable[ApplicableStandard],
    overlay: Iterable[ApplicableStandard],
) -> list[ApplicableStandard]:
    """Append-and-supersede on ``standard_id`` (ADR-0011 WRAI lifecycle).

    An overlay row with the same ``standard_id`` as a base row REPLACES it; a new
    id is appended. No row is ever deleted. Insertion order is preserved (base
    first, then new overlay ids) before the caller sorts by trust.
    """
    merged: dict[str, ApplicableStandard] = {}
    for std in base:
        merged[std.standard_id] = std
    for std in overlay:
        # Supersede in place (preserve position) when the id already exists,
        # else append at the end.
        merged[std.standard_id] = std
    return list(merged.values())


def infer_domain(brief_text: str) -> str | None:
    """Infer the project-type domain from brief text, or ``None`` if unrecognized.

    First keyword match wins (more specific signals are ordered first). An
    unrecognized brief returns ``None`` so only the cross-cutting substrate
    loads — Atelier never fabricates a domain it cannot justify from the text.

    Args:
        brief_text: Raw brief text.

    Returns:
        A domain key in :data:`_DOMAIN_PACKS`, or ``None``.
    """
    lowered = brief_text.lower()
    for keyword, domain in _DOMAIN_KEYWORDS:
        if keyword in lowered:
            return domain
    return None


def load_standards_pack(
    domain: str | None,
    *,
    extra_overlay: Sequence[ApplicableStandard] | None = None,
) -> list[ApplicableStandard]:
    """Load the applicable standards for a domain: cross-cutting + domain overlay.

    The global cross-cutting substrate is ALWAYS loaded first. When ``domain``
    matches a known pack, that pack is merged on top via append-and-supersede on
    ``standard_id``. An unrecognized ``domain`` (or ``None``) yields the
    cross-cutting substrate only. A runtime ``extra_overlay`` (e.g. rows WRAI
    surfaced this run) is merged last, so a fresh citation supersedes a seed row.

    The result is sorted by ``trust_score`` descending so the planner surfaces
    the strongest-provenance defaults first.

    Args:
        domain: Project-type key (see :data:`_DOMAIN_PACKS`) or ``None``.
        extra_overlay: Optional runtime standards to merge last (append-and-supersede).

    Returns:
        Standards sorted by trust descending; every row carries a citation + trust.
    """
    standards: list[ApplicableStandard] = list(_load_pack(_CROSS_CUTTING_STEM))

    pack_stem = _DOMAIN_PACKS.get(domain) if domain else None
    if pack_stem is not None:
        standards = _merge_supersede(standards, _load_pack(pack_stem))
    elif domain:
        logger.info("standards_extractor: unrecognized domain %r; cross-cutting only", domain)

    if extra_overlay:
        standards = _merge_supersede(standards, extra_overlay)

    standards.sort(key=lambda s: s.trust_score, reverse=True)
    return standards
