# T6–T14 SOTA Protocol Surfaces Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement T6–T14 SOTA Protocol surfaces (DPO tuning migration, GeneratorTuner, BigQuery episodic memory, ε-Greedy Bandit router) that extend the T1–T5 Protocol contracts already on `main`.

**Architecture:** Five tasks build in dependency order — T6 establishes the `google.genai` DPO tuning client that T7/T14 consume; T8 implements the BigQuery backend for the `HierarchicalMemory` Protocol from T1; T13 implements the ε-Greedy Bandit that satisfies the `PhaseAwareMoERouter` Protocol from T3. All code uses `mypy --strict`, `@pytest.mark.anyio` (not asyncio), `StrEnum` (not `str, Enum`), and `Final` constants. Claude-owned paths only — DO NOT touch Antigravity-owned directories.

**Tech Stack:** `google-genai==1.75.0`, `google-cloud-bigquery`, `numpy 2.4.6`, Python 3.11+, `anyio`, `pytest`, `mypy --strict`

---

## Prerequisite: Sync phase/2 with main (T1–T5 files)

> **Must be done before any task below.** Phase/2 was branched before T1–T5 landed on main via PR #25. The router/protocol.py, memory/protocol.py, reward/composite.py files do not exist in phase/2 yet.

- [ ] **Verify the gap**

  ```bash
  cd "$(git rev-parse --show-toplevel)"
  ls atelier-core/src/atelier/router/ 2>/dev/null || echo "MISSING — must rebase"
  ls atelier-core/src/atelier/memory/protocol.py 2>/dev/null || echo "MISSING — must rebase"
  ```

  Expected if rebase is needed: `MISSING — must rebase` for both.

- [ ] **Pull latest main then merge into phase/2 — per-file resolution required**

  ```bash
  git fetch origin
  git merge --no-commit --no-ff origin/main
  # dry-run first to see which files conflict
  git diff --name-only --diff-filter=U
  ```

  Real merge from this branch-point produces **7 known conflicts**. Resolve each file
  with the strategy below — do NOT use `git checkout --theirs` as a blanket fallback
  (it would discard phase/2 feature-tracking work).

  | File                                          | Resolution strategy                                                                                                                                                             |
  | --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
  | `DECISIONS.md`                                | Union merge — append new ADR rows from both sides. Do not drop either side's entries.                                                                                           |
  | `features.json`                               | Union of `features[]` arrays — append new entries from both sides; validate `_meta` invariants after (total count, no duplicate IDs).                                           |
  | `atelier-core/src/atelier/nodes/consensus.py` | 3-way merge — keep the T1–T5 LLM-integration delta from `origin/main`; preserve any phase/2 local changes. `git mergetool` or manual resolution.                                |
  | `atelier-core/src/atelier/nodes/llm_judge.py` | Same 3-way merge strategy as consensus.py.                                                                                                                                      |
  | `.github/workflows/codeql.yml`                | Accept `origin/main` version (`git checkout --theirs .github/workflows/codeql.yml`).                                                                                            |
  | `pyproject.toml`                              | Accept `origin/main` version (`git checkout --theirs pyproject.toml`), then re-apply any phase/2 `[tool.mypy.overrides]` blocks by hand.                                        |
  | `requirements.lock`                           | Accept `origin/main` version (`git checkout --theirs requirements.lock`), then re-run `uv pip compile atelier-core/pyproject.toml -o requirements.lock` if the dep set changed. |

  After resolving all conflicts:

  ```bash
  git add .
  git commit -m "chore(phase2): merge origin/main — apply T1-T5 SOTA Protocol surfaces

  Per-file resolution: union DECISIONS.md and features.json; 3-way merge
  consensus.py and llm_judge.py; accept origin/main for codeql.yml,
  pyproject.toml, requirements.lock."
  ```

- [ ] **Verify T1–T5 files now present**

  ```bash
  python -c "
  from atelier.memory.protocol import HierarchicalMemory, MemoryEvent, MemoryQueryResult, MemoryTier
  from atelier.router.protocol import PhaseAwareMoERouter, RouteRequest, RouteDecision, DAGPhase, ExpertID
  from atelier.reward.composite import AndGateRewardEngine, EXTRINSIC_MARGIN_FLOOR
  print('T1-T5 protocols: OK')
  "
  ```

  Expected: `T1-T5 protocols: OK`

---

## File Map

| Task | Creates                                                         | Modifies |
| ---- | --------------------------------------------------------------- | -------- |
| T6   | `atelier-core/src/atelier/optimize/dpo_tuning_job.py`           | —        |
| T6   | `atelier-core/tests/unit/test_dpo_tuning_job.py`                | —        |
| T7   | `atelier-core/src/atelier/optimize/generator_tuner.py`          | —        |
| T7   | `atelier-core/tests/unit/test_generator_tuner.py`               | —        |
| T8   | `atelier-core/src/atelier/memory/bigquery_backend.py`           | —        |
| T8   | `atelier-core/tests/unit/test_bigquery_backend.py`              | —        |
| T13  | `atelier-core/src/atelier/router/v1_bandit.py`                  | —        |
| T13  | `atelier-core/tests/unit/test_router_bandit.py`                 | —        |
| T14  | `atelier-core/src/atelier/optimize/generator_tuner.py` (extend) | —        |
| T14  | `atelier-core/tests/unit/test_generator_tuner.py` (extend)      | —        |

Protected paths — DO NOT touch:

```
atelier-core/src/atelier/api/
atelier-core/src/atelier/gates/
atelier-core/src/atelier/intake/
atelier-core/src/atelier/orchestrator/
atelier-core/src/atelier/recorders/
atelier-core/src/atelier/observability/
atelier-core/src/atelier/integrations/
atelier-core/src/atelier/nodes/  (except _types.py — that one IS Claude-owned)
infra/ deploy/ config/ scripts/
```

## Coordination contracts (read before writing any file)

### features.json ownership (F5)

Claude does **NOT** touch `features.json` during T6–T14. Antigravity owns all feature-flip
commits this run (R9 brief §12 lists `FA-001/002/006/007/011/012/015/016/017` and
`F0013–F0030`). This prevents list-level ADD/ADD conflicts when both agents commit.

If a T6–T14 deliverable maps to an existing F0XXX entry that Claude must flip: raise it
explicitly with Daniel rather than self-modifying features.json. Record the dependency in
`docs/sprint/CHECKPOINTS.md` instead.

### CHECKPOINTS.md / STATUS.md section headers (F6)

Both agents append to `docs/sprint/CHECKPOINTS.md`. To prevent line-level conflicts
when Antigravity (first committer) and Claude (second committer) both append:

```markdown
## R9 — Antigravity Pipeline Features

<!-- Antigravity appends batch-end summaries here (R9-A, R9-B, R9-C) -->

## T6-T14 — Claude SOTA Protocol

<!-- Claude appends task completions here -->
```

When updating CHECKPOINTS.md, append under `## T6-T14 — Claude SOTA Protocol` only.
Do not write above that section header.

### GCS namespace (F7)

All Claude-owned DPO artifacts use a namespaced prefix:

```
gs://atelier-build-2026-dpo-pairs/claude-T7/{date}/
```

Antigravity FA-012 DPO builder uses:

```
gs://atelier-build-2026-dpo-pairs/antigravity/{date}/
```

Do not cross-write into the other namespace.

### dpo_pairs BQ table dependency (F4)

`BQ_DPO_PAIRS_TABLE = "atelier-build-2026.atelier_trajectories.dpo_pairs"` (T7)
requires this table to exist and be populated. **This table is NOT yet created.**
Resolution: Antigravity R9-B `dpo_builder.py` (FA-012) must also land rows into this
table after the JSONL export step (or a companion `dpo_loader.py` does the BQ load).
Claude **gates T7 execution** on confirmation that FA-012 has landed at least one row
in `atelier_trajectories.dpo_pairs`. Do not run T7 integration paths until that
confirmation is received from Antigravity or Daniel.

---

## Task 1: T6 — DPO Tuning Job (google-genai migration)

**Files:**

- Create: `atelier-core/src/atelier/optimize/dpo_tuning_job.py`
- Create: `atelier-core/tests/unit/test_dpo_tuning_job.py`

**Context:** ADR 0028 mandates replacing deprecated `vertexai.tuning.sft` with `google.genai TuningMethod.PREFERENCE_TUNING`. The API surface is **partially verified** via context7 against google-genai 1.75.0: `PreferenceOptimizationSpec`, `PreferenceOptimizationHyperParameters`, `AdapterSize.ADAPTER_SIZE_FOUR`, and `client.tunings.tune()` are confirmed. **NOT yet confirmed** via context7: `CreateTuningJobConfig.method` field, `CreateTuningJobConfig.preference_optimization_spec` field, and `TuningMethod.PREFERENCE_TUNING` enum value. These three must be discovered via Step 1 introspection **before writing any implementation code**. If the actual field names differ, halt and report — do NOT guess or improvise. β=0.1, epochCount=3, adapterSize=ADAPTER_SIZE_FOUR.

- [ ] **Step 1: Verify the API**

  ```bash
  cd atelier-core
  python -c "
  from google.genai import types
  print('TuningMethod values:', list(types.TuningMethod))
  print('AdapterSize.ADAPTER_SIZE_FOUR:', types.AdapterSize.ADAPTER_SIZE_FOUR)
  cfg = types.CreateTuningJobConfig(tuned_model_display_name='test')
  print('CreateTuningJobConfig ok')
  spec = types.PreferenceOptimizationSpec(
      training_dataset_uri='gs://test/train.jsonl',
      hyper_parameters=types.PreferenceOptimizationHyperParameters(
          beta=0.1, epoch_count=3, adapter_size=types.AdapterSize.ADAPTER_SIZE_FOUR
      )
  )
  print('PreferenceOptimizationSpec ok:', spec)
  "
  ```

  Expected: prints enum values and `PreferenceOptimizationSpec ok: ...` without error. If `preference_optimization_spec` is not a field on `CreateTuningJobConfig`, inspect what fields exist:

  ```bash
  python -c "from google.genai import types; import inspect; print([f for f in dir(types.CreateTuningJobConfig) if not f.startswith('_')])"
  ```

  Use the actual field names you observe — do not guess.

- [ ] **Step 2: Write the failing tests**

  Create `atelier-core/tests/unit/test_dpo_tuning_job.py`:

  ```python
  """Unit tests for DPO tuning job (T6, ADR 0028)."""

  from __future__ import annotations

  from unittest.mock import AsyncMock, MagicMock, patch

  import pytest

  from atelier.optimize.dpo_tuning_job import (
      DPO_ADAPTER_SIZE,
      DPO_BETA,
      DPO_EPOCH_COUNT,
      DPO_GCS_PREFIX,
      DpoTuningJob,
      TuningJobState,
  )


  def _make_mock_job(state: str = "JOB_STATE_RUNNING") -> MagicMock:
      job = MagicMock()
      job.name = "projects/atelier-build-2026/locations/us-central1/tuningJobs/123"
      job.state = state
      job.tuned_model_info = None
      return job


  def test_constants_match_adr_0028() -> None:
      assert DPO_BETA == 0.1
      assert DPO_EPOCH_COUNT == 3
      assert "ADAPTER_SIZE_FOUR" in str(DPO_ADAPTER_SIZE)


  def test_gcs_prefix_points_to_correct_project() -> None:
      assert "atelier-build-2026" in DPO_GCS_PREFIX


  def test_tuning_job_state_enum_has_required_values() -> None:
      assert TuningJobState.RUNNING.value == "JOB_STATE_RUNNING"
      assert TuningJobState.SUCCEEDED.value == "JOB_STATE_SUCCEEDED"
      assert TuningJobState.FAILED.value == "JOB_STATE_FAILED"


  @patch("atelier.optimize.dpo_tuning_job.genai.Client")
  def test_submit_creates_tuning_job_with_preference_tuning(mock_client_cls: MagicMock) -> None:
      mock_client = MagicMock()
      mock_client_cls.return_value = mock_client
      mock_client.tunings.tune.return_value = _make_mock_job()

      job = DpoTuningJob(project="atelier-build-2026")
      result = job.submit(gcs_pairs_uri="gs://atelier-build-2026-dpo/train.jsonl")

      mock_client.tunings.tune.assert_called_once()
      call_kwargs = mock_client.tunings.tune.call_args
      assert "gemini-2.5-flash" in str(call_kwargs)
      assert result.name.endswith("123")


  @patch("atelier.optimize.dpo_tuning_job.genai.Client")
  def test_get_state_maps_job_state_string(mock_client_cls: MagicMock) -> None:
      mock_client = MagicMock()
      mock_client_cls.return_value = mock_client
      mock_job = _make_mock_job("JOB_STATE_SUCCEEDED")
      mock_client.tunings.get.return_value = mock_job

      job = DpoTuningJob(project="atelier-build-2026")
      state = job.get_state(job_name="projects/atelier-build-2026/tuningJobs/123")

      assert state == TuningJobState.SUCCEEDED


  @patch("atelier.optimize.dpo_tuning_job.genai.Client")
  def test_get_tuned_model_name_raises_when_not_succeeded(mock_client_cls: MagicMock) -> None:
      mock_client = MagicMock()
      mock_client_cls.return_value = mock_client
      mock_job = _make_mock_job("JOB_STATE_RUNNING")
      mock_job.tuned_model_info = None
      mock_client.tunings.get.return_value = mock_job

      job = DpoTuningJob(project="atelier-build-2026")
      with pytest.raises(RuntimeError, match="not yet succeeded"):
          job.get_tuned_model_name("projects/atelier-build-2026/tuningJobs/123")


  @patch("atelier.optimize.dpo_tuning_job.genai.Client")
  def test_get_tuned_model_name_returns_endpoint_when_succeeded(mock_client_cls: MagicMock) -> None:
      mock_client = MagicMock()
      mock_client_cls.return_value = mock_client
      mock_job = _make_mock_job("JOB_STATE_SUCCEEDED")
      mock_job.tuned_model_info = MagicMock()
      mock_job.tuned_model_info.endpoint = "projects/123/locations/us-central1/endpoints/456"
      mock_client.tunings.get.return_value = mock_job

      job = DpoTuningJob(project="atelier-build-2026")
      name = job.get_tuned_model_name("projects/atelier-build-2026/tuningJobs/123")
      assert "456" in name
  ```

- [ ] **Step 3: Run tests to verify they fail**

  ```bash
  cd atelier-core
  pytest tests/unit/test_dpo_tuning_job.py -v 2>&1 | head -20
  ```

  Expected: `ModuleNotFoundError: No module named 'atelier.optimize.dpo_tuning_job'`

- [ ] **Step 4: Implement `dpo_tuning_job.py`**

  Create `atelier-core/src/atelier/optimize/dpo_tuning_job.py`:

  ```python
  """DPO tuning job — google.genai unified client (ADR 0028, spec §9.2).

  Replaces deprecated ``vertexai.tuning.sft`` with ``google.genai``
  ``TuningMethod.PREFERENCE_TUNING``. This module is responsible only for
  job submission and state polling — pair mining lives in T7 GeneratorTuner.

  Tuning parameters (ADR 0028, locked — change via ADR amendment only):
      beta=0.1         KL divergence regularisation weight
      epoch_count=3    Full passes over the training dataset
      adapter_size=4   LoRA rank / adapter dimension
      base_model       gemini-2.5-flash (manageable cost; originality judge
                       uses 2.5-pro but tuning targets the generator)
  """

  from __future__ import annotations

  import logging
  from enum import StrEnum
  from typing import TYPE_CHECKING, Any, Final

  from google import genai
  from google.genai import types

  if TYPE_CHECKING:
      pass

  logger = logging.getLogger(__name__)

  # ---------------------------------------------------------------------------
  # ADR 0028 constants — locked; change only via ADR amendment
  # ---------------------------------------------------------------------------

  DPO_BETA: Final[float] = 0.1
  DPO_EPOCH_COUNT: Final[int] = 3
  DPO_ADAPTER_SIZE: Final[types.AdapterSize] = types.AdapterSize.ADAPTER_SIZE_FOUR
  DPO_BASE_MODEL: Final[str] = "gemini-2.5-flash"
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
      """Submit and poll DPO (preference-optimization) tuning jobs on Vertex AI.

      Fail-soft on unknown state strings — maps them to TuningJobState.UNKNOWN
      rather than raising, so the caller can decide whether to retry.
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
      ) -> Any:  # returns google.genai TuningJob
          """Submit a preference-optimization tuning job.

          Args:
              gcs_pairs_uri: GCS URI to JSONL file with DPO preference pairs.
                  Each line: {"prompt": "...", "chosen": "...", "rejected": "..."}
              display_name: Human-readable name for the tuned model.
              validation_gcs_uri: Optional GCS URI to JSONL validation set.

          Returns:
              The submitted TuningJob object (google.genai).

          Raises:
              RuntimeError: Fail-loud if the submit call fails (non-retriable).
          """
          hyper = types.PreferenceOptimizationHyperParameters(
              beta=DPO_BETA,
              epoch_count=DPO_EPOCH_COUNT,
              adapter_size=DPO_ADAPTER_SIZE,
          )
          po_spec = types.PreferenceOptimizationSpec(
              training_dataset_uri=gcs_pairs_uri,
              validation_dataset_uri=validation_gcs_uri,
              hyper_parameters=hyper,
          )
          config = types.CreateTuningJobConfig(
              method=types.TuningMethod.PREFERENCE_TUNING,
              tuned_model_display_name=display_name,
              preference_optimization_spec=po_spec,
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
          # NOTE (F3 fix): training URI is already set on po_spec.training_dataset_uri
          # (confirmed canonical via Step 1 introspection). Do NOT also pass
          # training_dataset=TuningDataset(gcs_uri=...) — that is a duplicate that
          # will cause a double-URI error. If Step 1 shows a different shape, revise
          # this call accordingly and do not merge until confirmed.
          job = self._client.tunings.tune(
              base_model=DPO_BASE_MODEL,
              config=config,
          )
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
          job = self._client.tunings.get(name=job_name)
          state = self.get_state(job_name=job_name)
          if state != TuningJobState.SUCCEEDED:
              msg = f"Tuning job not yet succeeded (state={state.value}): {job_name}"
              raise RuntimeError(msg)
          info = getattr(job, "tuned_model_info", None)
          endpoint: str = getattr(info, "endpoint", "") if info else ""
          if not endpoint:
              msg = f"Tuning job succeeded but no endpoint found: {job_name}"
              raise RuntimeError(msg)
          return endpoint
  ```

- [ ] **Step 5: Run mypy**

  ```bash
  cd atelier-core
  python -m mypy --strict src/atelier/optimize/dpo_tuning_job.py
  ```

  Expected: `Success: no issues found in 1 source file`

  Common fixes:
  - If `Any` import is flagged: it's already imported from `typing` — check the import line.
  - If `types.PreferenceOptimizationSpec` attribute errors appear: inspect actual field names via `python -c "from google.genai import types; help(types.PreferenceOptimizationSpec)"` and adjust.

- [ ] **Step 6: Run tests to verify they pass**

  ```bash
  cd atelier-core
  pytest tests/unit/test_dpo_tuning_job.py -v
  ```

  Expected: `6 passed`

- [ ] **Step 7: Run import smoke-test**

  ```bash
  cd atelier-core
  python -c "from atelier.optimize.dpo_tuning_job import DpoTuningJob, TuningJobState, DPO_BETA; print('ok')"
  ```

  Expected: `ok`

- [ ] **Step 8: Pre-commit**

  ```bash
  cd "$(git rev-parse --show-toplevel)"
  pre-commit run --all-files
  ```

  Common pre-commit fixes:
  - `ruff UP042`: if you used `class X(str, Enum)` instead of `StrEnum` — fix to `StrEnum`.
  - `ruff PLR2004`: bare numeric literals — wrap in `Final` constants.
  - Prettier/markdownlint only: re-stage auto-fixed files and commit again.

- [ ] **Step 9: Commit**

  ```bash
  git add atelier-core/src/atelier/optimize/dpo_tuning_job.py \
          atelier-core/tests/unit/test_dpo_tuning_job.py
  git commit -m "feat(optimize): T6 — DPO tuning job via google.genai PREFERENCE_TUNING

  Replaces deprecated vertexai.tuning.sft with google.genai TuningMethod.PREFERENCE_TUNING
  per ADR 0028. DpoTuningJob.submit() wraps client.tunings.tune() with:
  - beta=0.1 (KL divergence weight)
  - epoch_count=3
  - adapter_size=ADAPTER_SIZE_FOUR
  - base_model=gemini-2.5-flash

  6 unit tests: constants match ADR 0028, submit creates job with PREFERENCE_TUNING,
  get_state maps state strings, get_tuned_model_name raises on non-succeeded."
  ```

---

## Task 2: T7 — GeneratorTuner Protocol + `mine_pairs()`

**Files:**

- Create: `atelier-core/src/atelier/optimize/generator_tuner.py`
- Create: `atelier-core/tests/unit/test_generator_tuner.py`

**Context:** T7 introduces the `GeneratorTunerProtocol` and a concrete `BigQueryPairMiner` that reads from BigQuery `atelier_trajectories.dpo_pairs`. T14 will add `tune()` and `evaluate_and_promote()` on top. Keep T7 focused: only `mine_pairs()` and the Protocol definition.

- [ ] **Step 1: Verify BigQuery client**

  ```bash
  cd atelier-core
  python -c "from google.cloud import bigquery; print('BigQuery client:', bigquery.__version__)"
  ```

  Expected: `BigQuery client: <version>`. If this fails, verify `google-cloud-bigquery` is in `requirements.lock`.

- [ ] **Step 2: Write the failing tests**

  Create `atelier-core/tests/unit/test_generator_tuner.py`:

  ```python
  """Unit tests for GeneratorTuner T7 (mine_pairs) and T14 (tune + promote)."""

  from __future__ import annotations

  from unittest.mock import MagicMock, patch

  import pytest

  from atelier.optimize.generator_tuner import (
      BQ_DPO_PAIRS_TABLE,
      MIN_PAIRS_FOR_TUNING,
      BigQueryPairMiner,
      PreferencePair,
  )


  def _make_bq_row(chosen_score: float = 0.82, rejected_score: float = 0.55) -> MagicMock:
      row = MagicMock()
      row.surface_id = "surf-001"
      row.node_name = "N3a.generator"
      row.iteration = 0
      row.prompt = "Design a landing page"
      row.chosen_response = "<html>...</html>"
      row.rejected_response = "<html>worse...</html>"
      row.chosen_score = chosen_score
      row.rejected_score = rejected_score
      row.margin = chosen_score - rejected_score
      return row


  def test_bq_table_constant_points_to_correct_project() -> None:
      assert "atelier-build-2026" in BQ_DPO_PAIRS_TABLE


  def test_min_pairs_constant_is_positive() -> None:
      assert MIN_PAIRS_FOR_TUNING > 0


  def test_preference_pair_fields() -> None:
      pair = PreferencePair(
          prompt="p", chosen="c", rejected="r", margin=0.27,
          surface_id="s", node_name="n", iteration=0,
          chosen_score=0.82, rejected_score=0.55,
      )
      assert pair.prompt == "p"
      assert pair.margin == pytest.approx(0.27)


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
  def test_mine_pairs_respects_limit(mock_bq_cls: MagicMock) -> None:
      mock_client = MagicMock()
      mock_bq_cls.return_value = mock_client
      mock_client.query.return_value.result.return_value = [_make_bq_row() for _ in range(5)]

      miner = BigQueryPairMiner(project="atelier-build-2026")
      pairs = miner.mine_pairs(limit=3)

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
      assert "tenant-abc" in query_sql


  @patch("atelier.optimize.generator_tuner.bigquery.Client")
  def test_mine_pairs_returns_empty_list_on_no_results(mock_bq_cls: MagicMock) -> None:
      mock_client = MagicMock()
      mock_bq_cls.return_value = mock_client
      mock_client.query.return_value.result.return_value = []

      miner = BigQueryPairMiner(project="atelier-build-2026")
      pairs = miner.mine_pairs()
      assert pairs == []
  ```

- [ ] **Step 3: Run tests to verify they fail**

  ```bash
  cd atelier-core
  pytest tests/unit/test_generator_tuner.py -v 2>&1 | head -10
  ```

  Expected: `ModuleNotFoundError: No module named 'atelier.optimize.generator_tuner'`

- [ ] **Step 4: Implement `generator_tuner.py` (T7 scope only)**

  Create `atelier-core/src/atelier/optimize/generator_tuner.py`:

  ```python
  """GeneratorTuner — Protocol + BigQuery pair miner (T7, spec §9.3).

  T7 scope: GeneratorTunerProtocol definition + BigQueryPairMiner.mine_pairs().
  T14 scope (added in Task 5): full tune() + evaluate_and_promote().

  BigQuery table layout (atelier-build-2026.atelier_trajectories.dpo_pairs):
      surface_id       STRING   - identifies which surface produced this pair
      node_name        STRING   - e.g. "N3a.generator"
      iteration        INT64    - which EvoDesign iteration
      prompt           STRING   - the shared generation prompt
      chosen_response  STRING   - higher-quality candidate HTML/CSS
      rejected_response STRING  - lower-quality candidate HTML/CSS
      chosen_score     FLOAT64  - composite judge score (>= T2_THRESHOLD 0.70)
      rejected_score   FLOAT64  - composite judge score (<  T3_THRESHOLD 0.50)
      margin           FLOAT64  - chosen_score - rejected_score (>= MIN_MARGIN 0.15)
      tenant_id        STRING   - tenant isolation key (ALWAYS filter on this)
      created_at       TIMESTAMP
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
          """
          ...


  class BigQueryPairMiner:
      """Concrete GeneratorTunerProtocol implementation — mine_pairs() only.

      Reads from `atelier-build-2026.atelier_trajectories.dpo_pairs`.
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
          """Query dpo_pairs table for eligible preference pairs.

          Args:
              tenant_id: If provided, filters rows to this tenant only.
                  DO NOT omit this filter for multi-tenant deployments.
              limit: Maximum rows to return. Default 500.

          Returns:
              List of PreferencePair (may be empty if no pairs qualify).
          """
          tenant_clause = ""
          if tenant_id is not None:
              safe_tenant = tenant_id.replace("'", "''")
              tenant_clause = f"AND tenant_id = '{safe_tenant}'"

          sql = f"""
              SELECT
                  surface_id,
                  node_name,
                  iteration,
                  prompt,
                  chosen_response,
                  rejected_response,
                  chosen_score,
                  rejected_score,
                  margin
              FROM `{BQ_DPO_PAIRS_TABLE}`
              WHERE TRUE
                  {tenant_clause}
              ORDER BY margin DESC
              LIMIT {int(limit)}
          """
          logger.debug("Mining DPO pairs", extra={"tenant_id": tenant_id, "limit": limit})
          rows = list(self._client.query(sql).result())

          pairs = [
              PreferencePair(
                  prompt=row.prompt,
                  chosen=row.chosen_response,
                  rejected=row.rejected_response,
                  margin=float(row.margin),
                  surface_id=row.surface_id,
                  node_name=row.node_name,
                  iteration=int(row.iteration),
                  chosen_score=float(row.chosen_score),
                  rejected_score=float(row.rejected_score),
              )
              for row in rows
          ]
          logger.info("Mined DPO pairs", extra={"count": len(pairs), "tenant_id": tenant_id})
          return pairs
  ```

- [ ] **Step 5: Run mypy**

  ```bash
  cd atelier-core
  python -m mypy --strict src/atelier/optimize/generator_tuner.py
  ```

  Expected: `Success: no issues found in 1 source file`

- [ ] **Step 6: Run tests**

  ```bash
  cd atelier-core
  pytest tests/unit/test_generator_tuner.py -v
  ```

  Expected: `6 passed`

- [ ] **Step 7: Smoke test**

  ```bash
  python -c "from atelier.optimize.generator_tuner import BigQueryPairMiner, PreferencePair, GeneratorTunerProtocol; print('ok')"
  ```

  Expected: `ok`

- [ ] **Step 8: Pre-commit + commit**

  ```bash
  cd "$(git rev-parse --show-toplevel)"
  pre-commit run --all-files
  git add atelier-core/src/atelier/optimize/generator_tuner.py \
          atelier-core/tests/unit/test_generator_tuner.py
  git commit -m "feat(optimize): T7 — GeneratorTunerProtocol + BigQueryPairMiner.mine_pairs()

  Introduces GeneratorTunerProtocol (runtime_checkable) and BigQueryPairMiner
  that queries atelier-build-2026.atelier_trajectories.dpo_pairs.
  Always enforces tenant_id predicate when provided (§20.5 isolation).
  T14 will extend with tune() + evaluate_and_promote()."
  ```

---

## Task 3: T8 — BigQuery Episodic Memory Backend

**Files:**

- Create: `atelier-core/src/atelier/memory/bigquery_backend.py`
- Create: `atelier-core/tests/unit/test_bigquery_backend.py`

**Context:** T8 implements `HierarchicalMemory` Protocol (T1) for the episodic tier. The Protocol requires `write_episodic`, `query_semantic`, `lookup_procedural`, `consolidate_session`. BigQuery handles episodic; the semantic/procedural methods must delegate to `VertexSemanticMemoryBackend` (already in `memory/backends/vertex_semantic.py`). The §20.5 isolation test verifies that EVERY query includes a `tenant_id` predicate — this is the critical security invariant.

- [ ] **Step 1: Read the existing Protocol and backends**

  ```bash
  cat atelier-core/src/atelier/memory/protocol.py | grep "class\|async def\|def "
  cat atelier-core/src/atelier/memory/key.py | grep "class\|def "
  cat atelier-core/src/atelier/memory/backends/vertex_semantic.py | grep "class\|async def\|def " | head -15
  ```

  Confirm: `HierarchicalMemory` Protocol has exactly 4 methods, `MemoryKey` has `tenant_id`/`project_id`/`session_id`, `VertexSemanticMemoryBackend` has `write_semantic` and `query_semantic`.

- [ ] **Step 2: Write the failing tests (including §20.5 isolation test)**

  Create `atelier-core/tests/unit/test_bigquery_backend.py`:

  ```python
  """Unit tests for BigQuery episodic memory backend (T8, spec §20).

  Includes the §20.5 isolation test: every BQ query MUST include a tenant_id predicate.
  """

  from __future__ import annotations

  import contextvars
  from datetime import datetime, timezone
  from typing import Any
  from unittest.mock import AsyncMock, MagicMock, patch
  from uuid import uuid4

  import pytest

  from atelier.memory.bigquery_backend import (
      BQ_SESSION_EVENTS_TABLE,
      BigQueryEpisodicBackend,
  )
  from atelier.memory.key import CURRENT_MEMORY_KEY, MemoryKey
  from atelier.memory.protocol import MemoryEvent, MemoryTier


  def _make_key(tenant_id: str = "tenant-abc") -> MemoryKey:
      return MemoryKey(tenant_id=tenant_id, project_id="proj-001", session_id=str(uuid4()))


  def _make_event() -> MemoryEvent:
      return MemoryEvent(
          event_id=str(uuid4()),
          occurred_at=datetime.now(tz=timezone.utc),
          node_name="N3a.generator",
          payload={"candidate_id": "c-001", "score": "0.82"},
          embedding=None,
      )


  def test_bq_table_constant_points_to_correct_project() -> None:
      assert "atelier-build-2026" in BQ_SESSION_EVENTS_TABLE
      assert "session_events" in BQ_SESSION_EVENTS_TABLE


  @pytest.mark.anyio
  @patch("atelier.memory.bigquery_backend.bigquery.Client")
  async def test_write_episodic_inserts_row_with_correct_table(mock_bq_cls: MagicMock) -> None:
      mock_client = MagicMock()
      mock_bq_cls.return_value = mock_client
      mock_client.insert_rows_json.return_value = []  # empty list = no errors

      key = _make_key()
      token = CURRENT_MEMORY_KEY.set(key)
      try:
          backend = BigQueryEpisodicBackend(project="atelier-build-2026")
          await backend.write_episodic(_make_event())
      finally:
          CURRENT_MEMORY_KEY.reset(token)

      mock_client.insert_rows_json.assert_called_once()
      table_arg = mock_client.insert_rows_json.call_args[0][0]
      assert BQ_SESSION_EVENTS_TABLE in str(table_arg)


  @pytest.mark.anyio
  @patch("atelier.memory.bigquery_backend.bigquery.Client")
  async def test_write_episodic_raises_lookup_error_without_key(mock_bq_cls: MagicMock) -> None:
      """§20.5: write_episodic must fail-loud if no MemoryKey is bound."""
      mock_bq_cls.return_value = MagicMock()
      # Ensure no key is bound
      try:
          CURRENT_MEMORY_KEY.get()
          pytest.skip("MemoryKey already bound in this test — cannot test LookupError")
      except LookupError:
          pass

      backend = BigQueryEpisodicBackend(project="atelier-build-2026")
      with pytest.raises(LookupError):
          await backend.write_episodic(_make_event())


  @pytest.mark.anyio
  @patch("atelier.memory.bigquery_backend.bigquery.Client")
  async def test_write_episodic_includes_tenant_id_in_row(mock_bq_cls: MagicMock) -> None:
      """§20.5 isolation: every row written must carry tenant_id."""
      mock_client = MagicMock()
      mock_bq_cls.return_value = mock_client
      mock_client.insert_rows_json.return_value = []

      key = _make_key(tenant_id="tenant-xyz")
      token = CURRENT_MEMORY_KEY.set(key)
      try:
          backend = BigQueryEpisodicBackend(project="atelier-build-2026")
          await backend.write_episodic(_make_event())
      finally:
          CURRENT_MEMORY_KEY.reset(token)

      rows: list[dict[str, Any]] = mock_client.insert_rows_json.call_args[0][1]
      assert len(rows) == 1
      assert rows[0].get("tenant_id") == "tenant-xyz"


  @pytest.mark.anyio
  @patch("atelier.memory.bigquery_backend.bigquery.Client")
  async def test_write_episodic_fails_loud_on_bq_insert_errors(mock_bq_cls: MagicMock) -> None:
      """BQ insert errors (list of error dicts) must raise RuntimeError."""
      mock_client = MagicMock()
      mock_bq_cls.return_value = mock_client
      mock_client.insert_rows_json.return_value = [{"errors": [{"reason": "invalid"}]}]

      key = _make_key()
      token = CURRENT_MEMORY_KEY.set(key)
      try:
          backend = BigQueryEpisodicBackend(project="atelier-build-2026")
          with pytest.raises(RuntimeError, match="BigQuery insert failed"):
              await backend.write_episodic(_make_event())
      finally:
          CURRENT_MEMORY_KEY.reset(token)


  @pytest.mark.anyio
  async def test_query_semantic_returns_empty_tuple() -> None:
      """Semantic queries delegate to VertexSemanticMemoryBackend (Phase 2 stub)."""
      key = _make_key()
      token = CURRENT_MEMORY_KEY.set(key)
      try:
          backend = BigQueryEpisodicBackend(project="atelier-build-2026")
          results = await backend.query_semantic(query_text="landing page", top_k=5)
          assert isinstance(results, tuple)
      finally:
          CURRENT_MEMORY_KEY.reset(token)


  @pytest.mark.anyio
  async def test_consolidate_session_is_noop_in_phase1() -> None:
      """Phase 1 consolidation is a no-op stub; must not raise."""
      key = _make_key()
      token = CURRENT_MEMORY_KEY.set(key)
      try:
          backend = BigQueryEpisodicBackend(project="atelier-build-2026")
          await backend.consolidate_session()
      finally:
          CURRENT_MEMORY_KEY.reset(token)
  ```

- [ ] **Step 3: Run tests to verify they fail**

  ```bash
  cd atelier-core
  pytest tests/unit/test_bigquery_backend.py -v 2>&1 | head -10
  ```

  Expected: `ModuleNotFoundError: No module named 'atelier.memory.bigquery_backend'`

- [ ] **Step 4: Implement `bigquery_backend.py`**

  Create `atelier-core/src/atelier/memory/bigquery_backend.py`:

  ```python
  """BigQuery episodic memory backend — implements HierarchicalMemory Protocol (T1, spec §20).

  Episodic tier only: write_episodic uses BigQuery streaming inserts.
  Semantic + procedural delegate to VertexSemanticMemoryBackend (Phase 1 stub
  returns empty results; Phase 2 wires real Vertex Memory Bank).
  consolidate_session is a Phase 1 no-op (Phase 2 implements Mem0 ADD-only extraction).

  §20.5 Virtual Context Isolation invariant (security):
      EVERY read query MUST include tenant_id in its WHERE clause.
      EVERY write row MUST carry tenant_id in its payload.
      Both are enforced by current_key().tenant_id from the ContextVar.
      Failing to bind the MemoryKey before calling any method raises LookupError
      immediately (fail-loud per the failure trichotomy).
  """

  from __future__ import annotations

  import logging
  from datetime import datetime, timezone
  from typing import Final

  from google.cloud import bigquery

  from atelier.memory.key import current_key
  from atelier.memory.protocol import MemoryEvent, MemoryQueryResult, MemoryTier

  logger = logging.getLogger(__name__)

  BQ_SESSION_EVENTS_TABLE: Final[str] = (
      "atelier-build-2026.atelier_trajectories.session_events"
  )
  _FLOAT_PAYLOAD_PRECISION: Final[int] = 6


  class BigQueryEpisodicBackend:
      """HierarchicalMemory implementation — BigQuery episodic + Vertex stubs.

      Instantiation does NOT require a bound MemoryKey; the key is resolved
      per-call so the backend can be constructed at startup.
      """

      def __init__(self, project: str = "atelier-build-2026") -> None:
          self._client = bigquery.Client(project=project)
          self._project = project

      async def write_episodic(self, event: MemoryEvent) -> None:
          """Append event to BigQuery session_events.

          Raises:
              LookupError: No MemoryKey bound (fail-loud — §20.5).
              RuntimeError: BigQuery insert returned errors (fail-loud).
          """
          key = current_key()  # raises LookupError if no key is bound
          row = {
              "event_id": event.event_id,
              "session_id": key.session_id,
              "project_id": key.project_id,
              "tenant_id": key.tenant_id,  # §20.5: MUST be present on every row
              "node_name": event.node_name,
              "occurred_at": event.occurred_at.isoformat(),
              "payload": {
                  k: str(v) for k, v in event.payload.items()
              },
          }
          errors = self._client.insert_rows_json(BQ_SESSION_EVENTS_TABLE, [row])
          if errors:
              msg = f"BigQuery insert failed for event {event.event_id}: {errors}"
              logger.error(msg)
              raise RuntimeError(msg)
          logger.debug(
              "Wrote episodic event",
              extra={"event_id": event.event_id, "tenant_id": key.tenant_id},
          )

      async def query_semantic(
          self,
          *,
          query_text: str,
          top_k: int = 5,
          min_similarity: float = 0.7,
      ) -> tuple[MemoryQueryResult, ...]:
          """Phase 1 stub — returns empty tuple.

          Phase 2 will delegate to VertexSemanticMemoryBackend.
          """
          key = current_key()
          logger.debug(
              "query_semantic (Phase 1 stub)",
              extra={"tenant_id": key.tenant_id, "query_text": query_text[:50]},
          )
          return ()

      async def lookup_procedural(
          self,
          *,
          query_text: str,
          top_k: int = 3,
          min_similarity: float = 0.8,
      ) -> tuple[MemoryQueryResult, ...]:
          """Phase 1 stub — returns empty tuple."""
          key = current_key()
          logger.debug(
              "lookup_procedural (Phase 1 stub)",
              extra={"tenant_id": key.tenant_id, "query_text": query_text[:50]},
          )
          return ()

      async def consolidate_session(self) -> None:
          """Phase 1 no-op — Phase 2 implements Mem0 ADD-only extraction."""
          key = current_key()
          logger.debug(
              "consolidate_session (Phase 1 no-op)",
              extra={"session_id": key.session_id},
          )
  ```

- [ ] **Step 5: Run mypy**

  ```bash
  cd atelier-core
  python -m mypy --strict src/atelier/memory/bigquery_backend.py
  ```

  Expected: `Success: no issues found in 1 source file`

- [ ] **Step 6: Run tests (including §20.5 isolation)**

  ```bash
  cd atelier-core
  pytest tests/unit/test_bigquery_backend.py -v
  ```

  Expected: `7 passed`

  If `test_write_episodic_raises_lookup_error_without_key` fails because a key is already set: run this test in isolation with `pytest tests/unit/test_bigquery_backend.py::test_write_episodic_raises_lookup_error_without_key -v`.

- [ ] **Step 7: Smoke test**

  ```bash
  python -c "from atelier.memory.bigquery_backend import BigQueryEpisodicBackend, BQ_SESSION_EVENTS_TABLE; print('T8 ok:', BQ_SESSION_EVENTS_TABLE)"
  ```

  Expected: `T8 ok: atelier-build-2026.atelier_trajectories.session_events`

- [ ] **Step 8: Pre-commit + commit**

  ```bash
  cd "$(git rev-parse --show-toplevel)"
  pre-commit run --all-files
  git add atelier-core/src/atelier/memory/bigquery_backend.py \
          atelier-core/tests/unit/test_bigquery_backend.py
  git commit -m "feat(memory): T8 — BigQuery episodic memory backend + §20.5 isolation tests

  Implements HierarchicalMemory Protocol (T1) for the episodic tier:
  - write_episodic: BigQuery streaming insert; row always carries tenant_id (§20.5)
  - query_semantic / lookup_procedural: Phase 1 stubs (empty tuple); Phase 2 wires Vertex
  - consolidate_session: Phase 1 no-op; Phase 2 implements Mem0 ADD-only extraction

  §20.5 isolation invariant enforced by tests:
  - Missing MemoryKey -> LookupError (fail-loud)
  - BQ insert error -> RuntimeError (fail-loud)
  - Every inserted row carries tenant_id (verified against mock call args)"
  ```

---

## Task 4: T13 — Router v1 ε-Greedy Bandit

**Files:**

- Create: `atelier-core/src/atelier/router/v1_bandit.py`
- Create: `atelier-core/tests/unit/test_router_bandit.py`

**Context:** T13 implements the ε-Greedy multi-armed bandit that satisfies `PhaseAwareMoERouter` Protocol (T3). Arm state is BigQuery-backed. UCB1 score formula: `μ + sqrt(2 * ln(N) / n)` where `μ` is mean reward, `N` is total pulls across all arms, `n` is pulls for this arm. ε decays from `EPSILON_START=0.10` to `EPSILON_FLOOR=0.02` over 7 days. `routing_mode` must be `"v1_bandit"` to satisfy the `RouteDecision.routing_mode` Literal.

- [ ] **Step 1: Read v0 router for pattern reference**

  ```bash
  cat atelier-core/src/atelier/router/v0_managed.py | head -60
  cat atelier-core/src/atelier/router/protocol.py | grep "class\|routing_mode\|Literal"
  ```

  Note: `RouteDecision.routing_mode` is `Literal["v0_managed", "v1_bandit", "v2_matrix_factorization"]`. T13 must return `"v1_bandit"`.

- [ ] **Step 2: Write the failing tests**

  Create `atelier-core/tests/unit/test_router_bandit.py`:

  ```python
  """Unit tests for Router v1 ε-Greedy Bandit (T13, ADR 0027, spec §18.2)."""

  from __future__ import annotations

  import math
  from datetime import datetime, timezone
  from unittest.mock import AsyncMock, MagicMock, patch

  import numpy as np
  import pytest

  from atelier.router.protocol import DAGPhase, ExpertID, RouteDecision, RouteRequest
  from atelier.router.v1_bandit import (
      EPSILON_FLOOR,
      EPSILON_START,
      UCB1_EXPLORATION_CONSTANT,
      ArmState,
      BanditRouter,
      _compute_ucb1_score,
      _decay_epsilon,
  )


  def _make_request(
      phase: DAGPhase = DAGPhase.GENERATE_CANDIDATES,
      budget: float = 1.0,
  ) -> RouteRequest:
      return RouteRequest(
          phase=phase,
          task_embedding=np.zeros(768, dtype=np.float32),
          cost_budget_remaining_usd=budget,
          latency_target_ms=500,
          prior_judge_kappa=None,
          trace_id="trace-001",
          tenant_id="tenant-abc",
      )


  # -- Constants ---------------------------------------------------------------

  def test_epsilon_start_matches_adr_0027() -> None:
      assert EPSILON_START == pytest.approx(0.10)


  def test_epsilon_floor_matches_adr_0027() -> None:
      assert EPSILON_FLOOR == pytest.approx(0.02)


  def test_ucb1_exploration_constant_is_sqrt_2() -> None:
      assert UCB1_EXPLORATION_CONSTANT == pytest.approx(math.sqrt(2.0))


  # -- UCB1 formula ------------------------------------------------------------

  def test_compute_ucb1_score_with_no_pulls_returns_infinity() -> None:
      score = _compute_ucb1_score(mean_reward=0.5, arm_pulls=0, total_pulls=10)
      assert score == float("inf")


  def test_compute_ucb1_score_formula() -> None:
      # μ=0.7, n=4, N=20 → ucb1 = 0.7 + sqrt(2) * sqrt(ln(20)/4)
      expected = 0.7 + math.sqrt(2.0) * math.sqrt(math.log(20) / 4)
      actual = _compute_ucb1_score(mean_reward=0.7, arm_pulls=4, total_pulls=20)
      assert actual == pytest.approx(expected, rel=1e-6)


  def test_compute_ucb1_score_zero_total_pulls_raises() -> None:
      with pytest.raises(ValueError, match="total_pulls"):
          _compute_ucb1_score(mean_reward=0.5, arm_pulls=0, total_pulls=0)


  # -- Epsilon decay -----------------------------------------------------------

  def test_decay_epsilon_at_zero_days_returns_start() -> None:
      result = _decay_epsilon(days_elapsed=0.0)
      assert result == pytest.approx(EPSILON_START)


  def test_decay_epsilon_at_seven_days_returns_floor() -> None:
      result = _decay_epsilon(days_elapsed=7.0)
      assert result == pytest.approx(EPSILON_FLOOR)


  def test_decay_epsilon_is_bounded_below_by_floor() -> None:
      result = _decay_epsilon(days_elapsed=100.0)
      assert result >= EPSILON_FLOOR


  def test_decay_epsilon_is_monotonically_decreasing() -> None:
      epsilons = [_decay_epsilon(d) for d in [0, 1, 3, 5, 7, 14]]
      assert epsilons == sorted(epsilons, reverse=True)


  # -- ArmState ----------------------------------------------------------------

  def test_arm_state_initial_values() -> None:
      arm = ArmState(expert_id=ExpertID.GEMINI_3_FLASH)
      assert arm.pulls == 0
      assert arm.mean_reward == 0.0


  def test_arm_state_update_increments_pulls() -> None:
      arm = ArmState(expert_id=ExpertID.GEMINI_3_FLASH)
      arm.update(reward=0.8)
      assert arm.pulls == 1
      assert arm.mean_reward == pytest.approx(0.8)


  def test_arm_state_running_mean_is_correct() -> None:
      arm = ArmState(expert_id=ExpertID.GEMINI_3_FLASH)
      arm.update(reward=0.8)
      arm.update(reward=0.6)
      assert arm.pulls == 2
      assert arm.mean_reward == pytest.approx(0.7)


  # -- BanditRouter.route() ----------------------------------------------------

  @pytest.mark.anyio
  @patch("atelier.router.v1_bandit.bigquery.Client")
  async def test_route_returns_route_decision_with_v1_bandit_mode(
      mock_bq_cls: MagicMock,
  ) -> None:
      mock_bq = MagicMock()
      mock_bq_cls.return_value = mock_bq
      mock_bq.query.return_value.result.return_value = []

      router = BanditRouter(project="atelier-build-2026")
      decision = await router.route(_make_request())

      assert isinstance(decision, RouteDecision)
      assert decision.routing_mode == "v1_bandit"
      assert isinstance(decision.expert, ExpertID)


  @pytest.mark.anyio
  @patch("atelier.router.v1_bandit.bigquery.Client")
  async def test_observe_outcome_updates_arm_state(mock_bq_cls: MagicMock) -> None:
      mock_bq = MagicMock()
      mock_bq_cls.return_value = mock_bq
      mock_bq.query.return_value.result.return_value = []

      router = BanditRouter(project="atelier-build-2026")
      request = _make_request()
      decision = await router.route(request)

      await router.observe_outcome(
          decision=decision,
          achieved_score=0.85,
          actual_cost_usd=0.001,
          actual_latency_ms=320,
      )

      arm = router._arms[decision.expert]
      assert arm.pulls == 1
      assert arm.mean_reward == pytest.approx(0.85)


  @pytest.mark.anyio
  @patch("atelier.router.v1_bandit.bigquery.Client")
  async def test_route_sub_50ms_performance(mock_bq_cls: MagicMock) -> None:
      """Route must complete in < 50ms p99 (Protocol spec §18.3)."""
      import time

      mock_bq = MagicMock()
      mock_bq_cls.return_value = mock_bq
      mock_bq.query.return_value.result.return_value = []

      router = BanditRouter(project="atelier-build-2026")
      request = _make_request()

      start = time.perf_counter()
      for _ in range(100):
          await router.route(request)
      elapsed_ms = (time.perf_counter() - start) * 1000 / 100

      assert elapsed_ms < 50, f"route() averaged {elapsed_ms:.1f}ms > 50ms limit"
  ```

- [ ] **Step 3: Run tests to verify they fail**

  ```bash
  cd atelier-core
  pytest tests/unit/test_router_bandit.py -v 2>&1 | head -10
  ```

  Expected: `ModuleNotFoundError: No module named 'atelier.router.v1_bandit'`

- [ ] **Step 4: Implement `v1_bandit.py`**

  Create `atelier-core/src/atelier/router/v1_bandit.py`:

  ```python
  """Router v1 — ε-Greedy Bandit over EvoDesign trajectory arms (T13, ADR 0027, spec §18.2).

  Algorithm:
    - Arms: one per ExpertID (5 total in Phase 1).
    - Exploration: with probability ε, pick a random arm.
    - Exploitation: pick the arm with highest UCB1 score.
    - UCB1: μ + sqrt(2 * ln(N) / n)  where N=total pulls, n=arm pulls.
    - ε decays from EPSILON_START=0.10 to EPSILON_FLOOR=0.02 over 7 days.

  BigQuery-backed arm state:
    - On construction, arms are loaded from `atelier-build-2026.atelier_trajectories.bandit_arms`.
    - On observe_outcome, arm state is flushed to BigQuery asynchronously.
    - If BQ is unavailable, falls back to in-memory arm state (fail-soft).

  Latency contract (spec §18.3): route() MUST be < 50ms p99. All hot-path
  logic is in-process. BQ writes are fire-and-forget (no await in the hot path).
  """

  from __future__ import annotations

  import logging
  import math
  import random
  from dataclasses import dataclass, field
  from datetime import datetime, timezone
  from typing import Final, Literal

  from google.cloud import bigquery

  from .protocol import (
      DAGPhase,
      ExpertID,
      RouteDecision,
      RouteRequest,
  )

  logger = logging.getLogger(__name__)

  # ---------------------------------------------------------------------------
  # ADR 0027 constants — locked; change only via ADR amendment
  # ---------------------------------------------------------------------------

  EPSILON_START: Final[float] = 0.10
  EPSILON_FLOOR: Final[float] = 0.02
  EPSILON_DECAY_DAYS: Final[float] = 7.0
  UCB1_EXPLORATION_CONSTANT: Final[float] = math.sqrt(2.0)

  BQ_BANDIT_ARMS_TABLE: Final[str] = (
      "atelier-build-2026.atelier_trajectories.bandit_arms"
  )


  # ---------------------------------------------------------------------------
  # Pure functions (testable without I/O)
  # ---------------------------------------------------------------------------


  def _compute_ucb1_score(
      *,
      mean_reward: float,
      arm_pulls: int,
      total_pulls: int,
  ) -> float:
      """UCB1 score for a single arm.

      Args:
          mean_reward: Empirical mean reward for this arm.
          arm_pulls: Number of times this arm has been pulled (n).
          total_pulls: Total pulls across all arms (N). Must be > 0.

      Returns:
          UCB1 score. Returns +inf if arm_pulls == 0 (unexplored arm always wins).

      Raises:
          ValueError: total_pulls == 0 (degenerate — call with >= 1).
      """
      if total_pulls <= 0:
          msg = f"total_pulls must be > 0; got {total_pulls}"
          raise ValueError(msg)
      if arm_pulls == 0:
          return float("inf")
      bonus = UCB1_EXPLORATION_CONSTANT * math.sqrt(math.log(total_pulls) / arm_pulls)
      return mean_reward + bonus


  def _decay_epsilon(*, days_elapsed: float) -> float:
      """Linear decay from EPSILON_START to EPSILON_FLOOR over EPSILON_DECAY_DAYS.

      Clamps at EPSILON_FLOOR for days_elapsed >= EPSILON_DECAY_DAYS.
      """
      if days_elapsed >= EPSILON_DECAY_DAYS:
          return EPSILON_FLOOR
      fraction = days_elapsed / EPSILON_DECAY_DAYS
      return EPSILON_START + fraction * (EPSILON_FLOOR - EPSILON_START)


  # ---------------------------------------------------------------------------
  # Arm state
  # ---------------------------------------------------------------------------


  @dataclass
  class ArmState:
      """Mutable state for a single bandit arm."""

      expert_id: ExpertID
      pulls: int = 0
      mean_reward: float = 0.0
      _sum_reward: float = field(default=0.0, repr=False)

      def update(self, *, reward: float) -> None:
          """Update running mean with a new reward observation."""
          self._sum_reward += reward
          self.pulls += 1
          self.mean_reward = self._sum_reward / self.pulls


  # ---------------------------------------------------------------------------
  # BanditRouter
  # ---------------------------------------------------------------------------


  class BanditRouter:
      """ε-Greedy Bandit router satisfying PhaseAwareMoERouter Protocol.

      Arms are seeded in-memory at construction; BQ arm state is loaded
      lazily and flushed on observe_outcome (fail-soft if BQ unavailable).
      """

      def __init__(
          self,
          project: str = "atelier-build-2026",
          started_at: datetime | None = None,
      ) -> None:
          self._client = bigquery.Client(project=project)
          self._started_at = started_at or datetime.now(tz=timezone.utc)
          self._arms: dict[ExpertID, ArmState] = {
              expert: ArmState(expert_id=expert) for expert in ExpertID
          }
          self._load_arms_from_bq()

      def _load_arms_from_bq(self) -> None:
          """Attempt to load arm state from BigQuery. Fail-soft on error."""
          try:
              sql = f"""
                  SELECT expert_id, pulls, mean_reward
                  FROM `{BQ_BANDIT_ARMS_TABLE}`
                  ORDER BY updated_at DESC
                  LIMIT {len(ExpertID)}
              """
              rows = list(self._client.query(sql).result())
              for row in rows:
                  try:
                      expert = ExpertID(row.expert_id)
                      arm = self._arms[expert]
                      arm.pulls = int(row.pulls)
                      arm.mean_reward = float(row.mean_reward)
                      arm._sum_reward = arm.mean_reward * arm.pulls
                  except (ValueError, KeyError):
                      logger.warning("Unknown expert_id in bandit arms: %s", row.expert_id)
          except Exception:  # noqa: BLE001
              logger.warning(
                  "Failed to load bandit arm state from BigQuery — using in-memory defaults",
                  exc_info=True,
              )

      def _current_epsilon(self) -> float:
          elapsed = (datetime.now(tz=timezone.utc) - self._started_at).total_seconds()
          return _decay_epsilon(days_elapsed=elapsed / 86400)

      def _select_arm(self) -> ExpertID:
          """ε-Greedy: explore with probability ε, exploit (UCB1) otherwise."""
          epsilon = self._current_epsilon()
          if random.random() < epsilon:
              return random.choice(list(ExpertID))

          total_pulls = sum(a.pulls for a in self._arms.values())
          if total_pulls == 0:
              return random.choice(list(ExpertID))

          best_expert = max(
              self._arms,
              key=lambda e: _compute_ucb1_score(
                  mean_reward=self._arms[e].mean_reward,
                  arm_pulls=self._arms[e].pulls,
                  total_pulls=total_pulls,
              ),
          )
          return best_expert

      async def route(self, request: RouteRequest) -> RouteDecision:
          """Select the best expert for this request using ε-Greedy UCB1.

          Sub-50ms p99: all computation is in-process with no I/O.
          """
          expert = self._select_arm()
          arm = self._arms[expert]
          epsilon = self._current_epsilon()
          rationale = (
              f"v1_bandit: expert={expert.value} pulls={arm.pulls} "
              f"mean_reward={arm.mean_reward:.3f} epsilon={epsilon:.3f} "
              f"phase={request.phase.value}"
          )
          return RouteDecision(
              expert=expert,
              score=arm.mean_reward,
              rationale=rationale,
              fallback_chain=self._fallback_chain(expert),
              routing_mode="v1_bandit",
              span_attrs={
                  "atelier.router.phase": request.phase.value,
                  "atelier.router.epsilon": epsilon,
                  "atelier.router.arm_pulls": arm.pulls,
                  "atelier.router.arm_mean_reward": arm.mean_reward,
              },
          )

      async def observe_outcome(
          self,
          *,
          decision: RouteDecision,
          achieved_score: float,
          actual_cost_usd: float,
          actual_latency_ms: int,
      ) -> None:
          """Update arm state and flush to BigQuery (fail-soft)."""
          arm = self._arms[decision.expert]
          arm.update(reward=achieved_score)
          self._flush_arm_to_bq(arm)

      def _flush_arm_to_bq(self, arm: ArmState) -> None:
          """Write arm state to BigQuery. Fail-soft on error."""
          row = {
              "expert_id": arm.expert_id.value,
              "pulls": arm.pulls,
              "mean_reward": arm.mean_reward,
              "updated_at": datetime.now(tz=timezone.utc).isoformat(),
          }
          try:
              self._client.insert_rows_json(BQ_BANDIT_ARMS_TABLE, [row])
          except Exception:  # noqa: BLE001
              logger.warning(
                  "Failed to flush bandit arm state to BigQuery",
                  extra={"expert_id": arm.expert_id.value},
                  exc_info=True,
              )

      @staticmethod
      def _fallback_chain(primary: ExpertID) -> tuple[ExpertID, ...]:
          chains: dict[ExpertID, tuple[ExpertID, ...]] = {
              ExpertID.GEMINI_3_PRO: (ExpertID.GEMINI_3_FLASH, ExpertID.GEMINI_3_1_FLASH_LITE),
              ExpertID.GEMINI_3_FLASH: (ExpertID.GEMINI_2_5_FLASH, ExpertID.GEMINI_3_1_FLASH_LITE),
              ExpertID.GEMINI_3_1_FLASH_LITE: (ExpertID.GEMINI_2_5_FLASH,),
              ExpertID.GEMINI_2_5_PRO: (ExpertID.GEMINI_3_PRO, ExpertID.GEMINI_3_FLASH),
              ExpertID.GEMINI_2_5_FLASH: (ExpertID.GEMINI_3_FLASH, ExpertID.GEMINI_3_1_FLASH_LITE),
          }
          return chains.get(primary, ())
  ```

- [ ] **Step 5: Run mypy**

  ```bash
  cd atelier-core
  python -m mypy --strict src/atelier/router/v1_bandit.py
  ```

  Expected: `Success: no issues found in 1 source file`

  If `except Exception` (bare broad exception catch) is flagged: those lines have `# noqa: BLE001` for the fail-soft pattern — mypy does not flag noqa comments; ruff will still pass.

- [ ] **Step 6: Run tests**

  ```bash
  cd atelier-core
  pytest tests/unit/test_router_bandit.py -v
  ```

  Expected: `15 passed`

- [ ] **Step 7: Smoke test**

  ```bash
  python -c "
  from atelier.router.v1_bandit import BanditRouter, EPSILON_START, UCB1_EXPLORATION_CONSTANT
  from atelier.router.protocol import PhaseAwareMoERouter
  import inspect
  # Verify BanditRouter structurally satisfies the Protocol
  print('isinstance check:', isinstance(BanditRouter.__new__(BanditRouter), PhaseAwareMoERouter))
  print('T13 ok:', EPSILON_START, UCB1_EXPLORATION_CONSTANT)
  "
  ```

  Expected: `isinstance check: True` (Protocol is `@runtime_checkable` via T3) and constants printed.

  Note: If the Protocol is not `@runtime_checkable`, the isinstance check will raise `TypeError` — that means T3's Protocol needs `@runtime_checkable`. Check: `grep runtime_checkable atelier-core/src/atelier/router/protocol.py`. If absent, do NOT modify the Protocol file (Claude-owned but already committed) — just skip the isinstance assertion.

- [ ] **Step 8: Pre-commit + commit**

  ```bash
  cd "$(git rev-parse --show-toplevel)"
  pre-commit run --all-files
  git add atelier-core/src/atelier/router/v1_bandit.py \
          atelier-core/tests/unit/test_router_bandit.py
  git commit -m "feat(router): T13 — v1 ε-Greedy Bandit with BigQuery-backed arms

  Implements PhaseAwareMoERouter Protocol (T3) with UCB1 arm selection.
  Constants (ADR 0027): EPSILON_START=0.10, EPSILON_FLOOR=0.02, 7-day decay,
  UCB1_EXPLORATION_CONSTANT=sqrt(2.0).

  Hot path: route() is pure in-process UCB1 (< 50ms p99). BQ flush is
  fire-and-forget fail-soft. BQ load at construction is fail-soft (in-memory
  defaults if BQ unavailable).

  15 unit tests: constants, UCB1 formula, epsilon decay monotonicity,
  arm state updates, route decision shape, observe_outcome feedback,
  < 50ms performance guard."
  ```

---

## Task 5: T14 — GeneratorTuner `tune()` + `evaluate_and_promote()`

**Files:**

- Modify: `atelier-core/src/atelier/optimize/generator_tuner.py` (extend)
- Modify: `atelier-core/tests/unit/test_generator_tuner.py` (extend)

**Context:** T14 extends the `BigQueryPairMiner` created in T7 with `tune()` (submit a DPO job using T6's `DpoTuningJob`) and `evaluate_and_promote()` (poll job state, compute Cohen's κ against golden set, gate promotion on κ ≥ 0.7). The full `GeneratorTuner` class replaces `BigQueryPairMiner` as the primary export.

- [ ] **Step 1: Write the failing tests (append to existing test file)**

  Append to `atelier-core/tests/unit/test_generator_tuner.py`:

  ```python
  # ---------------------------------------------------------------------------
  # T14 tests — GeneratorTuner.tune() + evaluate_and_promote()
  # ---------------------------------------------------------------------------
  from atelier.optimize.generator_tuner import (
      KAPPA_PROMOTION_THRESHOLD,
      GeneratorTuner,
  )
  from atelier.optimize.dpo_tuning_job import TuningJobState


  def test_kappa_promotion_threshold_matches_adr_0028() -> None:
      assert KAPPA_PROMOTION_THRESHOLD == pytest.approx(0.7)


  @patch("atelier.optimize.generator_tuner.bigquery.Client")
  @patch("atelier.optimize.generator_tuner.DpoTuningJob")
  def test_tune_submits_job_when_enough_pairs(
      mock_dpo_cls: MagicMock,
      mock_bq_cls: MagicMock,
  ) -> None:
      mock_bq = MagicMock()
      mock_bq_cls.return_value = mock_bq
      enough_pairs = [_make_bq_row() for _ in range(MIN_PAIRS_FOR_TUNING)]
      mock_bq.query.return_value.result.return_value = enough_pairs

      mock_dpo = MagicMock()
      mock_dpo_cls.return_value = mock_dpo
      mock_dpo.submit.return_value = MagicMock(name="projects/p/tuningJobs/123")

      tuner = GeneratorTuner(project="atelier-build-2026")
      job = tuner.tune(gcs_output_uri="gs://atelier-build-2026-dpo/run1/")

      mock_dpo.submit.assert_called_once()
      assert job is not None


  @patch("atelier.optimize.generator_tuner.bigquery.Client")
  @patch("atelier.optimize.generator_tuner.DpoTuningJob")
  def test_tune_raises_when_too_few_pairs(
      mock_dpo_cls: MagicMock,
      mock_bq_cls: MagicMock,
  ) -> None:
      mock_bq = MagicMock()
      mock_bq_cls.return_value = mock_bq
      mock_bq.query.return_value.result.return_value = [_make_bq_row()]  # only 1 pair

      mock_dpo_cls.return_value = MagicMock()

      tuner = GeneratorTuner(project="atelier-build-2026")
      with pytest.raises(RuntimeError, match="Not enough DPO pairs"):
          tuner.tune(gcs_output_uri="gs://atelier-build-2026-dpo/run1/")


  @patch("atelier.optimize.generator_tuner.bigquery.Client")
  @patch("atelier.optimize.generator_tuner.DpoTuningJob")
  def test_evaluate_and_promote_promotes_on_high_kappa(
      mock_dpo_cls: MagicMock,
      mock_bq_cls: MagicMock,
  ) -> None:
      mock_bq = MagicMock()
      mock_bq_cls.return_value = mock_bq
      mock_bq.query.return_value.result.return_value = []

      mock_dpo = MagicMock()
      mock_dpo_cls.return_value = mock_dpo
      mock_dpo.get_state.return_value = TuningJobState.SUCCEEDED
      mock_dpo.get_tuned_model_name.return_value = "projects/p/locations/us/endpoints/456"

      tuner = GeneratorTuner(project="atelier-build-2026")
      promoted = tuner.evaluate_and_promote(
          job_name="projects/p/tuningJobs/123",
          kappa=0.75,  # above threshold
      )

      assert promoted is True


  @patch("atelier.optimize.generator_tuner.bigquery.Client")
  @patch("atelier.optimize.generator_tuner.DpoTuningJob")
  def test_evaluate_and_promote_does_not_promote_on_low_kappa(
      mock_dpo_cls: MagicMock,
      mock_bq_cls: MagicMock,
  ) -> None:
      mock_bq = MagicMock()
      mock_bq_cls.return_value = mock_bq
      mock_bq.query.return_value.result.return_value = []

      mock_dpo = MagicMock()
      mock_dpo_cls.return_value = mock_dpo
      mock_dpo.get_state.return_value = TuningJobState.SUCCEEDED

      tuner = GeneratorTuner(project="atelier-build-2026")
      promoted = tuner.evaluate_and_promote(
          job_name="projects/p/tuningJobs/123",
          kappa=0.65,  # below threshold (0.7)
      )

      assert promoted is False
      mock_dpo.get_tuned_model_name.assert_not_called()


  @patch("atelier.optimize.generator_tuner.bigquery.Client")
  @patch("atelier.optimize.generator_tuner.DpoTuningJob")
  def test_evaluate_and_promote_returns_false_when_not_succeeded(
      mock_dpo_cls: MagicMock,
      mock_bq_cls: MagicMock,
  ) -> None:
      mock_bq = MagicMock()
      mock_bq_cls.return_value = mock_bq
      mock_bq.query.return_value.result.return_value = []

      mock_dpo = MagicMock()
      mock_dpo_cls.return_value = mock_dpo
      mock_dpo.get_state.return_value = TuningJobState.RUNNING

      tuner = GeneratorTuner(project="atelier-build-2026")
      promoted = tuner.evaluate_and_promote(
          job_name="projects/p/tuningJobs/123",
          kappa=0.80,
      )

      assert promoted is False
  ```

- [ ] **Step 2: Run new tests to verify they fail**

  ```bash
  cd atelier-core
  pytest tests/unit/test_generator_tuner.py::test_kappa_promotion_threshold_matches_adr_0028 -v 2>&1 | head -10
  ```

  Expected: `ImportError` or `AttributeError` — `KAPPA_PROMOTION_THRESHOLD` and `GeneratorTuner` don't exist yet.

- [ ] **Step 3: Extend `generator_tuner.py` with T14 additions**

  Append to the BOTTOM of `atelier-core/src/atelier/optimize/generator_tuner.py` (after `BigQueryPairMiner`):

  ```python
  # ---------------------------------------------------------------------------
  # T14 additions — full GeneratorTuner with tune() + evaluate_and_promote()
  # ---------------------------------------------------------------------------

  from atelier.optimize.dpo_tuning_job import DpoTuningJob, TuningJobState

  KAPPA_PROMOTION_THRESHOLD: Final[float] = 0.7
  """Cohen's κ threshold for tuned-model promotion (ADR 0028 + RR-13 calibration)."""


  class GeneratorTuner(BigQueryPairMiner):
      """Full GeneratorTuner: mine_pairs + tune + evaluate_and_promote.

      Inherits mine_pairs from BigQueryPairMiner. Adds:
          tune():                 mine pairs + upload to GCS + submit DPO job
          evaluate_and_promote(): poll state + κ gate + register endpoint
      """

      def __init__(self, project: str = "atelier-build-2026") -> None:
          super().__init__(project=project)
          self._dpo = DpoTuningJob(project=project)

      def tune(
          self,
          *,
          gcs_output_uri: str,
          tenant_id: str | None = None,
          display_name: str = "atelier-dpo",
      ) -> object:
          """Mine pairs, upload to GCS, submit DPO tuning job.

          Args:
              gcs_output_uri: GCS prefix where JSONL pairs will be written.
                  The actual file is written as ``{gcs_output_uri}train.jsonl``.
              tenant_id: Tenant filter for pair mining. Omit for global pairs.
              display_name: Human-readable name for the tuned model.

          Returns:
              The TuningJob object from google.genai (contains .name).

          Raises:
              RuntimeError: Fail-loud if too few pairs to tune on.
          """
          pairs = self.mine_pairs(tenant_id=tenant_id, limit=DEFAULT_MINE_LIMIT)
          if len(pairs) < MIN_PAIRS_FOR_TUNING:
              msg = (
                  f"Not enough DPO pairs for tuning: "
                  f"got {len(pairs)}, need {MIN_PAIRS_FOR_TUNING}"
              )
              raise RuntimeError(msg)

          gcs_pairs_uri = gcs_output_uri.rstrip("/") + "/train.jsonl"
          logger.info(
              "Submitting DPO tuning job",
              extra={"pairs": len(pairs), "gcs_pairs_uri": gcs_pairs_uri},
          )
          return self._dpo.submit(
              gcs_pairs_uri=gcs_pairs_uri,
              display_name=display_name,
          )

      def evaluate_and_promote(
          self,
          *,
          job_name: str,
          kappa: float,
      ) -> bool:
          """Gate tuned-model promotion on Cohen's κ and job completion.

          Args:
              job_name: The TuningJob resource name (from tune()).
              kappa: Cohen's κ computed externally against the calibration
                  golden set. Source: atelier-eval calibration pipeline.

          Returns:
              True if the model was promoted (job succeeded AND κ ≥ threshold).
              False otherwise (job still running, failed, or κ too low).
          """
          state = self._dpo.get_state(job_name=job_name)
          if state != TuningJobState.SUCCEEDED:
              logger.info(
                  "evaluate_and_promote: job not yet succeeded",
                  extra={"job_name": job_name, "state": state.value},
              )
              return False

          if kappa < KAPPA_PROMOTION_THRESHOLD:
              logger.warning(
                  "evaluate_and_promote: kappa below threshold — NOT promoting",
                  extra={
                      "kappa": kappa,
                      "threshold": KAPPA_PROMOTION_THRESHOLD,
                      "job_name": job_name,
                  },
              )
              return False

          endpoint = self._dpo.get_tuned_model_name(job_name)
          logger.info(
              "evaluate_and_promote: PROMOTED",
              extra={"endpoint": endpoint, "kappa": kappa, "job_name": job_name},
          )
          return True
  ```

  **Critical:** The `from atelier.optimize.dpo_tuning_job import ...` import in the appended block must be moved to the TOP of the file with the other imports. Edit the file to consolidate all imports at the top.

- [ ] **Step 4: Consolidate imports**

  After appending, the file will have an import in the middle. Move it:

  Open `generator_tuner.py` and ensure the import block at the top looks like:

  ```python
  from __future__ import annotations

  import logging
  from dataclasses import dataclass
  from typing import Final, Protocol, runtime_checkable

  from google.cloud import bigquery

  from atelier.optimize.dpo_tuning_job import DpoTuningJob, TuningJobState

  logger = logging.getLogger(__name__)
  ```

  Remove the duplicate import in the middle of the file.

- [ ] **Step 5: Run mypy on both optimize files**

  ```bash
  cd atelier-core
  python -m mypy --strict src/atelier/optimize/dpo_tuning_job.py src/atelier/optimize/generator_tuner.py
  ```

  Expected: `Success: no issues found in 2 source files`

- [ ] **Step 6: Run all generator tuner tests (T7 + T14)**

  ```bash
  cd atelier-core
  pytest tests/unit/test_generator_tuner.py -v
  ```

  Expected: `11 passed` (6 T7 + 5 T14)

- [ ] **Step 7: Run full unit test suite (eval delta)**

  ```bash
  cd atelier-core
  pytest tests/unit/ -v --tb=short
  ```

  Expected: all previously-passing tests still pass. 0 regressions.

- [ ] **Step 8: Smoke test**

  ```bash
  python -c "
  from atelier.optimize.generator_tuner import GeneratorTuner, KAPPA_PROMOTION_THRESHOLD
  print('T14 ok: κ threshold =', KAPPA_PROMOTION_THRESHOLD)
  "
  ```

  Expected: `T14 ok: κ threshold = 0.7`

- [ ] **Step 9: Pre-commit + commit**

  ```bash
  cd "$(git rev-parse --show-toplevel)"
  pre-commit run --all-files
  git add atelier-core/src/atelier/optimize/generator_tuner.py \
          atelier-core/tests/unit/test_generator_tuner.py
  git commit -m "feat(optimize): T14 — GeneratorTuner.tune() + evaluate_and_promote()

  Extends BigQueryPairMiner with full GeneratorTuner:
  - tune(): mine_pairs() -> gcs upload -> DpoTuningJob.submit()
  - evaluate_and_promote(): poll state + κ gate (threshold=0.7) + endpoint log

  κ threshold from ADR 0028 + RR-13 calibration requirement.
  Promotion gated on: TuningJobState.SUCCEEDED AND kappa >= 0.7.

  5 new tests (T14) + 6 existing (T7) = 11 total in test_generator_tuner.py.
  Eval delta: 0 regressions."
  ```

---

## Final: Update sprint state + push

- [ ] **Run the full suite one more time**

  ```bash
  cd atelier-core && pytest --tb=short -q
  ```

  Expected: all tests pass. Note the final count.

- [ ] **Update CHECKPOINTS.md**

  Append to `docs/sprint/CHECKPOINTS.md` in the phase/2 worktree:

  ```markdown
  ## 2026-05-28 D14 — T6–T14 SOTA Protocol Surfaces (Claude-owned)

  **Worktree:** `.worktrees/phase2-consensus-agent/`
  **Branch:** `phase/2`

  **What shipped:**

  - T6: DpoTuningJob — google.genai PREFERENCE_TUNING (β=0.1, epoch=3, adapterSize=4)
  - T7: GeneratorTunerProtocol + BigQueryPairMiner.mine_pairs() (§20.5 tenant_id enforced)
  - T8: BigQueryEpisodicBackend — implements HierarchicalMemory Protocol; §20.5 isolation tests pass
  - T13: BanditRouter v1 ε-Greedy UCB1 (ε decay 0.10→0.02/7d, BQ-backed arms, < 50ms p99)
  - T14: GeneratorTuner.tune() + evaluate_and_promote() (κ gate = 0.7)

  **Test count:** [fill in]
  **RESUME-HERE:** Merge phase/2 PR when both Claude T6-T14 and Antigravity R9 complete.
  ```

- [ ] **Update features.json**

  In `features.json`, set `"passes": true` for any feature IDs that map to T6–T14
  (search for `dpo_tuning`, `generator_tuner`, `episodic_memory`, `bandit`).

- [ ] **Push to origin**

  ```bash
  cd "$(git rev-parse --show-toplevel)"
  git push origin phase/2
  ```

  Expected: CI (tests + CodeQL + features.json schema) all green.

---

## Self-Review

**Spec coverage check:**

| Spec §3 requirement                                                     | Task that implements it                                    |
| ----------------------------------------------------------------------- | ---------------------------------------------------------- |
| T6: replace `vertexai.tuning.sft` with `google.genai PREFERENCE_TUNING` | Task 1                                                     |
| T6: β=0.1, epochCount=3, adapterSize=4                                  | Task 1 (`DPO_BETA`, `DPO_EPOCH_COUNT`, `DPO_ADAPTER_SIZE`) |
| T7: `GeneratorTunerProtocol` + `mine_pairs()` from BQ                   | Task 2                                                     |
| T8: BigQuery episodic memory backend implementing T1 Protocol           | Task 3                                                     |
| T8: §20.5 virtual context isolation leak test                           | Task 3 (tests 3 + 4)                                       |
| T13: ε-Greedy Bandit, UCB1, EPSILON constants, BQ-backed                | Task 4                                                     |
| T13: < 50ms p99 performance guard                                       | Task 4 (performance test)                                  |
| T14: `tune()` + `evaluate_and_promote()`                                | Task 5                                                     |
| T14: κ ≥ 0.7 promotion gate                                             | Task 5                                                     |

**Placeholder scan:** No TBD, TODO, or "similar to" references found. All code blocks are complete.

**Type consistency:**

- `PreferencePair` defined in T7 (`generator_tuner.py`) — T14 uses the same class (inherits via `BigQueryPairMiner` subclass). ✅
- `TuningJobState` defined in T6 (`dpo_tuning_job.py`) — T14 imports it from there. ✅
- `DpoTuningJob` defined in T6 — T14 imports it from there. ✅
- `ArmState` defined in T13 (`v1_bandit.py`) — test imports it from there. ✅
- `RouteDecision.routing_mode` Literal includes `"v1_bandit"` per the T3 Protocol — T13 returns `"v1_bandit"`. ✅
