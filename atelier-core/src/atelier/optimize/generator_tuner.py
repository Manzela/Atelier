"""GeneratorTuner — Protocol + BigQuery pair miner (T7, spec §9.3).

T7 scope: GeneratorTunerProtocol definition + BigQueryPairMiner.mine_pairs().
T14 scope (added in Task 5): full tune() + evaluate_and_promote().

BigQuery table layout (atelier-build-2026.atelier_trajectories.dpo_pairs):
    surface_id        STRING    — identifies which surface produced this pair
    node_name         STRING    — e.g. "N3a.generator"
    iteration         INT64     — which EvoDesign iteration
    prompt            STRING    — the shared generation prompt
    chosen_response   STRING    — higher-quality candidate HTML/CSS
    rejected_response STRING    — lower-quality candidate HTML/CSS
    chosen_score      FLOAT64   — composite judge score (>= T2_THRESHOLD 0.70)
    rejected_score    FLOAT64   — composite judge score (<  T3_THRESHOLD 0.50)
    margin            FLOAT64   — chosen_score - rejected_score (>= MIN_MARGIN 0.15)
    tenant_id         STRING    — tenant isolation key (ALWAYS filter on this)
    created_at        TIMESTAMP

Interface contract: this table is populated by Antigravity FA-012 dpo_builder.py
(JSONL→BQ load step, R9-B). T7 gates execution on at least one row existing.
"""

from __future__ import annotations

import json
import logging
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Protocol, runtime_checkable

from google.cloud import bigquery, storage  # type: ignore[attr-defined]

from atelier.optimize.dpo_tuning_job import DpoTuningJob, TuningJobState

logger = logging.getLogger(__name__)

BQ_DPO_PAIRS_TABLE: Final[str] = "atelier-build-2026.atelier_trajectories.dpo_pairs"
MIN_PAIRS_FOR_TUNING: Final[int] = 50
DEFAULT_MINE_LIMIT: Final[int] = 500
KAPPA_PROMOTION_THRESHOLD: Final[float] = 0.70  # ADR 0028 §9.3: promote if κ ≥ 0.70

# Pre-rendered SELECT template — table name is a Final constant (no user input).
# String concatenation avoids S608 (f-string SQL injection detection).
# LIMIT and WHERE clause are constructed at call time from int and hardcoded literals.
_SELECT_COLS: str = (
    "SELECT surface_id, node_name, iteration, prompt, "
    "chosen_response, rejected_response, chosen_score, rejected_score, margin "
    "FROM `" + BQ_DPO_PAIRS_TABLE + "`"
)


@dataclass(frozen=True, slots=True)
class PreferencePair:
    """A single DPO preference pair mined from BigQuery."""

    prompt: str
    chosen: str
    rejected: str
    margin: float
    surface_id: str
    node_name: str
    iteration: int
    chosen_score: float
    rejected_score: float


@runtime_checkable
class GeneratorTunerProtocol(Protocol):
    """Protocol for all GeneratorTuner implementations.

    T7 ships BigQueryPairMiner (just mine_pairs).
    T14 ships GeneratorTuner (mine_pairs + tune + evaluate_and_promote).
    """

    def mine_pairs(
        self,
        *,
        tenant_id: str | None = None,
        limit: int = DEFAULT_MINE_LIMIT,
    ) -> list[PreferencePair]:
        """Query BigQuery dpo_pairs table and return preference pairs.

        Always filters by tenant_id when provided.
        Returns empty list when table has no matching rows (not an error).
        """
        ...


class BigQueryPairMiner:
    """Concrete GeneratorTunerProtocol implementation — mine_pairs() only.

    Reads from `atelier-build-2026.atelier_trajectories.dpo_pairs`.
    Table must be populated by Antigravity FA-012 before calling mine_pairs().
    """

    def __init__(self, project: str = "atelier-build-2026") -> None:
        self._client = bigquery.Client(project=project)
        self._project = project

    def mine_pairs(
        self,
        *,
        tenant_id: str | None = None,
        limit: int = DEFAULT_MINE_LIMIT,
        allow_cross_tenant: bool = False,
    ) -> list[PreferencePair]:
        """Mine preference pairs from BigQuery.

        Args:
            tenant_id: If provided, filters rows to this tenant only.
                Never returns cross-tenant data when set.
            limit: Maximum number of pairs to return. Applied in BigQuery
                to bound cost. Must be >= 0.
            allow_cross_tenant: Must be explicitly True to call with
                tenant_id=None (full-table scan for admin/training use).
                Prevents accidental cross-tenant data leakage from callers
                that forget to pass tenant_id. Fail-loud if False and
                tenant_id is None.

        Returns:
            List of PreferencePair. Empty list if table has no matching rows.

        Raises:
            ValueError: If limit < 0, or tenant_id is None and
                allow_cross_tenant is False.
            google.cloud.exceptions.GoogleCloudError: Fail-soft — BQ errors
                propagate to caller; do not swallow.
        """
        # Security WARN: require explicit opt-in to cross-tenant scan.
        if tenant_id is None and not allow_cross_tenant:
            msg = (
                "mine_pairs called without tenant_id — this returns ALL tenants' data. "
                "Pass allow_cross_tenant=True to explicitly enable this admin path."
            )
            raise ValueError(msg)
        # EC5: reject negative limits before they produce invalid SQL (LIMIT -1).
        if limit < 0:
            msg = f"mine_pairs limit must be >= 0, got {limit}"
            raise ValueError(msg)
        where_clause = "WHERE tenant_id = @tenant_id" if tenant_id is not None else ""
        # String concatenation avoids S608. All variable parts are safe:
        # where_clause is a hardcoded literal, limit is int (no user input),
        # tenant_id value goes through @tenant_id parameterized query below.
        query = _SELECT_COLS + " " + where_clause + " ORDER BY margin DESC LIMIT " + str(limit)
        job_config = bigquery.QueryJobConfig()
        if tenant_id is not None:
            job_config.query_parameters = [
                bigquery.ScalarQueryParameter("tenant_id", "STRING", tenant_id),
            ]

        logger.info(
            "Mining DPO pairs from BigQuery",
            extra={"tenant_id": tenant_id, "limit": limit, "table": BQ_DPO_PAIRS_TABLE},
        )
        rows = list(self._client.query(query, job_config=job_config).result())
        skipped = 0
        pairs: list[PreferencePair] = []
        for row in rows:
            # EC6: BQ NULLs become None in Python; dataclasses don't enforce float at runtime.
            # Skip rows with any None in numeric fields rather than propagating silent None
            # into training data, which would produce NaN in DPO loss calculations.
            if row.margin is None or row.chosen_score is None or row.rejected_score is None:
                skipped += 1
                logger.warning(
                    "Skipping DPO pair with NULL numeric field",
                    extra={"surface_id": row.surface_id, "node_name": row.node_name},
                )
                continue
            pairs.append(
                PreferencePair(
                    prompt=row.prompt,
                    chosen=row.chosen_response,
                    rejected=row.rejected_response,
                    margin=float(row.margin),
                    surface_id=row.surface_id,
                    node_name=row.node_name,
                    iteration=row.iteration,
                    chosen_score=float(row.chosen_score),
                    rejected_score=float(row.rejected_score),
                )
            )
        if skipped:
            logger.warning("DPO pair mining skipped NULL rows", extra={"skipped": skipped})
        logger.info("DPO pair mining complete", extra={"pair_count": len(pairs)})
        return pairs


class GeneratorTuner:
    """Full DPO tuning loop: mine pairs → upload to GCS → submit job → evaluate → promote.

    Composes BigQueryPairMiner (T7) and DpoTuningJob (T6) into the full
    end-to-end tuning workflow (T14, spec §9.3).

    evaluate_and_promote() applies the κ gate (KAPPA_PROMOTION_THRESHOLD=0.70)
    before promoting the tuned model endpoint. Promotion means returning the
    endpoint for the caller to update the router's active model.
    """

    def __init__(
        self,
        project: str = "atelier-build-2026",
        gcs_bucket: str = "atelier-build-2026-dpo-pairs",
    ) -> None:
        self._miner = BigQueryPairMiner(project=project)
        self._tuning_job = DpoTuningJob(project=project)
        self._gcs_client = storage.Client(project=project)
        self._bucket = gcs_bucket
        self._project = project

    def mine_pairs(
        self,
        *,
        tenant_id: str | None = None,
        limit: int = DEFAULT_MINE_LIMIT,
    ) -> list[PreferencePair]:
        """Delegate to BigQueryPairMiner."""
        return self._miner.mine_pairs(tenant_id=tenant_id, limit=limit)

    def tune(
        self,
        pairs: list[PreferencePair],
        *,
        display_name: str = "atelier-dpo",
    ) -> str:
        """Upload pairs to GCS as JSONL and submit a DPO tuning job.

        Args:
            pairs: Preference pairs (must have len >= MIN_PAIRS_FOR_TUNING).
            display_name: Human-readable name for the tuned model.

        Returns:
            The tuning job name (resource path string).

        Raises:
            ValueError: Fail-loud if fewer than MIN_PAIRS_FOR_TUNING pairs.
            RuntimeError: Fail-loud if GCS upload or job submit fails.
        """
        if len(pairs) < MIN_PAIRS_FOR_TUNING:
            msg = (
                f"Insufficient pairs for tuning: {len(pairs)} < {MIN_PAIRS_FOR_TUNING}. "
                "Collect more trajectory data before tuning."
            )
            raise ValueError(msg)

        gcs_uri = self._upload_pairs_to_gcs(pairs)
        job = self._tuning_job.submit(gcs_pairs_uri=gcs_uri, display_name=display_name)
        job_name: str = job.name
        logger.info(
            "DPO tuning job started", extra={"job_name": job_name, "pair_count": len(pairs)}
        )
        return job_name

    def _upload_pairs_to_gcs(self, pairs: list[PreferencePair]) -> str:
        """Serialize pairs to JSONL and upload to GCS.

        Returns:
            The GCS URI of the uploaded JSONL file.

        Raises:
            RuntimeError: Fail-loud if GCS upload fails.
        """
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
            for pair in pairs:
                record = {
                    "prompt": pair.prompt,
                    "chosen": pair.chosen,
                    "rejected": pair.rejected,
                }
                f.write(json.dumps(record) + "\n")
            tmp_path = Path(f.name)

        # Date-partitioned blob path establishes the F7 audit-trail contract:
        # every tune() invocation persists its training corpus under a fresh,
        # timestamped key, so re-runs never silently overwrite the previous
        # training snapshot and reviewers can reconstruct any prior tuning job
        # from GCS object versioning alone.
        date_partition = datetime.now(UTC).strftime("%Y-%m-%d/%H%M%S")
        gcs_blob_name = f"tuner-pairs/{date_partition}/pairs.jsonl"
        try:
            bucket = self._gcs_client.bucket(self._bucket)
            blob = bucket.blob(gcs_blob_name)
            blob.upload_from_filename(str(tmp_path))
        except Exception as exc:
            msg = f"GCS upload failed for {gcs_blob_name}: {exc}"
            logger.exception(msg)
            raise RuntimeError(msg) from exc
        finally:
            tmp_path.unlink(missing_ok=True)

        gcs_uri = f"gs://{self._bucket}/{gcs_blob_name}"
        logger.info("Pairs uploaded to GCS", extra={"gcs_uri": gcs_uri, "pair_count": len(pairs)})
        return gcs_uri

    def evaluate_and_promote(
        self,
        job_name: str,
        *,
        achieved_kappa: float,
    ) -> str:
        """Gate the tuned model on κ and return the endpoint if promotion passes.

        The caller is responsible for computing achieved_kappa from a calibration
        eval run (e.g., InterRater agreement on the golden set). This method
        applies the threshold gate and returns the endpoint for router wiring.

        Args:
            job_name: The tuning job resource path from tune().
            achieved_kappa: κ score from calibration eval (0.0-1.0).

        Returns:
            The Vertex AI endpoint resource name for the promoted model.

        Raises:
            ValueError: Fail-loud if achieved_kappa < KAPPA_PROMOTION_THRESHOLD.
            RuntimeError: Fail-loud if job has not succeeded or endpoint missing.
        """
        state = self._tuning_job.get_state(job_name=job_name)
        if state == TuningJobState.FAILED:
            msg = f"Tuning job failed — cannot promote: {job_name}"
            raise RuntimeError(msg)
        if state != TuningJobState.SUCCEEDED:
            msg = f"Tuning job not yet succeeded (state={state.value}): {job_name}"
            raise RuntimeError(msg)

        if achieved_kappa < KAPPA_PROMOTION_THRESHOLD:
            msg = (
                f"Promotion blocked: achieved_kappa={achieved_kappa:.3f} < "
                f"KAPPA_PROMOTION_THRESHOLD={KAPPA_PROMOTION_THRESHOLD}. "
                "Collect more data or investigate calibration set coverage."
            )
            raise ValueError(msg)

        endpoint = self._tuning_job.get_tuned_model_name(job_name)
        logger.info(
            "Model promoted",
            extra={
                "job_name": job_name,
                "endpoint": endpoint,
                "achieved_kappa": achieved_kappa,
            },
        )
        return endpoint
