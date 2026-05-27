# Audit Plan — Antigravity Phase 2 (Environment Audit & Assessment 4)

**Status**: Pass 2 complete. Awaiting user approval before any implementation.
**Source findings**: audit/findings-antigravity-env4.md
**Total findings**: 16 (4 P0, 7 P1, 5 P2)

---

## P0 — Must Fix Before Merge (4 items)

### P0-1: Bump google-github-actions/auth to v3 + add Attribute Condition

**What**: `.github/workflows/bench-publish.yml` uses deprecated `google-github-actions/auth@v2`.
**Why**: v3 released 2025-09-03 contains security fixes. Missing Attribute Condition allows
token forgery from any other repository in the same GitHub organization.
**Where**: `.github/workflows/bench-publish.yml:17-20`
**Fix**:
```yaml
- uses: google-github-actions/auth@v3
  with:
    workload_identity_provider: ${{ secrets.GCP_WORKLOAD_IDENTITY_PROVIDER }}
    service_account: ${{ secrets.GCP_SERVICE_ACCOUNT }}
    attribute_condition: "assertion.repository == 'Manzela/atelier'"
```
**Effort**: 5 min.

### P0-2: Add workflow_dispatch trigger to bench-publish.yml

**What**: No manual retrigger possible.
**Why**: Standard CI/CD ops requirement; nightly cron + push are insufficient for incident response.
**Where**: `.github/workflows/bench-publish.yml:3`
**Fix**:
```yaml
on:
  schedule:
    - cron: '17 3 * * *'
  push:
    branches: ['phase/2']
  workflow_dispatch:
```
**Effort**: 2 min.

### P0-3: Replace pip install with requirements.lock in CI

**What**: `pip install -e "atelier-core[dev]"` and `npm install -g firebase-tools` violate
the `<lockfile_only_installs>` CLAUDE.md invariant.
**Why**: Transient dep drift; CLAUDE.md cites LiteLLM Mar 2026 slopsquatting as rationale.
**Where**: `.github/workflows/bench-publish.yml:21-24`
**Fix**:
```yaml
- name: Install Python deps
  run: pip install -r requirements.lock && pip install -e atelier-core/
- name: Install Firebase CLI
  run: npm install -g firebase-tools@13
```
**Effort**: 5 min.

### P0-4: Fix non-best candidate composite_score=0.0 in trajectory records

**What**: `generate.py:188` assigns `composite_score=0.0` to all non-winning N3a candidates.
**Why**: DPO pair miner ranks by margin. Zero scores create artificial large margins and
corrupt training signal — pairs mined from these records are unreliable.
**Where**: `atelier-core/src/atelier/api/generate.py:185-192`
**Fix**: Extract per-candidate composite score from `result["evaluations"]`:
```python
eval_idx = sum(1 for gr in gate_results[:i] if gr.get("all_passed")) - 1
actual_score = evaluations[eval_idx]["composite_score"] if 0 <= eval_idx < len(evaluations) else 0.0
composite_score=actual_score,
```
**Effort**: 20 min (includes updating the `_record_trajectory` function signature).

---

## P1 — Should Fix Before Production (7 items)

### P1-1: Fix cross-tenant DPO pairs in fixture

**What**: Shared surface_ids in `trajectories_seed.jsonl` span tenant-alpha / tenant-beta boundary.
**Why**: Cross-tenant preference pairs corrupt per-tenant judge personalization.
**Where**: `atelier-core/tests/fixtures/trajectories_seed.jsonl`
**Fix**: Regenerate fixture — assign shared surface_ids only within tenant-alpha records.
Concretely: records 0,1,2 (accepted, tenant-alpha) share surfaces with records 18,19,20
(rejected) — move records 19,20 to tenant-alpha or move shared surfaces to tenant-beta only.
**Effort**: 15 min.

### P1-2: Fix temporal inconsistency in fixture (ended_at < ts)

**What**: 3 records have `ended_at` before `ts`.
**Why**: Negative-duration spans produce malformed Gantt bars in the replay UI.
**Where**: `atelier-core/tests/fixtures/trajectories_seed.jsonl` rows ~6, 8, 16
**Fix**: Regenerate with `ended_at = ts + timedelta(seconds=random.randint(30, 300))`.
**Effort**: 10 min.

### P1-3: Replace hardcoded `candidates[:3]` with ENSEMBLE_SIZE constant

**What**: `generate.py:170` hardcodes K=3.
**Why**: If ensemble width changes, trajectory recording silently drops candidates.
**Where**: `atelier-core/src/atelier/api/generate.py:170`
**Fix**:
```python
from atelier.orchestrator.generator_ensemble import ENSEMBLE_SIZE
# ...
for i, candidate in enumerate(candidates[:ENSEMBLE_SIZE]):
```
**Effort**: 5 min.

### P1-4: Bump google-genai to 2.6.0

**What**: `pyproject.toml` pins `google-genai>=1.0,<2`. Latest stable is 2.6.0 (2026-05-22).
**Why**: 2.x has improved Grounding API, better typed responses. `chunk.web.domain` confirmed present.
**Where**: `atelier-core/pyproject.toml`
**Fix**: `"google-genai>=2.6,<3"`. Run `pip install -e ".[dev]"` to verify no breaking changes
in `web_research.py` and `dpo_tuning_job.py`.
**Effort**: 20 min (including regression test run).

### P1-5: Firebase auth — catch typed exception subclasses

**What**: `_decode_token()` catches bare `Exception`, producing identical 401 for all failures.
**Why**: `<no_silent_error_suppression>` invariant; judges need distinguishable error codes.
**Where**: `atelier-core/src/atelier/auth/firebase.py` (inside `_decode_token`)
**Fix**:
```python
from firebase_admin import auth as fb_auth
try:
    return fb_auth.verify_id_token(token, check_revoked=check_revoked)
except fb_auth.ExpiredIdTokenError:
    raise HTTPException(401, detail={"error": "token_expired", ...})
except fb_auth.RevokedIdTokenError:
    raise HTTPException(401, detail={"error": "token_revoked", ...})
except fb_auth.UserDisabledError:
    raise HTTPException(401, detail={"error": "user_disabled", ...})
except fb_auth.InvalidIdTokenError:
    raise HTTPException(401, detail={"error": "invalid_token", ...})
```
**Effort**: 25 min (includes adding unit tests for each path).

### P1-6: Fix DEMO timestamps — replace frozen ISO literals with dynamic offsets

**What**: `_build_demo_data()` uses hardcoded `"2026-05-25T04:00:00.000Z"` for `promoted_at`.
**Why**: Stale timestamps in DEMO mode undermine demo credibility for judges.
**Where**: `atelier-core/scripts/generate_bench_data.py` (~line 70, 78)
**Fix**:
```python
now = datetime.now(timezone.utc)
"promoted_at": (now - timedelta(hours=8)).isoformat(),
```
**Effort**: 5 min.

### P1-7: Document latency gap in BQ payload summary

**What**: BQ path summary missing `avg_latency_ms` / `p99_latency_ms`; DEMO has both.
**Why**: Dashboard shows `—` for latency in live mode; DEMO shows values — inconsistent.
The `trajectory_records` table has no latency column in `to_bq_row()`.
**Where**: `atelier-core/scripts/generate_bench_data.py` BQ summary dict
**Fix**: Add explicit `None` values with TODO comment:
```python
"avg_latency_ms": None,   # TODO: add latency_ms to trajectory_records schema
"p99_latency_ms": None,
```
**Effort**: 5 min.

---

## P2 — Nice to Have (5 items)

### P2-1: Remove unreachable `return []` in web_research.py

**Where**: `atelier-core/src/atelier/intake/web_research.py:429`
**Fix**: Delete dead `return []` line. **Effort**: 2 min.

### P2-2: Simplify UUID generation in generate.py

**Where**: `atelier-core/src/atelier/api/generate.py:178,181,184`
**Fix**: Replace `UUID(int=int(uuid4()) & ((1 << 128) - 1))` with `uuid4()`. **Effort**: 5 min.

### P2-3: Rename `l` to `line` in test_dpo_builder.py

**Where**: `atelier-core/tests/unit/test_dpo_builder.py` (load_fixture)
**Fix**: `for line in FIXTURE.read_text().splitlines() if line.strip()`. **Effort**: 2 min.

### P2-4: Move `from uuid import UUID` to top of test_dpo_builder.py

**Where**: `atelier-core/tests/unit/test_dpo_builder.py`
**Fix**: Combine with existing `from uuid import uuid4` at top. **Effort**: 2 min.

### P2-5: Add `pinTag: true` to firebase.json Cloud Run rewrite

**Where**: `firebase.json`
**Fix**: `"pinTag": true` inside the run block. **Effort**: 2 min.

---

## Dependency Order

```
P0-4 (fix composite scores) → P1-1 regeneration may need the fixed scoring
P0-1, P0-2, P0-3 → independent, parallelizable
P1-1, P1-2 → fixture regeneration (one operation, do together)
P1-4 (SDK bump) → run full test suite after
P1-5 (typed exceptions) → requires firebase-admin to be installed
P2 items → all independent, can be batched in a single commit
```

## Estimated Total Effort

- P0: ~32 min
- P1: ~85 min  
- P2: ~13 min
- **Total: ~2.2 hours**

## Changes from Pass 1 (web research enrichment)

The following findings were **added or upgraded** by the web research agent:

| Finding | Change from Pass 1 |
|---------|-------------------|
| P0-1 auth@v2 → v3 | **Upgraded from WARN to P0** — v3 is current, Attribute Condition is security-critical |
| P1-4 google-genai 2.6.0 | **New** — version lag not detectable from codebase alone |
| P1-5 typed exceptions | **Strengthened** — firebase-admin typed subclasses confirmed in SDK docs |
| P2-5 pinTag | **New** — Firebase Hosting docs mention this |
| P0-3 lockfile install | **Confirmed** — lockfile_only_installs invariant from CLAUDE.md cross-referenced |
