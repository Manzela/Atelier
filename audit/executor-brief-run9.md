# Executor Brief — Round 9 (R9)

**Issued:** 2026-05-25 (Day 11 of 21 sprint)
**Author:** Daniel Manzela + Claude (Opus 4.7 MAX)
**Target executor:** Google Antigravity (Gemini 3.1 Pro Preview)
**Branch:** `phase/2` — worktree `.worktrees/phase2-consensus-agent/`
**Commit policy:** Per-batch commits required (3 batch commits + 1 checklist commit)
**SLA:** R9-A by D12 EOD, R9-B by D13 EOD, R9-C by D14 EOD

---

## 0. Read-first (mandatory before touching any code)

Read these documents in order. Do not skip.

1. `docs/superpowers/specs/2026-05-25-atelier-days-11-21-parallel-execution-design.md` — this brief's parent spec
2. `CLAUDE.md` — sprint invariants (non-negotiable; every `<tag>` in that file applies to you)
3. `DECISIONS.md` — 10+ locked decisions; do not re-litigate
4. `REJECTED.md` — 6+ rejected approaches; do not resurrect
5. `docs/sprint/CHECKPOINTS.md` — last 50 lines; understand what shipped in D1–D7
6. `docs/superpowers/specs/2026-05-14-atelier-prd.md` §6.3, §7.1–7.3, §9, §11, §21 — architecture spec

Estimated reading time: 20 minutes. Do not begin implementation without reading these.

---

## 1. Mission

Deliver a working 3-node pipeline (N1 Brief Parser → N2 Source Resolver → N3a Generator) with full
observability (OTel), DPO pipeline (TrajectoryRecorder + dataset builder), MetacognitiveGovernor, and
docker sandbox security. All features implemented at enterprise production-grade quality with full type
coverage (mypy --strict), exhaustive tests, and CI-clean pre-commit hooks.

**Why this matters for the competition:**

- Technical Implementation (30% rubric): OTel + Governor + DPO pipeline are specifically named in the scoring criteria
- Demo Quality (20% rubric): without a working N1→N2→N3a pipeline, there is no demo
- Innovation (20% rubric): the MetacognitiveGovernor's MAPE-K failure trichotomy is a differentiator

---

## 2. State at handoff (verified 2026-05-25)

### 2.1 What already exists in your owned directories

**DO NOT REBUILD** — these are already implemented and tested:

| File                                                        | Status                     | Notes                                                                            |
| ----------------------------------------------------------- | -------------------------- | -------------------------------------------------------------------------------- |
| `atelier-core/src/atelier/gates/deterministic.py`           | ✅ Complete                | 6 gates (3 real, 3 stub). Do NOT modify.                                         |
| `atelier-core/src/atelier/api/app.py`                       | ✅ Complete                | FastAPI skeleton with `/health`, `/ready`, `/livez`. Do NOT modify.              |
| `atelier-core/src/atelier/intake/brief_spec.py`             | ✅ Complete                | BriefSpec Pydantic model. Do NOT modify.                                         |
| `atelier-core/src/atelier/recorders/trajectory_recorder.py` | ⚠️ Exists, needs migration | Points to `i-for-ai` BQ table — update to `atelier-build-2026` in R9-B           |
| `atelier-core/src/atelier/models/model_registry.py`         | ✅ Complete                | `JUDGE_MODEL_CONFIG` routing dict already implemented. Verify before rebuilding. |
| `atelier-core/src/atelier/models/axis_weights.py`           | ✅ Complete                | `AxisWeights` data contract.                                                     |
| `atelier-core/src/atelier/models/constitution_registry.py`  | ✅ Complete                | `ConstitutionRegistry`.                                                          |
| `atelier-core/src/atelier/models/data_contracts.py`         | ✅ Complete                | `CandidateUI`, `GateOutcome`, `JudgeVote`, `TrajectoryRecord`.                   |
| `atelier-core/src/atelier/nodes/consensus.py`               | ✅ Complete (Phase 1)      | Phase 1 heuristic judges. Phase 2 LLM swap is NOT in R9 scope.                   |
| `atelier-core/src/atelier/nodes/anti_bias.py`               | ✅ Complete                | Anti-bias report utilities.                                                      |
| `atelier-core/src/atelier/nodes/llm_judge.py`               | ✅ Complete                | LLM judge (Claude T5 deliverable).                                               |
| `atelier-core/src/atelier/nodes/trajectory.py`              | ✅ Complete                | `TrajectoryRecord` model.                                                        |
| `atelier-core/src/atelier/nodes/generator.py`               | ✅ Complete                | Generator node skeleton.                                                         |

**Critical first step:** Before writing any file, `cat` the existing file to see if it already implements what
you plan to write. Do not duplicate. Do not override. Extend where needed.

### 2.2 What needs to be built (your deliverables)

| File                                                          | Batch | Status            |
| ------------------------------------------------------------- | ----- | ----------------- |
| `atelier-core/src/atelier/intake/brief_parser.py`             | R9-A  | ❌ Does not exist |
| `atelier-core/src/atelier/orchestrator/runner.py`             | R9-A  | ❌ Does not exist |
| `atelier-core/src/atelier/observability/spans.py`             | R9-A  | ❌ Does not exist |
| `config/otel-collector-config.yaml`                           | R9-A  | ❌ Does not exist |
| `config/scrubber-patterns.yaml`                               | R9-A  | ❌ Does not exist |
| `deploy/docker-compose.dev.yml`                               | R9-A  | ❌ Does not exist |
| `atelier-core/src/atelier/orchestrator/governor.py`           | R9-B  | ❌ Does not exist |
| `atelier-core/src/atelier/recorders/dpo_builder.py`           | R9-B  | ❌ Does not exist |
| `atelier-core/tests/unit/test_otel_spans.py`                  | R9-A  | ❌ Does not exist |
| `atelier-core/tests/unit/test_brief_parser.py`                | R9-A  | ❌ Does not exist |
| `atelier-core/tests/integration/test_pipeline_n1.py`          | R9-A  | ❌ Does not exist |
| `atelier-core/tests/security/test_scrubber.py`                | R9-A  | ❌ Does not exist |
| `atelier-core/tests/unit/test_governor.py`                    | R9-B  | ❌ Does not exist |
| `atelier-core/tests/unit/test_dpo_builder.py`                 | R9-B  | ❌ Does not exist |
| `atelier-core/tests/integration/test_trajectory_recorder.py`  | R9-B  | ❌ Needs update   |
| `atelier-core/src/atelier/integrations/stitch_mcp.py`         | R9-C  | ❌ Does not exist |
| `atelier-core/src/atelier/orchestrator/generator_ensemble.py` | R9-C  | ❌ Does not exist |
| `atelier-core/tests/integration/test_pipeline_n1_n2_n3a.py`   | R9-C  | ❌ Does not exist |

### 2.3 CI state at handoff

- `phase/1` merged to `main` (PR #25) — CI, CodeQL, features.json, Dependency Review: all green
- `phase/2` tip: `1051dec` — design spec commit, no implementation yet
- Test count: 404 (phase/1 cumulative) + ConsensusAgent tests (phase/2) = ~455 total

---

## 3. Protected paths — DO NOT MODIFY

These are Claude-owned SOTA Protocol surfaces. **Any edit here is a merge conflict.**

```
atelier-core/src/atelier/router/
atelier-core/src/atelier/reward/
atelier-core/src/atelier/memory/
atelier-core/src/atelier/optimize/
atelier-core/src/atelier/nodes/_types.py
```

---

## 4. Coordination protocol

- **`git pull --rebase origin phase/2`** before every push
- **Shared files** (`features.json`, `docs/sprint/CHECKPOINTS.md`, `DECISIONS.md`, `pyproject.toml`,
  `requirements.lock`) — commit at batch end only, never mid-batch
- **`pyproject.toml`** — you may add to `[project.dependencies]` only. Do not touch
  `[tool.mypy.overrides]` (Claude-owned).
- If you discover a missing dependency not in `requirements.lock`: add to `pyproject.toml`
  `[project.dependencies]`, run `uv pip compile atelier-core/pyproject.toml -o requirements.lock`,
  commit lock file, then install. Never `pip install` directly.

---

## 5. Non-negotiable invariants (from CLAUDE.md)

**Every file you write must satisfy all of the following before commit:**

```
1. mypy --strict atelier-core/src/atelier/<path>.py  → exit 0
2. python -c "from atelier.<module> import <symbol>"  → exit 0
3. pytest -x --no-header atelier-core/tests/<test_file>.py  → exit 0
4. pre-commit run --all-files  → exit 0
```

**Never:**

- Import a library without verifying the API first (`python -c "import LIB; print(LIB.__version__)"`)
- Use bare `except:` or `except Exception: pass`
- Speculate about code you haven't opened — `cat` the file first
- Add a new dependency without updating `requirements.lock`
- Claim DONE without running all 4 verification commands above

**Google ADK API note:** Before using any `google-adk` class or method, verify it exists:

```bash
python -c "from google.adk.agents import SequentialAgent, LlmAgent; print('ok')"
python -c "from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset; print('ok')"
```

If these fail, fall back to the abstract base and leave a clearly marked TODO.

---

## 6. R9-A batch — Core observability + Brief Parser (D11–D12)

### Goal

End of R9-A: `pytest tests/unit/test_brief_parser.py tests/integration/test_pipeline_n1.py
tests/unit/test_otel_spans.py tests/security/test_scrubber.py` all pass.

### 6.1 FA-007 — OTel span attributes schema

**File:** `atelier-core/src/atelier/observability/spans.py`

**Guiding question before starting:** Run `cat atelier-core/src/atelier/observability/__init__.py`
— does it already define any span constants? If yes, extend; do not duplicate.

**Implementation contract:**

```python
# spans.py must define:
ATELIER_SPAN_ATTRS: dict[str, str]  # 15 mandatory attributes per PRD §7.3

# Required keys (implement ALL 15):
"gen_ai.system"              # value: "atelier"
"gen_ai.operation.name"      # value: node name (e.g. "N1.brief_parser")
"gen_ai.request.model"       # value: model ID used in this span
"gen_ai.usage.input_tokens"  # value: token count string
"gen_ai.usage.output_tokens" # value: token count string
"atelier.tenant_id"          # value: tenant UUID
"atelier.project_id"         # value: project UUID
"atelier.session_id"         # value: session UUID
"atelier.surface_id"         # value: surface UUID
"atelier.node_name"          # value: e.g. "N1.brief_parser"
"atelier.iteration"          # value: iteration number string
"atelier.candidate_id"       # value: candidate UUID or empty
"atelier.cost_usd"           # value: cost string with 6 decimal places
"atelier.gate_decision"      # value: "PASS" | "FAIL" | "SKIP"
"atelier.composite_score"    # value: float string or "-1" if not yet scored
```

**Type signature:**

```python
from typing import Final
ATELIER_SPAN_ATTRS: Final[dict[str, str]] = { ... }

def make_span_attrs(**overrides: str) -> dict[str, str]:
    """Return a copy of ATELIER_SPAN_ATTRS with overrides applied."""
    ...
```

**Tests** (`atelier-core/tests/unit/test_otel_spans.py`):

1. `test_all_15_mandatory_keys_present` — assert `len(ATELIER_SPAN_ATTRS) == 15`
2. `test_make_span_attrs_override_merges` — verify override replaces key without mutating original
3. `test_gen_ai_system_is_atelier` — assert `ATELIER_SPAN_ATTRS["gen_ai.system"] == "atelier"`

### 6.2 FA-006 — OTel Collector config

**File:** `config/otel-collector-config.yaml`

**Research to do first:**

```bash
# Verify opentelemetry-collector Docker image version
docker pull otel/opentelemetry-collector-contrib:0.100.0 2>/dev/null || echo "Docker not available — config-only"
```

**Implementation contract:**

```yaml
# config/otel-collector-config.yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    timeout: 1s
    send_batch_size: 512
  resource:
    attributes:
      - action: upsert
        key: gen_ai.system
        value: atelier

exporters:
  debug:
    verbosity: detailed # Phoenix-compatible dev exporter
  googlecloud:
    project: atelier-build-2026 # prod project
    log:
      default_log_name: atelier.agent
    trace: {}
    metric: {}

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch, resource]
      exporters: [debug, googlecloud]
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [googlecloud]
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [googlecloud]
```

**Test:** `pytest tests/integration/test_otel_export.py` — this test should:

1. Verify `config/otel-collector-config.yaml` is valid YAML (`yaml.safe_load` succeeds)
2. Assert `receivers.otlp.protocols.grpc.endpoint` is set
3. Assert `processors.resource.attributes[0].value == "atelier"`
4. Assert `exporters.googlecloud.project == "atelier-build-2026"`

### 6.3 F0013 — N1 Brief Parser (GateAgent + LlmAgent)

**File:** `atelier-core/src/atelier/intake/brief_parser.py`

**Research to do first:**

```bash
# 1. Read the existing BriefSpec model
cat atelier-core/src/atelier/intake/brief_spec.py

# 2. Read the existing GateAgent pattern
cat atelier-core/src/atelier/gates/deterministic.py | head -80

# 3. Verify ADK LlmAgent API
python -c "from google.adk.agents import LlmAgent; print(LlmAgent.__doc__[:200])"

# 4. Verify Vertex AI Gemini model availability
python -c "from google.genai import types; print(types.__version__ if hasattr(types, '__version__') else 'ok')"
```

**Architecture:** N1 has two layers per the deterministic-gate-first invariant:

1. `BriefParserGate` (deterministic): validates the raw brief text — non-empty, minimum token count,
   no injection patterns. Returns `GateOutcome`. Cost: 0.
2. `BriefParserAgent` (probabilistic): calls Gemini 3 Flash via Vertex AI ADK to extract a structured
   `BriefSpec` from the validated brief text. Cost: ~$0.001 per call.

**Guiding question:** Does `atelier.models.data_contracts` already export `GateOutcome`?

```bash
grep "GateOutcome" atelier-core/src/atelier/models/data_contracts.py | head -5
```

If yes, import from there. Do not redefine.

**Implementation contract:**

```python
# brief_parser.py

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from atelier.models.data_contracts import GateOutcome
from atelier.models.enums import GateDecision
from atelier.intake.brief_spec import BriefSpec


# ---------------------------------------------------------------------------
# Tunable thresholds
# ---------------------------------------------------------------------------
MIN_BRIEF_TOKENS: int = 10        # below this → gate FAIL (too vague)
MAX_BRIEF_TOKENS: int = 4096      # above this → gate FAIL (too large for single call)
INJECTION_PATTERNS: tuple[str, ...] = (
    r"<script",
    r"javascript:",
    r"data:text/html",
    r"{{.*}}",          # template injection
    r"__import__",      # Python injection
)

class BriefParserGate:
    """Deterministic gate — validates raw brief text before LLM parsing."""

    def check(self, brief_text: str) -> GateOutcome:
        """Returns GateDecision.PASS or GateDecision.FAIL with diagnostic."""
        ...

class BriefParserAgent:
    """Probabilistic agent — extracts BriefSpec from validated brief text via Gemini 3 Flash."""

    def __init__(self, model: str = "gemini-3-flash", project: str = "atelier-build-2026") -> None:
        ...

    async def parse(self, brief_text: str) -> BriefSpec:
        """Parse validated brief text → BriefSpec. Raises ValueError on parse failure."""
        ...
```

**Tests** (`atelier-core/tests/unit/test_brief_parser.py`) — 3 minimum:

1. `test_gate_pass_valid_brief` — 50-word brief → `GateDecision.PASS`
2. `test_gate_fail_empty_brief` — empty string → `GateDecision.FAIL`
3. `test_gate_fail_injection_attempt` — `<script>alert('xss')</script>` → `GateDecision.FAIL`
4. `test_agent_returns_valid_brief_spec` — mocked Gemini response → valid `BriefSpec` (use
   `unittest.mock.AsyncMock` or `pytest-asyncio` fixture)

**Important — mocking pattern:** Do NOT use a live Gemini call in unit tests. Mock at the ADK agent
level:

```python
from unittest.mock import AsyncMock, patch

async def test_agent_returns_valid_brief_spec():
    with patch.object(BriefParserAgent, "_call_llm", new_callable=AsyncMock) as mock:
        mock.return_value = '{"intent": "build a landing page", ...}'  # valid JSON
        agent = BriefParserAgent()
        result = await agent.parse("Design a landing page for a SaaS product")
        assert isinstance(result, BriefSpec)
```

### 6.4 F0015 — ADK SequentialAgent runner

**File:** `atelier-core/src/atelier/orchestrator/runner.py`

**Research to do first:**

```bash
python -c "from google.adk.agents import SequentialAgent; help(SequentialAgent.__init__)" 2>/dev/null | head -30
python -c "from google.adk.sessions import InMemorySessionService; print('ok')" 2>/dev/null || echo "Check ADK sessions API"
```

**Implementation contract:**

```python
# runner.py — Phase 1 scaffold (InMemorySessionService; BigQuery session service in Phase 2)

from __future__ import annotations

from typing import Any

from atelier.intake.brief_parser import BriefParserAgent, BriefParserGate
from atelier.intake.brief_spec import BriefSpec

class AtelierRunner:
    """Phase 1 ADK SequentialAgent runner — N1 only.

    Phase 2 will add N2 Source Resolver and N3a Generator.
    Thin wrapper around ADK so tests can mock the runner interface.
    """

    async def run(self, brief_text: str) -> BriefSpec:
        """Gate → Agent → BriefSpec. Raises on gate failure or parse error."""
        gate = BriefParserGate()
        outcome = gate.check(brief_text)
        if outcome.decision != GateDecision.PASS:
            raise ValueError(f"Brief failed gate: {outcome.diagnostic}")
        agent = BriefParserAgent()
        return await agent.parse(brief_text)
```

### 6.5 F0016 — Pipeline integration test (N1)

**File:** `atelier-core/tests/integration/test_pipeline_n1.py`

Single test with mocked Gemini:

```python
async def test_brief_text_to_brief_spec_via_runner():
    """End-to-end: brief text → BriefSpec via AtelierRunner with mocked Gemini."""
```

### 6.6 FA-002 — Secret scrubber patterns

**File:** `config/scrubber-patterns.yaml`

```yaml
# config/scrubber-patterns.yaml
# Redact these patterns before any LLM call, log line, or trajectory record.
# Format: name (description) → regex pattern
patterns:
  google_api_key:
    description: 'Google API key (AIza...)'
    pattern: 'AIza[0-9A-Za-z\-_]{35}'
    redact_with: 'REDACTED_GOOGLE_API_KEY'
  github_token:
    description: 'GitHub personal access token'
    pattern: 'ghp_[0-9A-Za-z]{36}'
    redact_with: 'REDACTED_GITHUB_TOKEN'
  service_account_key:
    description: 'GCP service account key JSON marker'
    pattern: '"private_key_id":\s*"[0-9a-f]{40}"'
    redact_with: '"private_key_id": "REDACTED"'
  generic_secret:
    description: 'Generic high-entropy secret (≥32 chars, mixed case + digits)'
    pattern: '[A-Za-z0-9+/]{32,}={0,2}'
    redact_with: 'REDACTED_SECRET'
  jwt_token:
    description: 'JSON Web Token'
    pattern: 'eyJ[A-Za-z0-9\-_=]+\.eyJ[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_.+/=]*'
    redact_with: 'REDACTED_JWT'
  vertex_endpoint:
    description: 'Vertex AI model endpoint URL'
    pattern: 'https://[a-z0-9\-]+\.aiplatform\.googleapis\.com/[^\s]+'
    redact_with: 'REDACTED_VERTEX_ENDPOINT'
```

**Test** (`atelier-core/tests/security/test_scrubber.py`):

```python
import yaml

def test_scrubber_patterns_yaml_valid():
    with open("config/scrubber-patterns.yaml") as f:
        data = yaml.safe_load(f)
    assert "patterns" in data
    assert len(data["patterns"]) == 6

def test_google_api_key_pattern_matches():
    import re
    pattern = yaml.safe_load(open("config/scrubber-patterns.yaml"))["patterns"]["google_api_key"]["pattern"]
    assert re.search(pattern, "AIzaSyBXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")

def test_jwt_pattern_matches():
    ...  # use a synthetic (non-real) JWT
```

### 6.7 FA-001 — Docker sandbox

**File:** `deploy/docker-compose.dev.yml`

```yaml
# deploy/docker-compose.dev.yml
# Development sandbox — security-hardened containers for code execution
version: '3.9'

services:
  shell-sandbox:
    image: python:3.12-slim
    cap_drop:
      - ALL
    read_only: true
    security_opt:
      - no-new-privileges:true
    network_mode: none # no outbound network
    tmpfs:
      - /tmp:noexec,nosuid,size=64m
    volumes:
      - ./workspace:/workspace:ro # read-only mount
    working_dir: /workspace
    command: ['python', '-c', "print('sandbox ready')"]
    restart: 'no'

  browser-sandbox:
    image: mcr.microsoft.com/playwright/python:v1.42.0-jammy
    cap_drop:
      - ALL
    read_only: true
    security_opt:
      - no-new-privileges:true
    network_mode: host # browser needs network for target URL rendering
    tmpfs:
      - /tmp:noexec,nosuid,size=256m
    volumes:
      - ./workspace:/workspace:ro
    working_dir: /workspace
    restart: 'no'
```

**Test:** `docker compose -f deploy/docker-compose.dev.yml config` exits 0 (validates compose file syntax).

### 6.8 R9-A commit

After all R9-A tests pass and `pre-commit run --all-files` exits 0:

```bash
git add \
  atelier-core/src/atelier/observability/spans.py \
  atelier-core/src/atelier/intake/brief_parser.py \
  atelier-core/src/atelier/orchestrator/runner.py \
  atelier-core/tests/unit/test_otel_spans.py \
  atelier-core/tests/unit/test_brief_parser.py \
  atelier-core/tests/integration/test_pipeline_n1.py \
  atelier-core/tests/integration/test_otel_export.py \
  atelier-core/tests/security/test_scrubber.py \
  config/otel-collector-config.yaml \
  config/scrubber-patterns.yaml \
  deploy/docker-compose.dev.yml

git commit -m "feat(intake,observability,security): R9-A — N1 Brief Parser + OTel schema + docker sandbox

Implements:
- F0013: BriefParserGate (deterministic) + BriefParserAgent (Gemini 3 Flash)
- F0015: AtelierRunner wrapping N1 as ADK SequentialAgent
- F0016: N1 integration test (brief text → BriefSpec, mocked Gemini)
- FA-006: OTel Collector config (OTLP + Google Cloud exporter)
- FA-007: ATELIER_SPAN_ATTRS (15 mandatory keys per PRD §7.3)
- FA-002: Secret scrubber patterns (6 regex patterns)
- FA-001: Docker sandbox compose (shell-sandbox cap_drop=ALL, browser-sandbox)

Tests: +N unit + M integration + P security tests (fill in actual counts)
Pre-commit: all hooks pass."
```

**Then update CHECKPOINTS.md:**

```markdown
## 2026-05-26 D12 — R9-A: N1 Brief Parser + OTel + Security

**Worktree:** `.worktrees/phase2-consensus-agent/`
**Branch:** `phase/2`

**What shipped:**

- FA-006: config/otel-collector-config.yaml
- FA-007: atelier-core/src/atelier/observability/spans.py (15 mandatory attrs)
- F0013/F0014: N1 BriefParserGate + BriefParserAgent
- F0015: AtelierRunner (ADK SequentialAgent)
- F0016: test_pipeline_n1.py integration test
- FA-002: config/scrubber-patterns.yaml (6 patterns)
- FA-001: deploy/docker-compose.dev.yml (cap_drop=ALL sandbox)

**Test count:** [fill in]
**RESUME-HERE:** R9-B begins — MetacognitiveGovernor first.
```

---

## 7. R9-B batch — Governor + DPO pipeline (D12–D13)

### Goal

End of R9-B: `pytest tests/unit/test_governor.py tests/unit/test_dpo_builder.py
tests/integration/test_trajectory_recorder.py` all pass.

### 7.1 FA-015 — MetacognitiveGovernor

**File:** `atelier-core/src/atelier/orchestrator/governor.py`

**Research to do first:**

```bash
# Understand the failure trichotomy as specified
grep -A 20 "Failure Trichotomy\|FAIL_LOUD\|FAIL_SOFT\|SELF_HEAL" docs/superpowers/specs/2026-05-14-atelier-prd.md | head -40
# Read existing governor stub if it exists
cat atelier-core/src/atelier/orchestrator/__init__.py
```

**Architecture — MAPE-K loop:**
The governor implements the MAPE-K (Monitor, Analyze, Plan, Execute, Knowledge) autonomous control loop
from IBM autonomic computing (Kephart & Chess 2003). Each Atelier pipeline execution is monitored
continuously; the governor classifies failures into the trichotomy and dispatches accordingly.

**Implementation contract (full, production-grade):**

```python
"""MetacognitiveGovernor — MAPE-K autonomous failure management.

Per PRD §21 Failure Trichotomy:
    FAIL_LOUD: security breach, budget cap, data corruption → alert + halt
    FAIL_SOFT: tool errors, stall, infinite loop → degrade + log + acknowledge
    SELF_HEAL: 429/503 transient → retry with bounded exponential backoff

MAPE-K mapping:
    Monitor  → _monitor_heartbeat(), _check_budget(), _check_step_budget()
    Analyze  → _classify_failure()
    Plan     → should_self_heal(), should_fail_soft(), should_fail_loud()
    Execute  → execute_self_heal() (backoff), execute_fail_soft() (log + degrade)
    Knowledge → _loop_detection_window (sliding window of recent steps)

Hard caps (from CLAUDE.md):
    MAX_SELF_HEAL_RETRIES = 3   # per operation
    MAX_LOOP_ITERATIONS = 10    # detect infinite loops
    STALL_TIMEOUT_SECONDS = 300 # 5 minutes without progress → fail-soft
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

MAX_SELF_HEAL_RETRIES: Final[int] = 3
MAX_LOOP_ITERATIONS: Final[int] = 10
STALL_TIMEOUT_SECONDS: Final[float] = 300.0
BACKOFF_BASE_SECONDS: Final[float] = 1.0
BACKOFF_MAX_SECONDS: Final[float] = 32.0


class FailureMode(StrEnum):
    FAIL_LOUD = "FAIL_LOUD"
    FAIL_SOFT = "FAIL_SOFT"
    SELF_HEAL = "SELF_HEAL"


@dataclass
class GovernorState:
    retry_count: int = 0
    last_step_time: float = field(default_factory=time.monotonic)
    step_history: deque[str] = field(default_factory=lambda: deque(maxlen=MAX_LOOP_ITERATIONS))
    total_cost_usd: float = 0.0
    budget_cap_usd: float = 5.0  # PRD §7.2

    def record_step(self, step_id: str) -> None: ...
    def is_loop(self) -> bool: ...
    def is_stalled(self) -> bool: ...
    def is_over_budget(self) -> bool: ...


class MetacognitiveGovernor:
    """Wraps any async coroutine with MAPE-K failure management."""

    def __init__(self, state: GovernorState | None = None) -> None:
        self._state = state or GovernorState()

    def _classify_failure(self, exc: BaseException) -> FailureMode:
        """Classify exception into trichotomy. Never returns None."""
        ...

    async def run_with_governance(
        self,
        operation: Callable[[], Awaitable[T]],
        step_id: str,
        cost_estimate_usd: float = 0.0,
    ) -> T:
        """Execute operation under MAPE-K governance. Retries on SELF_HEAL."""
        ...

    def _check_budget(self, cost_usd: float) -> None:
        """Raises GovernorBudgetExceeded (FAIL_LOUD) if over budget."""
        ...

    def _check_step_budget(self, step_cost: float) -> None:
        """Raises GovernorStepBudgetExceeded if single step exceeds $0.50."""
        ...
```

**Tests** (`atelier-core/tests/unit/test_governor.py`) — minimum 20 tests:

| Category               | Tests                                                                       |
| ---------------------- | --------------------------------------------------------------------------- |
| Failure classification | 429 → SELF_HEAL; ValueError → FAIL_SOFT; BudgetExceeded → FAIL_LOUD         |
| Retry behavior         | SELF_HEAL retries up to MAX (3); backoff is exponential; 4th failure raises |
| Budget enforcement     | Cost > cap → FAIL_LOUD immediately; cumulative cost tracked correctly       |
| Loop detection         | Same step_id 10× → is_loop() = True; deque wraps correctly                  |
| Stall detection        | last_step_time > 300s ago → is_stalled() = True                             |
| Backoff calculation    | Verify backoff_base \* 2^attempt formula is correct                         |

**Guiding questions for implementation:**

- How do you classify `httpx.TimeoutException`? → SELF_HEAL (transient)
- How do you classify `google.api_core.exceptions.Unauthenticated`? → FAIL_LOUD (config error)
- How do you classify `RuntimeError("context length exceeded")`? → FAIL_SOFT (degrade)
- Does `should_self_heal` consume a retry count before checking? Yes — so 3 retries means 4 total attempts (1 original + 3 retries).

### 7.2 FA-011 — TrajectoryRecorder (update for GCP migration)

**File:** `atelier-core/src/atelier/recorders/trajectory_recorder.py` (UPDATE EXISTING)

**Research to do first:**

```bash
# Read the existing file completely before touching it
cat atelier-core/src/atelier/recorders/trajectory_recorder.py
```

**Only change:** Update the `DEFAULT_TABLE_ID` constant:

```python
# BEFORE:
DEFAULT_TABLE_ID = "i-for-ai.atelier_trajectories.trajectory_records"

# AFTER:
DEFAULT_TABLE_ID = "atelier-build-2026.atelier_trajectories.trajectory_records"
```

Verify no other `i-for-ai` references remain in this file after the change.

**Integration test update** (`atelier-core/tests/integration/test_trajectory_recorder.py`):

- If this test file already exists, update the expected table ID
- If it does not exist, create it with a mocked BigQuery client:

```python
async def test_trajectory_recorder_buffers_and_flushes():
    """Verify records buffer until threshold then flush to BQ (mocked client)."""
```

### 7.3 FA-012 — DPO dataset builder

**File:** `atelier-core/src/atelier/recorders/dpo_builder.py`

**Research to do first:**

```bash
# Understand the existing TrajectoryRecord schema
grep -n "class TrajectoryRecord\|composite_score\|candidate_id\|node_name\|iteration" atelier-core/src/atelier/nodes/trajectory.py | head -20
```

**Critical: G10 audit fix.** The previous DPO logic (before this sprint) had a flaw: it was comparing
consecutive iterations of the SAME candidate instead of comparing DIFFERENT candidates at the same
decision point. The correct logic:

```
For each (surface_id, node_name, iteration) group:
  - candidates in this group = all CandidateUIs evaluated at this decision point
  - chosen = candidate with composite_score >= 0.70
  - rejected = candidate with composite_score < 0.50
  - pair is valid only if |chosen.score - rejected.score| >= MIN_MARGIN (0.15)
  - if multiple candidates qualify as chosen, pick highest score
  - if multiple candidates qualify as rejected, pick lowest score
  - discard groups with < 2 qualifying candidates
```

**Implementation contract:**

```python
"""DPO dataset builder — produces preference pairs from trajectory records.

G10 fix: compares DIFFERENT candidates evaluated at the same (surface_id, node_name, iteration)
decision point. Does NOT compare consecutive iterations of the same candidate.

Output format: JSONL, one JSON object per line:
{
  "prompt": "...",       # the shared prompt for this decision point
  "chosen": "...",       # candidate with composite_score >= T2_THRESHOLD
  "rejected": "...",     # candidate with composite_score < T3_THRESHOLD
  "margin": 0.23,        # chosen.score - rejected.score (always >= MIN_MARGIN)
  "metadata": {
    "surface_id": "...",
    "node_name": "...",
    "iteration": 0,
    "chosen_score": 0.82,
    "rejected_score": 0.59
  }
}
"""

T2_THRESHOLD: Final[float] = 0.70   # chosen floor
T3_THRESHOLD: Final[float] = 0.50   # rejected ceiling
MIN_MARGIN: Final[float] = 0.15     # minimum score gap to be a valid pair

def prepare_dpo_dataset(records: list[TrajectoryRecord]) -> list[dict[str, Any]]:
    """Group records by decision point, extract preference pairs, return JSONL-ready dicts."""
    ...
```

**Tests** (`atelier-core/tests/unit/test_dpo_builder.py`) — minimum 10 tests:

| Test                                             | Assertion                                                                  |
| ------------------------------------------------ | -------------------------------------------------------------------------- |
| `test_valid_pair_extracted`                      | 0.82 vs 0.59 → 1 pair with margin 0.23                                     |
| `test_g10_fix_same_candidate_no_pair`            | Same candidate_id × 2 iterations → 0 pairs                                 |
| `test_margin_too_small_rejected`                 | 0.75 vs 0.63 → 0 pairs (margin 0.12 < MIN_MARGIN)                          |
| `test_both_above_threshold_picks_highest_lowest` | 0.90, 0.75, 0.40 → chosen=0.90, rejected=0.40                              |
| `test_empty_records_returns_empty`               | `[]` → `[]`                                                                |
| `test_chosen_threshold_boundary`                 | 0.70 exactly → chosen eligible                                             |
| `test_rejected_threshold_boundary`               | 0.50 exactly → NOT eligible (strict `<`)                                   |
| `test_multiple_decision_points_independent`      | 2 separate groups → 2 independent pairs                                    |
| `test_output_format_has_required_keys`           | Every output dict has `prompt`, `chosen`, `rejected`, `margin`, `metadata` |
| `test_metadata_fields_present`                   | `metadata` has all 5 required subkeys                                      |

### 7.4 FA-016 + FA-017 — model_registry.py and judge_harness.py (verify, extend if needed)

**Research before any code changes:**

```bash
# FA-016: model_registry already exists — check if JUDGE_MODEL_CONFIG is complete
cat atelier-core/src/atelier/models/model_registry.py | grep -A 30 "JUDGE_MODEL_CONFIG"

# FA-017: anti_bias already exists — check if anti-bias rules are complete
cat atelier-core/src/atelier/nodes/anti_bias.py | head -60
grep "CoT\|position_swap\|self_prefer" atelier-core/src/atelier/nodes/anti_bias.py
```

**If model_registry.py already defines `JUDGE_MODEL_CONFIG` with all 5 axes:** FA-016 is done. Mark
`passes: true` in features.json and move on.

**If anti_bias.py already implements CoT-before-score and position swap:** FA-017 is done.

**Only build what's missing.** Verify before writing a single line.

### 7.5 R9-B commit

```bash
git add \
  atelier-core/src/atelier/orchestrator/governor.py \
  atelier-core/src/atelier/recorders/trajectory_recorder.py \
  atelier-core/src/atelier/recorders/dpo_builder.py \
  atelier-core/tests/unit/test_governor.py \
  atelier-core/tests/unit/test_dpo_builder.py \
  atelier-core/tests/integration/test_trajectory_recorder.py

git commit -m "feat(orchestrator,recorders): R9-B — MetacognitiveGovernor + DPO pipeline

Implements:
- FA-015: MetacognitiveGovernor (MAPE-K, FailureMode trichotomy, 3-retry cap,
          budget enforcement, loop + stall detection)
- FA-011: TrajectoryRecorder migrated to atelier-build-2026 BQ table
- FA-012: DPO dataset builder (G10 fix: cross-candidate comparison, MIN_MARGIN=0.15)
- FA-016/FA-017: model_registry + anti_bias verified complete (or extended)

Tests: +N tests
Pre-commit: all hooks pass."
```

---

## 8. R9-C batch — Source Resolver + Generator + Phase 1 Gate (D13–D14)

### Goal

End of R9-C: full pipeline integration test passes, Phase 1 Gate validated, `v0.1.0-phase-1-gate` tag ready.

### 8.1 F0021–F0022 — N2 Source Resolver

**File:** `atelier-core/src/atelier/intake/source_resolver.py`

**Research to do first:**

```bash
python -c "from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset; print('ok')"
grep -n "ProjectContext\|SourceDescriptor\|descriptor" atelier-core/src/atelier/models/data_contracts.py | head -10
```

**Architecture:**

```
SourceResolverGate (deterministic): descriptor present OR brief contains path → PASS
SourceResolverAgent (probabilistic): pull DESIGN.md tokens, pull Memory Bank priors, merge
```

**Output type:** `ProjectContext` (check if it exists in `models/data_contracts.py` first).

### 8.2 F0027–F0030 — Stitch MCP + N3a Generator ensemble

**File:** `atelier-core/src/atelier/integrations/stitch_mcp.py`

**Research to do first:**

```bash
# Verify Stitch MCP integration as already scaffolded
cat atelier-core/src/atelier/integrations/stitch_mcp.py 2>/dev/null || echo "Does not exist"

# Verify ADK MCPToolset API
python -c "from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset; help(MCPToolset.__init__)" 2>/dev/null | head -20
```

**File:** `atelier-core/src/atelier/orchestrator/generator_ensemble.py`

K=3 candidates via `ParallelAgent`. Each generator: Stitch `generate_screen_from_text` OR Gemini 3 Pro
direct (fallback if Stitch unavailable).

### 8.3 Phase 1 Gate validation

**Gate criteria** (from PRD §11 and the D1-D7 consolidated CHECKPOINTS):

| #   | Criterion                                        | Verification                   |
| --- | ------------------------------------------------ | ------------------------------ |
| G1  | `/health` returns 200 on Cloud Run staging       | `curl -sf $STAGING_URL/health` |
| G2  | BriefSpec frozen model passes JSON roundtrip     | pytest unit test               |
| G3  | N1 Brief Parser gate + agent end-to-end (mocked) | test_pipeline_n1.py            |
| G4  | Governor SELF_HEAL retries 3× then escalates     | test_governor.py               |
| G5  | TrajectoryRecorder flushes to BigQuery (mocked)  | test_trajectory_recorder.py    |
| G6  | DPO dataset builder emits valid pairs (G10 fix)  | test_dpo_builder.py            |
| G7  | OTel span schema has 15 mandatory attributes     | test_otel_spans.py             |

**Important:** G1 (Cloud Run) is a Daniel-action gate. Mark it as pending in the checklist.

### 8.4 R9-C commit + tag

```bash
git add \
  atelier-core/src/atelier/intake/source_resolver.py \
  atelier-core/src/atelier/integrations/stitch_mcp.py \
  atelier-core/src/atelier/orchestrator/generator_ensemble.py \
  atelier-core/tests/integration/test_pipeline_n1_n2_n3a.py

git commit -m "feat(intake,integrations,orchestrator): R9-C — N2 Source Resolver + N3a Generator

Implements:
- F0021/F0022: SourceResolverGate + SourceResolverAgent (DESIGN.md + Memory Bank)
- F0027/F0028: Stitch MCP via ADK MCPToolset
- F0029/F0030: N3a Generator ensemble K=3 via ParallelAgent
- F0016+: Pipeline integration test N1→N2→N3a

Phase 1 Gate G1-G7: G2-G7 passing; G1 pending Daniel action (Cloud Run).
Pre-commit: all hooks pass."
```

---

## 9. Daniel-action checklist (output at R9 end — non-blocking)

Produce this checklist as the final R9 artifact, committed to `docs/sprint/D14-daniel-actions.md`:

````markdown
# Daniel Actions — Day 14 (2026-05-28)

These are GCP-gated actions that require your interactive credentials.
All code is ready; these are the deployment steps.

## Order-dependent actions (run in sequence)

### 1. Create IAM service account

```bash
gcloud iam service-accounts create atelier-runtime \
  --project=atelier-build-2026 \
  --display-name="Atelier Runtime SA" \
  --description="Main runtime SA for Atelier Cloud Run + BigQuery + Vertex"
```
````

### 2. Apply Terraform (review plan first)

```bash
cd infra/terraform
terraform init
terraform plan -var-file=staging.tfvars   # REVIEW OUTPUT
terraform apply -var-file=staging.tfvars  # Only after reviewing plan
```

Expected outputs: `staging_url` (Cloud Run URL), `bigquery_dataset_id`

### 3. Migrate GEAP secret

```bash
bash scripts/migration/07_migrate_geap_secret.sh --wet
```

### 4. Apply branch protection

```bash
bash scripts/governance/protect_phase_1.sh --apply
```

### 5. Deploy to Cloud Run (live)

```bash
agents-cli deploy \
  --project=atelier-build-2026 \
  --target=cloud_run \
  --service=atelier-staging
```

After this: `curl -sf $(gcloud run services describe atelier-staging --project=atelier-build-2026 --region=europe-west4 --format='value(status.url)')/health` should return 200.

### 6. Submit to UIBench (2h session)

Go to UIBench submission portal → submit Atelier → record DPO labels.

### 7. Phase 1 Gate G1 — verify Cloud Run /health

After step 5: `curl -sf $STAGING_URL/health` → 200

## Tag the gate (after all 7 steps pass)

```bash
git tag -a v0.1.0-phase-1-gate -m "Phase 1 Gate: all 7 criteria green"
git push origin v0.1.0-phase-1-gate
```

````

---

## 10. Research context

### 10.1 Key architectural decisions (already locked — do not re-litigate)

| Decision | Resolution | ADR |
|---|---|---|
| GCP project | `atelier-build-2026` (not `i-for-ai`) | ADR 0019 |
| Model for Brief Parser | Gemini 3 Flash (low cost, fast) | ADR 0015 |
| Session service | `InMemorySessionService` in Phase 1; BigQuery in Phase 2 | ADR 0007 |
| DPO implementation | `google.genai TuningMethod.PREFERENCE_TUNING`, β=0.1 | ADR 0028 |
| Originality judge | Gemini 2.5 Pro (thinking mode) — NOT 3.1 Pro Preview | ADR 0020 |
| Failure trichotomy | 3-mode: FAIL_LOUD / FAIL_SOFT / SELF_HEAL | ADR 0016 |
| Commit discipline | Conventional Commits 1.0.0, per-batch | ADR 0007 |
| Domain-split | Claude owns router/reward/memory/optimize; Antigravity owns pipeline | This doc §1 |

### 10.2 Python type system rules

This codebase uses `mypy --strict`. Key patterns you must follow:

```python
# ✅ Correct — TYPE_CHECKING guard for type-only imports
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from collections.abc import Callable

# ✅ Correct — Final for module-level constants
from typing import Final
THRESHOLD: Final[float] = 0.70

# ✅ Correct — StrEnum (Python 3.11+)
from enum import StrEnum
class FailureMode(StrEnum):
    FAIL_LOUD = "FAIL_LOUD"

# ❌ Wrong — bare Enum subclass on Python 3.11+
class FailureMode(str, Enum): ...  # UP042: use StrEnum

# ❌ Wrong — non-Final module constant
THRESHOLD = 0.70  # mypy PLR2004
````

### 10.3 Google ADK patterns (verified in this codebase)

```python
# SequentialAgent wraps a list of agents in order
from google.adk.agents import SequentialAgent, LlmAgent

pipeline = SequentialAgent(
    name="atelier_phase1",
    sub_agents=[brief_parser_agent, source_resolver_agent],
)

# ParallelAgent runs sub_agents concurrently — use for N3a K=3 candidates
from google.adk.agents import ParallelAgent

generator_ensemble = ParallelAgent(
    name="n3a_generator_ensemble",
    sub_agents=[gen_a, gen_b, gen_c],
)
```

### 10.4 Pydantic v2 patterns (frozen + strict)

All models in this codebase use:

```python
from pydantic import BaseModel, ConfigDict

class MyModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: int = 1
    # ... fields
```

`frozen=True` means the model is immutable after construction — no `model.field = value`.
`extra="forbid"` means unexpected fields raise `ValidationError` at parse time.

### 10.5 Test patterns (anyio + pytest)

This codebase uses `anyio` (not `asyncio`) for async tests:

```python
import pytest

@pytest.mark.anyio
async def test_something_async():
    result = await some_async_function()
    assert result == expected
```

Do NOT use `@pytest.mark.asyncio` — this will silently fail.

### 10.6 BigQuery streaming inserts (for TrajectoryRecorder update)

```python
from google.cloud import bigquery

client = bigquery.Client(project="atelier-build-2026")
table_ref = client.dataset("atelier_trajectories").table("trajectory_records")

# insertId-based idempotent insert
errors = client.insert_rows_json(
    table_ref,
    [{"insertId": record_id, **row_data}],
)
```

---

## 11. Guiding questions

Ask yourself these questions at each stage. If the answer is "I don't know," verify before writing code.

### Before writing any file:

1. Does this file already exist? (`cat <path>` first)
2. Does the model or type I'm importing already exist in `models/`?
3. Have I verified the ADK/Vertex AI API I'm about to use exists and has the signature I expect?
4. Is this file in my owned paths (§3 of this brief)? If not, stop.

### Before committing:

1. Have I run `mypy --strict` on every file I modified?
2. Have I run `python -c "import <module>"` for every new module?
3. Have I run `pytest -x` on every test file I modified?
4. Have I run `pre-commit run --all-files`?
5. Did I update `docs/sprint/CHECKPOINTS.md` with this batch's entry?
6. Did I update `features.json` to flip `passes: true` for each delivered feature?

### If a test fails:

1. Is it a mypy error? → Fix the type annotation, not the test.
2. Is it an import error? → Verify the module exists (`python -c "import X"`).
3. Is it an assertion error? → Read the actual vs. expected carefully. Fix the implementation.
4. Is it an anyio/asyncio marker error? → Use `@pytest.mark.anyio`, not `@pytest.mark.asyncio`.

### If a pre-commit hook fails:

1. `markdownlint` → check for table pipe spacing (this codebase uses compact style)
2. `prettier` → re-stage the auto-fixed file and commit again
3. `ruff` → check for UP042 (use StrEnum), E501 (line too long), or TC002 (TYPE_CHECKING guard)
4. `mypy` → check for missing type annotations or incorrect `ignore` directives

### If you hit a Google ADK API that doesn't exist:

1. Try `python -c "from google.adk import <module>; help(<module>)"` to explore the actual API
2. Check `requirements.lock` for the pinned google-adk version
3. If the API truly doesn't exist: implement a stub with a clear `# TODO: wire to ADK when API lands` comment
4. Do NOT invent API signatures. Do NOT hallucinate method names.

---

## 12. Success criteria (definition of R9 DONE)

R9 is DONE when ALL of the following are true. Do not emit a DONE signal until every item is verified:

**Code quality:**

- [ ] `mypy --strict atelier-core/src/` exits 0
- [ ] `pre-commit run --all-files` exits 0
- [ ] `pytest atelier-core/` exits 0 (no failures, xfails acceptable)

**Feature completion:**

- [ ] `features.json`: FA-001, FA-002, FA-006, FA-007, FA-011, FA-012, FA-015, FA-016, FA-017 flipped to `passes: true`
- [ ] `features.json`: F0013, F0014, F0015, F0016, F0021, F0022, F0027, F0028, F0029, F0030 flipped to `passes: true`

**Phase 1 Gate:**

- [ ] G2–G7 passing (G1 pending Daniel action)
- [ ] `docs/sprint/D14-daniel-actions.md` committed with clear GCP action steps

**Documentation:**

- [ ] `docs/sprint/CHECKPOINTS.md` updated with D11–D14 entries
- [ ] `docs/sprint/STATUS.md` updated: "Phase 1 Gate: G2-G7 passing, G1 pending Daniel action"

**No regressions:**

- [ ] All tests that were passing before R9 are still passing (eval-delta clean)
- [ ] CI on `phase/2` push: all checks green

**Final git state:**

- [ ] Working tree clean on `phase/2`
- [ ] 3 batch commits + 1 checklist commit pushed to `origin/phase/2`

---

_Issued by Claude (Opus 4.7 MAX) on behalf of Daniel Manzela — 2026-05-25_
_Next brief after R9: R10 (Phase 2 gate — EvoDesign, Campaign Orchestrator, WebGen-Bench eval harness)_
