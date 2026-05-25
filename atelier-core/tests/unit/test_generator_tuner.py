"""Unit tests for GeneratorTuner T7 (mine_pairs) and T14 (tune + promote)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from atelier.optimize.generator_tuner import (
    BQ_DPO_PAIRS_TABLE,
    MIN_PAIRS_FOR_TUNING,
    BigQueryPairMiner,
    GeneratorTunerProtocol,
    PreferencePair,
)


def _make_bq_row(
    chosen_score: float = 0.82,
    rejected_score: float = 0.55,
    surface_id: str = "surf-001",
) -> MagicMock:
    row = MagicMock()
    row.surface_id = surface_id
    row.node_name = "N3a.generator"
    row.iteration = 0
    row.prompt = "Design a landing page"
    row.chosen_response = "<html>chosen</html>"
    row.rejected_response = "<html>rejected</html>"
    row.chosen_score = chosen_score
    row.rejected_score = rejected_score
    row.margin = chosen_score - rejected_score
    return row


# ─── Constants ────────────────────────────────────────────────────────────────


def test_bq_table_constant_points_to_correct_project() -> None:
    assert "atelier-build-2026" in BQ_DPO_PAIRS_TABLE


def test_bq_table_constant_points_to_dpo_pairs() -> None:
    assert "dpo_pairs" in BQ_DPO_PAIRS_TABLE


def test_min_pairs_constant_is_positive() -> None:
    assert MIN_PAIRS_FOR_TUNING > 0


# ─── PreferencePair ───────────────────────────────────────────────────────────


def test_preference_pair_fields() -> None:
    pair = PreferencePair(
        prompt="p",
        chosen="c",
        rejected="r",
        margin=0.27,
        surface_id="s",
        node_name="n",
        iteration=0,
        chosen_score=0.82,
        rejected_score=0.55,
    )
    assert pair.prompt == "p"
    assert pair.margin == pytest.approx(0.27)
    assert pair.chosen_score == pytest.approx(0.82)


def test_preference_pair_is_frozen() -> None:
    pair = PreferencePair(
        prompt="p",
        chosen="c",
        rejected="r",
        margin=0.3,
        surface_id="s",
        node_name="n",
        iteration=0,
        chosen_score=0.8,
        rejected_score=0.5,
    )
    with pytest.raises((AttributeError, TypeError)):
        pair.margin = 0.99  # type: ignore[misc]


# ─── Protocol structural check ────────────────────────────────────────────────


def test_bigquery_pair_miner_satisfies_protocol() -> None:
    with patch("atelier.optimize.generator_tuner.bigquery.Client"):
        miner = BigQueryPairMiner(project="atelier-build-2026")
    assert isinstance(miner, GeneratorTunerProtocol)


# ─── mine_pairs ───────────────────────────────────────────────────────────────


@patch("atelier.optimize.generator_tuner.bigquery.Client")
def test_mine_pairs_returns_list_of_preference_pairs(mock_bq_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_bq_cls.return_value = mock_client
    mock_client.query.return_value.result.return_value = [_make_bq_row()]

    miner = BigQueryPairMiner(project="atelier-build-2026")
    pairs = miner.mine_pairs(limit=10)

    assert len(pairs) == 1
    assert isinstance(pairs[0], PreferencePair)
    assert pairs[0].surface_id == "surf-001"


@patch("atelier.optimize.generator_tuner.bigquery.Client")
def test_mine_pairs_returns_empty_list_on_no_results(mock_bq_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_bq_cls.return_value = mock_client
    mock_client.query.return_value.result.return_value = []

    miner = BigQueryPairMiner(project="atelier-build-2026")
    pairs = miner.mine_pairs()
    assert pairs == []


@patch("atelier.optimize.generator_tuner.bigquery.Client")
def test_mine_pairs_sql_contains_limit(mock_bq_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_bq_cls.return_value = mock_client
    mock_client.query.return_value.result.return_value = []

    miner = BigQueryPairMiner(project="atelier-build-2026")
    miner.mine_pairs(limit=3)

    query_sql = mock_client.query.call_args[0][0]
    assert "LIMIT" in query_sql.upper()
    assert "3" in query_sql


@patch("atelier.optimize.generator_tuner.bigquery.Client")
def test_mine_pairs_enforces_tenant_id_predicate(mock_bq_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_bq_cls.return_value = mock_client
    mock_client.query.return_value.result.return_value = []

    miner = BigQueryPairMiner(project="atelier-build-2026")
    miner.mine_pairs(tenant_id="tenant-abc", limit=10)

    query_sql = mock_client.query.call_args[0][0]
    assert "tenant_id" in query_sql.lower()


@patch("atelier.optimize.generator_tuner.bigquery.Client")
def test_mine_pairs_uses_parameterized_query_for_tenant_id(mock_bq_cls: MagicMock) -> None:
    """tenant_id must use a query parameter, not string interpolation (SQL injection)."""
    mock_client = MagicMock()
    mock_bq_cls.return_value = mock_client
    mock_client.query.return_value.result.return_value = []

    miner = BigQueryPairMiner(project="atelier-build-2026")
    miner.mine_pairs(tenant_id="tenant-abc", limit=10)

    job_config = mock_client.query.call_args[1]["job_config"]
    param_names = [p.name for p in job_config.query_parameters]
    assert "tenant_id" in param_names


@patch("atelier.optimize.generator_tuner.bigquery.Client")
def test_mine_pairs_no_tenant_filter_when_not_provided(mock_bq_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_bq_cls.return_value = mock_client
    mock_client.query.return_value.result.return_value = []

    miner = BigQueryPairMiner(project="atelier-build-2026")
    miner.mine_pairs()

    query_sql = mock_client.query.call_args[0][0]
    assert "WHERE" not in query_sql.upper()


@patch("atelier.optimize.generator_tuner.bigquery.Client")
def test_mine_pairs_maps_row_fields_to_preference_pair(mock_bq_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_bq_cls.return_value = mock_client
    row = _make_bq_row(chosen_score=0.90, rejected_score=0.45)
    mock_client.query.return_value.result.return_value = [row]

    miner = BigQueryPairMiner(project="atelier-build-2026")
    pairs = miner.mine_pairs()

    assert pairs[0].chosen_score == pytest.approx(0.90)
    assert pairs[0].rejected_score == pytest.approx(0.45)
    assert pairs[0].margin == pytest.approx(0.45)
    assert pairs[0].prompt == "Design a landing page"
    assert pairs[0].chosen == "<html>chosen</html>"
    assert pairs[0].rejected == "<html>rejected</html>"


@patch("atelier.optimize.generator_tuner.bigquery.Client")
def test_mine_pairs_returns_multiple_pairs(mock_bq_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_bq_cls.return_value = mock_client
    mock_client.query.return_value.result.return_value = [
        _make_bq_row(surface_id="surf-001"),
        _make_bq_row(surface_id="surf-002"),
        _make_bq_row(surface_id="surf-003"),
    ]

    miner = BigQueryPairMiner(project="atelier-build-2026")
    pairs = miner.mine_pairs()

    assert len(pairs) == 3
    assert {p.surface_id for p in pairs} == {"surf-001", "surf-002", "surf-003"}
