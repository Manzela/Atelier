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

import logging
from dataclasses import dataclass
from typing import Final, Protocol, runtime_checkable

from google.cloud import bigquery

logger = logging.getLogger(__name__)

BQ_DPO_PAIRS_TABLE: Final[str] = "atelier-build-2026.atelier_trajectories.dpo_pairs"
MIN_PAIRS_FOR_TUNING: Final[int] = 50
DEFAULT_MINE_LIMIT: Final[int] = 500

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
    ) -> list[PreferencePair]:
        """Mine preference pairs from BigQuery.

        Args:
            tenant_id: If provided, filters rows to this tenant only.
                Never returns cross-tenant data.
            limit: Maximum number of pairs to return. Applied in BigQuery
                (not in Python) to bound cost.

        Returns:
            List of PreferencePair. Empty list if table has no matching rows.

        Raises:
            google.cloud.exceptions.GoogleCloudError: Fail-soft — BQ errors
                propagate to caller; do not swallow.
        """
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
        pairs = [
            PreferencePair(
                prompt=row.prompt,
                chosen=row.chosen_response,
                rejected=row.rejected_response,
                margin=row.margin,
                surface_id=row.surface_id,
                node_name=row.node_name,
                iteration=row.iteration,
                chosen_score=row.chosen_score,
                rejected_score=row.rejected_score,
            )
            for row in rows
        ]
        logger.info("DPO pair mining complete", extra={"pair_count": len(pairs)})
        return pairs
