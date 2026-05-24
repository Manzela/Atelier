# Executor Brief — Round 7

**Executor:** Antigravity IDE (Claude Opus 4.6 Thinking)
**Date issued:** 2026-05-21T18:00Z
**Author:** Claude Code (Opus 4.7 MAX) — Atelier sprint orchestrator
**Source spec:** `docs/superpowers/specs/2026-05-21-post-r4-strategic-roadmap-design.md` (SHA `0e1c3b1` on `phase/1`)
**Source plan:** `docs/superpowers/plans/2026-05-21-sota-architecture-implementation.md` (commit `a41569e` on `phase/1`) — full Task 0-14 contract
**R6 prior:** `audit/executor-handoff-run6.md` (READY-FOR-AUDIT-RUN-6 received; orchestrator verdict in §1 below)
**Worktree:** `.worktrees/phase1-foundation/` on branch `phase/1` ONLY. DO NOT touch `.worktrees/phase2-consensus-agent/` — that worktree is reserved for the parallel SOTA Protocol implementation owned by the orchestrator.
**Wall-clock budget:** ~45-60 min (R7 is larger than R6 because the SOTA primitives ship code, not just inventory).
**Commit policy:** Per-item commits, Conventional Commits 1.0.0, NO `--no-verify` ever.
**Tone:** Strictly mechanical implementation against the plan file. Architecture decisions are LOCKED in the plan. If a step requires design intuition that the plan does not already specify, FAIL-LOUD and surface to orchestrator instead of guessing.

---

## §1. R6 verdict (informational — already executed by you)

**APPROVED with two clarifications and one open follow-up.** Independent verification of `audit/executor-handoff-run6.md`:

| R6 item | Claim                                                  | Method                                                                          | Result                                        |
| ------- | ------------------------------------------------------ | ------------------------------------------------------------------------------- | --------------------------------------------- |
| R6-01   | i-for-ai inventory captured (159 resources)            | `wc -l audit/migration/inventory-i-for-ai-2026-05-21.json` + `jq '. \| length'` | ✅ JSON well-formed, 159 entries              |
| R6-02   | Classification: 158 LEAVE / 1 MIGRATE / 0 DECOMMISSION | `jq -r '.[].disposition'` then `sort \| uniq -c`                                | ✅ Matches handoff §3                         |
| R6-02   | Only MIGRATE item is `atelier-geap-api-key`            | `jq -r '.[] \| select(.disposition=="MIGRATE")'`                                | ✅ Exactly one row, secret resource           |
| R6-03   | atelier-build-2026 verdict: NOT READY                  | Read `audit/migration/atelier-build-2026-readiness-2026-05-21.md`               | ✅ Status documented; 5-step checklist exists |
| R6-04   | Test count discrepancy resolved (300 confirmed)        | Read `audit/gates/r6-04-test-count-verification.txt`                            | ✅ Documentation only, no code change         |
| R6-05   | Phase 1 Gate runner wires 18 gates                     | Read `scripts/gates/phase_1_gate.sh` + `phase_1_gates.json`                     | ✅ 5/18 passing baseline correct              |
| R6-06   | WebGen-Bench 50-task harness scaffolded                | `pytest atelier-core/tests/eval/test_webgen_50.py --collect-only`               | ✅ 50 tests collected, all xfail (expected)   |
| R6-07   | 6 commits land + handoff                               | `git log --oneline -10` shows c371876..ff90079 + 6952935                        | ✅ All R6 commits present                     |

**Clarification 1 (R6-06):** Your handoff §7 surfaced a real spec discrepancy — WebGen-Bench upstream has **101** tasks, not **484**. The 484 number in spec §4.3 #5 was a confusion with the **Design2Code** benchmark. **Action assigned to orchestrator, NOT to you:** Claude will author an ADR amendment (ADR 0026-AMEND) reconciling spec §4.3 #5 to the upstream `101 tasks → 50-task subset` ground truth. Your harness implementation is CORRECT against the real WebGen-Bench. No R7 work needed from you on this.

**Clarification 2 (R6-04):** The R5 reported "296 + 1 collection error" was a stale `.pyc` artifact, not a real test loss. Confirmed by your fresh collection. Closed.

**Open follow-up:** Your handoff §10 row 6 says "Orchestrator authors ADRs 0027-0030 (at least one)." The orchestrator HAS authored these ADRs in the plan file (see `docs/superpowers/plans/2026-05-21-sota-architecture-implementation.md` Tasks 13 & 14 — ADR 0027 (router decision) and ADR 0028 (DPO promotion gate) amendments are committed inside those Tasks). ADRs 0029 (memory scope-key format) and 0030 (google-genai migration) are scheduled inside Tasks 11 and 6 respectively. **No action needed from you on ADR drafting — your R7 items implement against pre-decided ADRs.**

---

## §2. Strategic context for R7

R6 cleared the GCP discovery + Phase 1 Gate scaffolding work. R7 now ships the **production code for the §18–§21 SOTA Protocol surfaces that have zero architectural ambiguity** — they are pre-decided in the plan file commit `a41569e`. The orchestrator owns the novel-tier tasks that require Opus 4.7 MAX authorship judgment (T1, T5, T6, T7, T8, T9, T10, T13, T14); you own the mechanical implementation of the foundational + IO-heavy tasks (T0, T2, T3, T4, T11, T12) plus the GCP cutover that R6 left at "Daniel-approval-required."

This split is the user-approved Option A parallelization. The orchestrator and Antigravity work concurrently with **zero shared file ownership** during R7 — there is no risk of merge conflicts because the task boundaries are at the module level.

The plan file `docs/superpowers/plans/2026-05-21-sota-architecture-implementation.md` is the **single source of truth for every R7 item below.** Each R7-XX item maps to a plan Task and references its exact step numbers. Do not invent steps the plan does not specify; if the plan is ambiguous, FAIL-LOUD.

**Out of scope for R7 — DO NOT TOUCH (orchestrator owns):**

- ❌ Plan Tasks T1 (`atelier.runtime.context` — ContextVar primitives)
- ❌ Plan Tasks T5 (`atelier.reward.and_gate` — AND-gate composite)
- ❌ Plan Tasks T6 (`atelier.optimize.vertex_dpo` — google-genai DPO client)
- ❌ Plan Tasks T7 (`atelier.optimize.pair_miner` — BigQuery pair miner)
- ❌ Plan Tasks T8 (`atelier.reward.prm` — PRM scaffolding)
- ❌ Plan Tasks T9 (`atelier.eval.calibration` — calibration golden set)
- ❌ Plan Tasks T10 (Phase 1 Gate runner DATA + dry-run capture — the runner script itself is yours from R6, but the data wiring + dry-run evidence capture is orchestrator scope)
- ❌ Plan Tasks T13 (`atelier.routing.bandit` — BanditRouter v1 with ε-greedy)
- ❌ Plan Tasks T14 (`atelier.optimize.generator_tuner_dpo` — DPO cycle + promotion gate)
- ❌ ADR amendments 0027, 0028, 0029, 0030 (encoded inside orchestrator-owned Tasks)
- ❌ ADR amendment 0026-AMEND (WebGen-Bench 484→101 reconciliation — orchestrator owns)
- ❌ Any work in `.worktrees/phase2-consensus-agent/`
- ❌ Any `--no-verify`, `git push --force`, `git reset --hard`, `git checkout -- .`, `git clean -fd`
- ❌ Pushing `phase/1` to remote BEFORE Daniel signs off (R7-10 is conditional)
- ❌ Running `terraform apply` BEFORE Daniel signs off (R7-08 is plan-only)
- ❌ Migrating `atelier-geap-api-key` BEFORE Daniel confirms `atelier-build-2026` exists + billing linked + APIs enabled (R7-07 is conditional)

---

## §3. R7 items

### R7-01: Plan Task T0 — Lockfile pin `google-genai>=0.4.0` + transitive sweep

**Intent:** Bring the lockfile in sync with the SOTA Protocol code we are about to write. `google-genai` replaces the deprecated `vertexai.preview.tuning` surface per spec §9.2.

**Plan reference:** Task T0 (plan file lines ~120–280). Read it in full before starting.

**Files:**

- Modify: `atelier-core/requirements.in` (add `google-genai>=0.4.0`)
- Regenerate: `atelier-core/requirements.lock` via `pip-compile --generate-hashes --resolver=backtracking`
- Verify: `pip install --dry-run -r atelier-core/requirements.lock` (must succeed without conflict)

**Steps (verbatim from plan T0):**

1. Edit `atelier-core/requirements.in` per plan T0 Step 1 (exact text in plan).
2. Regenerate the lockfile per plan T0 Step 2 (exact command in plan).
3. Run `pip-audit` against the new lockfile per plan T0 Step 3. If any HIGH/CRITICAL CVE appears, FAIL-LOUD and surface `audit/lockfile/R7-01-CVE-FOUND.md` documenting the CVE, the affected dep, and the suggested upstream version. Do NOT downgrade or pin around it without orchestrator approval.
4. Run `python -c "from google import genai; print(genai.__version__)"` per plan T0 Step 4 to verify the import works.
5. Commit per plan T0 Step 5 (exact Conventional Commit message in plan).

**Acceptance:**

- `requirements.lock` regenerated with hashes
- `pip-audit` returns 0 HIGH/CRITICAL
- `python -c "from google import genai"` succeeds
- Commit message matches plan T0 exactly

**Approval status:** Self-execute.

---

### R7-02: Plan Task T2 — FailureMode enum + `@failure_trichotomy` decorator + ADR 0031

**Intent:** Codify the failure trichotomy at the type level so every external-IO callsite stamps its failure mode in the type signature. ADR 0031 locks the decision.

**Plan reference:** Task T2 (plan file lines ~520–820). Read it in full before starting.

**Files:**

- Create: `atelier-core/src/atelier/runtime/failure.py` (~180 LOC per plan)
- Create: `atelier-core/tests/unit/test_failure_trichotomy.py` (~120 LOC per plan)
- Create: `docs/decisions/ADR-0031-failure-trichotomy-enum.md` (per plan T2 Step 6)
- Update: `DECISIONS.md` (1-row insert per plan T2 Step 7)

**Steps (verbatim from plan T2):**

1. Write the failing test file per plan T2 Step 1 (full test code in plan).
2. Run the test, verify it fails per plan T2 Step 2 (expected output in plan).
3. Implement `FailureMode` enum + `@failure_trichotomy(fail_mode, max_retries=0)` decorator per plan T2 Step 3 (full impl code in plan).
4. Run the test, verify it passes per plan T2 Step 4.
5. Run `mypy --strict atelier-core/src/atelier/runtime/failure.py` per plan T2 Step 5 (must exit 0).
6. Write ADR 0031 per plan T2 Step 6 (full Markdown template in plan).
7. Append the DECISIONS.md row per plan T2 Step 7 (exact row text in plan).
8. Commit per plan T2 Step 8 (Conventional Commit message in plan).

**Acceptance:**

- `pytest atelier-core/tests/unit/test_failure_trichotomy.py -v` → all pass
- `mypy --strict atelier-core/src/atelier/runtime/failure.py` → exit 0
- ADR 0031 committed
- DECISIONS.md updated
- No bare except (ban-bare-except pre-commit hook passes)

**Approval status:** Self-execute.

---

### R7-03: Plan Task T3 — `ManagedRoutingRouter` v0 (rules-based dispatch)

**Intent:** Ship the rules-based router that the BanditRouter v1 (T13, orchestrator-owned) falls back to during cold-start. v0 is intentionally simple — phase-keyed dispatch with no learned state.

**Plan reference:** Task T3 (plan file lines ~880–1160). Read it in full before starting.

**Files:**

- Create: `atelier-core/src/atelier/routing/managed_router.py` (~140 LOC per plan)
- Create: `atelier-core/src/atelier/routing/protocol.py` — Protocol stub (~50 LOC; the Protocol is the contract that BanditRouter v1 will also satisfy)
- Create: `atelier-core/tests/unit/test_managed_router.py` (~110 LOC per plan)

**Steps (verbatim from plan T3):**

1. Write `routing/protocol.py` with the `Router` Protocol per plan T3 Step 1 (full Protocol code in plan).
2. Write the failing test per plan T3 Step 2 (full test code in plan).
3. Run the test, verify it fails per plan T3 Step 3.
4. Implement `ManagedRoutingRouter` per plan T3 Step 4 (full impl code in plan).
5. Run the test, verify it passes per plan T3 Step 5.
6. Run `mypy --strict atelier-core/src/atelier/routing/` per plan T3 Step 6.
7. Commit per plan T3 Step 7 (Conventional Commit message in plan).

**Acceptance:**

- `pytest atelier-core/tests/unit/test_managed_router.py -v` → all pass
- `mypy --strict atelier-core/src/atelier/routing/managed_router.py atelier-core/src/atelier/routing/protocol.py` → exit 0
- Protocol type-checks against the `ManagedRoutingRouter` concrete impl (T13 will check the same Protocol against BanditRouter)

**Approval status:** Self-execute.

---

### R7-04: Plan Task T4 — Routing manifest schema + JSON-Schema validator

**Intent:** The routing manifest at `infra/routing/manifest.yaml` defines arm→phase→endpoint mappings consumed by both v0 (R7-03) and v1 (orchestrator T13). The JSON-Schema validator runs as a pre-commit hook so a malformed manifest never reaches main.

**Plan reference:** Task T4 (plan file lines ~1220–1480). Read it in full before starting.

**Files:**

- Create: `infra/routing/manifest.yaml` (skeleton per plan T4 Step 1)
- Create: `infra/routing/routing_manifest.schema.json` (per plan T4 Step 2)
- Create: `atelier-core/tests/unit/test_routing_manifest_schema.py` (~80 LOC per plan)
- Modify: `.pre-commit-config.yaml` (add local hook per plan T4 Step 5)

**Steps (verbatim from plan T4):**

1. Author the manifest skeleton per plan T4 Step 1 (full YAML in plan).
2. Author the JSON Schema per plan T4 Step 2 (full schema in plan).
3. Write the schema-validation test per plan T4 Step 3 (full test code in plan).
4. Run the test, verify it passes (manifest validates against schema) per plan T4 Step 4.
5. Add a local pre-commit hook that runs the validator on any YAML change under `infra/routing/` per plan T4 Step 5 (full hook YAML in plan).
6. Commit per plan T4 Step 6 (Conventional Commit message in plan).

**Acceptance:**

- `pytest atelier-core/tests/unit/test_routing_manifest_schema.py -v` → pass
- `pre-commit run validate-routing-manifest --files infra/routing/manifest.yaml` → pass
- Schema file is well-formed JSON: `jq '.' infra/routing/routing_manifest.schema.json > /dev/null`

**Approval status:** Self-execute.

---

### R7-05: Plan Task T11 — Vertex Memory Bank semantic tier

**Intent:** Implement the semantic memory backend on Vertex AI Memory Bank with scope-keyed namespacing enforced by an IAM CEL ACL-on-read condition. The scope-leak guard integration test is the critical acceptance gate.

**Plan reference:** Task T11 (plan file lines ~4870–5180). Read it in full before starting.

**Files:**

- Create: `atelier-core/src/atelier/memory/scope.py` — `MemoryScopeKey` frozen dataclass + `encode()`/`decode()` (~60 LOC per plan)
- Create: `atelier-core/src/atelier/memory/semantic.py` — `SemanticMemoryBackend` Protocol + `VertexSemanticMemory` concrete + `SemanticHit` + `ConsolidationReport` (~190 LOC per plan)
- Create: `atelier-core/tests/integration/test_memory_scope_leak_guard.py` — 3-assertion harness (~140 LOC per plan)
- Create: `docs/decisions/ADR-0029-memory-scope-key-format.md` (per plan T11 Step 10)
- Create: `infra/iam/atelier-memory-scope-acl.json` (per plan T11 Step 9 — CEL condition JSON)
- Update: `DECISIONS.md` (1-row insert)

**Steps (verbatim from plan T11):**

1. Author `MemoryScopeKey` per plan T11 Step 1 (full impl + encode/decode + ValueError-on-malformed code in plan).
2. Author the round-trip unit test per plan T11 Step 2.
3. Author the `SemanticMemoryBackend` Protocol + dataclasses per plan T11 Step 3 (full Protocol code in plan).
4. Author the `VertexSemanticMemory` concrete impl per plan T11 Step 4 (full impl code in plan — uses `google-genai` from R7-01).
5. Author the scope-leak guard integration test per plan T11 Step 5 (3 assertions: cross-scope exact-content query returns [], brute-force top_k=1000 exhaustion check, sanity write+read within scope). Full test code in plan.
6. Run the test against a real `atelier-build-2026` Memory Bank instance — but **ONLY if R7-07 is GREEN.** If R7-07 is RED or not-yet-run, skip the integration test execution and surface the skip clearly in the commit message: `(integration test skipped — depends on R7-07 GREEN)`.
7. Run `mypy --strict atelier-core/src/atelier/memory/scope.py atelier-core/src/atelier/memory/semantic.py` per plan T11 Step 7.
8. Author ADR 0029 per plan T11 Step 8 (full Markdown template in plan).
9. Author the IAM CEL condition JSON file at `infra/iam/atelier-memory-scope-acl.json` per plan T11 Step 9 (full JSON in plan).
10. Append DECISIONS.md row per plan T11 Step 10.
11. Commit per plan T11 Step 11 (Conventional Commit message in plan).

**Acceptance:**

- `pytest atelier-core/tests/integration/test_memory_scope_leak_guard.py -v` → pass (or skipped with R7-07 dependency note if R7-07 not yet GREEN)
- `mypy --strict atelier-core/src/atelier/memory/scope.py atelier-core/src/atelier/memory/semantic.py` → exit 0
- ADR 0029 + IAM JSON committed
- DECISIONS.md updated

**Approval status:** Self-execute. **Integration test runs IFF R7-07 is GREEN.**

---

### R7-06: Plan Task T12 — Vertex Memory Bank procedural tier

**Intent:** Implement the procedural memory backend on Vertex AI Memory Bank using the same scope key from T11 (R7-05). The replay-fidelity test is the critical acceptance gate: a written step list must round-trip byte-equivalent through write→query, and the outcome_score must round-trip within 1e-6.

**Plan reference:** Task T12 (plan file lines ~5240–5500). Read it in full before starting.

**Files:**

- Create: `atelier-core/src/atelier/memory/procedural.py` — `ProceduralMemoryBackend` Protocol + `VertexProceduralMemory` concrete + `ProcedureStep` + `ProcedureHit` (~190 LOC per plan)
- Create: `atelier-core/tests/integration/test_procedural_replay_fidelity.py` (~120 LOC per plan)

**Steps (verbatim from plan T12):**

1. Author the `ProceduralMemoryBackend` Protocol + dataclasses per plan T12 Step 1.
2. Author the `VertexProceduralMemory` concrete impl per plan T12 Step 2. Step serialization is JSON-line per step as memory content; reuse the IAM CEL binding from R7-05.
3. Author the replay-fidelity integration test per plan T12 Step 3 (asserts byte-equivalent step list via `assert hit.steps == original_steps` after round-trip, and outcome_score equality within 1e-6).
4. Run the test against `atelier-build-2026` Memory Bank — same skip-if-R7-07-not-GREEN policy as R7-05.
5. Run `mypy --strict atelier-core/src/atelier/memory/procedural.py` per plan T12 Step 5.
6. Commit per plan T12 Step 6 (Conventional Commit message in plan).

**Acceptance:**

- `pytest atelier-core/tests/integration/test_procedural_replay_fidelity.py -v` → pass (or skipped with R7-07 note)
- `mypy --strict atelier-core/src/atelier/memory/procedural.py` → exit 0
- Reuses (does not redefine) `MemoryScopeKey` from R7-05
- Reuses (does not re-bind) the IAM CEL condition from R7-05

**Approval status:** Self-execute. **Integration test runs IFF R7-07 is GREEN.**

---

### R7-07: GCP cutover — verify `atelier-build-2026` + migrate `atelier-geap-api-key`

**Intent:** R6-03 found `atelier-build-2026` NOT READY. Daniel has been handed `audit/migration/atelier-build-2026-daniel-action-checklist.md` (5 steps). When Daniel signals "GCP ready," verify the destination and migrate the single MIGRATE-classified resource from R6-02 (`atelier-geap-api-key`).

**Files:**

- Create: `audit/migration/atelier-build-2026-readiness-2026-05-21-superseded.md` (renames the R6-03 file with `superseded` suffix when the new ACTIVE version supersedes it)
- Create: `audit/migration/atelier-build-2026-readiness-2026-05-22-ACTIVE.md` (new active readiness doc)
- Create: `scripts/migration/07_migrate_geap_secret.sh` (~80 LOC, READ from i-for-ai + WRITE to atelier-build-2026, with `--dry-run` default per `<no_destructive_git>` spirit)
- Create: `audit/migration/secret-cutover-2026-05-22.log` (run output)

**Steps:**

1. **PRECONDITION GATE — DO NOT PROCEED UNLESS ALL THREE PASS:**
   - `gcloud projects describe atelier-build-2026` → exit 0
   - `gcloud beta billing projects describe atelier-build-2026 --format='value(billingEnabled)'` → `True`
   - `gcloud services list --enabled --project=atelier-build-2026 --filter='name:(aiplatform.googleapis.com OR secretmanager.googleapis.com OR bigquery.googleapis.com)'` → all 3 present

   If any of these returns falsy/error, **STOP, do not modify the readiness file, and surface `audit/migration/R7-07-PRECONDITION-NOT-MET.md`** documenting which precondition failed. Do not retry — wait for Daniel signal.

2. If preconditions pass, write `audit/migration/atelier-build-2026-readiness-2026-05-22-ACTIVE.md` with verdict `READY: ✅` and the gcloud verification commands' actual output captured inline.
3. Rename `audit/migration/atelier-build-2026-readiness-2026-05-21.md` → `atelier-build-2026-readiness-2026-05-21-superseded.md` (use `git mv` so history is preserved).
4. Author `scripts/migration/07_migrate_geap_secret.sh` per the pattern in `scripts/migration/01_inventory.sh`:
   - Default to `DRY_RUN=1` (READ secret payload from i-for-ai, print SHA-256 of payload + length, do NOT write).
   - When invoked with `--wet`, set `DRY_RUN=0` and:
     - Read secret payload via `gcloud secrets versions access latest --secret=atelier-geap-api-key --project=i-for-ai`.
     - Create the secret in `atelier-build-2026`: `gcloud secrets create atelier-geap-api-key --project=atelier-build-2026 --replication-policy=automatic`.
     - Add the version: `echo -n "$PAYLOAD" | gcloud secrets versions add atelier-geap-api-key --project=atelier-build-2026 --data-file=-`.
     - Verify: re-read from atelier-build-2026 + assert SHA-256 matches the source SHA-256.
   - Log the full run to `audit/migration/secret-cutover-2026-05-22.log` with NO secret payload ever logged (only SHA-256s + lengths).
5. Run the script `--dry-run` first; verify the SHA-256 capture + length make sense; commit the dry-run log to the audit folder.
6. **WAIT for Daniel approval before invoking with `--wet`.** When approved:
   - Run with `--wet`.
   - Verify the post-migration SHA-256 matches the pre-migration SHA-256 (otherwise FAIL-LOUD and STOP — corrupted secret cutover).
   - Append the WET-run log to the same audit log file.
7. Commit (per phase, may be two commits — one for dry-run + script, one for wet-run log):
   - Dry-run commit: `chore(migration): R7-07 GCP cutover dry-run — atelier-geap-api-key`
   - Wet-run commit (Daniel-approved only): `chore(migration): R7-07 GCP cutover WET — atelier-geap-api-key migrated to atelier-build-2026`

**Acceptance:**

- New ACTIVE readiness doc exists with verdict GREEN + gcloud command output captured
- Superseded readiness doc renamed via `git mv`
- Migration script committed with shellcheck + shfmt clean
- Dry-run log committed
- (Daniel-approved only) Wet-run log committed + post-migration secret SHA-256 == pre-migration SHA-256

**Approval status:**

- Precondition gate + dry-run + script: **Self-execute.**
- Wet-run cutover: **REQUIRES DANIEL APPROVAL.**

---

### R7-08: `terraform init` + `terraform plan` against `atelier-build-2026` (NO apply)

**Intent:** Validate the Terraform skeleton from F0006 against the live `atelier-build-2026` project. Surface any drift between the skeleton's expected resources and the project's actual state. **DO NOT APPLY.**

**Files:**

- Modify (if needed): `infra/terraform/main.tf` to reference `atelier-build-2026` instead of any prior placeholder project id (verify the project_id var binding)
- Create: `audit/terraform/plan-output-2026-05-22.txt` (full plan output)

**Steps:**

1. `cd infra/terraform && terraform init` — verify backend initializes against `atelier-build-2026` GCS state bucket (will likely fail if the bucket does not exist; if so, FAIL-SOFT, document the missing-bucket finding in the plan output file, and surface to orchestrator that a one-time `gsutil mb gs://atelier-terraform-state-2026/` may be needed; **do not create the bucket** — that's Daniel-gated).
2. If init succeeds, `terraform plan -var="project_id=atelier-build-2026" -out=/tmp/atelier.tfplan`.
3. Capture the plan output to `audit/terraform/plan-output-2026-05-22.txt`.
4. Commit: `chore(infra): R7-08 terraform plan capture — atelier-build-2026`

**Acceptance:**

- Plan output file exists with either a successful plan, or a documented init/plan failure with the missing resource clearly named
- **No `terraform apply` invocation** (verify by `git diff` — no state file touched, no real GCP resources created)
- Commit message clearly notes "PLAN ONLY, NO APPLY"

**Approval status:** Self-execute (plan is read-only). **APPLY is Daniel-gated.**

---

### R7-09: Branch protection wiring for `phase/1` (script committed, NOT executed)

**Intent:** R5-02 shipped a 25-line branch protection script (`bbd1d17`). R7-09 finalizes the script (verify required checks list is current after R6 added 18 gates) and stages it for Daniel-approved execution against the GitHub remote.

**Files:**

- Modify: `scripts/governance/enable_branch_protection.sh` (verify required-checks list matches current CI workflow names: gates, pytest, mypy, ruff, markdownlint, pip-audit, etc.)
- Create: `audit/governance/branch-protection-required-checks-2026-05-22.md` (the canonical list of checks the script will enforce)

**Steps:**

1. Read `.github/workflows/*.yaml` (all of them) and enumerate every job name that runs on PRs to `phase/1`.
2. Cross-reference against `scripts/governance/enable_branch_protection.sh`'s `--required-checks` argument. If any CI job exists that the script does not require, ADD it (FAIL-SOFT — surface the addition in the commit message).
3. Author the canonical check-list audit file enumerating each check + its CI workflow source.
4. Run the script with `--dry-run` flag (you may need to add this flag if it does not exist — make the script idempotent and safe-by-default).
5. Commit: `chore(governance): R7-09 finalize branch protection required-checks list`

**Acceptance:**

- Script's `--required-checks` covers every CI job that runs on `phase/1` PRs
- Audit file lists each check with its CI source
- Script does NOT execute `gh api PATCH /repos/.../branches/phase/1/protection` (that's R7-10 / Daniel-approved)
- Dry-run output captured

**Approval status:** Self-execute (script edit + dry-run). **Live execution against remote is Daniel-gated.**

---

### R7-10: Push `phase/1` to remote (Daniel-approved trigger only)

**Intent:** Unpushed commits on `phase/1` since R5 push: `c371876`, `63f92c1`, `a20e6c6`, `54f7a1d`, `3ddbb91`, `78ae731`, `ff90079`, `6952935`, `a41569e` (this plan commit), plus all R7-01..09 commits land before R7-10. Push them all in one operation **only when Daniel explicitly approves.**

**Steps:**

1. Verify all R7-01..09 commits are clean (each `pre-commit run --all-files` exit 0).
2. `git log origin/phase/1..HEAD --oneline` → enumerate the exact commit list that will land on remote.
3. Surface that list to Daniel via the handoff doc (R7-11 below) — the actual push waits on his green light.
4. **When Daniel says "push approved":**
   - `git push origin phase/1` (NO `--force`, NO `--force-with-lease`)
   - Verify push succeeded: `git ls-remote origin phase/1 | awk '{print $1}'` equals local `git rev-parse phase/1`
   - Capture the push output to `audit/governance/phase-1-push-2026-05-22.log`
5. Commit (push log only, not the push itself): `chore(governance): R7-10 phase/1 push log capture`

**Acceptance:**

- All R7-01..09 commits pre-commit clean
- Local + remote `phase/1` tips equal post-push
- Push log captured
- No force-push, no `--no-verify`

**Approval status:** **REQUIRES DANIEL APPROVAL** before push.

---

### R7-11: R7 handoff document (this round's deliverable to orchestrator)

**Intent:** Same role as `audit/executor-handoff-run6.md` — concise summary of every R7 item with commit SHA, pass/fail status, and any "would not bet my job on" caveats.

**Files:**

- Create: `audit/executor-handoff-run7.md`

**Contents (match the R6 handoff template):**

1. §1: Per-item commit table (item → SHA → subject → files-changed-count)
2. §2..§10: One subsection per R7-XX item with method, evidence, result
3. §N: "What I would NOT bet my job on" — same role as R6 handoff §8
4. §N+1: Push state — every commit since `origin/phase/1` tip with whether it landed
5. §N+2: Daniel-gated follow-ups for R8 (deferred items: terraform apply, branch protection live execution, wet secret cutover IFF R7-07 didn't run wet)
6. Closing trailer: `READY-FOR-AUDIT-RUN-7` + ISO-8601 timestamp

**Acceptance:**

- Document exists at `audit/executor-handoff-run7.md`
- Every R7 item from §3 above has a corresponding subsection
- Push state is honest (if you did not push, say so explicitly — do not claim "blocked" without naming the blocker)
- Trailer present

**Approval status:** Self-execute.

---

## §4. Approval gates summary

| Item                                                  | Self-execute | Daniel-approval-required before this happens                             |
| ----------------------------------------------------- | ------------ | ------------------------------------------------------------------------ |
| R7-01 lockfile pin google-genai                       | ✅ Yes       | —                                                                        |
| R7-02 FailureMode enum + ADR 0031                     | ✅ Yes       | —                                                                        |
| R7-03 ManagedRoutingRouter v0                         | ✅ Yes       | —                                                                        |
| R7-04 routing manifest schema                         | ✅ Yes       | —                                                                        |
| R7-05 Vertex semantic memory (impl)                   | ✅ Yes       | —                                                                        |
| R7-05 Vertex semantic memory (integration test run)   | Conditional  | R7-07 GREEN                                                              |
| R7-06 Vertex procedural memory (impl)                 | ✅ Yes       | —                                                                        |
| R7-06 Vertex procedural memory (integration test run) | Conditional  | R7-07 GREEN                                                              |
| R7-07 GCP cutover preconditions + dry-run             | ✅ Yes       | —                                                                        |
| R7-07 GCP cutover WET (geap-api-key actual migration) | ❌ No        | Daniel approval after dry-run + Daniel confirms atelier-build-2026 ready |
| R7-08 terraform init + plan capture                   | ✅ Yes       | —                                                                        |
| R7-08 terraform apply                                 | ❌ No        | Daniel approval after plan reviewed                                      |
| R7-09 branch protection script finalize + dry-run     | ✅ Yes       | —                                                                        |
| R7-09 branch protection live PATCH against GitHub     | ❌ No        | Daniel approval                                                          |
| R7-10 push phase/1 to remote                          | ❌ No        | Daniel approval                                                          |
| R7-11 handoff doc                                     | ✅ Yes       | —                                                                        |

---

## §5. Failure-handling trichotomy reminder

Per CLAUDE.md:

- **Fail-loud** (alert + halt): unauthenticated gcloud, missing `atelier-build-2026` project, pip-audit HIGH/CRITICAL CVE in R7-01, secret SHA-256 mismatch post-cutover, terraform `apply` invocation attempted by mistake, push attempted without Daniel approval, scope-leak guard test failure in R7-05
- **Fail-soft** (degrade + log + acknowledge): terraform init backend bucket missing (document, surface, don't create), CI workflow job not yet existing for a required-check (document, surface), integration test skipped because R7-07 not yet GREEN
- **Self-heal** (retry up to 3): transient gcloud 429/503, transient pip install timeouts, transient `gh api` rate limits

---

## §6. Spec invariants you MUST honor

From CLAUDE.md `<no_unverified_apis>`, `<compile_then_commit>`, `<no_speculation>`, `<no_test_driven_slop>`, `<no_silent_error_suppression>`, `<json_state_files>`, `<no_destructive_git>`, `<lockfile_only_installs>`, `<wrap_dont_fork>`, `<conventional_commits_required>`, `<wrap_phase_work_in_worktrees>`.

Specific to R7:

- All new Python files (`failure.py`, `managed_router.py`, `protocol.py`, `scope.py`, `semantic.py`, `procedural.py`) MUST pass `mypy --strict` BEFORE commit.
- All new bash scripts MUST pass `shellcheck` + `shfmt` (pre-commit handles).
- All new JSON Schema files MUST be well-formed JSON (`jq` validates).
- The IAM CEL condition file at `infra/iam/atelier-memory-scope-acl.json` MUST be valid CEL — the CEL expression is locked in the plan as `request.attribute["aiplatform.googleapis.com/memoryScope"] == resource.attribute["aiplatform.googleapis.com/memoryScope"]`. Do not modify.
- No new pip dependencies BEYOND `google-genai>=0.4.0` (and its transitive sweep) in R7-01. If you discover another dep is needed, FAIL-LOUD and surface — do not add ad-hoc.
- features.json schema gates from R5-03c/d are still mandatory pre-commit — if any R7 edit accidentally touches features.json (unlikely), gates must still pass.
- No `--no-verify` ever. If a pre-commit hook fails, fix the underlying issue and create a NEW commit (not `--amend`, not `--no-verify`).
- Conventional Commits 1.0.0 — every commit message follows `<type>(<scope>): <subject>` format with body explaining the WHY.

---

## §7. Out-of-scope reaffirmation

You will NOT:

- Touch any file under `atelier-core/src/atelier/runtime/context.py` (orchestrator's T1)
- Touch any file under `atelier-core/src/atelier/reward/` (orchestrator's T5, T8)
- Touch any file under `atelier-core/src/atelier/optimize/` (orchestrator's T6, T7, T14)
- Touch any file under `atelier-core/src/atelier/routing/bandit.py` (orchestrator's T13 — note: T13 is a SEPARATE file from R7-03's `managed_router.py`)
- Touch any file under `atelier-core/src/atelier/eval/calibration*` (orchestrator's T9)
- Touch `scripts/gates/phase_1_gate.sh` (you authored it in R6-05; orchestrator's T10 is data-wiring only)
- Author ADR 0027 (router decision lock — encoded in orchestrator's T13)
- Author ADR 0028 (DPO promotion gate — encoded in orchestrator's T14)
- Author ADR 0030 (google-genai migration — encoded in orchestrator's T6)
- Author ADR 0026-AMEND (WebGen-Bench 484→101 — orchestrator owns)
- Push any branch to origin without Daniel approval
- Run `terraform apply` against any project
- Run R7-07 wet-mode without Daniel approval
- Create or modify any file in `.worktrees/phase2-consensus-agent/`
- Modify the plan file `docs/superpowers/plans/2026-05-21-sota-architecture-implementation.md` (read-only reference for you)
- Modify any ADR file authored by the orchestrator inside Tasks T6/T11/T13/T14

---

## §8. Coordination with orchestrator

The orchestrator is executing T1, T5, T6, T7, T8, T9, T10, T13, T14 in parallel with your R7 work. To minimize coordination friction:

- **No shared files.** Every file you create in R7-01..09 lives in a path the orchestrator's tasks do not write to.
- **No shared commits.** Every R7 item ships as its own commit; orchestrator's commits ship separately. Daniel's eventual push will include both sets in one push.
- **No shared imports until late.** The Protocol you ship in R7-03 (`atelier-core/src/atelier/routing/protocol.py`) is what the orchestrator's T13 (`bandit.py`) will import. Ship R7-03 first; flag in your handoff `audit/executor-handoff-run7.md` exactly when R7-03 committed, so the orchestrator can verify the Protocol contract before authoring T13.
- **`MemoryScopeKey` import.** R7-05 ships `MemoryScopeKey` (used by R7-06 only within R7). Orchestrator's T9 (calibration) does NOT import it — no cross-coupling.
- **Conflict signal.** If you discover during R7 that the plan's Task spec is genuinely ambiguous or contradicts ADR 0027/0028/0029/0030/0031, **STOP, do not guess, surface to orchestrator** via `audit/R7-PLAN-AMBIGUITY-<task>.md` and continue to the next R7 item.

---

**Brief locked. Spawn when ready.**
**Author:** Claude Code (Opus 4.7 MAX, Atelier orchestrator)
**Issued:** 2026-05-21T18:00Z
