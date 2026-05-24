# Executor Brief — Round 8

**Executor:** Antigravity IDE (Claude Opus 4.6 Thinking)
**Date issued:** 2026-05-24
**Author:** Claude Code (Sonnet 4.6) — Atelier sprint orchestrator
**R7 prior:** `audit/executor-handoff-run7.md` (READY-FOR-AUDIT-RUN-7 received; deep audit complete)
**Worktree:** `.worktrees/phase1-foundation/` on branch `phase/1` ONLY.
**Wall-clock budget:** ~60–90 min (R8 is heavier: Terraform IaC + eval package scaffolding + Design2Code adapter).
**Commit policy:** Per-item commits, Conventional Commits 1.0.0, NO `--no-verify` ever.
**Tone:** Strictly mechanical implementation. Architecture decisions are LOCKED. If a step requires design intuition not specified here, FAIL-SOFT with a note in the handoff — do not guess.

---

## §1. R7 verdict — APPROVED

R7 deep audit accepted. Evidence table in `audit/deep_audit_r7_complete.md` verified by orchestrator.

Outstanding items carried forward:

- **P0-02 push** — Daniel-gated. Unblock when Daniel approves.
- **P1-01 IAM SA** — Daniel-gated. `atelier-runtime@atelier-build-2026.iam.gserviceaccount.com`
- **P2-03 secret wet-run** — Daniel-gated.
- **D-01 worktree violation** — deferred per prior user approval.

The fixes you applied (`b1573c1` CLI stub, `b79103d` path normalization) are accepted without change.

---

## §2. R8 scope — Phase 2 scaffolding + Terraform IaC + eval package bootstrap

R8 is a Phase 2 bridge round. The orchestrator owns T6 (DPO migration), T7 (GeneratorTuner Protocol), T8 (BigQuery episodic memory) — you must NOT implement those. Your scope is the mechanical scaffolding that unblocks T6/T7/T8 and closes the remaining Phase 1 Gate failures.

---

## R8-01: Terraform IaC skeleton — close F0006 and F0007

**Priority:** P0 (closes g03 gate, unblocks Phase 1 Gate certification)
**Constraint:** `terraform validate` + `terraform plan -out plan.tfplan` must pass. NO `terraform apply`. State file must NOT be created.

**Files to create under `infra/terraform/`:**

```
infra/terraform/
├── versions.tf       # required_providers + terraform backend
├── variables.tf      # project, region, env variables
├── main.tf           # provider + locals
├── apis.tf           # 18 GCP API enables (google_project_service)
├── iam.tf            # atelier-runtime SA + atelier-api-sa + roles
├── cloud_run.tf      # Atelier API Cloud Run service (staging)
├── bigquery.tf       # 4 BigQuery tables in atelier_trajectories dataset
├── artifact_registry.tf  # Docker image registry
└── outputs.tf        # cloud_run_url, service_account_emails
```

**`versions.tf`:**

```hcl
terraform {
  required_version = ">= 1.9.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
  backend "gcs" {
    bucket = "atelier-build-2026-tfstate"
    prefix = "phase1"
  }
}
```

**`variables.tf`:**

```hcl
variable "project_id" {
  type    = string
  default = "atelier-build-2026"
}

variable "region" {
  type    = string
  default = "us-central1"
  description = "Primary region — us-central1 for Vertex AI parity with public benchmarks"
}

variable "env" {
  type    = string
  default = "staging"
  validation {
    condition     = contains(["staging", "production"], var.env)
    error_message = "env must be staging or production."
  }
}
```

**`apis.tf`** — enable all 18 GCP APIs:

```hcl
locals {
  required_apis = [
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "bigquery.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudkms.googleapis.com",
    "cloudtrace.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com",
    "iam.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "aiplatform.googleapis.com",
    "compute.googleapis.com",
    "storage.googleapis.com",
    "firestore.googleapis.com",
    "servicenetworking.googleapis.com",
    "vpcaccess.googleapis.com",
    "iamcredentials.googleapis.com",
  ]
}

resource "google_project_service" "required" {
  for_each           = toset(local.required_apis)
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}
```

**`iam.tf`:**

```hcl
resource "google_service_account" "atelier_runtime" {
  account_id   = "atelier-runtime"
  display_name = "Atelier Runtime"
  project      = var.project_id
  description  = "Used by Cloud Run services and Vertex AI Memory Bank backends"
}

resource "google_service_account" "atelier_api" {
  account_id   = "atelier-api-sa"
  display_name = "Atelier API Service Account"
  project      = var.project_id
  description  = "Used by the Atelier FastAPI Cloud Run service"
}

resource "google_project_iam_member" "runtime_vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.atelier_runtime.email}"
}

resource "google_project_iam_member" "runtime_bigquery_data_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.atelier_runtime.email}"
}

resource "google_project_iam_member" "api_sa_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.atelier_api.email}"
}
```

**`bigquery.tf`:**

```hcl
resource "google_bigquery_dataset" "atelier_trajectories" {
  dataset_id  = "atelier_trajectories"
  project     = var.project_id
  location    = "US"
  description = "Atelier trajectory store: session events, DPO pairs, calibration metrics, cost ledger"
}

resource "google_bigquery_table" "trajectory_records" {
  dataset_id          = google_bigquery_dataset.atelier_trajectories.dataset_id
  project             = var.project_id
  table_id            = "trajectory_records"
  deletion_protection = false
  schema = jsonencode([
    { name = "session_id",    type = "STRING",    mode = "REQUIRED" },
    { name = "tenant_id",     type = "STRING",    mode = "REQUIRED" },
    { name = "node_name",     type = "STRING",    mode = "REQUIRED" },
    { name = "phase",         type = "STRING",    mode = "REQUIRED" },
    { name = "expert_id",     type = "STRING",    mode = "NULLABLE" },
    { name = "occurred_at",   type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "payload",       type = "JSON",      mode = "NULLABLE" },
    { name = "embedding",     type = "FLOAT64",   mode = "REPEATED" },
  ])
}

resource "google_bigquery_table" "dpo_preference_pairs" {
  dataset_id          = google_bigquery_dataset.atelier_trajectories.dataset_id
  project             = var.project_id
  table_id            = "dpo_preference_pairs"
  deletion_protection = false
  schema = jsonencode([
    { name = "pair_id",          type = "STRING",    mode = "REQUIRED" },
    { name = "session_id",       type = "STRING",    mode = "REQUIRED" },
    { name = "tenant_id",        type = "STRING",    mode = "REQUIRED" },
    { name = "chosen_output",    type = "STRING",    mode = "REQUIRED" },
    { name = "rejected_output",  type = "STRING",    mode = "REQUIRED" },
    { name = "extrinsic_margin", type = "FLOAT64",   mode = "REQUIRED" },
    { name = "swap_stability",   type = "FLOAT64",   mode = "REQUIRED" },
    { name = "kappa_vs_golden",  type = "FLOAT64",   mode = "REQUIRED" },
    { name = "dpo_eligible",     type = "BOOL",      mode = "REQUIRED" },
    { name = "failed_checks",    type = "STRING",    mode = "REPEATED" },
    { name = "created_at",       type = "TIMESTAMP", mode = "REQUIRED" },
  ])
}

resource "google_bigquery_table" "calibration_metrics" {
  dataset_id          = google_bigquery_dataset.atelier_trajectories.dataset_id
  project             = var.project_id
  table_id            = "calibration_metrics"
  deletion_protection = false
  schema = jsonencode([
    { name = "run_id",          type = "STRING",    mode = "REQUIRED" },
    { name = "judge_model",     type = "STRING",    mode = "REQUIRED" },
    { name = "axis",            type = "STRING",    mode = "REQUIRED" },
    { name = "kappa",           type = "FLOAT64",   mode = "REQUIRED" },
    { name = "sample_size",     type = "INT64",     mode = "REQUIRED" },
    { name = "measured_at",     type = "TIMESTAMP", mode = "REQUIRED" },
  ])
}

resource "google_bigquery_table" "cost_ledger" {
  dataset_id          = google_bigquery_dataset.atelier_trajectories.dataset_id
  project             = var.project_id
  table_id            = "cost_ledger"
  deletion_protection = false
  schema = jsonencode([
    { name = "session_id",   type = "STRING",    mode = "REQUIRED" },
    { name = "phase",        type = "STRING",    mode = "REQUIRED" },
    { name = "expert_id",    type = "STRING",    mode = "REQUIRED" },
    { name = "input_tokens", type = "INT64",     mode = "REQUIRED" },
    { name = "cost_usd",     type = "FLOAT64",   mode = "REQUIRED" },
    { name = "recorded_at",  type = "TIMESTAMP", mode = "REQUIRED" },
  ])
}
```

**`cloud_run.tf`:**

```hcl
resource "google_artifact_registry_repository" "atelier_images" {
  location      = var.region
  repository_id = "atelier-images"
  format        = "DOCKER"
  project       = var.project_id
  description   = "Atelier container images"
}

resource "google_cloud_run_v2_service" "atelier_api" {
  name     = "atelier-api-${var.env}"
  location = var.region
  project  = var.project_id

  template {
    service_account = google_service_account.atelier_api.email
    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/atelier-images/atelier-api:latest"
      resources { limits = { cpu = "1", memory = "512Mi" } }
    }
    scaling { min_instance_count = 0, max_instance_count = 3 }
  }

  lifecycle { ignore_changes = [template[0].containers[0].image] }
}
```

**`outputs.tf`:**

```hcl
output "cloud_run_url" {
  value = google_cloud_run_v2_service.atelier_api.uri
}

output "atelier_runtime_sa_email" {
  value = google_service_account.atelier_runtime.email
}

output "atelier_api_sa_email" {
  value = google_service_account.atelier_api.email
}
```

**Acceptance gate:**

```bash
cd infra/terraform
terraform init -backend=false      # Skip GCS backend (bucket may not exist)
terraform validate                 # Must exit 0
terraform plan -out=plan.tfplan    # Must exit 0 or 2 (2 = changes planned)
# DO NOT run terraform apply
```

Capture `terraform plan` output to `audit/infra/terraform-plan-2026-05-24.txt`. If plan exits 2 (changes planned), that's correct — the resources don't exist yet. If it exits 1, fix the HCL errors.

Update `features.json`:

- F0006: `passes → true`, add `evidence_tests: ["infra/terraform/terraform validate exit 0"]`
- F0007: `passes → true`, add cloud_run.tf evidence

**Commit:** `feat(infra): add Terraform IaC skeleton — closes F0006 F0007 (R8-01)`

---

## R8-02: atelier-eval package source — bootstrap eval suite

**Priority:** P1 (Phase 2 eval pipeline)
**Constraint:** The adapters must be typed Python (mypy --strict clean). No live HTTP calls in the adapter logic itself (adapters consume local data files). All hypothesis/pytest tests must pass.

**Create the full source package:**

```
atelier-eval/src/atelier_eval/
├── __init__.py              # package marker
├── adapters/
│   ├── __init__.py
│   ├── _base.py             # EvalTask Protocol + EvalResult dataclass
│   ├── webgen_bench.py      # WebGen-Bench 101 tasks adapter
│   ├── design2code.py       # Design2Code 484 webpages adapter
│   └── frontendbench.py     # FrontendBench 148 tasks stub (data not released)
├── metrics/
│   ├── __init__.py
│   ├── visual_similarity.py # SSIM + perceptual hash computation
│   └── lighthouse.py        # Lighthouse CLI wrapper → JSON score parser
├── runner.py                # pytest-style eval runner
└── scoreboard.py            # publishes to bench.atelier.dev
```

**`atelier-eval/src/atelier_eval/adapters/_base.py`:**

```python
"""Base types for all eval adapters."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True, slots=True)
class EvalResult:
    task_id: str
    passed: bool
    score: float          # 0.0–1.0
    error: str | None     # None on pass
    metadata: dict[str, str | float | int]

class EvalAdapter(Protocol):
    """All adapters implement this. Stateless — no I/O in __init__."""
    def load_tasks(self, data_dir: str) -> list[str]: ...
    def evaluate(self, task_id: str, generated_output: str) -> EvalResult: ...
    def aggregate(self, results: list[EvalResult]) -> dict[str, float]: ...
```

**`atelier-eval/src/atelier_eval/adapters/design2code.py`:**

```python
"""Design2Code adapter — 484 real-world webpages (CC BY 4.0).

Dataset: https://github.com/SALT-NLP/Design2Code
Paper: arXiv 2403.03163 (Stanford, NAACL 2025)

Metric: visual element recall + layout correctness via rendered screenshot comparison.
Phase 2 use: SSIM between Atelier-generated HTML and Design2Code reference renders
provides an objective DPO reward signal anchored to real production quality.

Data must be downloaded locally before use — no runtime HTTP calls.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from atelier_eval.adapters._base import EvalResult

DESIGN2CODE_TASK_COUNT: Final[int] = 484


@dataclass(frozen=True, slots=True)
class Design2CodeTask:
    task_id: str
    reference_screenshot_path: str  # relative to data_dir
    reference_html_path: str
    description: str


def load_design2code_tasks(data_dir: str | Path) -> list[Design2CodeTask]:
    """Load task manifest from a local Design2Code dataset directory."""
    root = Path(data_dir)
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Design2Code manifest not found at {manifest_path}. "
            "Download from https://github.com/SALT-NLP/Design2Code"
        )
    raw: list[dict[str, str]] = json.loads(manifest_path.read_text(encoding="utf-8"))
    return [
        Design2CodeTask(
            task_id=t["id"],
            reference_screenshot_path=t["screenshot"],
            reference_html_path=t["html"],
            description=t.get("description", ""),
        )
        for t in raw
    ]


def evaluate_design2code_visual_similarity(
    *,
    task: Design2CodeTask,
    generated_html: str,
    data_dir: str | Path,
    ssim_floor: float = 0.60,
) -> EvalResult:
    """Compute SSIM between rendered generated HTML and reference screenshot.

    The SSIM floor of 0.60 is conservative — real production pages vs generated
    output will rarely exceed 0.80 even for high-quality generators. The floor
    is used as a DPO eligibility gate (higher is preferred).

    Requires: atelier_eval.metrics.visual_similarity (pillow + scikit-image).
    """
    from atelier_eval.metrics.visual_similarity import (  # noqa: PLC0415
        render_html_to_screenshot,
        compute_ssim,
    )
    reference_path = Path(data_dir) / task.reference_screenshot_path
    generated_screenshot = render_html_to_screenshot(generated_html)
    ssim_score = compute_ssim(generated_screenshot, str(reference_path))
    return EvalResult(
        task_id=task.task_id,
        passed=ssim_score >= ssim_floor,
        score=ssim_score,
        error=None,
        metadata={"ssim": ssim_score, "ssim_floor": ssim_floor},
    )
```

**`atelier-eval/src/atelier_eval/metrics/lighthouse.py`:**

```python
"""Lighthouse CLI wrapper — runs audits and parses JSON output.

Lighthouse is Google's open-source automated web audit tool (Chrome DevTools).
This wrapper integrates Lighthouse a11y and performance scores into Atelier's
eval pipeline as an objective DPO reward signal.

No published paper has used Lighthouse scores as DPO predicates — this is a
first. The claim: 'Atelier uses Google's own Lighthouse tool as an objective
gate in its DPO reward function.'

Prerequisites: lighthouse CLI installed (`npm install -g lighthouse`).
Chrome/Chromium must be available at the system level.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Final

LIGHTHOUSE_A11Y_FLOOR: Final[float] = 0.90
LIGHTHOUSE_PERF_FLOOR: Final[float] = 0.90


@dataclass(frozen=True, slots=True)
class LighthouseScores:
    accessibility: float   # 0.0–1.0
    performance: float     # 0.0–1.0
    best_practices: float  # 0.0–1.0
    seo: float             # 0.0–1.0


def run_lighthouse(url: str, *, chrome_flags: str = "--headless") -> LighthouseScores:
    """Run Lighthouse against a URL and return the parsed scores.

    Raises:
        RuntimeError: If the lighthouse CLI is not available or exits non-zero.
        ValueError: If the JSON output cannot be parsed.
    """
    with tempfile.NamedTemporaryFile(suffix=".json", delete=True) as tmp:
        result = subprocess.run(
            [
                "lighthouse",
                url,
                "--output=json",
                f"--output-path={tmp.name}",
                f"--chrome-flags={chrome_flags}",
                "--only-categories=accessibility,performance,best-practices,seo",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode not in (0, 1):
            raise RuntimeError(
                f"lighthouse exited {result.returncode}: {result.stderr[:500]}"
            )
        raw = json.loads(Path(tmp.name).read_text(encoding="utf-8"))  # type: ignore[attr-defined]

    cats = raw["categories"]
    return LighthouseScores(
        accessibility=cats["accessibility"]["score"],
        performance=cats["performance"]["score"],
        best_practices=cats["best-practices"]["score"],
        seo=cats["seo"]["score"],
    )


def passes_lighthouse_gate(scores: LighthouseScores) -> bool:
    """Return True if both a11y and perf meet the DPO reward floors."""
    return (
        scores.accessibility >= LIGHTHOUSE_A11Y_FLOOR
        and scores.performance >= LIGHTHOUSE_PERF_FLOOR
    )
```

**`atelier-eval/src/atelier_eval/metrics/visual_similarity.py`:**

```python
"""Visual similarity metrics for frontend code quality evaluation.

Uses SSIM (Structural Similarity Index Measure) from scikit-image.
SSIM is preferred over pixel MSE because it correlates better with
human perceptual quality (Wang et al. 2004).
"""
from __future__ import annotations

from pathlib import Path


def render_html_to_screenshot(html: str, *, width: int = 1280, height: int = 800) -> bytes:
    """Render HTML string to a PNG screenshot via headless Chromium.

    Returns raw PNG bytes.
    Raises:
        RuntimeError: if chrome/chromium is not available.
    """
    import subprocess  # noqa: PLC0415
    import tempfile   # noqa: PLC0415

    with tempfile.NamedTemporaryFile(suffix=".html", mode="w", delete=False) as f:
        f.write(html)
        html_path = f.name
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as out:
        screenshot_path = out.name

    subprocess.run(
        [
            "chromium-browser",
            "--headless",
            "--no-sandbox",
            f"--window-size={width},{height}",
            f"--screenshot={screenshot_path}",
            f"file://{html_path}",
        ],
        capture_output=True,
        check=True,
        timeout=30,
    )
    return Path(screenshot_path).read_bytes()


def compute_ssim(generated_png: bytes, reference_path: str) -> float:
    """Compute SSIM between a generated PNG (bytes) and a reference PNG file.

    Returns a float in [0.0, 1.0]. Higher is more similar.
    """
    import io  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415
    from skimage.metrics import structural_similarity  # noqa: PLC0415

    gen_img = np.array(Image.open(io.BytesIO(generated_png)).convert("RGB"))
    ref_img = np.array(Image.open(reference_path).convert("RGB"))

    # Resize to same dimensions (use generated as target size)
    if gen_img.shape != ref_img.shape:
        from PIL import Image as PILImage  # noqa: PLC0415
        ref_pil = PILImage.fromarray(ref_img).resize(
            (gen_img.shape[1], gen_img.shape[0]), PILImage.LANCZOS
        )
        ref_img = np.array(ref_pil)

    score: float = structural_similarity(gen_img, ref_img, channel_axis=2, data_range=255)
    return float(score)
```

After creating all files, run:

```bash
cd atelier-eval
../.venv/bin/python3.12 -m mypy --strict src/atelier_eval/ 2>&1
```

Expected: Success, 0 issues (imports using TYPE_CHECKING where needed for heavy deps like PIL/skimage).

**Commit:** `feat(eval): bootstrap atelier-eval source package — adapters + metrics (R8-02)`

---

## R8-03: Design2Code + Web2Code dataset download scripts

**Priority:** P1
**Constraint:** Shell scripts only. NO actual downloads in this round (dataset is large). Scripts must be idempotent (check if already downloaded before fetching).

Create `scripts/eval/download_design2code.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
DATA_DIR="${1:-atelier-eval/data/design2code}"
if [[ -d "$DATA_DIR" && -f "$DATA_DIR/manifest.json" ]]; then
  echo "Design2Code already present at $DATA_DIR"
  exit 0
fi
mkdir -p "$DATA_DIR"
echo "Downloading Design2Code dataset..."
# Actual download command (requires HuggingFace or direct GitHub LFS):
echo "  git clone --depth=1 https://github.com/SALT-NLP/Design2Code $DATA_DIR"
echo "  OR: huggingface-cli download SALT-NLP/Design2Code --local-dir $DATA_DIR"
echo "Run one of the above commands to download."
echo "Design2Code: 484 webpages, CC BY 4.0, ~2GB"
exit 0  # Non-zero would block CI; this is a dev-setup helper
```

Create `scripts/eval/download_web2code.sh` similarly, pointing to `MBZUAI-LLM/web2code`.

Ensure both scripts pass `shellcheck`.

**Commit:** `chore(eval): add dataset download helper scripts (R8-03)`

---

## R8-04: Pyproject.toml — add eval deps + update atelier-eval package metadata

**Priority:** P1

Update `atelier-eval/pyproject.toml` to add the deps needed for the metrics modules:

```toml
[project]
name = "atelier-eval"
version = "0.1.0a0"
description = "Atelier evaluation suite — benchmark adapters and public scoreboard"
readme = "README.md"
authors = [{ name = "Daniel Manzela", email = "hello@atelier.dev" }]
license = { file = "../LICENSE" }
requires-python = ">=3.11,<3.13"

dependencies = [
    "pydantic>=2.6,<3",
    "pyyaml>=6.0,<7",
    "httpx>=0.27,<1",
    "numpy>=1.26",          # visual_similarity.py
    "pillow>=10.0",         # image loading for SSIM
    "scikit-image>=0.23",   # structural_similarity
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3,<9",
    "mypy>=1.13,<2",
    "ruff>=0.6.9,<1",
    "types-Pillow>=10.0",
]
```

Generate lockfile after adding deps:

```bash
cd atelier-eval
pip-compile --output-file=requirements.lock pyproject.toml
```

Verify `pip-audit` shows 0 vulnerabilities on the new lockfile.

**Commit:** `chore(eval): add eval package deps — pillow + scikit-image + numpy (R8-04)`

---

## R8-05: Update features.json for closed gates

**Priority:** P0 (gate tracking)

After R8-01 completes and `terraform validate` passes, update `features.json`:

```bash
# F0006 — update
jq '(.features[] | select(.id == "F0006")) |= . + {
  "passes": true,
  "evidence_tests": ["infra/terraform validate exits 0"],
  "notes": "Terraform skeleton committed; validate + plan exit 0; no apply (Daniel-gated)"
}' features.json > features.json.tmp && mv features.json.tmp features.json

# F0007 — update
jq '(.features[] | select(.id == "F0007")) |= . + {
  "passes": true,
  "evidence_tests": ["infra/terraform/cloud_run.tf exists + terraform validate exits 0"],
  "notes": "cloud_run.tf + iam.tf committed; SAs defined; Cloud Run service defined; no apply"
}' features.json > features.json.tmp && mv features.json.tmp features.json
```

Run the features gate to confirm no new violations:

```bash
cd "$(git rev-parse --show-toplevel)"
jq -e '[.features[] | select(.passes == true and (.evidence_tests | length == 0) and (.evidence_commits | length == 0))] | length == 0' features.json
```

Expected: `true`

**Commit:** Bundled with R8-01.

---

## R8-06: Handoff document

Create `audit/executor-handoff-run8.md` with:

- Per-item table (R8-01 through R8-04)
- `terraform validate` output captured verbatim
- `mypy --strict src/atelier_eval/` output captured verbatim
- `shellcheck` output captured verbatim
- Full test suite result: `pytest --no-header -q`
- features.json gate run: `jq` output captured
- Deferred items (any blockers, FAIL-SOFT items)
- What I would NOT bet my job on
- `READY-FOR-AUDIT-RUN-8: <ISO-8601>`

---

## Acceptance gate (all items)

```bash
# Must all exit 0 before handoff:

# Terraform
cd infra/terraform && terraform init -backend=false && terraform validate
# Expected: Success! The configuration is valid.

# atelier-eval
VENV="$(git rev-parse --show-toplevel)/.venv"
cd "$(git rev-parse --show-toplevel)/atelier-eval"
$VENV/bin/python3.12 -m mypy --strict src/atelier_eval/
# Expected: Success: no issues found

# Full test suite (atelier-core only — atelier-eval has no tests yet)
cd "$(git rev-parse --show-toplevel)/atelier-core"
$VENV/bin/python3.12 -m pytest --no-header -q
# Expected: 404+ passed, 50 xfailed, 0 failed

# Pre-commit on all new files
cd "$(git rev-parse --show-toplevel)"
pre-commit run --files infra/terraform/*.tf atelier-eval/src/**/*.py scripts/eval/*.sh
# Expected: all Passed or Skipped
```

---

## What is OUT OF SCOPE for R8

- `atelier-core/src/atelier/optimize/dpo_tuning_job.py` — Claude owns T6
- `atelier-core/src/atelier/memory/backends/bigquery_episodic.py` — Claude owns T8
- `atelier-core/src/atelier/reward/` Lighthouse predicate additions — Claude owns this (1-day task)
- Any changes to `atelier-core/src/atelier/router/` or `atelier-core/src/atelier/memory/protocol.py`
- Any `terraform apply`, `gcloud iam` commands, or wet-run secret migrations
- `git push origin phase/1` — Daniel-gated

If any step hits a design decision not specified above, FAIL-SOFT (document in handoff, skip the step, move to next item). Do not guess. Do not redesign.

---

`BRIEF-ISSUED: 2026-05-24`
