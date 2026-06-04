"""BigQuery ML & Conversational Telemetry Helper — AT-080 (PRD v2.2 §20).

Exposes helper routines to deploy Gemini-backed text-to-SQL models on BigQuery
and execute conversational telemetry audits over design trajectories.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from google.cloud import bigquery

logger = logging.getLogger(__name__)


def _bq_enabled() -> bool:
    """True when BigQuery telemetry is enabled."""
    is_prod = os.getenv("SESSION_BACKEND", "memory").strip().lower() == "vertex"
    explicit = os.getenv("ATELIER_BQ_ENABLED", "").lower() in ("1", "true", "yes")
    return is_prod or explicit


class BigQueryMLHelper:
    """Helper class for BigQuery ML Text-to-SQL remote models and conversational audits."""

    def __init__(
        self,
        project_id: str | None = None,
        dataset_id: str = "atelier_telemetry",
        model_name: str = "gemini_sql_model",
    ) -> None:
        """Initialize the helper.

        Args:
            project_id: GCP project ID.
            dataset_id: BigQuery dataset ID containing trajectories.
            model_name: Name of the BigQuery ML remote model.
        """
        self.project_id = project_id or os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
        self.dataset_id = dataset_id
        self.model_name = model_name

    def setup_remote_model(self, connection_id: str = "us.atelier-bq-conn") -> bool:
        """Create a remote model in BigQuery using the Vertex AI connection.

        Fail-soft: returns False if BigQuery is disabled, connection fails, or raises.
        """
        if not _bq_enabled() or not self.project_id:
            logger.info(
                "BigQuery ML setup skipped: BQ telemetry is disabled or project ID is missing."
            )
            return False

        try:
            client = bigquery.Client(project=self.project_id)

            # 1. Create dataset if not exists
            dataset_ref = client.dataset(self.dataset_id)
            try:
                client.get_dataset(dataset_ref)
            except Exception:  # noqa: BLE001
                logger.info("Creating dataset %s in BigQuery", self.dataset_id)
                client.create_dataset(bigquery.Dataset(dataset_ref))

            # 2. Deploy remote model pointing to Gemini endpoint
            sql = f"""
            CREATE OR REPLACE MODEL `{self.project_id}.{self.dataset_id}.{self.model_name}`
            REMOTE WITH CONNECTION `{self.project_id}.{connection_id}`
            OPTIONS(endpoint = 'gemini-1.5-flash');
            """
            logger.info("Deploying remote BigQuery ML model %s", self.model_name)
            query_job = client.query(sql)
            query_job.result()  # Wait for execution

        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "BigQuery ML remote model setup failed: %s (fail-soft)",
                exc,
                exc_info=True,
            )
            return False
        else:
            return True

    def query_telemetry_conversational(self, natural_question: str) -> list[dict[str, Any]]:
        """Translate a natural language question into SQL using BigQuery ML and run it.

        Fail-soft: returns empty list if BigQuery is offline.
        """
        if not _bq_enabled() or not self.project_id:
            logger.info("Conversational query skipped: BQ telemetry is disabled.")
            return []

        results: list[dict[str, Any]] = []
        try:
            client = bigquery.Client(project=self.project_id)
            model_path = f"{self.project_id}.{self.dataset_id}.{self.model_name}"

            # Prompt to guide the model to output ONLY valid SQL
            prompt = (
                f"Translate the following conversational telemetry request into a single valid BigQuery SQL query. "
                f"The table name is `{self.project_id}.{self.dataset_id}.trajectories` with columns: "
                f"session_id (STRING), tenant_id (STRING), iteration (INT64), converged (BOOL), "
                f"composite_score (FLOAT64), timestamp (TIMESTAMP), failures (ARRAY<STRING>). "
                f"Return ONLY the SQL query text and nothing else.\n"
                f'Request: "{natural_question}"'
            )

            # Query the BigQuery ML model using ML.GENERATE_TEXT
            # We parameterize the dynamic prompt value to protect against SQL injection.
            # The model_path identifier is a safe internal string.
            ml_query = f"""
            SELECT ml_generate_text_result
            FROM ML.GENERATE_TEXT(
              MODEL `{model_path}`,
              (SELECT @prompt_param AS prompt),
              STRUCT(0.1 AS temperature, 1000 AS max_output_tokens)
            )
            """  # noqa: S608
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("prompt_param", "STRING", prompt),
                ]
            )
            job = client.query(ml_query, job_config=job_config)
            result = list(job.result())
            if not result:
                logger.warning("BigQuery ML returned no text translation.")
            else:
                generated_output = result[0].get("ml_generate_text_result", "")
                # Simple clean up of generated markdown SQL fences if present
                sql_query = generated_output.replace("```sql", "").replace("```", "").strip()

                if not sql_query:
                    logger.warning("No SQL query generated.")
                else:
                    # Strict safety audit validation: enforce read-only SELECT and block destructive queries
                    import re  # noqa: PLC0415

                    sql_upper = sql_query.strip().upper()
                    if not sql_upper.startswith("SELECT"):
                        logger.error(
                            "Security violation: BigQuery ML generated a non-SELECT query: %s",
                            sql_query,
                        )
                    else:
                        forbidden_keywords = [
                            "INSERT",
                            "UPDATE",
                            "DELETE",
                            "DROP",
                            "CREATE",
                            "ALTER",
                            "TRUNCATE",
                            "GRANT",
                            "REVOKE",
                            "MERGE",
                            "REPLACE",
                        ]
                        has_forbidden = False
                        for kw in forbidden_keywords:
                            if re.search(r"\b" + kw + r"\b", sql_upper):
                                logger.error(
                                    "Security violation: BigQuery ML query contains forbidden keyword '%s': %s",
                                    kw,
                                    sql_query,
                                )
                                has_forbidden = True
                                break
                        if not has_forbidden:
                            logger.info("Executing generated SQL query: %s", sql_query)
                            query_job = client.query(sql_query)
                            rows = query_job.result()
                            results = [dict(row) for row in rows]

        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "BigQuery ML conversational telemetry query failed: %s (fail-soft)",
                exc,
                exc_info=True,
            )

        return results
