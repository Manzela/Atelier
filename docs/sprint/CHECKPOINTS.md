# Sprint Checkpoints

> Per Strategy v2 daily checkpoint ritual. Append-only. Each checkpoint records: what shipped, what's next, blockers, test status, cost burn, and a `RESUME-HERE` marker if the session ended mid-feature.

---

## 2026-05-21 D7 — D1-D7 Consolidated Backfill

**Rationale**: Daily entries lapsed; backfilled from `git log phase/1` + Antigravity brain checklist + executor-brief audit findings. This consolidated entry covers all work from D1 (2026-05-15) through D7 (2026-05-21).

**Session**: Multi-agent execution (Antigravity IDE + Claude Opus 4.7 subagent)
**Worktree**: `.worktrees/phase1-foundation/`
**Branch**: `phase/1`

### What shipped (D1-D7)

1. **Foundation data contracts** (`2720f71`): BriefSpec, CandidateUI, GateOutcome, JudgeVote, TrajectoryRecord — frozen Pydantic models with `schema_version=1`
2. **API skeleton** (`2720f71`): FastAPI app with `/brief`, `/health`, `/ready` endpoints
3. **Governor** (`2720f71`): fail-loud, fail-soft, self-heal trichotomy with exponential backoff
4. **Model registry** (`71a1c7e`): D-O-R-A-V judge → model mapping, Gemini 2.5 Flash pin
5. **A2A agent card** (`71a1c7e`): `agent_card.json` with skills and capabilities
6. **OTel span schema** (`71a1c7e`): 15 mandatory attributes in `spans.py`
7. **Terraform IaC** (`cf396bb`): versions.tf, variables.tf, main.tf for staging
8. **BigQuery schema** (`cf396bb`): 4 tables live in `i-for-ai.atelier_trajectories`
9. **Stitch MCP wrapper** (`a967567`): Design system integration with 7 visual register mappings
10. **6 deterministic gates** (`fe7fd96`): semantic_html, css_validity, token_fidelity + 3 stubs
11. **N3a generator** (`fe7fd96`): Template-based HTML/CSS generation per visual_register
12. **Axis weights** (`fe7fd96`): BriefSpec-conditional D-O-R-A-V weighting (FA-018, FA-019)
13. **Constitution registry** (`fe7fd96`): apple-grade + brutalist YAML constitutions (FA-021)
14. **Trajectory recorder** (`7b52e0f`): N3h data models + DPO preference pair extraction

### Test delta

- D0 baseline: 0 tests
- D7 current: 177 tests passing in 0.27s

### Cost burn

- Estimated cumulative: ~$200 of $5,000 (4.0%)
- Cache-hit-rate: data not available

### Blockers at D7

- Executor-brief C1-C15 remediation items blocking Phase 2 gate
- No external blockers

---

## 2026-05-14 22:30 UTC — Checkpoint 0 (Pre-Sprint Bootstrap)

**Session**: Initial repo scaffold + PRD lock
**Worktree**: `main`
**Branch**: `main` (4 commits)

**What shipped**:

- Full repo scaffold: LICENSE (Apache-2.0) + NOTICE + README + CHANGELOG + ROADMAP + SECURITY + CONTRIBUTING + CODE_OF_CONDUCT + GOVERNANCE
- Sprint state files: CLAUDE.md (sprint invariants) + DECISIONS.md (10 locked decisions) + REJECTED.md (6 pre-emptive rejections) + features.json (Anthropic harness JSON ledger) + claude-progress.txt + init.sh
- Configuration: .gitignore + .editorconfig + .gitattributes + .nvmrc + .python-version + pyproject.toml + package.json + .pre-commit-config.yaml + .markdownlint.yaml + .yamllint.yaml + release-please-config.json + .release-please-manifest.json + .secrets.baseline
- GitHub: CODEOWNERS + dependabot.yml + PULL_REQUEST_TEMPLATE + 4 ISSUE_TEMPLATE/\* + SECURITY.md + FUNDING.yml
- GitHub Actions (minimum-viable): ci.yml + release.yml only (codeql/eval/docs/stale workflows deferred per user directive on workflow credit conservation)
- Documentation: docs/superpowers/specs/2026-05-14-atelier-prd.md (PRD, 1100+ lines after principles audit) + 10 ADRs + decisions/README + decisions/template
- Sprint state: docs/sprint/STATUS.md + CHECKPOINTS.md (this file) + BLOCKERS.md + COST_LEDGER.md + ROADMAP.md

**Cost at session end**: ~$50 of $5000

---

(Future checkpoints append above the Checkpoint 0 entry.)

RESUME-HERE: Close C1-C15 executor-brief items, then proceed to F0023 (N3d ConsensusAgent skeleton). Next unblocked feature after remediation: F0023.

---

## R9 — Antigravity Pipeline Features

<!-- Antigravity appends batch-end summaries here (R9-A, R9-B, R9-C) -->

---

## T6-T14 — Claude SOTA Protocol

### D11 (2026-05-25) — T6-T14 SOTA Protocol surfaces complete

**Commits**: f1a2628 (T6), 128a9e6 (T7), c4b9577 (T8), 8d10cd8 (T13), 2bcd93a (T14)
**Branch**: `phase/2`, pushed to `origin/phase/2`

**What shipped**:

- **T6** `atelier/optimize/dpo_tuning_job.py` — DpoTuningJob using `google.genai` PREFERENCE_TUNING. API shape verified via Step-1 introspection: beta/epoch_count/adapter_size flat on CreateTuningJobConfig (no preference_optimization_spec field). 14 tests.
- **T7** `atelier/optimize/generator_tuner.py` — GeneratorTunerProtocol + BigQueryPairMiner.mine_pairs(). Reads `atelier_trajectories.dpo_pairs`, tenant_id parameterized query. 14 tests.
- **T8** `atelier/memory/bigquery_backend.py` — BigQueryEpisodicBackend.write_episodic(). ContextVar fail-loud, tenant_id isolation, embedding excluded from BQ rows. 11 tests.
- **T13** `atelier/router/v1_bandit.py` — EpsilonGreedyBandit v1 PhaseAwareMoERouter. EPSILON_START=0.10, EPSILON_FLOOR=0.02, EPSILON_DECAY=7 days, UCB1_EXPLORATION_CONSTANT=sqrt(2.0). Sub-50ms p99 (in-process arm state). 21 tests.
- **T14** GeneratorTuner.tune() + evaluate_and_promote() in generator_tuner.py. KAPPA_PROMOTION_THRESHOLD=0.70 gate. Full DPO loop: mine → GCS upload → tune job → promote. 7 tests.
- Bonus: fixed test_router_v0.py asyncio→anyio markers (Antigravity defect in Claude-owned test file).

**Test count**: 495 passing (0 failures, 1 warning)
**mypy --strict**: 0 issues on all 5 new files

**T7 gate**: still blocked on Antigravity FA-012 dpo_builder.py creating `atelier_trajectories.dpo_pairs` BQ table. Unit tests mock the BQ client. Integration path not runnable until R9-B lands.

### D11 verification pass (2026-05-25) — test fixes + plan contradiction resolved

**Commit**: d9bd9f0 (test fixes)

**Additional fixes found during verification-before-completion:**

- Fixed 6 failing tests (not 0 as initially believed):
  - `@pytest.mark.asyncio` → `@pytest.mark.anyio` in `test_vertex_memory_bank_scope.py` and `test_vertex_procedural_replay.py` (same asyncio-marker bug as test_router_v0.py; tests were failing due to wrong marker, NOT credentials)
  - `Path("config/...")` → `Path(__file__).resolve().parents[3] / "config" / "..."` in `test_otel_export.py` and `test_scrubber.py` (relative path was wrong when running from atelier-core/ CWD)
- Resolved plan F5 contradiction: plan checklist had "Update features.json" step that contradicted the F5 coordination contract. Verified: 0 T6-T14 feature IDs exist in features.json. Marked step N/A.
- Antigravity brief Priority 1 (fix 6 failing tests) is now moot — Claude already fixed all 6.

**Net suite count post-verification:** 504 passed, 0 failures, 50 xfailed.
