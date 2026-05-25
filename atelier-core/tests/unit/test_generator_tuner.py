"""Unit tests for GeneratorTuner — mine_pairs surface and tune+promote surface."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from atelier.optimize.generator_tuner import (
    BQ_DPO_PAIRS_TABLE,
    KAPPA_PROMOTION_THRESHOLD,
    MIN_PAIRS_FOR_TUNING,
    BigQueryPairMiner,
    GeneratorTuner,
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


# ─── mine_pairs security guards ──────────────────────────────────────────────


@patch("atelier.optimize.generator_tuner.bigquery.Client")
def test_mine_pairs_raises_without_tenant_and_no_allow_flag(mock_bq_cls: MagicMock) -> None:
    """Security WARN fix: caller must opt-in to cross-tenant scan."""
    mock_bq_cls.return_value = MagicMock()
    miner = BigQueryPairMiner(project="atelier-build-2026")
    with pytest.raises(ValueError, match="allow_cross_tenant=True"):
        miner.mine_pairs()


@patch("atelier.optimize.generator_tuner.bigquery.Client")
def test_mine_pairs_raises_on_negative_limit(mock_bq_cls: MagicMock) -> None:
    """EC5: negative limit would produce invalid SQL LIMIT -1."""
    mock_bq_cls.return_value = MagicMock()
    miner = BigQueryPairMiner(project="atelier-build-2026")
    with pytest.raises(ValueError, match="limit must be >= 0"):
        miner.mine_pairs(tenant_id="tenant-abc", limit=-1)


@patch("atelier.optimize.generator_tuner.bigquery.Client")
def test_mine_pairs_skips_null_margin_rows(mock_bq_cls: MagicMock) -> None:
    """EC6: BQ NULL in numeric field must be skipped, not silently stored as None."""
    mock_client = MagicMock()
    mock_bq_cls.return_value = mock_client
    null_row = _make_bq_row(chosen_score=0.82, rejected_score=0.55)
    null_row.margin = None
    good_row = _make_bq_row(chosen_score=0.80, rejected_score=0.50, surface_id="surf-ok")
    mock_client.query.return_value.result.return_value = [null_row, good_row]

    miner = BigQueryPairMiner(project="atelier-build-2026")
    pairs = miner.mine_pairs(tenant_id="tenant-test")
    assert len(pairs) == 1
    assert pairs[0].surface_id == "surf-ok"


# ─── mine_pairs ───────────────────────────────────────────────────────────────


@patch("atelier.optimize.generator_tuner.bigquery.Client")
def test_mine_pairs_returns_list_of_preference_pairs(mock_bq_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_bq_cls.return_value = mock_client
    mock_client.query.return_value.result.return_value = [_make_bq_row()]

    miner = BigQueryPairMiner(project="atelier-build-2026")
    pairs = miner.mine_pairs(tenant_id="tenant-test", limit=10)

    assert len(pairs) == 1
    assert isinstance(pairs[0], PreferencePair)
    assert pairs[0].surface_id == "surf-001"


@patch("atelier.optimize.generator_tuner.bigquery.Client")
def test_mine_pairs_returns_empty_list_on_no_results(mock_bq_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_bq_cls.return_value = mock_client
    mock_client.query.return_value.result.return_value = []

    miner = BigQueryPairMiner(project="atelier-build-2026")
    pairs = miner.mine_pairs(tenant_id="tenant-test")
    assert pairs == []


@patch("atelier.optimize.generator_tuner.bigquery.Client")
def test_mine_pairs_sql_contains_limit(mock_bq_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_bq_cls.return_value = mock_client
    mock_client.query.return_value.result.return_value = []

    miner = BigQueryPairMiner(project="atelier-build-2026")
    miner.mine_pairs(tenant_id="tenant-test", limit=3)

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
    # allow_cross_tenant=True required now — explicit admin-path opt-in (Security WARN fix)
    miner.mine_pairs(allow_cross_tenant=True)

    query_sql = mock_client.query.call_args[0][0]
    assert "WHERE" not in query_sql.upper()


@patch("atelier.optimize.generator_tuner.bigquery.Client")
def test_mine_pairs_maps_row_fields_to_preference_pair(mock_bq_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_bq_cls.return_value = mock_client
    row = _make_bq_row(chosen_score=0.90, rejected_score=0.45)
    mock_client.query.return_value.result.return_value = [row]

    miner = BigQueryPairMiner(project="atelier-build-2026")
    pairs = miner.mine_pairs(tenant_id="tenant-test")

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
    pairs = miner.mine_pairs(tenant_id="tenant-test")

    assert len(pairs) == 3
    assert {p.surface_id for p in pairs} == {"surf-001", "surf-002", "surf-003"}


# ─── T14: GeneratorTuner.tune() ───────────────────────────────────────────────


def _make_pairs(n: int = 60) -> list[PreferencePair]:
    return [
        PreferencePair(
            prompt=f"prompt-{i}",
            chosen="chosen",
            rejected="rejected",
            margin=0.30,
            surface_id=f"surf-{i}",
            node_name="N3a.generator",
            iteration=0,
            chosen_score=0.82,
            rejected_score=0.52,
        )
        for i in range(n)
    ]


@patch("atelier.optimize.generator_tuner.storage.Client")
@patch("atelier.optimize.generator_tuner.bigquery.Client")
@patch("atelier.optimize.dpo_tuning_job.genai.Client")
def test_tune_raises_value_error_on_insufficient_pairs(
    mock_genai_cls: MagicMock, mock_bq_cls: MagicMock, mock_gcs_cls: MagicMock
) -> None:
    mock_genai_cls.return_value = MagicMock()
    mock_bq_cls.return_value = MagicMock()
    mock_gcs_cls.return_value = MagicMock()

    tuner = GeneratorTuner(project="atelier-build-2026")
    with pytest.raises(ValueError, match="Insufficient pairs"):
        tuner.tune(_make_pairs(n=MIN_PAIRS_FOR_TUNING - 1))


@patch("atelier.optimize.generator_tuner.storage.Client")
@patch("atelier.optimize.generator_tuner.bigquery.Client")
@patch("atelier.optimize.dpo_tuning_job.genai.Client")
def test_tune_submits_job_with_gcs_uri(
    mock_genai_cls: MagicMock, mock_bq_cls: MagicMock, mock_gcs_cls: MagicMock
) -> None:
    mock_job = MagicMock()
    mock_job.name = "projects/atelier-build-2026/locations/us-central1/tuningJobs/42"
    mock_genai_client = MagicMock()
    mock_genai_client.tunings.tune.return_value = mock_job
    mock_genai_cls.return_value = mock_genai_client
    mock_bq_cls.return_value = MagicMock()

    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_gcs_client = MagicMock()
    mock_gcs_client.bucket.return_value = mock_bucket
    mock_gcs_cls.return_value = mock_gcs_client

    tuner = GeneratorTuner(project="atelier-build-2026")
    job_name = tuner.tune(_make_pairs(n=MIN_PAIRS_FOR_TUNING))

    assert job_name == "projects/atelier-build-2026/locations/us-central1/tuningJobs/42"
    mock_blob.upload_from_filename.assert_called_once()


@patch("atelier.optimize.generator_tuner.storage.Client")
@patch("atelier.optimize.generator_tuner.bigquery.Client")
@patch("atelier.optimize.dpo_tuning_job.genai.Client")
def test_tune_returns_job_name_string(
    mock_genai_cls: MagicMock, mock_bq_cls: MagicMock, mock_gcs_cls: MagicMock
) -> None:
    mock_job = MagicMock()
    mock_job.name = "projects/.../tuningJobs/99"
    mock_genai_client = MagicMock()
    mock_genai_client.tunings.tune.return_value = mock_job
    mock_genai_cls.return_value = mock_genai_client
    mock_bq_cls.return_value = MagicMock()

    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = MagicMock()
    mock_gcs_client = MagicMock()
    mock_gcs_client.bucket.return_value = mock_bucket
    mock_gcs_cls.return_value = mock_gcs_client

    tuner = GeneratorTuner(project="atelier-build-2026")
    result = tuner.tune(_make_pairs(n=MIN_PAIRS_FOR_TUNING))
    assert isinstance(result, str)
    assert "tuningJobs" in result


# ─── T14: GeneratorTuner.evaluate_and_promote() ───────────────────────────────


@patch("atelier.optimize.generator_tuner.storage.Client")
@patch("atelier.optimize.generator_tuner.bigquery.Client")
@patch("atelier.optimize.dpo_tuning_job.genai.Client")
def test_evaluate_and_promote_raises_on_kappa_below_threshold(
    mock_genai_cls: MagicMock, mock_bq_cls: MagicMock, mock_gcs_cls: MagicMock
) -> None:
    mock_genai_client = MagicMock()
    mock_genai_client.tunings.get.return_value.state = "JOB_STATE_SUCCEEDED"
    mock_genai_cls.return_value = mock_genai_client
    mock_bq_cls.return_value = MagicMock()
    mock_gcs_cls.return_value = MagicMock()

    tuner = GeneratorTuner(project="atelier-build-2026")
    with pytest.raises(ValueError, match="Promotion blocked"):
        tuner.evaluate_and_promote(
            "projects/.../tuningJobs/42",
            achieved_kappa=KAPPA_PROMOTION_THRESHOLD - 0.01,
        )


@patch("atelier.optimize.generator_tuner.storage.Client")
@patch("atelier.optimize.generator_tuner.bigquery.Client")
@patch("atelier.optimize.dpo_tuning_job.genai.Client")
def test_evaluate_and_promote_raises_on_failed_job(
    mock_genai_cls: MagicMock, mock_bq_cls: MagicMock, mock_gcs_cls: MagicMock
) -> None:
    mock_genai_client = MagicMock()
    mock_genai_client.tunings.get.return_value.state = "JOB_STATE_FAILED"
    mock_genai_cls.return_value = mock_genai_client
    mock_bq_cls.return_value = MagicMock()
    mock_gcs_cls.return_value = MagicMock()

    tuner = GeneratorTuner(project="atelier-build-2026")
    with pytest.raises(RuntimeError, match="Tuning job failed"):
        tuner.evaluate_and_promote(
            "projects/.../tuningJobs/42",
            achieved_kappa=KAPPA_PROMOTION_THRESHOLD,
        )


@patch("atelier.optimize.generator_tuner.storage.Client")
@patch("atelier.optimize.generator_tuner.bigquery.Client")
@patch("atelier.optimize.dpo_tuning_job.genai.Client")
def test_evaluate_and_promote_returns_endpoint_on_success(
    mock_genai_cls: MagicMock, mock_bq_cls: MagicMock, mock_gcs_cls: MagicMock
) -> None:
    mock_job = MagicMock()
    mock_job.state = "JOB_STATE_SUCCEEDED"
    mock_job.tuned_model_info = MagicMock()
    mock_job.tuned_model_info.endpoint = (
        "projects/atelier-build-2026/locations/us-central1/endpoints/99"
    )
    mock_genai_client = MagicMock()
    mock_genai_client.tunings.get.return_value = mock_job
    mock_genai_cls.return_value = mock_genai_client
    mock_bq_cls.return_value = MagicMock()
    mock_gcs_cls.return_value = MagicMock()

    tuner = GeneratorTuner(project="atelier-build-2026")
    endpoint = tuner.evaluate_and_promote(
        "projects/.../tuningJobs/42",
        achieved_kappa=KAPPA_PROMOTION_THRESHOLD,
    )
    assert "endpoints/99" in endpoint


def test_kappa_promotion_threshold_is_correct() -> None:
    assert pytest.approx(0.70) == KAPPA_PROMOTION_THRESHOLD
