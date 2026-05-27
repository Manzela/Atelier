# Findings — Antigravity Phase 2 (Environment Audit & Assessment 4)

**Target**: All code touched by Antigravity across the full session transcript
**Reference**: Environment Audit and Assessment-4.md (2871-line session transcript)
**Pass 1 date**: 2026-05-25
**Auditors**: 5 parallel Claude Opus 4.7 subagents + Claude orchestrator
**Method**: Every cited file read directly from disk. No trust in Antigravity's self-reported test counts.

---

## Test Count Discrepancy

Antigravity claimed "527 passed" and later "577 passed" at various points.
Actual test collection at audit time: **636 tests collected, 586 passed**.
The inflation is explained by Claude's subsequent work (stub upgrades, DAG wiring, /v1/generate, etc.)
that added tests after Antigravity's session. Antigravity's 577 figure was accurate for its session scope.

---

## P0 — Must Fix Before Merge (4 findings)

### P0-1: GitHub Actions auth@v2 is OUTDATED (Security/CI correctness)

**File**: `.github/workflows/bench-publish.yml`
**Finding**: `google-github-actions/auth@v2` is outdated. Current stable is **v3** (released 2025-09-03).
v2 uses deprecated internal APIs and the authentication flow differs.
Additionally, the workflow is missing a required Attribute Condition on the WIF provider restricting
it to `Manzela/atelier`. Google's documentation explicitly states "Always add an Attribute Condition"
to prevent token forgery from other repos in the same organization.
**Evidence**: Web research agent confirmed v3 is current; v2 lacks the Attribute Condition requirement.
**Fix**: Bump to `google-github-actions/auth@v3`; add `attribute_condition` restricting to `Manzela/atelier`.

### P0-2: `workflow_dispatch` trigger missing from bench-publish.yml

**File**: `.github/workflows/bench-publish.yml`
**Finding**: Workflow only triggers on `schedule` (nightly) and `push`. No `workflow_dispatch` means
engineers cannot manually retrigger the pipeline to refresh the bench dashboard after an incident.
This is a standard CI/CD operational requirement.
**Fix**: Add `workflow_dispatch:` to the `on:` block.

### P0-3: `pip install -e "atelier-core[dev]"` violates `<lockfile_only_installs>` invariant

**File**: `.github/workflows/bench-publish.yml:21`
**Finding**: CLAUDE.md `<lockfile_only_installs>` invariant explicitly forbids ad-hoc `pip install`.
All dependencies must go through `pip install -r requirements.lock`. Using `-e` editable install
with dev extras opens the door to transient dependency drift and slopsquatting (LiteLLM Mar 2026 incident
is cited in CLAUDE.md as the rationale). Similarly, `npm install -g firebase-tools` at line 24
is unpinned — version should be pinned (e.g., `firebase-tools@13.x`).
**Fix**: Replace with `pip install -r requirements.lock && pip install -e atelier-core/`; pin firebase-tools.

### P0-4: Non-best candidate composite_score set to 0.0 in trajectory records

**File**: `atelier-core/src/atelier/api/generate.py:188`
**Finding**: `composite_score=float(composite) if is_best else 0.0` assigns zero to all non-winning
candidates. The DPO pair miner (`BigQueryPairMiner.mine_pairs()`) uses the margin between
`chosen_score` and `rejected_score` to rank pairs. Rejected candidates with `composite_score=0.0`
create artificially large margins and low-quality training signal — the miner cannot distinguish
a genuinely bad candidate from one that simply wasn't selected.
**Fix**: Pass per-candidate actual composite scores from `result["evaluations"]` instead of 0.0.
The `_run_n3c_n3d_n4()` already returns `all_evaluations` with per-candidate scores.

---

## P1 — Should Fix Before Production (7 findings)

### P1-1: Cross-tenant DPO pairs in fixture (data quality)

**File**: `atelier-core/tests/fixtures/trajectories_seed.jsonl`
**Finding**: The 3 shared surface_id groups that enable DPO pairing span the tenant boundary —
e.g., surface `220b35cc` has an accepted record from `tenant-alpha` (record 1) paired with a
rejected record from `tenant-beta` (record 19). `extract_dpo_pairs()` doesn't filter by tenant,
so the fixture yields cross-tenant preference pairs. This is architecturally incorrect —
DPO training data should not mix signals from different tenants as it would pollute per-tenant
judge personalization.
**Fix**: Regenerate fixture so shared surface_ids stay within the same tenant.

### P1-2: Fixture temporal inconsistency (3 records have ended_at < ts)

**File**: `atelier-core/tests/fixtures/trajectories_seed.jsonl` (rows ~6, 8, 16)
**Finding**: Three records have `ended_at` before `ts` (started_at). This happens because
`random.randint(0, 3)` can produce the same offset for both, or a higher number for ended_at.
The replay UI renders `started_at → ended_at` as the span duration — negative duration
would produce malformed Gantt bars.
**Fix**: Ensure `ended_at = ts + timedelta(seconds=random.randint(30, 300))`.

### P1-3: `candidates[:3]` hardcodes ensemble size K=3

**File**: `atelier-core/src/atelier/api/generate.py:170`
**Finding**: The K=3 ensemble width is hardcoded inline. `runner.py` defines
`ENSEMBLE_SIZE = 3` in `generator_ensemble.py`. These must stay in sync.
If the ensemble is changed to K=6, trajectory recording will silently record
only 3 of 6 candidates.
**Fix**: Import `ENSEMBLE_SIZE` from `generator_ensemble.py` and use it as the slice limit.

### P1-4: google-genai SDK version lag (1.75.0 vs 2.6.0)

**File**: `atelier-core/pyproject.toml`
**Finding**: `google-genai>=1.0,<2` pins to major version 1. Latest stable is **2.6.0** (released 2026-05-22).
The 2.x SDK has improvements to the Grounding API response schema and typed chunk attributes.
The `chunk.web.domain` field (used by web_research.py) is confirmed present in 2.x.
**Fix**: Bump bound to `google-genai>=2.6,<3` after verifying no breaking changes in web_research.py.

### P1-5: Firebase auth catches bare Exception, not typed subclasses

**File**: `atelier-core/src/atelier/auth/firebase.py`
**Finding**: `_decode_token()` catches bare `Exception as exc`, converting all failures to HTTP 401.
This means `RuntimeError` (e.g., firebase-admin not installed), `ValueError` (config error),
and auth-specific errors (`auth.RevokedIdTokenError`, `auth.ExpiredIdTokenError`) all produce
identical 401 responses with no distinguishable error codes. The `<no_silent_error_suppression>`
invariant requires structured error context. For judges, "token expired" and "SDK misconfigured"
should produce different error codes so the client can handle them correctly.
**Fix**: Catch typed subclasses (`auth.ExpiredIdTokenError`, `auth.RevokedIdTokenError`,
`auth.InvalidIdTokenError`) separately and surface distinct error codes.

### P1-6: DEMO timestamps frozen as ISO literals in _build_demo_data()

**File**: `atelier-core/scripts/generate_bench_data.py`
**Finding**: `_build_demo_data()` at line ~70 has hardcoded ISO date strings for `promoted_at`
(e.g., `"2026-05-25T04:00:00.000Z"`). When invoked months later these will show stale "Last promoted"
timestamps on the dashboard. In contrast, `index.html:899,906` uses `Date.now() - N * 3600000`
for dynamic offsets.
**Fix**: Replace literals with `(datetime.now(timezone.utc) - timedelta(hours=8)).isoformat()` etc.

### P1-7: BQ payload inconsistency — summary missing avg_latency_ms / p99_latency_ms

**File**: `atelier-core/scripts/generate_bench_data.py`
**Finding**: The BQ path populates `summary` without `avg_latency_ms` and `p99_latency_ms`.
The DEMO path (correctly) includes both. The bench-schema.json doesn't require them but the
`index.html` dashboard template renders them if present. When live BQ data is used,
the dashboard will show `—` for latency while DEMO mode shows values, creating inconsistency.
The `trajectory_records` table has no latency column in `to_bq_row()` (confirmed), so these
cannot be computed without a schema change. Document this as a known gap.
**Fix**: Add `avg_latency_ms: None` and `p99_latency_ms: None` to the BQ payload path summary,
and document the gap with a TODO linking to the schema extension.

---

## P2 — Nice to Have (5 findings)

### P2-1: Unreachable `return []` in web_research.py

**File**: `atelier-core/src/atelier/intake/web_research.py:429`
**Finding**: Dead code after the `else:` block — `return []` is unreachable because the
`except` branch already returns and the `else:` block always returns. Self-acknowledged in comment.
**Fix**: Remove the dead `return []` line or restructure try/except/else cleanly.

### P2-2: `UUID(int=int(uuid4()) & ...)` — needlessly complex

**File**: `atelier-core/src/atelier/api/generate.py:178,181,184`
**Finding**: Trajectory ID generation uses `UUID(int=int(uuid4()) & ((1 << 128) - 1))`
which is semantically identical to just `uuid4()`. The bitmask is a no-op since uuid4()
already produces a 128-bit value. This obscures intent.
**Fix**: Replace with `uuid4()` directly.

### P2-3: Single-letter loop variable `l` in load_fixture

**File**: `atelier-core/tests/unit/test_dpo_builder.py`
**Finding**: `for l in FIXTURE.read_text().splitlines() if l.strip()` — ruff E741 will flag `l`
as an ambiguous variable name (looks like `1`).
**Fix**: Rename to `line`.

### P2-4: `from uuid import UUID` inside function body

**File**: `atelier-core/tests/unit/test_dpo_builder.py`
**Finding**: Import inside `test_fixture_extract_dpo_pairs()`. The top level already imports `uuid4`.
Combine into top-level `from uuid import UUID, uuid4`.
**Fix**: Move import to top of file.

### P2-5: Add `pinTag: true` to firebase.json rewrite

**File**: `firebase.json`
**Finding**: Firebase Hosting rewrites to Cloud Run benefit from `pinTag: true` which keeps
the Cloud Run revision pinned during preview channel deploys, enabling atomic rollbacks.
Current `firebase.json` omits this flag.
**Fix**: Add `"pinTag": true` to the Cloud Run rewrite block.

---

## Verified Correct — No Issues Found

| Area | Result | Evidence |
|------|--------|----------|
| `generate_bench_data.py` — SQL injection defense | PASS | `_PROJECT_ID_RE` regex at line ~38 |
| `generate_bench_data.py` — fail-soft BQ | PASS | every BQ call wrapped in try/except |
| `generate_bench_data.py` — schema validation | PASS | jsonschema.validate before write |
| `generate_bench_data.py` — compute_stats non-mutation | PASS | `sorted()` copy not `.sort()` |
| `generate_bench_data.py` — run_id is UUID | PASS | BQ job_id or `uuid.uuid4()` |
| `trajectories_seed.jsonl` — 30 records | PASS | wc -l confirmed |
| `trajectories_seed.jsonl` — outcome distribution 18/8/4 | PASS | verified by agent |
| `trajectories_seed.jsonl` — tenant distribution 20/10 | PASS | verified by agent |
| `trajectories_seed.jsonl` — score range 0.32–0.97, all unique | PASS | 30 unique scores |
| `trajectories_seed.jsonl` — judge vote scores varied | PASS | 255 unique scores across 270 cells |
| `test_dpo_builder.py` — 5 new tests present | PASS | all 5 fixture test functions confirmed |
| `test_dpo_builder.py` — @pytest.mark.unit on all 5 | PASS | confirmed at each def |
| `test_dpo_builder.py` — extract_dpo_pairs min_margin=0.05 | PASS | L258 |
| `test_dpo_builder.py` — original tests preserved | PASS | L41-177 unmodified |
| `auth/firebase.py` — _BYPASS_AUTH production guard | PASS | RuntimeError at import |
| `auth/firebase.py` — optional_auth returns None not 401 | PASS | confirmed |
| `api/replay.py` — tenant_id in SQL WHERE clause | PASS | parameterized @tenant_id |
| `api/replay.py` — ownership 403 as second layer | PASS | confirmed |
| `api/generate.py` — POST /v1/generate exists | PASS | router at /v1/generate |
| `api/generate.py` — requires Firebase auth | PASS | Depends(require_auth) |
| `api/generate.py` — trajectory recording fail-soft | PASS | broad except → logger.warning |
| `web_research.py` — chunk.web.domain used | PASS | line 392-398 |
| `web_research.py` — module-level client cache | PASS | _genai_client at module level |
| `bench-publish.yml` — secrets all via ${{ secrets.* }} | PASS | no hardcoded values |
| `chunk.web.domain` field validity | PASS | confirmed via web research on google-genai 2.x |
| `firebase-admin==7.4.0` is current | PASS | confirmed via PyPI |
