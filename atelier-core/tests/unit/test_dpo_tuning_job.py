"""Unit tests for DPO tuning job (T6, ADR 0028).

API shape verified via Step-1 discovery (google-genai 1.75.0, 2026-05-25):
- CreateTuningJobConfig(method, beta, epoch_count, adapter_size, validation_dataset)
- training_dataset=TuningDataset(gcs_uri=...) passed to client.tunings.tune()
- NO preference_optimization_spec field on CreateTuningJobConfig.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from atelier.optimize.dpo_tuning_job import (
    DPO_ADAPTER_SIZE,
    DPO_BASE_MODEL,
    DPO_BETA,
    DPO_EPOCH_COUNT,
    DPO_GCS_PREFIX,
    DpoTuningJob,
    TuningJobState,
)
from google.genai import types as genai_types


def _make_mock_job(state: str = "JOB_STATE_RUNNING") -> MagicMock:
    job = MagicMock()
    job.name = "projects/atelier-build-2026/locations/us-central1/tuningJobs/123"
    job.state = state
    job.tuned_model_info = None
    return job


def test_constants_match_adr_0028() -> None:
    assert pytest.approx(0.1) == DPO_BETA
    assert DPO_EPOCH_COUNT == 3
    assert str(DPO_ADAPTER_SIZE) == "AdapterSize.ADAPTER_SIZE_FOUR"


def test_dpo_base_model_matches_adr_0028() -> None:
    """ADR 0028 locks the DPO source model to a Vertex-AI-DPO-supported tier.

    Drift here silently fails at runtime: Vertex AI preference tuning only
    accepts Gemini 2.5 Flash / Flash-Lite. Any other model id will be rejected
    by the tuning service after a job has already been submitted, wasting both
    a job-quota slot and operator attention. This test pins the constant to the
    locked value so a code review can spot drift before a release.
    """
    assert DPO_BASE_MODEL == "gemini-2.5-flash-001"


def test_gcs_prefix_targets_correct_project() -> None:
    assert "atelier-build-2026" in DPO_GCS_PREFIX


def test_tuning_job_state_values_cover_all_vertex_states() -> None:
    assert TuningJobState.RUNNING == "JOB_STATE_RUNNING"
    assert TuningJobState.SUCCEEDED == "JOB_STATE_SUCCEEDED"
    assert TuningJobState.FAILED == "JOB_STATE_FAILED"
    assert TuningJobState.UNKNOWN == "JOB_STATE_UNSPECIFIED"


@patch("atelier.optimize.dpo_tuning_job.genai.Client")
def test_submit_calls_tune_with_training_dataset_gcs_uri(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.tunings.tune.return_value = _make_mock_job()

    job_obj = DpoTuningJob(project="atelier-build-2026")
    job_obj.submit(
        gcs_pairs_uri="gs://atelier-build-2026-dpo-pairs/tuner-pairs/2026-05-25/120000/pairs.jsonl"
    )

    call_kwargs = mock_client.tunings.tune.call_args.kwargs
    assert "training_dataset" in call_kwargs
    assert call_kwargs["training_dataset"].gcs_uri == (
        "gs://atelier-build-2026-dpo-pairs/tuner-pairs/2026-05-25/120000/pairs.jsonl"
    )


@patch("atelier.optimize.dpo_tuning_job.genai.Client")
def test_submit_config_uses_preference_tuning_method(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.tunings.tune.return_value = _make_mock_job()

    job_obj = DpoTuningJob(project="atelier-build-2026")
    job_obj.submit(gcs_pairs_uri="gs://bucket/train.jsonl")

    call_kwargs = mock_client.tunings.tune.call_args.kwargs
    config = call_kwargs["config"]
    assert config.method == genai_types.TuningMethod.PREFERENCE_TUNING


@patch("atelier.optimize.dpo_tuning_job.genai.Client")
def test_submit_config_beta_epoch_adapter_match_adr(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.tunings.tune.return_value = _make_mock_job()

    job_obj = DpoTuningJob(project="atelier-build-2026")
    job_obj.submit(gcs_pairs_uri="gs://bucket/train.jsonl")

    config = mock_client.tunings.tune.call_args.kwargs["config"]
    assert config.beta == pytest.approx(DPO_BETA)
    assert config.epoch_count == DPO_EPOCH_COUNT
    assert config.adapter_size == DPO_ADAPTER_SIZE


@patch("atelier.optimize.dpo_tuning_job.genai.Client")
def test_submit_no_validation_dataset_when_not_provided(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.tunings.tune.return_value = _make_mock_job()

    job_obj = DpoTuningJob(project="atelier-build-2026")
    job_obj.submit(gcs_pairs_uri="gs://bucket/train.jsonl")

    config = mock_client.tunings.tune.call_args.kwargs["config"]
    assert config.validation_dataset is None


@patch("atelier.optimize.dpo_tuning_job.genai.Client")
def test_submit_passes_validation_dataset_when_provided(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.tunings.tune.return_value = _make_mock_job()

    job_obj = DpoTuningJob(project="atelier-build-2026")
    job_obj.submit(
        gcs_pairs_uri="gs://bucket/train.jsonl",
        validation_gcs_uri="gs://bucket/val.jsonl",
    )

    config = mock_client.tunings.tune.call_args.kwargs["config"]
    assert config.validation_dataset is not None
    assert config.validation_dataset.gcs_uri == "gs://bucket/val.jsonl"


@patch("atelier.optimize.dpo_tuning_job.genai.Client")
def test_submit_raises_runtime_error_on_tune_exception(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.tunings.tune.side_effect = Exception("network error")

    job_obj = DpoTuningJob(project="atelier-build-2026")
    with pytest.raises(RuntimeError, match="DPO tuning job submit failed"):
        job_obj.submit(gcs_pairs_uri="gs://bucket/train.jsonl")


@patch("atelier.optimize.dpo_tuning_job.genai.Client")
def test_get_state_returns_correct_enum(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.tunings.get.return_value = _make_mock_job(state="JOB_STATE_SUCCEEDED")

    job_obj = DpoTuningJob(project="atelier-build-2026")
    state = job_obj.get_state(job_name="projects/.../tuningJobs/123")
    assert state == TuningJobState.SUCCEEDED


@patch("atelier.optimize.dpo_tuning_job.genai.Client")
def test_get_state_returns_unknown_for_unrecognised_state(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_job = MagicMock()
    mock_job.state = "JOB_STATE_SOME_FUTURE_STATE"
    mock_client.tunings.get.return_value = mock_job

    job_obj = DpoTuningJob(project="atelier-build-2026")
    state = job_obj.get_state(job_name="projects/.../tuningJobs/123")
    assert state == TuningJobState.UNKNOWN


@patch("atelier.optimize.dpo_tuning_job.genai.Client")
def test_get_tuned_model_name_raises_if_not_succeeded(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.tunings.get.return_value = _make_mock_job(state="JOB_STATE_RUNNING")

    job_obj = DpoTuningJob(project="atelier-build-2026")
    with pytest.raises(RuntimeError, match="not yet succeeded"):
        job_obj.get_tuned_model_name("projects/.../tuningJobs/123")


@patch("atelier.optimize.dpo_tuning_job.genai.Client")
def test_get_tuned_model_name_raises_if_endpoint_missing(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    job = _make_mock_job(state="JOB_STATE_SUCCEEDED")
    job.tuned_model_info = MagicMock()
    job.tuned_model_info.endpoint = ""
    mock_client.tunings.get.return_value = job

    job_obj = DpoTuningJob(project="atelier-build-2026")
    with pytest.raises(RuntimeError, match="no endpoint found"):
        job_obj.get_tuned_model_name("projects/.../tuningJobs/123")


@patch("atelier.optimize.dpo_tuning_job.genai.Client")
def test_get_tuned_model_name_returns_endpoint_on_success(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    job = _make_mock_job(state="JOB_STATE_SUCCEEDED")
    job.tuned_model_info = MagicMock()
    job.tuned_model_info.endpoint = (
        "projects/atelier-build-2026/locations/us-central1/endpoints/456"
    )
    mock_client.tunings.get.return_value = job

    job_obj = DpoTuningJob(project="atelier-build-2026")
    endpoint = job_obj.get_tuned_model_name("projects/.../tuningJobs/123")
    assert "endpoints/456" in endpoint


@patch("atelier.optimize.dpo_tuning_job.genai.Client")
def test_submit_raises_if_job_name_is_none(mock_client_cls: MagicMock) -> None:
    """EC1: SDK returning job.name=None must fail-loud, not propagate None silently."""
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    bad_job = _make_mock_job()
    bad_job.name = None
    mock_client.tunings.tune.return_value = bad_job

    job_obj = DpoTuningJob(project="atelier-build-2026")
    with pytest.raises(RuntimeError, match=r"job\.name is empty or None"):
        job_obj.submit(gcs_pairs_uri="gs://bucket/train.jsonl")
