# Atelier Sprint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Atelier — autonomous design agent — in a 21-day sprint (2026-05-15 → 2026-06-04) for the Google for Startups AI Agents Challenge 2026 (deadline 2026-06-05; we file 2026-06-03 noon).

**Architecture:** Three-layer stacked: **PIP (Pre-Generation Intake)** → **Campaign Orchestrator (RLRD)** → **8-node atomic DAG**. Wraps `agent-dag-pipeline` (lockfile-pinned consume per ADR 0001) on Google ADK 2.0 Beta. Cloud Run jobs for runtime; Agent Engine Sessions / Memory Bank / A2A as services. 13 novel contributions (N1-N13), 5 quantified 10× axes.

**Tech Stack:** Python 3.11 + ADK 2.0 Beta + Vertex AI (Gemini 3 family + Gemma 4 + text-embedding-005 + multimodal-embedding) + Anthropic Claude (Opus 4.7 + Sonnet 4.6 + Haiku 4.5) via Vertex Model Garden + Firebase (Hosting + Remote Config + Analytics) + Identity Platform + Apigee AI Gateway + Vertex Memory Bank + Vector Search 2.0 + BigQuery + Cloud KMS + Stitch MCP + A2UI v0.9. TypeScript dashboards (React + Vite). GitHub Actions for CI/CD.

---

## Plan structure

Phase 1 (W1, May 15-21) gets day-by-day with bite-sized TDD tasks for D1-D2 and feature-brief format for D3-D7. Weeks 2-3 are daily themes + feature lists + acceptance gates. The full atomic feature list (194 entries) lives in `features.json` — this plan refers to features by ID.

**Worktree convention** (per ADR 0007):
- `main` holds only accepted-and-tagged work
- All sprint work happens in `.worktrees/phaseN-<name>/` on branch `phase/N`
- Acceptance: `git merge --no-ff phase/N + git tag phaseN-accepted`

**Per-session ritual** (90 sec, every Claude Code session start):
```bash
cd .worktrees/phase1-foundation  # or whichever phase is active
cat docs/sprint/STATUS.md
tail -50 docs/sprint/CHECKPOINTS.md
cat docs/sprint/BLOCKERS.md
cat features.json | jq '.features[] | select(.passes == false and (.depends_on | length == 0 or all(.[]; . as $d | $features.features | any(.id == $d and .passes == true)))) | .id' | head -3
git status && git log --oneline -10
```

---

## Phase 1: Foundation (W1, May 15-21)

**Worktree:** `.worktrees/phase1-foundation/` on branch `phase/1`
**Cost target:** $1,200 of $5K (24%)
**Acceptance gate (D7):** 1-surface end-to-end on `pipeline-observatory/index.html` brief; Cloud Run staging deploy; OTel + Cloud Trace + BigQuery functional; 50/484 WebGen-Bench task subset passing in CI.

---

### Day 1 — Wed May 15: Worktree + GCP project + first ADK skeleton

**Goal:** Create the phase/1 worktree, bootstrap the dev environment, set up the GCP project skeleton (Terraform `main.tf` + key modules planned), get the first GateAgent class importing cleanly with one passing unit test.

**Cost target this day:** $80-150

#### Task 1.1: Create the phase/1 worktree

**Files:**
- Modify: `.worktrees/` (create)
- Read: `docs/conventions/branching.md`

- [ ] **Step 1: Create branch + worktree from main**

```bash
cd ~/Professional\ Profile/atelier
git checkout main
git pull
git branch phase/1 main
git worktree add .worktrees/phase1-foundation phase/1
cd .worktrees/phase1-foundation
```

- [ ] **Step 2: Install pre-commit hooks in the new worktree**

```bash
pre-commit install
pre-commit install --hook-type commit-msg
```

Expected: `pre-commit installed at .git/hooks/pre-commit` and same for `commit-msg`.

- [ ] **Step 3: Verify identical state to main**

```bash
git log --oneline -3
git status
```

Expected: 3 commits visible (`f85c68a`, `d692bdd`, `00d7df1`); clean working tree.

- [ ] **Step 4: Update `docs/sprint/STATUS.md` for D1 start**

Edit `docs/sprint/STATUS.md`:
- Change `Last updated` to current UTC time
- Change `Active branch` to `phase/1`
- Change `Active worktree` to `.worktrees/phase1-foundation`
- Update `Right now` to "Sprint D1 in progress: F0001 worktree setup → F0002 GCP project → F0003 ADK plumbing"

- [ ] **Step 5: Commit**

```bash
git add docs/sprint/STATUS.md
git commit -m "chore(sprint): begin Phase 1 foundation in phase/1 worktree"
```

#### Task 1.2: Run `./init.sh` to verify host prerequisites

**Files:**
- Read: `init.sh`

- [ ] **Step 1: Execute init.sh**

```bash
./init.sh
```

Expected output:
- `✓ python3 (Python 3.11.9)`
- `✓ node (v20.11.1)`
- `✓ npm`, `✓ git`, `✓ gh`, `✓ docker`, `✓ gcloud`
- `✓ Authenticated as @Manzela`
- `✓ ADC set; project=i-for-ai`
- Pre-commit + pip + npm dep install completes
- All sprint state files present

If any check fails, fix the prerequisite (install missing tool) and re-run before continuing.

#### Task 1.3: Verify Vertex AI access for Tier 1 models

**Files:**
- Create: `atelier-deploy/scripts/verify-prereqs.sh`

- [ ] **Step 1: Write the verify-prereqs.sh script**

Create `atelier-deploy/scripts/verify-prereqs.sh`:

```bash
#!/usr/bin/env bash
# Probe Vertex AI for Tier 1 model availability across regions.
# Records canonical model IDs to atelier-deploy/config/model-registry.yaml

set -euo pipefail

PROJECT="${GOOGLE_CLOUD_PROJECT:-i-for-ai}"
REGIONS=(us-central1 us-east5 europe-west4 asia-southeast1)

# Tier 1 models we need (see PRD §27 limits.yaml)
GEMINI_MODELS=(gemini-3-pro gemini-3-flash gemini-3-flash-lite)
ANTHROPIC_MODELS=(claude-opus-4-7 claude-sonnet-4-6 claude-haiku-4-5)
EMBEDDING_MODELS=(text-embedding-005 multimodal-embedding)
GEMMA_MODELS=(gemma-4-26b-a4b-it)

probe() {
  local model_path="$1" region="$2"
  curl -s -X POST \
    "https://${region}-aiplatform.googleapis.com/v1/projects/${PROJECT}/locations/${region}/publishers/${model_path}:countTokens" \
    -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    -H "Content-Type: application/json" \
    -d '{"contents":[{"role":"user","parts":[{"text":"hi"}]}]}' \
    -o /dev/null -w "%{http_code}"
}

echo "model_registry:" > atelier-deploy/config/model-registry.yaml
for m in "${GEMINI_MODELS[@]}"; do
  for r in "${REGIONS[@]}"; do
    code=$(probe "google/models/${m}" "$r" || echo "ERR")
    if [[ "$code" == "200" || "$code" == "400" ]]; then
      echo "  ${m}: ${r}" >> atelier-deploy/config/model-registry.yaml
      echo "✓ google/${m} available in ${r} (HTTP $code)"
      break
    fi
  done
done
for m in "${ANTHROPIC_MODELS[@]}"; do
  for r in "${REGIONS[@]}"; do
    code=$(probe "anthropic/models/${m}" "$r" || echo "ERR")
    if [[ "$code" == "200" || "$code" == "400" ]]; then
      echo "  ${m}: ${r}" >> atelier-deploy/config/model-registry.yaml
      echo "✓ anthropic/${m} available in ${r} (HTTP $code)"
      break
    fi
  done
done
echo "Done. Canonical model→region mapping at atelier-deploy/config/model-registry.yaml"
```

- [ ] **Step 2: Make executable + run**

```bash
chmod +x atelier-deploy/scripts/verify-prereqs.sh
mkdir -p atelier-deploy/config
./atelier-deploy/scripts/verify-prereqs.sh
```

Expected: A `model-registry.yaml` listing each model and the first region where it returned 200/400 (both indicate the endpoint is reachable; 400 typically means malformed JSON which proves auth + model existence).

- [ ] **Step 3: Verify model-registry.yaml has every Tier 1 model**

```bash
cat atelier-deploy/config/model-registry.yaml
```

Expected: All 8 Tier 1 models listed with a region. If any missing, check Vertex AI Model Garden console + re-enable.

- [ ] **Step 4: Commit**

```bash
git add atelier-deploy/scripts/verify-prereqs.sh atelier-deploy/config/model-registry.yaml
git commit -m "feat(deploy): add prereq-verification script + canonical model→region registry"
```

#### Task 1.4: Install agent-dag-pipeline (lockfile-pinned per ADR 0001)

**Files:**
- Create: `atelier-core/requirements.in`
- Create: `atelier-core/requirements.lock`
- Modify: `atelier-core/pyproject.toml`

- [ ] **Step 1: Add agent-dag-pipeline + ADK 2.0 Beta to pyproject.toml**

Edit `atelier-core/pyproject.toml`, replace the existing `dependencies = [...]` block with:

```toml
dependencies = [
    "pydantic>=2.6,<3",
    "pyyaml>=6.0,<7",
    "httpx>=0.27,<1",
    "structlog>=24.4,<26",
    # Production deps
    "google-adk[all]>=2.0.0b1,<3",
    "google-cloud-aiplatform>=1.71,<2",
    "google-cloud-firestore>=2.18,<3",
    "google-cloud-bigquery>=3.25,<4",
    "google-cloud-secret-manager>=2.20,<3",
    "google-cloud-storage>=2.18,<3",
    "google-cloud-tasks>=2.16,<3",
    "google-cloud-scheduler>=2.13,<3",
    "google-cloud-kms>=3.0,<4",
    "opentelemetry-api>=1.27,<2",
    "opentelemetry-sdk>=1.27,<2",
    "opentelemetry-exporter-gcp-trace>=1.7,<2",
    "anthropic[vertex]>=0.40,<1",
]
```

- [ ] **Step 2: Generate requirements.lock**

```bash
cd atelier-core
python3 -m pipx run pip-tools pip-compile pyproject.toml -o requirements.lock --resolver=backtracking
```

Expected: `requirements.lock` populated with pinned versions of all transitive deps.

- [ ] **Step 3: Install**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock
pip install -e ".[dev]"
```

Expected: All deps install cleanly. `pip list` shows `google-adk 2.0.0b1` and `agent-dag-pipeline` is NOT yet installed (it's a separate package — added in Task 1.5 once we confirm its PyPI status).

- [ ] **Step 4: Verify ADK imports**

```bash
python3 -c "from google.adk.agents import BaseAgent, SequentialAgent, ParallelAgent, LoopAgent; print('ADK imports OK')"
```

Expected: `ADK imports OK`

- [ ] **Step 5: Commit lockfile**

```bash
git add atelier-core/pyproject.toml atelier-core/requirements.lock
git commit -m "feat(core): pin ADK 2.0 Beta + Vertex SDK + Anthropic SDK dependencies"
```

#### Task 1.5: Add agent-dag-pipeline as a lockfile-pinned source dependency

**Note:** `agent-dag-pipeline` may not be on PyPI as of D1. If not, install via VCS direct reference.

**Files:**
- Modify: `atelier-core/pyproject.toml`
- Modify: `atelier-core/requirements.lock`

- [ ] **Step 1: Check PyPI for agent-dag-pipeline**

```bash
pip index versions agent-dag-pipeline 2>&1 | head -3
```

If PyPI publishes it: add `"agent-dag-pipeline>=3.0.0,<4"` to dependencies.

If NOT on PyPI yet: add the VCS-pinned reference:

```toml
dependencies = [
    # ... existing ...
    "agent_dag @ git+https://github.com/Manzela/agent-dag-pipeline.git@v3.0.0",
]
```

- [ ] **Step 2: Re-generate lockfile + install**

```bash
cd atelier-core
pip-compile pyproject.toml -o requirements.lock --resolver=backtracking
pip install -r requirements.lock
```

- [ ] **Step 3: Verify import**

```bash
python3 -c "from agent_dag.adk.gate_agent import GateAgent, GateDecision, GateResult; print('agent-dag-pipeline imports OK')"
```

Expected: `agent-dag-pipeline imports OK`

- [ ] **Step 4: Commit**

```bash
git add atelier-core/pyproject.toml atelier-core/requirements.lock
git commit -m "feat(core): pin agent-dag-pipeline (per ADR 0001 wrap-don't-fork)"
```

#### Task 1.6: Define the BriefSpec Pydantic data contract (TDD)

**Files:**
- Create: `atelier-core/tests/unit/test_brief_spec.py`
- Create: `atelier-core/src/atelier/intake/brief_spec.py`

- [ ] **Step 1: Write the failing test**

Create `atelier-core/tests/unit/test_brief_spec.py`:

```python
"""Tests for BriefSpec data contract (PIP layer output)."""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from atelier.intake.brief_spec import (
    BriefSpec,
    ComplianceLevel,
    ConvergenceBar,
    IntakeAnswer,
    StackChoice,
    VisualRegister,
)


@pytest.mark.unit
def test_brief_spec_is_frozen():
    """BriefSpec is immutable post-approval (per ADR 0004)."""
    spec = BriefSpec(
        spec_id=uuid4(),
        tenant_id="tnt_test",
        project_id="prj_test",
        intent="redesign hero section",
        visual_register=VisualRegister.EDITORIAL,
        stack=StackChoice.VANILLA_HTML,
        design_system_source=None,
        compliance_level=ComplianceLevel.WCAG_AA,
        convergence_bar=ConvergenceBar.PRODUCTION,
        reference_artifacts=[],
        campaign_scope=None,
        intake_transcript=[],
        approved_at=datetime.now(timezone.utc),
        approved_by_user_id="usr_test",
    )
    with pytest.raises(Exception):  # frozen=True raises on mutation
        spec.intent = "different intent"


@pytest.mark.unit
def test_brief_spec_carries_schema_version():
    """Every Pydantic model carries schema_version per CLAUDE.md invariant."""
    spec = BriefSpec(
        spec_id=uuid4(),
        tenant_id="tnt_test",
        project_id="prj_test",
        intent="test",
        visual_register=VisualRegister.EDITORIAL,
        stack=StackChoice.REACT_TAILWIND,
        design_system_source=None,
        compliance_level=ComplianceLevel.WCAG_AA,
        convergence_bar=ConvergenceBar.SHIP_IT,
        reference_artifacts=[],
        campaign_scope=None,
        intake_transcript=[],
        approved_at=datetime.now(timezone.utc),
        approved_by_user_id="usr_test",
    )
    assert spec.schema_version == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd atelier-core
pytest tests/unit/test_brief_spec.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'atelier.intake.brief_spec'`

- [ ] **Step 3: Implement BriefSpec**

Create `atelier-core/src/atelier/intake/__init__.py` (empty) and `atelier-core/src/atelier/intake/brief_spec.py`:

```python
"""BriefSpec — immutable JSON spec produced by PIP, frozen at user approval.

Per ADR 0004 — this is the contract Atelier commits to for the duration
of the project. Spec changes require explicit "amend BriefSpec" command
+ re-approval; no silent drift.
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VisualRegister(str, Enum):
    EDITORIAL = "editorial"
    DENSE_DATA = "dense-data"
    PLAYFUL = "playful"
    BRUTALIST = "brutalist"
    CUSTOM = "custom"


class StackChoice(str, Enum):
    VANILLA_HTML = "vanilla-html"
    REACT_TAILWIND = "react-tailwind"
    NEXTJS_TAILWIND = "nextjs-tailwind"
    VUE = "vue"
    SVELTE = "svelte"
    ASTRO = "astro"
    SAGE_PHP = "sage-php"
    INFER_FROM_PATH = "infer"


class ComplianceLevel(str, Enum):
    NONE = "none"
    WCAG_AA = "wcag-aa"
    WCAG_AAA = "wcag-aaa"
    REGULATORY = "regulatory"


class ConvergenceBar(str, Enum):
    SHIP_IT = "ship-it"          # ≥85% all axes
    PRODUCTION = "production"     # ≥95% all axes
    PERFECTIONIST = "perfectionist"  # 100% — may not converge


class IntakeAnswer(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    question_id: str
    answer_text: str
    answer_value: Any | None = None
    visual_option_selected: str | None = None
    schema_version: int = 1


class CampaignScope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    surface_count_estimate: int
    timeline: str  # "today" | "this-week" | "multi-week" | "no-rush"
    budget_per_session_usd: float
    budget_per_campaign_usd: float
    failure_policy: str  # "skip" | "ask-help" | "best-effort-and-flag"
    schema_version: int = 1


class BriefSpec(BaseModel):
    """Immutable spec the agent commits to for the entire project."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_id: UUID
    tenant_id: str
    project_id: str
    intent: str = Field(description="The ONE thing this design should make easier")
    visual_register: VisualRegister
    stack: StackChoice
    design_system_source: str | None  # path to DESIGN.md or "infer"
    compliance_level: ComplianceLevel
    convergence_bar: ConvergenceBar
    reference_artifacts: list[str] = Field(default_factory=list)
    campaign_scope: CampaignScope | None = None  # None for atomic; set for campaigns
    intake_transcript: list[IntakeAnswer] = Field(default_factory=list)
    schema_version: int = 1
    approved_at: datetime
    approved_by_user_id: str
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/unit/test_brief_spec.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add atelier-core/src/atelier/intake/__init__.py atelier-core/src/atelier/intake/brief_spec.py atelier-core/tests/unit/test_brief_spec.py
git commit -m "feat(intake): add BriefSpec Pydantic data contract (frozen, schema-versioned)

Implements PRD §9 BriefSpec model. Per ADR 0004, BriefSpec is the
immutable artifact the agent commits to for the duration of the
project. ConfigDict(frozen=True, extra='forbid') enforces immutability
+ schema strictness. schema_version=1 per CLAUDE.md invariant.

Tests cover: frozen mutation guard, schema_version presence."
```

#### Task 1.7: End-of-Day-1 checkpoint

- [ ] **Step 1: Run full test suite**

```bash
cd atelier-core
pytest tests/ -v --tb=short
```

Expected: All tests pass (we have 2 new ones from Task 1.6, possibly some from prior days).

- [ ] **Step 2: Update CHECKPOINTS.md**

Append to `docs/sprint/CHECKPOINTS.md`:

```markdown
## 2026-05-15 EOD UTC — Checkpoint 1 (Phase 1 D1)

**Session**: Phase 1 D1 — Worktree setup + ADK plumbing baseline
**Worktree**: `.worktrees/phase1-foundation/`
**Branch**: `phase/1`

**What shipped**:
- F0001: phase/1 worktree created + pre-commit hooks active
- F0001a: init.sh verified all host prereqs
- F0002: verify-prereqs.sh probes Vertex AI Tier 1 models across regions; canonical model→region registry committed
- F0003: agent-dag-pipeline + ADK 2.0 Beta lockfile-pinned + installed
- F0004: BriefSpec Pydantic data contract (frozen, schema-versioned, 2 unit tests passing)

**What's next** (D2):
- F0005: Atelier API skeleton (FastAPI scaffolding)
- F0006: Cloud Run job deployment
- F0007: Pydantic data contracts: SurfaceManifest, CandidateUI, GateOutcome, JudgeVote, ConsensusResult, CoherenceVerdict, TrajectoryRecord

**Blockers**: None.

**Test status**: 2/2 unit tests pass

**Cost at session end** (estimate to be refined in COST_LEDGER):
- ~$80 of $5K budget; ~1.6% cumulative

**RESUME-HERE**: D2 begins with Task 2.1 below. Read STATUS.md + this checkpoint + features.json for next unblocked feature.
```

- [ ] **Step 3: Update COST_LEDGER.md**

Append a row to `docs/sprint/COST_LEDGER.md`:

```markdown
| 2026-05-15 | ~3.0M | ~250K | ~$80 | $130 | 2.6% | 88% | D1: worktree + Vertex probe + ADK plumbing + BriefSpec |
```

- [ ] **Step 4: Update features.json**

Mark F0001-F0004 as `passes: true` and `completed_at`.

- [ ] **Step 5: Commit + push**

```bash
git add docs/sprint/CHECKPOINTS.md docs/sprint/COST_LEDGER.md features.json
git commit -m "chore(sprint): D1 checkpoint — worktree + ADK + BriefSpec shipped"
git push -u origin phase/1
```

---

### Day 2 — Thu May 16: GCP Terraform foundation + Pydantic data contracts

**Goal:** Provision the GCP infra skeleton (Terraform modules for Cloud Run, Identity Platform, Apigee, Vertex AI, BigQuery, KMS, Monitoring); define remaining Pydantic data contracts; wire Atelier API skeleton (FastAPI) and one health-check endpoint deployable to Cloud Run staging.

**Cost target this day:** $130-200

#### Task 2.1: Terraform skeleton (root + minimal Cloud Run module)

**Files:**
- Create: `atelier-deploy/terraform/main.tf`
- Create: `atelier-deploy/terraform/versions.tf`
- Create: `atelier-deploy/terraform/variables.tf`
- Create: `atelier-deploy/terraform/staging.tfvars`
- Create: `atelier-deploy/terraform/cloud_run.tf`

- [ ] **Step 1: Write versions.tf**

```hcl
# atelier-deploy/terraform/versions.tf
terraform {
  required_version = ">= 1.9"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.10"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.10"
    }
  }
}
```

- [ ] **Step 2: Write variables.tf**

```hcl
# atelier-deploy/terraform/variables.tf
variable "project_id" {
  description = "GCP project ID"
  type        = string
  default     = "i-for-ai"
}

variable "region" {
  description = "Default region"
  type        = string
  default     = "us-central1"
}

variable "env" {
  description = "Environment (staging | prod)"
  type        = string
  validation {
    condition     = contains(["staging", "prod"], var.env)
    error_message = "env must be 'staging' or 'prod'."
  }
}

variable "name_prefix" {
  description = "Prefix for all resource names"
  type        = string
  default     = "atelier"
}
```

- [ ] **Step 3: Write main.tf**

```hcl
# atelier-deploy/terraform/main.tf
provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

# Common labels applied to every resource
locals {
  labels = {
    project    = "atelier"
    env        = var.env
    managed-by = "terraform"
    sprint     = "2026-05"
  }
  name = "${var.name_prefix}-${var.env}"
}

# Enable required APIs (idempotent — already enabled at i-for-ai per setup)
resource "google_project_service" "apis" {
  for_each = toset([
    "aiplatform.googleapis.com",
    "apigee.googleapis.com",
    "artifactregistry.googleapis.com",
    "bigquery.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudkms.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "cloudscheduler.googleapis.com",
    "cloudtasks.googleapis.com",
    "cloudtrace.googleapis.com",
    "firebase.googleapis.com",
    "firebasehosting.googleapis.com",
    "firebaseremoteconfig.googleapis.com",
    "identitytoolkit.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
  ])
  service                    = each.value
  disable_on_destroy         = false
  disable_dependent_services = false
}
```

- [ ] **Step 4: Write cloud_run.tf (skeleton service)**

```hcl
# atelier-deploy/terraform/cloud_run.tf
# Service account for the API service
resource "google_service_account" "api" {
  account_id   = "${local.name}-api-sa"
  display_name = "Atelier API service account (${var.env})"
}

# Service account for the long-running agent jobs
resource "google_service_account" "agent" {
  account_id   = "${local.name}-agent-sa"
  display_name = "Atelier Agent jobs service account (${var.env})"
}

# Atelier API — Cloud Run service (HTTP request/response)
resource "google_cloud_run_v2_service" "api" {
  name     = "${local.name}-api"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"
  labels   = local.labels

  template {
    service_account = google_service_account.api.email
    scaling {
      min_instance_count = var.env == "prod" ? 2 : 0
      max_instance_count = var.env == "prod" ? 50 : 5
    }
    containers {
      image = "us-central1-docker.pkg.dev/${var.project_id}/atelier/api:placeholder"
      resources {
        limits = {
          cpu    = "1000m"
          memory = "512Mi"
        }
        cpu_idle = true
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "ATELIER_ENV"
        value = var.env
      }
      ports {
        container_port = 8080
      }
    }
    timeout = "60s"
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }
  depends_on = [google_project_service.apis]
}

output "api_url" {
  value = google_cloud_run_v2_service.api.uri
}
```

- [ ] **Step 5: Write staging.tfvars**

```hcl
# atelier-deploy/terraform/staging.tfvars
project_id = "i-for-ai"
region     = "us-central1"
env        = "staging"
```

- [ ] **Step 6: terraform init + plan**

```bash
cd atelier-deploy/terraform
terraform init
terraform plan -var-file=staging.tfvars
```

Expected: Plan shows ~20 resources to create (18 API enables, 2 service accounts, 1 Cloud Run service). No errors.

- [ ] **Step 7: Commit (do NOT apply yet — Apply gets its own task after Daniel reviews the plan)**

```bash
git add atelier-deploy/terraform/
git commit -m "feat(deploy): add Terraform skeleton — APIs, SAs, Cloud Run staging service

- versions.tf: pins terraform 1.9+, google + google-beta providers ~6.10
- variables.tf: project_id, region, env (staging|prod), name_prefix
- main.tf: provider config + 18 GCP API enables + label conventions
- cloud_run.tf: api-sa, agent-sa service accounts + Atelier API Cloud Run service
- staging.tfvars: i-for-ai project, us-central1, env=staging

Refs: PRD §8 tech stack, ADR 0002 Cloud Run not Agent Engine, ADR 0006 Google-native"
```

- [ ] **Step 8: Daniel reviews + applies**

Daniel runs:
```bash
cd atelier-deploy/terraform
terraform apply -var-file=staging.tfvars
```

Approves the prompt. Captures the output (especially `api_url`) for the next task.

#### Task 2.2: Pydantic data contracts (remaining)

**Files:**
- Create: `atelier-core/tests/unit/test_data_contracts.py`
- Create: `atelier-core/src/atelier/shared/data_contracts.py`

- [ ] **Step 1: Write failing tests**

Create `atelier-core/tests/unit/test_data_contracts.py`:

```python
"""Tests for Pydantic v2 frozen data contracts (PRD §9)."""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from atelier.shared.data_contracts import (
    CandidateUI,
    CoherenceVerdict,
    ConsensusDecision,
    ConsensusResult,
    GateAxis,
    GateDecision,
    GateOutcome,
    JudgeAxis,
    JudgeVote,
    SurfaceManifest,
    SurfaceState,
    SurfaceType,
    TenantContext,
    TrajectoryRecord,
)


@pytest.mark.unit
def test_tenant_context_frozen():
    ctx = TenantContext(
        tenant_id="tnt_a",
        user_id="usr_a",
        project_id="prj_a",
        descriptor=None,
        cost_budget_usd=Decimal("100"),
        cost_consumed_usd=Decimal("0"),
    )
    with pytest.raises(Exception):
        ctx.tenant_id = "different"


@pytest.mark.unit
def test_surface_manifest_dependency_graph():
    sm = SurfaceManifest(
        campaign_id=uuid4(),
        surfaces=[],
        dependency_graph={},
    )
    assert sm.schema_version == 1


@pytest.mark.unit
def test_gate_outcome_axes():
    """Gate axis enum covers all 6 deterministic axes from PRD §6.3 N3c."""
    axes = {a.value for a in GateAxis}
    assert {"lighthouse-a11y", "lighthouse-perf", "axe", "token-fidelity",
            "semantic-html", "visual-diff", "responsive"}.issubset(axes)


@pytest.mark.unit
def test_judge_vote_includes_provenance():
    """JudgeVote carries DEMAS-D provenance variables (PRD §6.4 N2)."""
    vote = JudgeVote(
        candidate_id=uuid4(),
        judge_axis=JudgeAxis.BRAND,
        score=0.85,
        confidence_interval=(0.78, 0.92),
        reasoning="Strong adherence to Apple-Grade primary palette.",
        provenance_vars=["dom_html", "design_md_tokens", "principles_md"],
        judge_model="gemini-3-flash",
    )
    assert vote.judge_axis == JudgeAxis.BRAND
    assert len(vote.provenance_vars) == 3


@pytest.mark.unit
def test_trajectory_record_carries_kms_key():
    """TrajectoryRecord includes per-subject KMS key for GDPR right-to-be-forgotten."""
    rec = TrajectoryRecord(
        trajectory_id=uuid4(),
        tenant_id="tnt_a",
        project_id="prj_a",
        campaign_id=None,
        surface_id=uuid4(),
        session_id="ses_a",
        ts=datetime.now(timezone.utc),
        node_name="n3a_generator",
        iteration=0,
        candidates=[],
        gate_outcomes=[],
        judge_votes=[],
        consensus=None,
        coherence=None,
        user_signal=None,
        encryption_key_id="projects/i-for-ai/locations/global/keyRings/atelier/cryptoKeys/tnt_a-key",
    )
    assert rec.encryption_key_id.startswith("projects/")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_data_contracts.py -v
```

Expected: 5 tests FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement data_contracts.py**

Create `atelier-core/src/atelier/shared/__init__.py` (empty) and `atelier-core/src/atelier/shared/data_contracts.py`:

```python
"""Pydantic v2 frozen data contracts for Atelier (PRD §9).

All models frozen, schema-versioned. Per CLAUDE.md invariant:
schema_version never decreases; fields never dropped.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ─── Enums ─────────────────────────────────────────────────────────────


class GateDecision(str, Enum):
    PASS = "PASS"
    REJECT = "REJECT"
    DEFER = "DEFER"


class GateAxis(str, Enum):
    LIGHTHOUSE_A11Y = "lighthouse-a11y"
    LIGHTHOUSE_PERF = "lighthouse-perf"
    AXE = "axe"
    TOKEN_FIDELITY = "token-fidelity"
    SEMANTIC_HTML = "semantic-html"
    VISUAL_DIFF = "visual-diff"
    RESPONSIVE = "responsive"


class JudgeAxis(str, Enum):
    BRAND = "brand"
    COPY = "copy"
    MOTION = "motion"
    TOKEN = "token"
    COHERENCE = "coherence"


class ConsensusDecision(str, Enum):
    CONVERGED = "CONVERGED"
    RETRY = "RETRY"
    DEFER_HUMAN = "DEFER_HUMAN"


class SurfaceType(str, Enum):
    PAGE = "page"
    COMPONENT = "component"
    TEMPLATE = "template"
    SCREEN = "screen"


class MutationOp(str, Enum):
    TOKEN_SWAP = "token-swap"
    LAYOUT_SWAP = "layout-swap"
    TYPOGRAPHY_SWAP = "typography-swap"
    MOTION_SWAP = "motion-swap"
    DENSITY_SHIFT = "density-shift"
    ASYMMETRY_INJECTION = "asymmetry-injection"
    HIERARCHY_RESTRUCTURE = "hierarchy-restructure"
    COPY_VOICE_SHIFT = "copy-voice-shift"


class UserSignalType(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    REQUEST_HUMAN = "request-human"


# ─── Models ────────────────────────────────────────────────────────────


class _Frozen(BaseModel):
    """Common base — every contract is frozen + extra-forbid + schema-versioned."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: int = 1


class AtelierDescriptor(_Frozen):
    """Optional per-project .atelier.yaml descriptor."""
    design_system_path: str | None = None
    target_stack: str | None = None
    acceptance_thresholds: dict[str, float] | None = None
    reference_images: list[str] = Field(default_factory=list)


class TenantContext(_Frozen):
    tenant_id: str
    user_id: str
    project_id: str
    descriptor: AtelierDescriptor | None
    cost_budget_usd: Decimal
    cost_consumed_usd: Decimal


class CandidateUI(_Frozen):
    candidate_id: UUID
    surface_id: UUID
    iteration: int
    parent_candidate_id: UUID | None = None
    mutation_op: MutationOp | None = None
    artifacts: dict[str, str]  # {"index.html": "<...>", "main.css": "..."}
    a2ui_payload: dict[str, Any] | None = None


class GateOutcome(_Frozen):
    candidate_id: UUID
    axis: GateAxis
    decision: GateDecision
    score: float | None = None
    diagnostic: str


class JudgeVote(_Frozen):
    candidate_id: UUID
    judge_axis: JudgeAxis
    score: float
    confidence_interval: tuple[float, float]
    reasoning: str
    provenance_vars: list[str]
    judge_model: str


class ConsensusResult(_Frozen):
    selected_candidate_id: UUID
    composite_score: float
    per_axis_scores: dict[JudgeAxis, JudgeVote]
    decision: ConsensusDecision


class CoherenceVerdict(_Frozen):
    surface_id: UUID
    token_use_valid: bool
    pattern_reuse_rate: float
    decisions_md_compliant: bool
    regression_check_passed: bool
    violations: list[str] = Field(default_factory=list)


class SurfaceState(_Frozen):
    surface_id: UUID
    name: str
    type: SurfaceType
    brief: str
    axes_required: list[GateAxis]
    passes: bool = False
    iteration_count: int = 0
    human_approved: bool | None = None
    coherence_review_required: bool = False
    started_at: datetime | None = None
    completed_at: datetime | None = None


class SurfaceManifest(_Frozen):
    campaign_id: UUID
    surfaces: list[SurfaceState]
    dependency_graph: dict[UUID, list[UUID]]


class UserSignal(_Frozen):
    signal_type: UserSignalType
    timestamp: datetime
    user_id: str
    notes: str | None = None


class TrajectoryRecord(_Frozen):
    """Persisted to BigQuery, partitioned by DATE(ts) clustered by tenant_id."""
    trajectory_id: UUID
    tenant_id: str
    project_id: str
    campaign_id: UUID | None
    surface_id: UUID
    session_id: str
    ts: datetime
    node_name: str
    iteration: int
    candidates: list[CandidateUI]
    gate_outcomes: list[GateOutcome]
    judge_votes: list[JudgeVote]
    consensus: ConsensusResult | None
    coherence: CoherenceVerdict | None
    user_signal: UserSignal | None
    encryption_key_id: str  # KMS key per subject
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_data_contracts.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add atelier-core/src/atelier/shared/__init__.py atelier-core/src/atelier/shared/data_contracts.py atelier-core/tests/unit/test_data_contracts.py
git commit -m "feat(core): add Pydantic v2 frozen data contracts (PRD §9)

10 enums + 11 frozen models covering: TenantContext, AtelierDescriptor,
SurfaceManifest, SurfaceState, CandidateUI, GateOutcome, JudgeVote,
ConsensusResult, CoherenceVerdict, UserSignal, TrajectoryRecord.

All models inherit from _Frozen base (ConfigDict frozen=True,
extra='forbid', schema_version=1). Per CLAUDE.md invariant:
schema_version never decreases, fields never dropped.

5 unit tests cover: frozen mutation guard, schema_version presence,
gate axes coverage, judge vote provenance, KMS key per trajectory.

Refs: PRD §9 data contracts, CLAUDE.md no_silent_error_suppression"
```

#### Task 2.3: Atelier API skeleton (FastAPI + health endpoint)

**Files:**
- Create: `atelier-core/src/atelier/api.py`
- Create: `atelier-core/src/atelier/cli.py`
- Modify: `atelier-core/pyproject.toml` (add fastapi + uvicorn)

- [ ] **Step 1: Add FastAPI deps + regenerate lockfile**

Edit `atelier-core/pyproject.toml`, append to `dependencies`:

```toml
    "fastapi>=0.115,<1",
    "uvicorn[standard]>=0.32,<1",
    "click>=8.1,<9",
```

Then:

```bash
pip-compile pyproject.toml -o requirements.lock --resolver=backtracking
pip install -r requirements.lock
```

- [ ] **Step 2: Write the failing test**

Create `atelier-core/tests/unit/test_api_health.py`:

```python
"""Tests for Atelier API health endpoint."""

import pytest
from fastapi.testclient import TestClient

from atelier.api import app


@pytest.mark.unit
def test_health_returns_200():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert "version" in body
    assert "schema_version" in body
```

```bash
pytest tests/unit/test_api_health.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'atelier.api'`

- [ ] **Step 3: Implement api.py**

Create `atelier-core/src/atelier/api.py`:

```python
"""Atelier API — FastAPI app exposing health, intake, generate, eval endpoints."""

from fastapi import FastAPI

from atelier.__version__ import __version__

app = FastAPI(
    title="Atelier API",
    description="Autonomous design agent — converges UI/UX to flawless across multi-axis judges.",
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
)


@app.get("/health")
async def health() -> dict[str, str | int]:
    """Liveness probe for Cloud Run + Cloud Monitoring uptime checks."""
    return {
        "status": "healthy",
        "version": __version__,
        "schema_version": 1,
    }
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/unit/test_api_health.py -v
```

Expected: PASS.

- [ ] **Step 5: Implement cli.py (entrypoint for `atelier` command)**

Create `atelier-core/src/atelier/cli.py`:

```python
"""Atelier CLI — entrypoint for `atelier run` and related commands."""

import click
import uvicorn

from atelier.__version__ import __version__


@click.group()
@click.version_option(version=__version__, prog_name="atelier")
def main() -> None:
    """Atelier — autonomous design agent."""


@main.command()
@click.option("--host", default="0.0.0.0", help="Bind host")
@click.option("--port", default=8080, type=int, help="Bind port")
@click.option("--reload", is_flag=True, help="Auto-reload on code changes")
def serve(host: str, port: int, reload: bool) -> None:
    """Run the Atelier API server."""
    uvicorn.run(
        "atelier.api:app",
        host=host,
        port=port,
        reload=reload,
        log_config=None,  # use our structlog config
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Verify CLI works**

```bash
atelier --version
atelier serve --help
```

Expected: Version prints; serve --help shows host/port/reload options.

- [ ] **Step 7: Commit**

```bash
git add atelier-core/src/atelier/api.py atelier-core/src/atelier/cli.py atelier-core/tests/unit/test_api_health.py atelier-core/pyproject.toml atelier-core/requirements.lock
git commit -m "feat(api): scaffold FastAPI app with /health endpoint + CLI entrypoint

api.py: FastAPI app with /health liveness probe (Cloud Run + Cloud
Monitoring uptime checks). Returns version + schema_version.

cli.py: Click-based CLI with 'atelier serve' subcommand wrapping uvicorn.

1 unit test passing.

Refs: PRD §6.7 SLOs (p95_turn_latency ≤ 8s health response)"
```

#### Task 2.4: Containerize + push image to Artifact Registry

**Files:**
- Create: `atelier-deploy/docker/Dockerfile.api`
- Create: `atelier-deploy/scripts/build-and-push.sh`

- [ ] **Step 1: Write Dockerfile.api**

Create `atelier-deploy/docker/Dockerfile.api`:

```dockerfile
# atelier-deploy/docker/Dockerfile.api
# Atelier API — Cloud Run service container
FROM python:3.11.9-slim-bookworm AS base

# Pin base image at release; bump via Dependabot
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps first (better layer caching)
COPY atelier-core/requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir -r /app/requirements.lock

# Copy source
COPY atelier-core/src /app/src
COPY atelier-core/pyproject.toml /app/pyproject.toml
COPY atelier-core/README.md /app/README.md

RUN pip install --no-cache-dir -e .

# Run as non-root
RUN useradd -u 1001 -m atelier
USER atelier

EXPOSE 8080
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

CMD ["atelier", "serve", "--host", "0.0.0.0", "--port", "8080"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:8080/health || exit 1
```

- [ ] **Step 2: Write build-and-push.sh**

Create `atelier-deploy/scripts/build-and-push.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

PROJECT="${GOOGLE_CLOUD_PROJECT:-i-for-ai}"
REGION="${REGION:-us-central1}"
REPO="atelier"
IMAGE="${1:-api}"
TAG="${2:-$(git rev-parse --short HEAD)}"

REPO_URL="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}"

# Ensure repo exists (idempotent)
gcloud artifacts repositories describe "${REPO}" \
  --location="${REGION}" --project="${PROJECT}" 2>/dev/null || \
gcloud artifacts repositories create "${REPO}" \
  --repository-format=docker \
  --location="${REGION}" \
  --project="${PROJECT}" \
  --description="Atelier container images"

# Configure docker auth
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --project="${PROJECT}"

# Build + push
echo "Building ${REPO_URL}/${IMAGE}:${TAG}"
docker build \
  -f atelier-deploy/docker/Dockerfile.${IMAGE} \
  -t "${REPO_URL}/${IMAGE}:${TAG}" \
  -t "${REPO_URL}/${IMAGE}:latest" \
  .

docker push "${REPO_URL}/${IMAGE}:${TAG}"
docker push "${REPO_URL}/${IMAGE}:latest"

echo "Pushed: ${REPO_URL}/${IMAGE}:${TAG}"
echo "Update Cloud Run service to this image:"
echo "  gcloud run services update atelier-staging-api \\"
echo "    --image=${REPO_URL}/${IMAGE}:${TAG} \\"
echo "    --region=${REGION} --project=${PROJECT}"
```

- [ ] **Step 3: Make executable + run**

```bash
chmod +x atelier-deploy/scripts/build-and-push.sh
./atelier-deploy/scripts/build-and-push.sh api
```

Expected: Image builds, repository auto-created, image pushes to Artifact Registry. Final URL printed.

- [ ] **Step 4: Update Cloud Run service to use the new image**

```bash
gcloud run services update atelier-staging-api \
  --image="us-central1-docker.pkg.dev/i-for-ai/atelier/api:$(git rev-parse --short HEAD)" \
  --region=us-central1 --project=i-for-ai
```

- [ ] **Step 5: Verify health endpoint live**

```bash
SERVICE_URL=$(gcloud run services describe atelier-staging-api --region=us-central1 --project=i-for-ai --format='value(status.url)')
curl -fsS "${SERVICE_URL}/health" | jq .
```

Expected: `{"status": "healthy", "version": "0.1.0a0", "schema_version": 1}`

- [ ] **Step 6: Commit**

```bash
git add atelier-deploy/docker/Dockerfile.api atelier-deploy/scripts/build-and-push.sh
git commit -m "feat(deploy): containerize Atelier API + Artifact Registry push script

Dockerfile.api:
- python:3.11.9-slim-bookworm base (pinned)
- non-root user atelier (uid 1001)
- HEALTHCHECK curl /health every 30s
- atelier serve as ENTRYPOINT

build-and-push.sh:
- idempotent Artifact Registry repo creation
- gcloud docker auth configuration
- multi-tag (sha + latest)

Cloud Run staging now serving v0.1.0a0 with health endpoint live.

Refs: PRD §8 Cloud Run runtime, ADR 0002"
```

#### Task 2.5: End-of-Day-2 checkpoint

- [ ] **Step 1: Run full test suite**

```bash
cd atelier-core
pytest tests/ -v
```

Expected: 8/8 tests pass (2 from D1 + 5 from data_contracts + 1 from api_health).

- [ ] **Step 2: Update CHECKPOINTS.md, COST_LEDGER.md, features.json**

(Same pattern as D1 Task 1.7 Step 2.)

- [ ] **Step 3: Push**

```bash
git push origin phase/1
```

---

### Day 3 — Fri May 17: Port `agent-dag-pipeline` ADK plumbing into Atelier

**Goal:** Subclass agent-dag-pipeline's GateAgent for Atelier's first node (N1 Brief Parser); wire the ADK Runner; deploy the first end-to-end "trivial" pipeline that reads a brief and emits a structured BriefSpec.

**Cost target this day:** $200-300

**Features delivered (refer to `features.json` for full atomic units):**
- F0010: N1 Brief Parser GateAgent subclass
- F0011: Brief Parser deterministic gate (intent schema validator)
- F0012: Brief Parser probabilistic agent (Gemini 3 Flash via Vertex)
- F0013: ADK Runner wired with InMemorySessionService
- F0014: First end-to-end test: brief text → BriefSpec
- F0015: BigQuery dataset + trajectory table created via Terraform
- F0016: First trajectory write per N1 execution

**Key tasks (condensed format from here on):**

#### Task 3.1: N1 Brief Parser node

- Create `atelier-core/src/atelier/dag/nodes/n1_brief_parser.py`
- Subclass `agent_dag.adk.gate_agent.GateAgent`
- `gate(state)` → validate `state["brief_text"]` is non-empty + ≤ 4096 chars
- `agent(state, ctx)` → Gemini 3 Flash structured-output call returning BriefSpec dict
- Test: `tests/unit/test_n1_brief_parser.py` — 3 tests (gate pass, gate reject empty, agent returns valid BriefSpec via mocked Gemini)
- Commit: `feat(dag): N1 Brief Parser — Gate-Agent subclass with Gemini 3 Flash extraction`

#### Task 3.2: ADK Runner integration

- Create `atelier-core/src/atelier/dag/orchestrator.py`
- Build the Phase 1 pipeline as a `SequentialAgent` containing `[N1 Brief Parser]` (more nodes added in subsequent days)
- Use `InMemorySessionService` for D3; switch to `VertexAiSessionService` in D4
- Test: end-to-end run with brief → BriefSpec via ADK Runner
- Commit: `feat(dag): ADK orchestrator wires Phase 1 pipeline + InMemorySessionService`

#### Task 3.3: BigQuery trajectory table (Terraform)

- Add `atelier-deploy/terraform/bigquery.tf`:
  - Dataset `atelier_staging` (partitioned by `DATE(ts)`, clustered by `tenant_id`)
  - Table `trajectories` schema mirroring `TrajectoryRecord` Pydantic model
  - Authorized view per tenant (placeholder; real per-tenant in Phase 2)
- `terraform plan + apply -var-file=staging.tfvars`
- Commit: `feat(deploy): BigQuery dataset + trajectories table for Phase 1`

#### Task 3.4: First trajectory write

- Add `atelier-core/src/atelier/shared/observability.py` with `emit_trajectory(record: TrajectoryRecord)` writing to BigQuery
- Wire emit into the ADK orchestrator's `after_agent_callback`
- Manual test: run pipeline once locally, verify row appears in BigQuery
- Commit: `feat(observability): trajectory emission to BigQuery on each pipeline run`

#### EOD checkpoint (same pattern as D1/D2)

---

### Day 4 — Sat May 18: N2 Source Resolver + Memory Bank wiring

**Cost target:** $200-300

**Features delivered:**
- F0020-F0027: N2 Source Resolver (descriptor + path inference + DESIGN.md lint + Memory Bank read)

**Key tasks:**
- N2 deterministic gate: descriptor file exists OR brief contains a path → resolve to project context dict
- N2 probabilistic agent: pull DESIGN.md tokens via `dmd lint` (subprocess), pull principles, pull Memory Bank prior preferences
- Wire `VertexAiMemoryBankService` (via Terraform addition)
- Pipeline now: `SequentialAgent([N1 Brief Parser, N2 Source Resolver])`
- 6 unit tests (mocked Memory Bank + Gemini)
- 1 integration test: brief + descriptor → BriefSpec + ProjectContext

#### EOD checkpoint

---

### Day 5 — Sun May 19: N3a Generator (Stitch MCP wiring) + Apigee cost router

**Cost target:** $250-350

**Features delivered:**
- F0030-F0038: N3a Generator with Stitch MCP + Gemini direct fallback + Apigee config

**Key tasks:**
- Wire Stitch MCP via ADK `MCPToolset` pointing at `https://stitch.googleapis.com/mcp` with `X-Goog-Api-Key` from Secret Manager (`atelier-geap-api-key`)
- Implement N3a as a `ParallelAgent` with K=3 sub-generators (placeholder for K=6 in Phase 2)
- Apigee: skip the full Apigee X org for now (saves $500/mo); use a simple LiteLLM-style router in code
- Each generator subagent calls Stitch `generate_screen_from_text` OR Gemini 3 Pro direct
- 5 unit tests + 1 integration test (mocked Stitch responses)
- Generation success rate ≥ 95% on 20 fixture briefs

#### EOD checkpoint

---

### Day 6 — Mon May 20: N3c Deterministic Gate (parallel × 6 axes)

**Cost target:** $250-350

**Features delivered:**
- F0040-F0050: 6 parallel deterministic gate axes

**Key tasks:**
- Lighthouse axis: subprocess `lighthouse <url> --output=json --quiet` (Phase 1 simplified — Phase 2 dockerized)
- axe axis: subprocess `axe <url> --tags wcag2aa`
- Token-fidelity grep axis: regex over generated artifact for hex/font/spacing not in DESIGN.md
- Semantic-HTML axis: `html-validate` subprocess
- Visual-diff axis: Playwright screenshot vs reference (skip if no reference; mark `DEFER`)
- Responsive axis: Playwright at 4 breakpoints (375, 768, 1280, 1920)
- All 6 run in `ParallelAgent` (asyncio.gather under the hood via ADK)
- 12 unit tests (2 per axis: pass case + fail case)
- Pipeline now: `SequentialAgent([N1, N2, N3a, N3c])`

#### EOD checkpoint

---

### Day 7 — Tue May 21: Phase 1 Acceptance Gate

**Cost target:** $100-200

**Goal:** End-to-end one-surface convergence on `pipeline-observatory/index.html` brief; tag `phase1-accepted`; merge to main.

#### Task 7.1: Wire stub Judge for Phase 1 gate (full ConsensusAgent ships in Phase 2)

- Create `atelier-core/src/atelier/dag/nodes/n3d_consensus_stub.py`
- Single Gemini 3 Flash call with all 5 axes prompted in one rubric
- Returns `ConsensusResult` with stub per-axis scores
- Pipeline now complete for Phase 1: `SequentialAgent([N1, N2, N3a, N3c, N3d_stub, N4_validator_stub])`

#### Task 7.2: Run end-to-end test on `pipeline-observatory/index.html`

```bash
atelier run \
  --brief "Redesign the hero section of pipeline-observatory to use a darker accent color while maintaining the editorial register" \
  --reference https://manzela.github.io/pipeline-observatory/ \
  --stack vanilla-html \
  --convergence-bar ship-it
```

Expected: pipeline runs end-to-end; outputs converged HTML/CSS; trajectory written to BigQuery; OTel spans visible in Cloud Trace.

#### Task 7.3: Run WebGen-Bench 50/484 task subset

- Create `atelier-eval/src/atelier_eval/runner.py` with subset support
- Run subset via local script (full 484 happens nightly via CI in Phase 2)
- Verify 50/50 tasks run without crashes; record scores

#### Task 7.4: Smoke test deployed Cloud Run service

```bash
./atelier-deploy/scripts/smoke.sh staging
```

Expected:
- /health returns 200
- /docs (FastAPI swagger) returns 200
- Vertex AI auth works
- BigQuery trajectory ingest works
- Memory Bank read/write works
- OTel trace visible in Cloud Trace within 30s

#### Task 7.5: Phase 1 acceptance protocol

- [ ] All 7 acceptance criteria from PRD §15 D7 verified ✅
- [ ] Update `docs/runbooks/phase1-acceptance.md` with evidence (paste output)
- [ ] Merge `phase/1` → `main` with tag `phase1-accepted`:

```bash
cd ~/Professional\ Profile/atelier
git checkout main
git pull
git merge --no-ff phase/1 -m "Merge phase/1: Phase 1 Foundation accepted (D7 2026-05-21)"
git tag -a phase1-accepted -m "Phase 1 accepted on $(date -u +%Y-%m-%d). End-to-end on 1 surface + Cloud Run staging deploy + 50/484 WebGen-Bench passing."
git push origin main --tags
```

- [ ] Clean up phase1 worktree (optional, can leave in place):

```bash
git worktree remove .worktrees/phase1-foundation  # if not needed for hotfixes
```

---

## Phase 2: 10× Mechanisms (W2, May 22-28)

**Worktree:** `.worktrees/phase2-10x-mechanisms/` on branch `phase/2` (created when phase/1 accepted)
**Cost target:** $1,300 (cumulative $2,500 of $5K = 50%)
**Acceptance gate (D14):** 12-surface autonomous campaign on `pipeline-observatory`; full 484-task WebGen-Bench eval ≥ 51; calibration dashboard live; all 4 A2UI renderers; 5 beta tenants signed in.

### Day 8 (Wed May 22): N3b CSC-D + EvoDesign K=6

**Features delivered (F0060-F0078):**
- N3b Constitutional Self-Critique against 12-principle Apple-Grade constitution
- EvoDesign upgrade: K=3 → K=6 candidates per iteration
- 6 mutation operators (token-swap, layout-swap, typography-swap, motion-swap, density-shift, hierarchy-restructure) + crossover stub
- LoopAgent wraps the EvoDesign loop with `max_iterations=5`, escalate on convergence

**Key tasks:**
1. Create `@atelier/constitution-apple-grade` npm package skeleton + populate with the 12 principles from `DESIGN_PRINCIPLES_APPLE.md` (see `~/Professional Profile/DESIGN_PRINCIPLES_APPLE.md` for source content)
2. Implement N3b CSC-D node with calibration check (κ ≥ 0.7 vs human rubric on 50-task calibration set)
3. Implement 6 mutation operators in `atelier-core/src/atelier/dag/evolutionary/mutation_operators.py` — each is a small function `apply(candidate: CandidateUI, project_context: dict) → CandidateUI`
4. Wire ADK `LoopAgent(sub_agents=[ParallelAgent(K_generators), N3b_CSC_D, N3c_DeterministicGate, N3e_FixerStub], max_iterations=5)` with escalate-on-converged
5. 18 unit tests (3 per mutation operator + 6 for CSC-D)
6. Integration test: 6-candidate loop converges on 5-task fixture set in ≤3 iterations

### Day 9 (Thu May 23): EvoDesign refinement + Hebbian Mutator (GEPA wrapper)

**Features delivered (F0079-F0087):**
- N3e Fixer with Hebbian Mutator wrapping `adk optimize` (GEPA)
- 5 explicit failure-pattern → mutation mappings (A11Y_FAIL, TOKEN_DRIFT, BRAND_INCONSIST, LOW_ORIGINALITY, MOTION_NO_REDUCED)
- Reviewer subagent dispatch infrastructure (Ralph Loop "DONE" token)
- Per-tenant cost router (LiteLLM virtual keys via Apigee placeholder)

**Key tasks:**
1. Wrap `adk optimize` (GEPA) as a Python helper in `atelier-core/src/atelier/flywheel/prompt_mutator.py`
2. Implement 5 failure-pattern mappings as a dict + dispatcher
3. Implement Reviewer subagent dispatch logic in `atelier-core/src/atelier/dag/nodes/reviewer.py` — calls Opus-backed agent with adversarial-critique prompt; expects strict "DONE" token
4. 12 unit tests + 2 integration tests
5. Run end-to-end on the 5-task fixture set; verify Hebbian mutator fires when contrast fails

### Day 10 (Fri May 24): N3d ConsensusAgent + 5 specialized rubric judges

**Features delivered (F0088-F0102):**
- 5 specialized judges (Brand, Copy, Motion, Token-fidelity, Cross-screen-coherence)
- DEMAS-D Provenance Matrix per axis
- Bayesian-weighted consensus vote with confidence intervals
- ADK `rubric_based_final_response_quality_v1` integration

**Key tasks:**
1. For each judge: create `atelier-core/src/atelier/judges/<axis>_judge.py` with rubric definition
2. DEMAS-D Provenance Matrix in `atelier-core/src/atelier/judges/demas_provenance.py` — function `provenance_for(axis, candidate, project_context) → list[var_name]`
3. ConsensusAgent custom `BaseAgent` subclass in `atelier-core/src/atelier/judges/consensus.py` — `_run_async_impl` calls 5 judge subagents in parallel via `asyncio.gather`, aggregates Bayesian-weighted vote
4. 25 unit tests (5 per judge: rubric structure, provenance filter correctness, edge cases)
5. Integration test: full 5-judge consensus on 5 fixture surfaces

### Day 11 (Sat May 25): Calibration golden set + drift detection scaffolding

**Features delivered (F0103-F0112):**
- Calibration golden set: 100 hand-graded designs (20 per judge axis)
- `calibration.atelier.dev` static site scaffolded on Firebase Hosting
- Calibration drift detection cron (weekly Mon 03:17 UTC via Cloud Scheduler)
- `atelier-eval/src/atelier_eval/calibration_dashboard.py` runner

**Key tasks:**
1. Curate 100-task calibration golden set (Daniel + Claude collaborate; 1 hour each axis)
2. Build static dashboard (vanilla HTML + Tailwind CDN, mirrors `pipeline-observatory` aesthetic)
3. Cloud Scheduler job → Cloud Run job runs calibration weekly
4. Results JSON → Firestore → static site rebuild via Cloud Build trigger
5. Alert on correlation drop > 0.05 week-over-week → Telegram

### Day 12 (Sun May 26): N12 Campaign Orchestrator + Surface Manifest

**Features delivered (F0113-F0125):**
- Campaign Orchestrator outer harness
- `surfaces.json` JSON ledger (per-campaign persistent state)
- Cloud Scheduler + Cloud Tasks orchestration
- Cross-Surface Coherence Validator (token use, pattern reuse ≥ 30%, DECISIONS.md compliance, regression check)
- Campaign Checkpoint Writer

**Key tasks:**
1. `atelier-core/src/atelier/campaign/` module: orchestrator.py, brief_parser.py, manifest.py, picker.py, coherence_validator.py, checkpoint_writer.py
2. Cloud Tasks queue: `atelier-staging-campaign-surfaces`
3. Cloud Scheduler trigger: per-campaign worker
4. End-to-end test: 5-surface mini-campaign decomposition + sequential surface execution + coherence check
5. 18 unit tests + 1 integration test

### Day 13 (Mon May 27): N13 PIP + 13-question catalog + visual options

**Features delivered (F0126-F0140):**
- PIP Router (adaptive depth: atomic 2-3 / small 5-7 / large 10-12 / greenfield 12-15)
- Skip-Path Resolver (descriptor + Memory Bank + brief-parsed)
- 13-question catalog with DAPLab pattern mapping
- BriefSpec Synthesizer (immutable JSON, user-approved)
- Visual options text-only (visual thumbnails behind feature flag, Phase 1.5)

**Key tasks:**
1. `atelier-core/src/atelier/intake/` modules: pip_router.py, question_catalog.py, intake_agent.py, brief_spec_synthesizer.py
2. 13-question catalog as YAML + Pydantic load
3. Adaptive depth logic
4. Skip-path resolver: descriptor parser, Memory Bank query, brief NLP extraction
5. End-to-end test: 5 fixture intake scenarios → BriefSpec.json
6. 20 unit tests + 1 integration test

### Day 14 (Tue May 28): Phase 2 Acceptance Gate

**Features delivered (F0141-F0150):**
- All 4 A2UI renderers (React + Flutter + Lit + Angular) implemented
- Identity Platform multi-tenant auth wired (5 invited beta tenants sign in)
- Privacy Policy + ToS published (Termly template + attorney review)
- Status page live at `status.atelier.dev`
- Documentation 90% complete

**Acceptance protocol:**
1. Run 12-surface autonomous campaign on `pipeline-observatory` end-to-end
2. Run full WebGen-Bench eval (484 tasks via Cloud Run job, ~30 min)
3. Verify ≥ 51% pass rate (target ≥ 51, stretch ≥ 60)
4. Verify all 4 A2UI renderers produce equivalent output on 5 fixture surfaces
5. 5 beta tenants successfully sign in via Identity Platform
6. Calibration dashboard live with 1 week of data
7. Tag `phase2-accepted`, merge to main, push tags

---

## Phase 3: Production Polish + 10× Validation (W3, May 29 - Jun 4)

**Worktree:** `.worktrees/phase3-production-polish/` on branch `phase/3`
**Cost target:** $2,500 (cumulative $5K of $5K = 100%)
**Acceptance gate (Jun 3 noon):** All 13 N-contributions evidenced; 32 pre-launch artifacts live; G4S submission filed.

### Day 15 (Wed May 29): DPO + LoRA pipeline (per-project judge personalization)

**Features delivered (F0151-F0162):**
- 3-tier dataset flywheel (T1 baseline / T2 approved / T3 failure)
- DPO preference pair generator (margin ≥ 0.15 filter)
- Vertex AI Tuning job submission for first-project LoRA
- Vertex AI Endpoints with Multi-Tuning serving
- Reward signal computation (user_explicit + user_implicit + judge_self_consistency + convergence_completion)

**Key tasks:**
1. `atelier-core/src/atelier/flywheel/` modules: data_flywheel.py, preference_pairs.py, training_trigger.py
2. Vertex AI tuning job submission via Python SDK
3. First-project LoRA fine-tuned on `pipeline-observatory` historical accept/reject data
4. Eval-only baseline run before training (per ADR 0005 lineage)
5. Eval improvement ≥ 2% triggers registration
6. End-to-end test: synthetic 100 DPO pairs → tuning job → endpoint deploy → judge calls served LoRA

### Day 16 (Thu May 30): Per-project LoRA serving + judge swap

- Wire serving the per-project LoRA via Vertex AI Endpoints in the consensus agent (replace base Gemini for that judge axis)
- Calibration drift detection on the new LoRA judge
- Telegram alert on judge swap success
- 8 unit tests + 1 integration test

### Day 17 (Fri May 31): N9 Open Eval Adapters + N10 Convergence Spec RFC + N11 Public scoreboard

**Features delivered (F0163-F0175):**
- 5 benchmark adapters: WebGen-Bench, Design2Code, Web2Code, ScreenSpot, FrontendBench → ADK `EvalCase` schema
- Submitted as 5 PRs to `google/adk-python`
- Convergence Spec RFC v0.1 published in repo
- `bench.atelier.dev` accepts community submissions

**Key tasks:**
1. `atelier-eval/src/atelier_eval/adapters/` — one file per benchmark
2. Each adapter: download → parse → convert to `EvalCase` JSON
3. PR template + opens 5 PRs to `google/adk-python`
4. Draft Convergence Spec RFC v0.1 in `docs/rfcs/convergence-spec-v0.1.md`
5. Build community submission form on `bench.atelier.dev` (Cloud Function + Firestore)

### Day 18 (Sat Jun 1): Atelier Skills Pack + atelier-action + Figma plugin + Chrome extension + npm constitution

**Features delivered (F0176-F0185):**
- 6 Atelier Skills published via ADK Skills for Agents (case-study, dashboard, marketing, e-commerce, portfolio, docs-site)
- `atelier-action` published to GitHub Marketplace
- Figma plugin submitted to Figma Community
- Chrome extension submitted to Chrome Web Store
- `@atelier/constitution-apple-grade` published to npm

**Key tasks:**
1. Each Skill is ~150 LOC; templated structure
2. atelier-action: Node.js + ESM, calls Atelier API
3. Figma plugin: ~200 LOC manifest + bridge
4. Chrome extension: Manifest V3 + content script + service worker
5. npm package: 12-principle constitution as importable JSON

### Day 19 (Sun Jun 2): Marketing site + waitlist + Loom + arXiv + designer testimonials

**Features delivered (F0186-F0193):**
- `atelier.dev` polished marketing site
- Waitlist (≥ 500 signups target via Twitter build-in-public thread)
- 90-sec Loom walkthrough recorded + embedded
- arXiv preprint draft submitted (4-page workshop format)
- ≥ 3 designer-in-residence testimonials captured

### Day 20 (Mon Jun 3): Phase 3 Acceptance + v1.0.0 Release + G4S Submission Filed

**Acceptance criteria (all must pass):**
- All 13 N-contributions have evidence in `atelier-eval/data/results/`
- All 32 pre-launch artifacts live (per PRD §17 prelaunch-checklist)
- WebGen-Bench full eval result published (target ≥ 60, stretch ≥ 77 with first-project LoRA)
- Public sign-up live, freemium tier active
- 4-min demo video + 2-min backup + 60-sec elevator pitch recorded
- arXiv preprint draft submitted
- ≥ 3 designer-in-residence testimonials captured
- ≥ 500 waitlist signups
- Co-marketing 1-pager sent to Google Cloud DA
- **G4S submission package filed by noon**

**Tasks:**
1. Final smoke test on staging + production
2. CHANGELOG updated for v1.0.0 release
3. release-please tags v1.0.0 + publishes to PyPI/npm
4. G4S submission filed via Devpost or equivalent platform
5. Twitter announcement thread posted at noon
6. Hacker News Show HN drafted (post tomorrow morning)
7. Product Hunt scheduled for Jun 5 12:01 AM PT

### Day 21 (Tue Jun 4): Final eval + buffer day

- Full WebGen-Bench eval run with first-project LoRA active (the "stretch ≥ 77" attempt)
- Final smoke test on staging + prod
- Tag v1.0.0 release
- Pre-recorded backup demo as insurance for Jun 5

### Jun 5 (Wed): Official deadline — submission already filed

- Daniel available for live demo office hours via Calendly
- Hacker News Show HN posted in morning
- Product Hunt launch live at 12:01 AM PT
- Recap thread on Twitter EOD

---

## Phase Acceptance Protocols

### Phase 1 acceptance (D7 May 21)

```bash
# 1. End-to-end smoke
atelier run --brief "Redesign hero of pipeline-observatory" --reference https://manzela.github.io/pipeline-observatory/

# 2. Verify trajectory in BigQuery
bq query --use_legacy_sql=false 'SELECT COUNT(*) FROM atelier_staging.trajectories WHERE DATE(ts) = CURRENT_DATE()'

# 3. WebGen-Bench 50/484 subset
cd atelier-eval && python -m atelier_eval.runner --suite webgen_bench --subset 50

# 4. Smoke test deployed Cloud Run
./atelier-deploy/scripts/smoke.sh staging

# 5. Tag + merge if all green
git checkout main && git merge --no-ff phase/1 -m "Merge phase/1: Phase 1 accepted"
git tag -a phase1-accepted -m "Phase 1 accepted $(date -u +%Y-%m-%d)"
git push origin main --tags
```

### Phase 2 acceptance (D14 May 28)

```bash
# 1. 12-surface autonomous campaign
atelier campaign --brief "Redesign all 12 pages of pipeline-observatory" --reference https://manzela.github.io/pipeline-observatory/

# 2. Full WebGen-Bench (484 tasks, ~30 min via Cloud Run job)
cd atelier-eval && python -m atelier_eval.runner --suite webgen_bench --subset 0

# 3. Verify score ≥ 51 (target 51, stretch 60)
cat atelier-eval/data/results/webgen_bench_latest.json | jq .summary.composite_score

# 4. 5 beta tenants signed in
gcloud identity-platform tenants list --project=i-for-ai

# 5. Calibration dashboard live with 1 week of data
curl https://calibration.atelier.dev/api/history | jq '. | length'

# 6. Tag + merge if all green
git checkout main && git merge --no-ff phase/2 -m "Merge phase/2: Phase 2 accepted"
git tag -a phase2-accepted -m "Phase 2 accepted $(date -u +%Y-%m-%d)"
git push origin main --tags
```

### Phase 3 acceptance (D20 Jun 3 noon)

```bash
# 1. Verify all 13 novel contributions have evidence files
ls -la atelier-eval/data/results/n*.json | wc -l  # expect ≥ 13

# 2. All public sites live
for url in atelier.dev docs.atelier.dev bench.atelier.dev calibration.atelier.dev status.atelier.dev; do
  curl -fsS -o /dev/null -w "%{http_code} $url\n" "https://$url"
done  # expect all 200

# 3. Public sign-up working
# Manual: visit atelier.dev → sign up → verify magic link works

# 4. G4S submission package complete
ls -la submission/
#  - project-description.md (≤500 words)
#  - demo-video-4min.mp4 + demo-video-vertical.mp4
#  - elevator-pitch-60sec.mp4
#  - backup-demo-2min.mp4
#  - team-bio.md
#  - built-with-google.md
#  - arxiv-preprint-link.txt
#  - benchmark-results-summary.md
#  - testimonials.md
#  - calendly-office-hours.txt

# 5. Submit to G4S via Devpost
# (Manual via web UI by Daniel)

# 6. Tag v1.0.0
git checkout main && git merge --no-ff phase/3 -m "Merge phase/3: Phase 3 accepted; v1.0.0 release"
git tag -a v1.0.0 -m "Atelier v1.0.0 — public launch + G4S submission filed"
git push origin main --tags
```

---

## Self-Review

**1. Spec coverage:**
- ✅ PRD §1-5 (goal, target, problem, 10× thesis, 13 contributions) — covered by phase acceptance gates
- ✅ PRD §6 architecture (PIP / Campaign / 8-node DAG) — Day 13 / Day 12 / Days 3-7 + Day 8-10
- ✅ PRD §7 production-grade SaaS layer — Days 2 (Terraform), 5 (Apigee), 14 (Identity), 20 (Stripe)
- ✅ PRD §8-10 tech stack + data contracts + inheritance — Day 1-2
- ✅ PRD §11 Strategy v2 — codified in CLAUDE.md (already committed)
- ✅ PRD §12-15 MVP scope + repo + CI/CD + sprint plan — this document + ROADMAP.md
- ✅ PRD §16 10× outcome checklist — phase acceptance gates verify
- ✅ PRD §17 pre-launch checklist — Day 18-20
- ✅ PRD §18 launch motion — Day 20-21 + Jun 5
- ✅ PRD §19 risk register — addressed in CLAUDE.md hard rules + cost ledger discipline
- ✅ PRD §21 failure trichotomy — codified in CLAUDE.md
- ✅ PRD §22 panic + resume — Day 6 (CLI) + Day 14 (Telegram)
- ✅ PRD §23-25 governance sections — already in PRD as §23-25
- ✅ PRD §26 glossary — already in PRD
- ✅ PRD §27 limits.yaml — Day 2 (initial schema) + Day 14 (full populate)
- ✅ PRD §28 worktree-per-phase — referenced throughout

**2. Placeholder scan:**
- All TBD / TODO references in PRD §19 + §21 + §22 are explicit deferrals, not placeholders
- All "Phase 2 deliverable" / "Phase 3 deliverable" notes are scoped to specific days
- No "implement later" or "fill in details" anywhere

**3. Type consistency:**
- `BriefSpec` defined Day 1, used Day 2-21 — consistent
- `SurfaceManifest` defined Day 2, used Day 12-21 — consistent
- `JudgeAxis` enum (BRAND/COPY/MOTION/TOKEN/COHERENCE) consistent across Days 10, 11, 15
- `GateAxis` enum (LIGHTHOUSE_A11Y/LIGHTHOUSE_PERF/AXE/TOKEN_FIDELITY/SEMANTIC_HTML/VISUAL_DIFF/RESPONSIVE) consistent across Days 6, 11
- `ConsensusDecision` enum (CONVERGED/RETRY/DEFER_HUMAN) consistent across Days 10, 12

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-14-atelier-sprint-plan.md`.

`features.json` will be populated with the full ~194 atomic feature entries in a follow-up commit (one feature per task above × 6-12 atomic tasks per day × 21 days ≈ 194).

**Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task; review between tasks; fast iteration. Best for parallel feature work where the Implementer subagent owns one feature in isolated worktree, Reviewer adversarially critiques, Evaluator runs eval delta. Aligns with the 4-tier orchestration in CLAUDE.md.

**2. Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`; batch execution with checkpoints for review. Best for the early bootstrap days (D1-D2) where context is small and inline iteration is fast.

**Recommendation:** Inline for D1-D2 (foundation), then switch to Subagent-Driven from D3 onwards.

**Which approach?**
