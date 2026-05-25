"""Unit tests for N14 WRAI — web_research.py.

Coverage:
    score_result()               — all trust tiers: 1, 2, 0 (unknown), -1 (denied)
                                   domain extraction from scoring_url
    generate_research_queries()  — count clamping, key term extraction,
                                   query format, empty brief handling
    research_brief()             — parallel gather, denied_count increment,
                                   top_results filtering, fail-soft on error
    _search_with_grounding()     — fail-soft when API raises, empty response
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from atelier.intake.web_research import (
    DEFAULT_QUERY_COUNT,
    MAX_QUERY_COUNT,
    DomainTrustConfig,
    WebResearchReport,
    WebResearchResult,
    _search_with_grounding,
    generate_research_queries,
    research_brief,
    score_result,
)

# ---------------------------------------------------------------------------
# Trust config fixture
# ---------------------------------------------------------------------------


def _config(
    tier1: set[str] | None = None,
    tier2: set[str] | None = None,
    deny: set[str] | None = None,
) -> DomainTrustConfig:
    return DomainTrustConfig(
        tier_1_domains=frozenset(tier1 or set()),
        tier_2_domains=frozenset(tier2 or set()),
        deny_domains=frozenset(deny or set()),
        tier_1_min_score=0.6,
        tier_2_min_score=0.8,
    )


# ---------------------------------------------------------------------------
# score_result — trust tier assignment
# ---------------------------------------------------------------------------


def test_score_result_tier1_domain_gets_trust_tier_1() -> None:
    cfg = _config(tier1={"material.io"})
    r = score_result("https://material.io/design", "T", "S", "q", cfg)
    assert r.trust_tier == 1
    assert r.trust_score >= 0.9


def test_score_result_tier2_domain_gets_trust_tier_2() -> None:
    cfg = _config(tier2={"medium.com"})
    r = score_result("https://medium.com/article", "T", "S", "q", cfg)
    assert r.trust_tier == 2
    assert r.trust_score >= 0.7


def test_score_result_unknown_domain_gets_trust_tier_0() -> None:
    cfg = _config()  # no entries
    r = score_result("https://randomsite.example.com", "T", "S", "q", cfg)
    assert r.trust_tier == 0
    assert r.trust_score == pytest.approx(0.5)


def test_score_result_denied_domain_gets_trust_tier_minus_1() -> None:
    cfg = _config(deny={"spam.example.com"})
    r = score_result("https://spam.example.com/bad", "T", "S", "q", cfg)
    assert r.trust_tier == -1
    assert r.trust_score == pytest.approx(0.0)


def test_score_result_denied_is_not_none() -> None:
    """score_result must ALWAYS return a WebResearchResult — never None.

    Callers that previously checked `if result is not None` relied on the old
    contract; after the denied_count fix, score_result always returns an object.
    """
    cfg = _config(deny={"denied.com"})
    r = score_result("https://denied.com", "T", "S", "q", cfg)
    assert isinstance(r, WebResearchResult)


def test_score_result_www_stripped_from_domain() -> None:
    cfg = _config(tier1={"example.com"})
    r = score_result("https://www.example.com/page", "T", "S", "q", cfg)
    assert r.trust_tier == 1  # www. stripped → example.com is in tier1


def test_score_result_populates_all_fields() -> None:
    cfg = _config()
    r = score_result("https://foo.com/path", "Title", "Snippet", "my query", cfg)
    assert r.url == "https://foo.com/path"
    assert r.title == "Title"
    assert r.snippet == "Snippet"
    assert r.query == "my query"
    assert r.domain == "foo.com"


def test_score_result_tier1_min_score_respected() -> None:
    cfg = _config(tier1={"great.com"})
    cfg = DomainTrustConfig(
        tier_1_domains=frozenset({"great.com"}),
        tier_2_domains=frozenset(),
        deny_domains=frozenset(),
        tier_1_min_score=0.95,  # very high floor
        tier_2_min_score=0.8,
    )
    r = score_result("https://great.com", "T", "S", "q", cfg)
    assert r.trust_score >= 0.95


# ---------------------------------------------------------------------------
# generate_research_queries
# ---------------------------------------------------------------------------


def test_generate_research_queries_count_respects_default() -> None:
    queries = generate_research_queries("Build a SaaS dashboard")
    assert len(queries) == DEFAULT_QUERY_COUNT


def test_generate_research_queries_count_clamped_at_max() -> None:
    queries = generate_research_queries("brief", count=100)
    assert len(queries) <= MAX_QUERY_COUNT


def test_generate_research_queries_count_exact() -> None:
    queries = generate_research_queries("brief", count=3)
    assert len(queries) == 3


def test_generate_research_queries_returns_strings() -> None:
    queries = generate_research_queries("design a landing page")
    assert all(isinstance(q, str) and len(q) > 0 for q in queries)


def test_generate_research_queries_empty_brief_has_fallback() -> None:
    """Empty brief must not crash — fallback to generic terms."""
    queries = generate_research_queries("")
    assert len(queries) >= 1
    assert all(isinstance(q, str) for q in queries)


def test_generate_research_queries_extracts_key_terms() -> None:
    """Key terms from brief appear in at least one generated query."""
    queries = generate_research_queries("enterprise dashboard analytics platform")
    combined = " ".join(queries).lower()
    # At least one of these terms from the brief should appear in the queries
    assert any(term in combined for term in ("enterprise", "dashboard", "analytics", "platform"))


def test_generate_research_queries_no_stop_words_dominate() -> None:
    """Queries should not just be stop words repeated."""
    queries = generate_research_queries("the a an is are for and or")
    for q in queries:
        # Each query should have some actual content beyond fallback
        assert len(q) > 5


# ---------------------------------------------------------------------------
# research_brief — integration (mocked _search_with_grounding)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_research_brief_counts_denied_results() -> None:
    """denied_count must increment for trust_tier=-1 results.

    This was previously dead code (denied was never reachable). After P1-1
    fix, score_result() returns trust_tier=-1 for denied domains and
    _search_with_grounding() includes them in the returned list.
    """
    denied_result = WebResearchResult(
        query="q",
        url="https://spam.com",
        domain="spam.com",
        title="T",
        snippet="S",
        trust_tier=-1,
        trust_score=0.0,
    )
    allowed_result = WebResearchResult(
        query="q",
        url="https://good.com",
        domain="good.com",
        title="T",
        snippet="S",
        trust_tier=1,
        trust_score=0.9,
    )

    # Each call to _search_with_grounding returns 1 denied + 1 allowed
    async def _fake_search(query: str, trust_config: Any) -> list[WebResearchResult]:
        return [denied_result, allowed_result]

    with patch(
        "atelier.intake.web_research._search_with_grounding",
        side_effect=_fake_search,
    ):
        report = await research_brief("brief text", query_count=2)

    # 2 queries x 1 denied each = 2 denied
    assert report.denied_count == 2
    # 2 queries x 1 allowed each = 2 allowed
    assert len(report.results) == 2


@pytest.mark.anyio
async def test_research_brief_denied_not_in_top_results() -> None:
    """top_results must exclude trust_tier=-1 denied results."""
    denied = WebResearchResult(
        query="q",
        url="https://deny.com",
        domain="deny.com",
        title="T",
        snippet="S",
        trust_tier=-1,
        trust_score=0.0,
    )
    allowed = WebResearchResult(
        query="q",
        url="https://good.com",
        domain="good.com",
        title="T",
        snippet="S",
        trust_tier=1,
        trust_score=0.9,
    )

    async def _fake(q: str, tc: Any) -> list[WebResearchResult]:
        return [denied, allowed]

    with patch("atelier.intake.web_research._search_with_grounding", side_effect=_fake):
        report = await research_brief("brief", query_count=1)

    assert all(r.trust_tier > 0 for r in report.top_results)
    assert len(report.top_results) == 1


@pytest.mark.anyio
async def test_research_brief_fail_soft_when_all_queries_fail() -> None:
    """If every grounding call fails, research_brief still returns an empty report."""

    async def _fail(q: str, tc: Any) -> list[WebResearchResult]:
        return []  # simulates the fail-soft path (empty on exception)

    with patch("atelier.intake.web_research._search_with_grounding", side_effect=_fail):
        report = await research_brief("brief", query_count=3)

    assert isinstance(report, WebResearchReport)
    assert len(report.results) == 0
    assert report.denied_count == 0
    assert report.total_queries == 3


@pytest.mark.anyio
async def test_research_brief_results_sorted_by_trust_score_descending() -> None:
    low = WebResearchResult(
        query="q",
        url="https://a.com",
        domain="a.com",
        title="T",
        snippet="S",
        trust_tier=0,
        trust_score=0.5,
    )
    high = WebResearchResult(
        query="q",
        url="https://b.com",
        domain="b.com",
        title="T",
        snippet="S",
        trust_tier=1,
        trust_score=0.9,
    )

    async def _mixed(q: str, tc: Any) -> list[WebResearchResult]:
        return [low, high]  # low before high — should be sorted

    with patch("atelier.intake.web_research._search_with_grounding", side_effect=_mixed):
        report = await research_brief("brief", query_count=1)

    scores = [r.trust_score for r in report.results]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.anyio
async def test_research_brief_trust_config_fallback_on_missing_yaml() -> None:
    """When research-trust.yaml is absent, research_brief uses empty config (no crash)."""

    async def _empty(q: str, tc: Any) -> list[WebResearchResult]:
        return []

    with (
        patch("atelier.intake.web_research._search_with_grounding", side_effect=_empty),
        patch("atelier.intake.web_research.load_trust_config", side_effect=FileNotFoundError),
    ):
        report = await research_brief("brief", query_count=1)

    assert isinstance(report, WebResearchReport)


# ---------------------------------------------------------------------------
# _search_with_grounding — fail-soft
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_search_with_grounding_fail_soft_on_api_error() -> None:
    """API error must be swallowed and return [] (fail-soft, PRD §21)."""
    cfg = _config()
    with patch("atelier.intake.web_research._get_genai_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = RuntimeError("quota exceeded")
        mock_client_fn.return_value = mock_client

        result = await _search_with_grounding("test query", cfg)

    assert result == []


@pytest.mark.anyio
async def test_search_with_grounding_returns_empty_on_no_candidates() -> None:
    """Response with no candidates must return empty list."""
    cfg = _config()
    with (
        patch("atelier.intake.web_research._get_genai_client") as mock_client_fn,
        patch("asyncio.to_thread") as mock_thread,
    ):
        mock_client_fn.return_value = MagicMock()
        mock_response = MagicMock()
        mock_response.candidates = []
        mock_thread.return_value = mock_response

        result = await _search_with_grounding("test", cfg)

    assert result == []
