"""DPO tuning job — google-genai PREFERENCE_TUNING migration (T6, ADR 0028).

Replaces the deprecated vertexai.tuning.sft surface with google.genai
CreateTuningJobConfig(method=TuningMethod.PREFERENCE_TUNING).

Verified API shape (google-genai 1.75.0, 2026-05-25 Step-1 discovery):
  - CreateTuningJobConfig fields: method, beta, epoch_count, adapter_size,
    validation_dataset (TuningValidationDataset), tuned_model_display_name.
  - NO preference_optimization_spec field on CreateTuningJobConfig.
  - training_dataset=TuningDataset(gcs_uri=...) passed to client.tunings.tune().
  - validation_dataset=TuningValidationDataset(gcs_uri=...) set on config.

Failure trichotomy:
  - submit(): fail-loud (non-retriable; bad GCS URI → callers must fix before retry)
  - get_state(): fail-soft (unknown state → UNKNOWN sentinel, caller decides retry)
  - get_tuned_model_name(): fail-loud on not-yet-succeeded state
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any, Final

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# ADR 0028 lock. Vertex AI preference tuning supports only Gemini 2.5 Flash / Flash-Lite
# (per docs.cloud.google.com/vertex-ai/generative-ai/docs/models/tune-gemini-overview).
# Pro tier is SFT-only; using a non-DPO-capable base model fails at job submission.
DPO_BASE_MODEL: Final[str] = "gemini-2.5-flash-001"
DPO_BETA: Final[float] = 0.1
DPO_EPOCH_COUNT: Final[int] = 3
DPO_ADAPTER_SIZE: Final[types.AdapterSize] = types.AdapterSize.ADAPTER_SIZE_FOUR
DPO_GCS_PREFIX: Final[str] = "gs://atelier-build-2026-dpo-pairs"
DPO_LOCATION: Final[str] = "us-central1"


class TuningJobState(StrEnum):
    RUNNING = "JOB_STATE_RUNNING"
    SUCCEEDED = "JOB_STATE_SUCCEEDED"
    FAILED = "JOB_STATE_FAILED"
    CANCELLED = "JOB_STATE_CANCELLED"
    QUEUED = "JOB_STATE_QUEUED"
    PENDING = "JOB_STATE_PENDING"
    UNKNOWN = "JOB_STATE_UNSPECIFIED"


class DpoTuningJob:
    """Submit and poll DPO preference-optimization tuning jobs on Vertex AI.

    Fail-soft on unknown state strings — maps them to TuningJobState.UNKNOWN
    rather than raising, so the caller decides whether to retry.
    """

    def __init__(self, project: str, location: str = DPO_LOCATION) -> None:
        self._client = genai.Client(vertexai=True, project=project, location=location)
        self._project = project

    def submit(
        self,
        *,
        gcs_pairs_uri: str,
        display_name: str = "atelier-dpo",
        validation_gcs_uri: str | None = None,
    ) -> Any:
        """Submit a DPO preference-optimization tuning job.

        Args:
            gcs_pairs_uri: GCS URI to JSONL with preference pairs.
                Each line: {"prompt": "...", "chosen": "...", "rejected": "..."}
            display_name: Human-readable name for the tuned model.
            validation_gcs_uri: Optional GCS URI to JSONL validation set.

        Returns:
            The submitted TuningJob object (google.genai).

        Raises:
            RuntimeError: Fail-loud if submit call fails (non-retriable).
        """
        validation_dataset: types.TuningValidationDataset | None = None
        if validation_gcs_uri is not None:
            validation_dataset = types.TuningValidationDataset(gcs_uri=validation_gcs_uri)

        config = types.CreateTuningJobConfig(
            method=types.TuningMethod.PREFERENCE_TUNING,
            beta=DPO_BETA,
            epoch_count=DPO_EPOCH_COUNT,
            adapter_size=DPO_ADAPTER_SIZE,
            tuned_model_display_name=display_name,
            validation_dataset=validation_dataset,
        )
        logger.info(
            "Submitting DPO tuning job",
            extra={
                "base_model": DPO_BASE_MODEL,
                "gcs_pairs_uri": gcs_pairs_uri,
                "beta": DPO_BETA,
                "epoch_count": DPO_EPOCH_COUNT,
            },
        )
        try:
            job = self._client.tunings.tune(
                base_model=DPO_BASE_MODEL,
                training_dataset=types.TuningDataset(gcs_uri=gcs_pairs_uri),
                config=config,
            )
        except Exception as exc:
            msg = f"DPO tuning job submit failed (non-retriable): {exc}"
            logger.exception(msg, extra={"gcs_pairs_uri": gcs_pairs_uri})
            raise RuntimeError(msg) from exc
        # EC1: guard against SDK returning an object with name=None.
        if not job.name:
            msg = "DPO tuning job submitted but job.name is empty or None — cannot track job."
            raise RuntimeError(msg)
        logger.info("DPO tuning job submitted", extra={"job_name": job.name})
        return job

    def get_state(self, *, job_name: str) -> TuningJobState:
        """Poll the current state of a tuning job.

        Fail-soft: unknown state strings map to TuningJobState.UNKNOWN.
        """
        job = self._client.tunings.get(name=job_name)
        raw_state: str = str(getattr(job, "state", "JOB_STATE_UNSPECIFIED"))
        try:
            return TuningJobState(raw_state)
        except ValueError:
            logger.warning("Unknown tuning job state", extra={"raw_state": raw_state})
            return TuningJobState.UNKNOWN

    def get_tuned_model_name(self, job_name: str) -> str:
        """Return the endpoint resource name for a completed tuning job.

        Raises:
            RuntimeError: Fail-loud if the job has not yet succeeded.
        """
        state = self.get_state(job_name=job_name)
        if state != TuningJobState.SUCCEEDED:
            msg = f"Tuning job not yet succeeded (state={state.value}): {job_name}"
            raise RuntimeError(msg)
        job = self._client.tunings.get(name=job_name)
        info = getattr(job, "tuned_model_info", None)
        endpoint: str = getattr(info, "endpoint", "") if info else ""
        if not endpoint:
            msg = f"Tuning job succeeded but no endpoint found: {job_name}"
            raise RuntimeError(msg)
        return endpoint
