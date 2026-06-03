"""Unit tests for AT-025 standards extraction — standards_extractor.py.

Coverage:
    load_standards_pack(domain)
        - cross-cutting (global) substrate is ALWAYS loaded
        - a recognized domain overlays its pack on top of cross-cutting
        - append-and-supersede on ``id``: a domain row with the same id as a
          cross-cutting row REPLACES it (never duplicates, never deletes)
        - an unrecognized domain yields the cross-cutting substrate only
        - every returned standard carries a citation_url + trust_score
        - results are sorted by trust_score descending
    infer_domain(brief_text)
        - recognizable-domain keyword routing (dashboard, checkout, fintech, landing)
        - unknown text routes to None (cross-cutting only)
"""

from __future__ import annotations

from atelier.intake.standards_extractor import (
    ApplicableStandard,
    infer_domain,
    load_standards_pack,
)

# ---------------------------------------------------------------------------
# load_standards_pack — cross-cutting substrate
# ---------------------------------------------------------------------------


def test_cross_cutting_always_loaded_for_unknown_domain() -> None:
    """An unrecognized domain still returns the global cross-cutting substrate."""
    standards = load_standards_pack("not-a-real-domain")
    assert len(standards) >= 3
    # All rows are from the global substrate when the domain is unknown.
    assert all(s.domain == "global" for s in standards)


def test_known_domain_overlays_cross_cutting() -> None:
    """A recognized domain returns cross-cutting PLUS the domain overlay."""
    cross_only = load_standards_pack("not-a-real-domain")
    dashboard = load_standards_pack("saas-dashboard")
    # The overlay strictly adds domain-scoped rows on top of the substrate.
    assert len(dashboard) > len(cross_only)
    domains = {s.domain for s in dashboard}
    assert "global" in domains
    assert "saas-dashboard" in domains


def test_every_standard_has_citation_and_trust_score() -> None:
    """Every extracted standard carries a citation_url AND a trust_score."""
    for domain in ("saas-dashboard", "marketing-landing", "ecommerce-checkout", "fintech"):
        standards = load_standards_pack(domain)
        assert standards, f"no standards for {domain}"
        for s in standards:
            assert isinstance(s, ApplicableStandard)
            assert s.citation_url.startswith("http"), f"{s.standard_id} missing citation_url"
            assert 0.0 <= s.trust_score <= 1.0, f"{s.standard_id} trust out of range"
            assert s.standard_id
            assert s.rule


def test_results_sorted_by_trust_descending() -> None:
    """Standards are returned highest-trust-first so the planner sees the strongest defaults."""
    standards = load_standards_pack("ecommerce-checkout")
    scores = [s.trust_score for s in standards]
    assert scores == sorted(scores, reverse=True)


def test_recognized_domain_yields_at_least_three_applicable_standards() -> None:
    """ACCEPTANCE: an under-specified brief in a recognizable domain yields >=3 standards."""
    for domain in ("saas-dashboard", "marketing-landing", "ecommerce-checkout", "fintech"):
        standards = load_standards_pack(domain)
        domain_specific = [s for s in standards if s.domain != "global"]
        assert len(domain_specific) >= 3, f"{domain} produced <3 domain standards"


# ---------------------------------------------------------------------------
# append-and-supersede on id (ADR-0011 WRAI lifecycle)
# ---------------------------------------------------------------------------


def test_append_and_supersede_on_id() -> None:
    """A domain row sharing an id with a cross-cutting row SUPERSEDES it (no duplicate)."""
    standards = load_standards_pack(
        "saas-dashboard",
        extra_overlay=[
            ApplicableStandard(
                standard_id="dash-card-cap",  # already present in saas-dashboard pack
                name="Superseded card cap",
                rule="Cap to 4 cards (superseded by WRAI refresh).",
                citation_url="https://example.org/refresh",
                trust_score=0.99,
                domain="saas-dashboard",
            )
        ],
    )
    matches = [s for s in standards if s.standard_id == "dash-card-cap"]
    assert len(matches) == 1, "append-and-supersede must not duplicate an id"
    assert matches[0].rule.startswith("Cap to 4 cards"), "overlay row must win"


def test_supersede_never_deletes_other_rows() -> None:
    """Superseding one id leaves every other id intact (never delete)."""
    base = load_standards_pack("saas-dashboard")
    base_ids = {s.standard_id for s in base}
    overlaid = load_standards_pack(
        "saas-dashboard",
        extra_overlay=[
            ApplicableStandard(
                standard_id="dash-card-cap",
                name="x",
                rule="y",
                citation_url="https://example.org/x",
                trust_score=0.5,
                domain="saas-dashboard",
            )
        ],
    )
    overlaid_ids = {s.standard_id for s in overlaid}
    assert base_ids == overlaid_ids


# ---------------------------------------------------------------------------
# infer_domain — keyword routing
# ---------------------------------------------------------------------------


def test_infer_domain_dashboard() -> None:
    assert (
        infer_domain("Build an analytics dashboard with KPI cards and charts") == "saas-dashboard"
    )


def test_infer_domain_checkout() -> None:
    assert infer_domain("A checkout page for our ecommerce store cart") == "ecommerce-checkout"


def test_infer_domain_landing() -> None:
    assert infer_domain("A marketing landing page with a hero and CTA") == "marketing-landing"


def test_infer_domain_fintech() -> None:
    assert infer_domain("A banking app screen to transfer money and show balance") == "fintech"


def test_infer_domain_unknown_returns_none() -> None:
    assert infer_domain("make the button slightly more rounded") is None
