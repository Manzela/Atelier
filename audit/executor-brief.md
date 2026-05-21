# Atelier Phase-1 Remediation Brief — Executor Hand-off

> **Audience:** Orchestrator agent (the executor) tasked with closing the C-items below.
> **Author:** Auditor/Governor session (Claude Opus 4.7, 2026-05-21 D7).
> **Authority:** This brief is the operational contract. Acceptance criteria, verification commands, and forbidden shortcuts are binding.
> **Re-audit:** When you claim completion, the same auditor will re-run **every** verification command in §4 with fresh evidence. No claim survives without it.
>
> **Path:** `/Users/danielmanzela/Professional Profile/Atelier/.worktrees/phase1-foundation/audit/executor-brief.md`
> **Companion artifacts (read these first):**
>
> - `audit/findings.md` — Pass-1 codebase-only state map
> - `audit/audit-plan.md` — Pass-1 prioritized fix list
> - `audit/verification-report.md` — Pass-2 synthesis with G-gap and FA-feature verdict tables

---

## 0. TL;DR for the orchestrator

You are picking up the Atelier sprint at **D7 of 21** (today 2026-05-21, submission 2026-06-03 noon). Phase 1 (8-Node DAG foundation) is mid-flight on branch `phase/1` in worktree `.worktrees/phase1-foundation/`. An audit identified **15 concrete remediation items (C1–C15)** plus **4 process items (P1–P4)** that must close before the auditor will green-light Phase 2.

- **Hard stop priority:** P0 items (C1, C2, C3, C4) block the judges loop and the daily ritual — these are sprint-critical. ~2.5h work.
- **Phase-1 close priority:** P1 items (C5–C9) before D14 Phase-2 gate. ~4h work.
- **Hygiene:** P2 items (C10–C15) before submission packaging. ~2.5h work.

Total estimate: **~9 hours of focused work** if executed in dependency order, plus the mandatory handoff report.

**You may NOT begin until you have:**

1. Read this entire document including §2 (operating constraints) and §3 (pre-flight)
2. Run every pre-flight check in §3 and confirmed all pass
3. Acknowledged the handoff protocol in §6
4. Posted a 5-line execution plan to `audit/executor-handoff.md` (see §6.2)

---

## 1. Mission & scope boundaries

### 1.1 In scope

- Close C1–C15 per §4 acceptance criteria.
- Update sprint state files honestly (no marketing language; describe what shipped, what didn't, why).
- Write **one ADR per locked architectural decision** introduced (model deviation, GitHub MCP choice).
- Reconcile `features.json` against actual `git log` evidence on `phase/1`.
- Produce the handoff report per §6.

### 1.2 Out of scope (do NOT touch)

- **No Phase-2 work.** Do not implement N5 (EvoDesign), N14 (WRAI agent loop), DPO Flywheel, Campaign Orchestrator, or Calibration Dashboard. Those are post-D7 deliverables. You may write the **config files** for N14/N15 (C3, C4) because they are foundation contracts, but not the agents themselves.
- **No changes to `main` branch.** All work goes on `phase/1` per ADR 0007 (worktree-per-phase).
- **No upstream forks.** ADR 0001 (`<wrap_dont_fork>`): if `google-adk` / `agent-dag-pipeline` / `hermes-agent` have bugs, file upstream, do not patch in-tree.
- **No new top-level dependencies** without an ADR + lockfile regeneration + Snyk scan (`<lockfile_only_installs>`).
- **No spec changes** to PRD `docs/superpowers/specs/2026-05-14-atelier-prd.md` without an ADR commit.
- **No destructive git** (`<no_destructive_git>` invariant; see §2).

### 1.3 The Iron Law (non-negotiable)

```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

Every C-item in §4 has a **Verification command** field. The auditor will run it. If you claim a C-item is closed without that command exiting clean, the audit fails and the work is rejected. There are no "should be passing" allowances.

---

## 2. Operating constraints (verbatim from `CLAUDE.md`)

These invariants are auto-loaded into every Claude Code session in this repo and **must be obeyed verbatim**. They are reproduced here so a fresh executor sees them without needing to read `CLAUDE.md` first.

```xml
<no_unverified_apis>
Before importing any non-stdlib library, verify the API exists:
- ADK / Vertex AI / Gemini: query context7 with the library ID
- Other Python: `python -c "import LIB; print(LIB.__version__)"` first
- npm: `npm view PKG version` first
- Google Cloud SDKs: cite official docs URL in a comment
If verification fails, do NOT write the import. Report the gap.
</no_unverified_apis>

<compile_then_commit>
No Python file commits without:
1. `mypy --strict path/to/file.py` exit 0
2. `python -c "import module.path"` exit 0
3. `pytest -x --no-header tests/path/test_file.py` exit 0
No TypeScript without `tsc --noEmit` exit 0.
No Markdown without `markdownlint` exit 0.
</compile_then_commit>

<no_speculation>
Never speculate about code you have not opened. If a file is referenced,
you MUST Read it before answering. Give grounded, hallucination-free
answers. If you don't know, say "I need to verify" and verify.
</no_speculation>

<eval_delta_required>
No commit ships without an eval-delta check. Code change:
`pytest tests/eval/ --baseline=HEAD~1` must show no regression.
Doc change: `markdownlint` + `markdown-link-check` must pass.
</eval_delta_required>

<no_test_driven_slop>
Write general-purpose solutions. No helper scripts to game tests.
No hard-coded values to pass tests. If a test is wrong, fix the test
(justified in commit message), not the code under test.
</no_test_driven_slop>

<no_silent_error_suppression>
Bare `except:`, `except Exception: pass`, and silent `try` blocks
are forbidden. Every caught exception must be logged with structured
context AND either re-raised, returned as a structured error, OR
have an explicit comment justifying the swallow.
</no_silent_error_suppression>

<json_state_files>
features.json, COST_LEDGER (json variant), and any other
agent-edited state file uses JSON not Markdown. Per Anthropic
2025 finding: Claude is less likely to silently rewrite JSON.
</json_state_files>

<no_destructive_git>
Forbidden without explicit human approval:
- git push --force / --force-with-lease
- git reset --hard
- git checkout -- .
- git clean -fd
- rm -rf any path under git control
- git branch -D for unmerged branches
Document the reason in the commit message if approved.
</no_destructive_git>

<lockfile_only_installs>
No ad-hoc `pip install LIB` or `npm install PKG`.
All deps via `pip install -r requirements.lock` or `npm ci`.
New dep: add to requirements.in or package.json, regenerate lock,
commit lock + verify Snyk scan, then install.
Defends against slopsquatting (LiteLLM Mar 2026 incident).
</lockfile_only_installs>

<wrap_dont_fork>
Atelier consumes upstream code via lockfile-pinned dependencies and
wraps it. Modifications to upstream packages (agent-dag-pipeline,
google-adk, hermes-agent) are out of scope.
</wrap_dont_fork>

<conventional_commits_required>
Every commit follows Conventional Commits 1.0.0:
  <type>(<scope>): <subject>
  <body>
  <footer>
Enforced by commitlint pre-commit hook.
</conventional_commits_required>

<wrap_phase_work_in_worktrees>
Per ADR 0007, all sprint work happens in .worktrees/phaseN-<name>/
on branch phase/N. Never commit directly to main except for merging
accepted phase branches and hotfixes.
</wrap_phase_work_in_worktrees>
```

**Additionally enforced:**

- No `--no-verify` ever (pre-commit hooks are part of the audit surface).
- No `force-push` without explicit human approval in commit-message footer.
- Reviewer subagent must emit a strict `"DONE"` token (Ralph Loop pattern) before any merge. Three `"REJECTED"` cycles = surface non-convergence to user.
- Daily checkpoint ritual mandatory — see `CLAUDE.md` Section "Daily checkpoint ritual".

---

## 3. Pre-flight checks (run BEFORE touching any C-item)

Run every command. **If any fails, stop and report the failure** before proceeding. The auditor's first re-audit step will be to re-run these — if they don't pass on your side, they certainly won't pass on the auditor's side.

```bash
# 3.1 Working directory verification
cd "/Users/danielmanzela/Professional Profile/Atelier/.worktrees/phase1-foundation"
pwd  # Must end in `.worktrees/phase1-foundation`
git rev-parse --abbrev-ref HEAD  # Must print `phase/1`
git status  # Must be clean (or note any deltas in handoff)

# 3.2 Worktree registration
git worktree list  # Must show phase1-foundation on phase/1

# 3.3 Toolchain
python --version  # Must be 3.11.x or 3.12.x (pyproject says <3.13)
ls .venv/bin/pytest  # Must exist
.venv/bin/pytest --version  # Must succeed
which terraform  # Must be present
which pre-commit  # Must be present

# 3.4 Baseline test suite (capture count — you will need to maintain or exceed it)
PYTHONPATH=atelier-core/src .venv/bin/pytest -q
# Expected: 87 passed (or higher). Record the exact number for your handoff.

# 3.5 Baseline mypy clean
cd atelier-core && ../.venv/bin/mypy --strict src/atelier/ && cd ..
# Expected: Success, no issues

# 3.6 Baseline pre-commit
pre-commit run --all-files
# Expected: All hooks pass (or note exact failing hook + file)

# 3.7 Confirm the four BigQuery production tables exist
bq ls -d --project_id=i-for-ai atelier_trajectories
# Expected: trajectory_records, dpo_preference_pairs, calibration_metrics, cost_ledger

# 3.8 Confirm the four sprint state files exist (even if stale)
ls -la docs/sprint/STATUS.md docs/sprint/BLOCKERS.md docs/sprint/CHECKPOINTS.md docs/sprint/COST_LEDGER.md
```

**If §3.4 shows < 87 tests passing, regression has occurred since the audit — investigate before proceeding.**

---

## 4. Remediation queue (C-items)

Each C-item below is structured identically:

- **ID, Priority, Effort**
- **Why** (rationale anchored to PRD/audit/CLAUDE.md)
- **Files** (exact paths to touch)
- **Acceptance criteria** (binary; the auditor will re-check each bullet)
- **Verification command** (the auditor will re-run this verbatim with fresh evidence)
- **Forbidden shortcuts** (common cheats the executor must NOT take)
- **Required handoff evidence** (what to include in `audit/executor-handoff.md` for this item)

---

### C1 — Reconcile `features.json` against actual `phase/1` git history

**Priority:** P0 | **Effort:** ~45 min | **Blocks:** Judges loop credibility, sprint health metric

**Why.** `CLAUDE.md` `<json_state_files>` invariant requires `features.json` to be authoritative agent-editable state. As of 2026-05-21, it reports `passes=1` despite ≥21 features shipped on `phase/1`. This breaks the daily ritual's `cat features.json | jq '.[] | select(.passes == false) | .id' | head -10` step — the orchestrator can't pick the next unblocked feature when the file lies about progress.

**Files.**

- `features.json` (root)
- Cross-reference: `git log phase/1 --oneline` and `.gemini/antigravity-ide/brain/e9962ddd-ddea-4979-a1d2-fa00102a9019/task.md`

**Acceptance criteria.**

- Every feature with status `passes=true` MUST have these fields populated:
  - `completed_at`: ISO 8601 timestamp (e.g., `"2026-05-21T09:58:00+05:30"`)
  - `evidence_commits`: array of commit SHAs (short form OK, e.g., `["9b70317", "a967567"]`)
  - `evidence_tests`: array of test file paths (e.g., `["tests/unit/test_model_registry.py"]`) — empty array `[]` if the feature is config-only (e.g., FA-005 agent_card.json)
- Minimum set that MUST be marked `passes=true` (verified shipped this session):
  - **F-series (10):** F0001a, F0001b, F0002, F0003, F0004, F0005, F0006, F0009, F0010, F0011
  - **FA-series (11):** FA-001, FA-002, FA-003, FA-005, FA-006, FA-007, FA-008, FA-009, FA-010, FA-015, FA-016
- If `features.json` lacks entries for any of the 21 features above, **add the entry** with full metadata.
- No feature may be marked `passes=true` without a corresponding entry in `git log phase/1 --oneline | grep -i <feature-id>` OR a justifying note in the entry's `evidence_notes` field.

**Verification command (auditor will re-run).**

```bash
# Expected output: count >= 21
jq '[.[] | select(.passes == true)] | length' features.json

# Expected output: empty (no passes=true without evidence)
jq '.[] | select(.passes == true) | select((.evidence_commits | length == 0) and (.evidence_notes == null))' features.json

# Expected output: empty (no required feature missing)
for f in F0001a F0001b F0002 F0003 F0004 F0005 F0006 F0009 F0010 F0011 FA-001 FA-002 FA-003 FA-005 FA-006 FA-007 FA-008 FA-009 FA-010 FA-015 FA-016; do
  jq -e --arg f "$f" '.[] | select(.id == $f and .passes == true)' features.json > /dev/null || echo "MISSING: $f"
done
```

**Forbidden shortcuts.**

- Marking `passes=true` for features you haven't verified.
- Setting `evidence_commits=[]` to silence the second check.
- Bulk-edit script that doesn't read commit history.
- Adding fake entries to pad the count.

**Required handoff evidence.**

- Diff of `features.json` (before/after).
- Output of the three verification commands above.
- Note any feature you marked `passes=false` despite the brain checklist saying complete — with rationale.

---

### C2 — Bring sprint state files current (D1 → D7 backlog)

**Priority:** P0 | **Effort:** ~30 min | **Blocks:** Daily checkpoint ritual (`CLAUDE.md` hard rule)

**Why.** `CLAUDE.md` "Daily checkpoint ritual" requires `STATUS.md`, `CHECKPOINTS.md`, `COST_LEDGER.md`, `BLOCKERS.md` to be updated at end-of-day. All four are frozen at 2026-05-14. The next session restoration ritual will see stale data and pick wrong next-tasks. This is one of seven "hard rules that don't bend" — leaving it broken on D7 is a discipline failure that compounds daily.

**Files.**

- `docs/sprint/STATUS.md`
- `docs/sprint/CHECKPOINTS.md`
- `docs/sprint/COST_LEDGER.md`
- `docs/sprint/BLOCKERS.md`

**Acceptance criteria.**

- `STATUS.md`: Top heading or top line reflects today's date `2026-05-21`. Body describes current state: what shipped D1-D7 (cite `features.json` IDs), what's blocked, what's next.
- `CHECKPOINTS.md`: Either daily entries for D1-D7 (preferred) OR one consolidated backfill entry titled `### 2026-05-21 D1-D7 Consolidated Backfill` with rationale ("daily entries lapsed; backfilled from git log + brain checklist") AND a `RESUME-HERE:` marker at the bottom pointing at the next unblocked feature.
- `COST_LEDGER.md`: At minimum, today's entry with cache-hit-rate (target ≥85% per `CLAUDE.md` ritual). If cache-hit-rate data is unavailable, note that explicitly.
- `BLOCKERS.md`: Either explicitly says "no current blockers" with today's date OR lists current blockers with owner + ETA per entry.
- All four files must end with a trailing newline (markdownlint MD047).
- All four files must pass `markdownlint` (no rule violations).

**Verification command (auditor will re-run).**

```bash
# Each file must contain today's date
for f in docs/sprint/STATUS.md docs/sprint/CHECKPOINTS.md docs/sprint/COST_LEDGER.md docs/sprint/BLOCKERS.md; do
  grep -q "2026-05-21" "$f" || echo "STALE: $f"
done
# Expected output: empty

# Markdownlint clean
pre-commit run markdownlint --files docs/sprint/STATUS.md docs/sprint/CHECKPOINTS.md docs/sprint/COST_LEDGER.md docs/sprint/BLOCKERS.md
# Expected: all files pass

# CHECKPOINTS.md must have a RESUME-HERE marker
grep -q "^RESUME-HERE:" docs/sprint/CHECKPOINTS.md || echo "MISSING resume marker"
# Expected output: empty
```

**Forbidden shortcuts.**

- Touching the file modification time only (`touch`) without content change.
- Copy-pasting D0 content with the date swapped — the body must reflect reality.
- Inventing cache-hit-rate numbers. If unknown, say so.

**Required handoff evidence.**

- Full text of each file after the update (or diff vs. previous version).
- Confirmation of markdownlint pass per file.

---

### C3 — Create `consensus/axis_weights_heuristic.yaml` (N15 / MJG / FA-019)

**Priority:** P0 | **Effort:** ~30 min | **Blocks:** ConsensusAgent (N3d) skeleton

**Why.** `brief_spec.py:L119` references `consensus/axis_weights_heuristic.yaml` as the source for axis-weight resolution. The file does not exist. When the ConsensusAgent skeleton is written in the next wave (F0029–F0040), it will fail to load weights. This is a foundation contract that must precede agent code, per the deterministic-gate-first architecture. FA-019 (Conditional Axis Weighting per ADR 0013) and N15 (Multi-Judge Bayesian governance per ADR 0008) both consume this file.

**Files.**

- `consensus/axis_weights_heuristic.yaml` (new file)

**Acceptance criteria.**

- File is valid YAML 1.2 (`python -c "import yaml; yaml.safe_load(open('consensus/axis_weights_heuristic.yaml'))"` exits 0).
- File MUST encode at minimum:
  - `version`: schema version string (e.g., `"1.0"`)
  - `surface_types`: a mapping of surface type → axis weight dict. At minimum these surface types: `landing_page`, `pricing`, `checkout`, `onboarding`, `dashboard`, `marketing_email`, `default`.
  - Each axis weight dict MUST contain the 5 D-O-R-A-V keys: `brand`, `originality`, `relevance`, `accessibility`, `visual_clarity` — values floats in `[0.0, 1.0]` summing to `1.0 ± 0.01`.
  - `prior_strength`: Bayesian prior strength scalar (recommended `2.0`–`8.0` per ADR 0008).
  - `uncertainty_floor`: minimum residual uncertainty after consensus (recommended `0.05`).
- File MUST include a top header comment block (5+ lines) citing: PRD §15 or §19 (whichever defines MJG), ADR 0008, ADR 0013, FA-019, N15.
- File MUST NOT contain any TODO/FIXME/XXX markers — incomplete sections are not acceptable for a foundation contract.

**Verification command (auditor will re-run).**

```bash
# Valid YAML and required structure
python -c "
import yaml
data = yaml.safe_load(open('consensus/axis_weights_heuristic.yaml'))
assert 'version' in data, 'missing version'
assert 'surface_types' in data, 'missing surface_types'
assert 'prior_strength' in data, 'missing prior_strength'
assert 'uncertainty_floor' in data, 'missing uncertainty_floor'
required_surfaces = {'landing_page','pricing','checkout','onboarding','dashboard','marketing_email','default'}
assert required_surfaces.issubset(data['surface_types'].keys()), f'missing surfaces: {required_surfaces - set(data[\"surface_types\"].keys())}'
required_axes = {'brand','originality','relevance','accessibility','visual_clarity'}
for s, w in data['surface_types'].items():
    assert required_axes == set(w.keys()), f'{s} axis keys wrong: {set(w.keys())}'
    total = sum(w.values())
    assert abs(total - 1.0) < 0.01, f'{s} weights sum {total} != 1.0'
print('PASS')
"
# Expected: PASS

# Header citations present
grep -E "PRD|ADR 0008|ADR 0013|FA-019|N15" consensus/axis_weights_heuristic.yaml | head -10
# Expected: multiple matches

# No TODO markers
grep -E "TODO|FIXME|XXX" consensus/axis_weights_heuristic.yaml && echo "FAIL: incomplete markers" || echo "PASS"
# Expected: PASS
```

**Forbidden shortcuts.**

- Stub file with one surface type ("we'll add the others later").
- Equal weights `0.2, 0.2, 0.2, 0.2, 0.2` for every surface — that defeats the whole point of conditional weighting (it'd be the unconditional baseline).
- Using floats that don't sum to 1.0.
- Omitting the header citations.

**Required handoff evidence.**

- Full file content in the handoff report.
- Output of the verification command.
- 2-sentence rationale for the weight choices (why `accessibility=0.30` on `checkout` and not `0.20`, etc.).

---

### C4 — Create `consensus/research-trust.yaml` (N14 / WRAI / FA-020)

**Priority:** P0 | **Effort:** ~45 min | **Blocks:** Relevance judge grounding, WRAI agent (when implemented)

**Why.** ADR 0011 (Web-Research-Augmented Intake) and `brief_spec.py:L119` both reference a domain trust lattice for the Relevance judge and the future N14 WRAI node. Without it, the Relevance judge has no way to score citations against trust tiers — every claim becomes equally credible, defeating the grounded-research design. This is the data contract that must exist before any WRAI agent code is written.

**Files.**

- `consensus/research-trust.yaml` (new file)

**Acceptance criteria.**

- File is valid YAML 1.2.
- File MUST encode:
  - `version`: schema version string
  - `default_trust`: float in `[0.0, 1.0]` for domains not explicitly listed (recommended `0.3`)
  - `tiers`: ordered list of named trust tiers, each with:
    - `name`: string identifier (e.g., `"primary_design_authority"`, `"vetted_journalism"`, `"community"`)
    - `trust_score`: float `[0.0, 1.0]`
    - `domains`: array of domain glob patterns (e.g., `"*.gov"`, `"dribbble.com"`, `"behance.net"`)
    - `citation_required`: bool (true means any factual claim sourced here must include an inline citation)
    - `refresh_days`: int (max cached lifetime of a fetched page)
  - `banned`: array of domain patterns to never fetch (e.g., known spam, content farms)
- At minimum these tiers must be present:
  - **Primary design authority** (Apple HIG, Material, NN/g, dribbble, behance, awwwards) — trust ≥ 0.85
  - **Vetted journalism** (nytimes.com, wsj.com, reuters.com, ft.com) — trust ≥ 0.80
  - **Technical reference** (mdn.io, web.dev, _.gov, _.edu) — trust ≥ 0.85
  - **Vendor docs** (cloud.google.com, developer.apple.com, react.dev) — trust ≥ 0.75
  - **Community** (stackoverflow.com, reddit.com, github.com) — trust ≥ 0.50
  - **General web** (default) — trust ≥ 0.30
- Header comment must cite: ADR 0011, FA-020, N14.

**Verification command (auditor will re-run).**

```bash
python -c "
import yaml
data = yaml.safe_load(open('consensus/research-trust.yaml'))
assert 'version' in data and 'default_trust' in data and 'tiers' in data and 'banned' in data
tier_names = {t['name'] for t in data['tiers']}
print('Tiers:', tier_names)
for t in data['tiers']:
    assert 0.0 <= t['trust_score'] <= 1.0
    assert isinstance(t['domains'], list) and len(t['domains']) > 0
    assert 'citation_required' in t
    assert isinstance(t['refresh_days'], int)
assert len(data['tiers']) >= 6, f'need >=6 tiers, got {len(data[\"tiers\"])}'
print('PASS')
"
# Expected: PASS with at least 6 tier names printed

grep -E "ADR 0011|FA-020|N14" consensus/research-trust.yaml | head -5
# Expected: at least 3 matches
```

**Forbidden shortcuts.**

- Single-tier file ("trust all https sources").
- Empty `banned` list (at minimum: known content farms; cite OpenAI/Anthropic crawler lists as starting point).
- Trust scores that all collapse to one value.

**Required handoff evidence.**

- Full file content.
- Verification command output.
- Citation of the source used to seed the banned list (e.g., common-crawl spam classifier, your own judgment with rationale).

---

### C5 — Implement FA-004 GitHub MCP wrapper

**Priority:** P1 | **Effort:** ~90 min | **Blocks:** WRAI reference-repo lookup (Phase 2)

**Why.** The audit identifies FA-004 (GitHub MCP integration) as required for Atelier's autonomous research flow — the agent needs to look up reference repos, READMEs, and code samples during the PIP intake phase. This is the **server-side wrapper Atelier exposes** (not the developer-time MCP server already available in the Claude Code session). It must mirror the architecture of `src/atelier/integrations/stitch_mcp.py` (which is the proven pattern for FA-003).

**Files.**

- `atelier-core/src/atelier/integrations/github_mcp.py` (new file, ~150 LOC)
- `atelier-core/tests/unit/test_github_mcp.py` (new file, 6+ tests)
- Possibly: `requirements.in` + `requirements.lock` if a new dep is needed (see Forbidden shortcuts).

**Acceptance criteria.**

- File `atelier-core/src/atelier/integrations/github_mcp.py` exists.
- File mirrors the `stitch_mcp.py` class structure (read it first; do not invent a new pattern).
- Exposes at minimum:
  - `class GitHubMCPClient` with `__init__(self, token: str, *, base_url: str = "https://api.github.com") -> None`
  - `async def fetch_readme(self, owner: str, repo: str) -> str`
  - `async def search_code(self, query: str, *, language: str | None = None, limit: int = 10) -> list[CodeSearchResult]`
  - `async def fetch_file(self, owner: str, repo: str, path: str, ref: str = "HEAD") -> str`
  - `class CodeSearchResult` Pydantic model with at least: `repo: str, path: str, snippet: str, score: float`
- All errors caught MUST follow `<no_silent_error_suppression>`:
  - HTTP 4xx → raise `GitHubMCPError` with structured context
  - HTTP 5xx → retry with bounded backoff (3 attempts max per the failure-trichotomy `self-heal` policy), then raise
  - HTTP 401/403 → raise `GitHubMCPError(reason="auth")` (no silent swallow)
- All public methods have full type hints; `mypy --strict` clean.
- Token MUST be read from env var `GITHUB_TOKEN` (or constructor arg) — never hardcoded.
- Test file `test_github_mcp.py` MUST include:
  - Test for successful README fetch (mocked response)
  - Test for 404 (raises `GitHubMCPError`)
  - Test for 5xx retry behavior (succeeds on retry)
  - Test for auth failure (raises with `reason="auth"`)
  - Test for rate-limit handling (X-RateLimit-Remaining=0 → backoff)
  - Test for token-from-env fallback

**Verification command (auditor will re-run).**

```bash
# File exists and imports
python -c "from atelier.integrations.github_mcp import GitHubMCPClient, GitHubMCPError, CodeSearchResult; print('OK')"
# Expected: OK

# mypy strict clean
cd atelier-core && ../.venv/bin/mypy --strict src/atelier/integrations/github_mcp.py && cd ..
# Expected: Success, no issues

# Tests pass
PYTHONPATH=atelier-core/src .venv/bin/pytest -v atelier-core/tests/unit/test_github_mcp.py
# Expected: >= 6 passed

# Test count delta — total suite must grow by >= 6
PYTHONPATH=atelier-core/src .venv/bin/pytest -q | tail -3
# Expected: >= 93 passed (was 87, +6 minimum from C5)

# No silent excepts (no `pass` after `except`)
grep -nE "except[^:]*:\s*$" atelier-core/src/atelier/integrations/github_mcp.py | grep -v "^[^:]*:[^:]*:#" && echo "FAIL: silent except" || echo "PASS"
# Expected: PASS

# Token not hardcoded
grep -E "ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,}" atelier-core/src/atelier/integrations/github_mcp.py && echo "FAIL: hardcoded token" || echo "PASS"
# Expected: PASS
```

**Forbidden shortcuts.**

- Using a new PyPI package without ADR + lockfile regen. **Use `httpx`** (already in deps) for HTTP. Do NOT add `PyGithub` or `gidgethub` without an ADR.
- Synchronous methods only — must be `async def` to match the agent loop.
- Returning raw dicts instead of typed Pydantic models.
- Skipping the rate-limit test ("GitHub will probably never rate-limit us").
- Catching `Exception` broadly — narrow it to `httpx.HTTPError` etc.
- Pre-commit hook scrub: do NOT commit a real token, even temporarily. `detect-secrets` will catch this and fail your commit.

**Required handoff evidence.**

- File content (or large diff snippet).
- Test output showing 6+ tests passing.
- mypy output showing 0 errors.
- Output of the silent-except and hardcoded-token greps.

---

### C6 — Implement FA-011 `TrajectoryRecorder` class

**Priority:** P1 | **Effort:** ~75 min | **Blocks:** DPO Flywheel data collection, Phase-2 RLRD pipeline

**Why.** The `TrajectoryRecord` Pydantic schema is locked at `atelier-core/src/atelier/contracts/data_contracts.py:L308`. The BigQuery table `i-for-ai.atelier_trajectories.trajectory_records` is live with the matching schema. The **writer class is absent** — nothing is emitting records to BigQuery. The DPO Flywheel (FA-011 through FA-014, Phase 2) requires this data to be flowing from D8 onward, so the writer must be in place before Phase 2 begins.

**Files.**

- `atelier-core/src/atelier/recorders/__init__.py` (new dir + file)
- `atelier-core/src/atelier/recorders/trajectory_recorder.py` (new file, ~100 LOC)
- `atelier-core/tests/unit/test_trajectory_recorder.py` (new file, 5+ tests using BigQuery mock; do NOT hit real BQ in unit tests)

**Acceptance criteria.**

- Class `TrajectoryRecorder` exposes:
  - `__init__(self, *, project_id: str, dataset: str = "atelier_trajectories", table: str = "trajectory_records", batch_size: int = 100, flush_interval_s: float = 5.0)`
  - `async def record(self, trajectory: TrajectoryRecord) -> None` — buffers, returns immediately
  - `async def flush(self) -> int` — forces buffer flush, returns count written
  - `async def __aenter__` / `__aexit__` for context-manager usage with auto-flush
- Must use `google-cloud-bigquery` (already in deps — verify with `pip show google-cloud-bigquery`).
- Must use `tabledata.insertAll` streaming API (NOT load jobs — wrong semantics for trajectory streaming).
- Must populate OTel span attributes per `src/atelier/observability/spans.py`:
  - When recording, emit a span `atelier.recorder.flush` with `gen_ai.system="atelier"`, `atelier.node_name="trajectory_recorder"`, and the row count as a span attribute.
- Idempotency: use `insertId` parameter (BQ-native dedup window 1 minute) — generate from `trajectory.trace_id + trajectory.candidate_id`.
- Failure-trichotomy compliance:
  - `fail-soft` if BigQuery returns a partial failure (some rows accepted, some rejected) — log structured warning, return count of successes, do NOT raise.
  - `self-heal` for transient 503/429 — retry with exponential backoff (max 3) inside `flush()`.
  - `fail-loud` for auth/quota errors — raise `TrajectoryRecorderError` with structured context.
- Tests:
  - Successful buffer + flush (mock BigQuery client returns empty errors list).
  - Partial failure (BigQuery returns some errors → log + return success count).
  - Auth failure → raises.
  - Auto-flush at `batch_size` boundary.
  - Context-manager auto-flush on `__aexit__`.

**Verification command (auditor will re-run).**

```bash
# Imports
python -c "from atelier.recorders.trajectory_recorder import TrajectoryRecorder, TrajectoryRecorderError; print('OK')"
# Expected: OK

# mypy strict
cd atelier-core && ../.venv/bin/mypy --strict src/atelier/recorders/ && cd ..

# Tests
PYTHONPATH=atelier-core/src .venv/bin/pytest -v atelier-core/tests/unit/test_trajectory_recorder.py
# Expected: >= 5 passed

# Verify uses streaming insert (not load jobs)
grep -E "insertAll|insert_rows" atelier-core/src/atelier/recorders/trajectory_recorder.py
# Expected: at least 1 match

# Verify NOT using load jobs (would be wrong)
grep "LoadJob\|load_table_from" atelier-core/src/atelier/recorders/trajectory_recorder.py && echo "FAIL: load jobs forbidden for streaming" || echo "PASS"
# Expected: PASS

# OTel span emitted
grep -E "start_as_current_span.*atelier\.recorder" atelier-core/src/atelier/recorders/trajectory_recorder.py
# Expected: at least 1 match
```

**Forbidden shortcuts.**

- Using BigQuery load jobs (wrong semantics for streaming).
- Hitting real BigQuery in unit tests (use `unittest.mock` / mock the client).
- Skipping `insertId` (no dedup = duplicate rows on retry).
- Synchronous flush (blocks the event loop).
- Bare `except` around BQ calls.

**Required handoff evidence.**

- File content.
- Test output showing 5+ tests passing.
- mypy clean output.
- Total test count delta (auditor expects ≥ 92 if C5 also done; ≥ 98 if both C5+C6 done).

---

### C7 — ADR 0014 documenting model registry deviation from PRD

**Priority:** P1 | **Effort:** ~30 min | **Blocks:** Audit acceptance of model choices

**Why.** `model_registry.py` pins `gemini-2.5-flash-preview-05-20` for the generator and most judges. PRD §6.3 and §7 (FA-016) reference `gemini-3-flash`. This is a substantive deviation that touches every node's behavior. `CLAUDE.md` requires that "mid-sprint changes to the PRD require an explicit ADR commit, not silent drift." The deviation has happened — the ADR must follow before the audit accepts the codebase.

**Files.**

- `docs/decisions/0014-model-registry-gemini-2-5-flash-pin.md` (new file)

**Acceptance criteria.**

- File follows the existing ADR template in `docs/decisions/0001-*.md` through `0013-*.md` (read at least 2 existing ADRs first to match style).
- Required sections (h2): `## Context`, `## Decision`, `## Consequences`, `## Alternatives Considered`, `## Status`.
- `## Status` must be `Accepted` (with today's date 2026-05-21) OR `Proposed` (if you want the user to ratify).
- Must reference: PRD §6.3, PRD §7 (FA-016), `model_registry.py:L84` (or whatever line you find the first deviation on).
- Must explain WHY the deviation happened. Acceptable rationales (use the truthful one):
  1. `gemini-3-flash` GA timeline slipped relative to PRD writing.
  2. `gemini-2.5-flash-preview-05-20` is the highest-capability stable variant available via Vertex AI at the time of D1.
  3. The model registry is configured to allow drop-in swap when `gemini-3-flash` GAs (verify this is actually true in code; if not, file a sub-task).
- Must include a migration plan: under what condition the registry will be re-pinned to `gemini-3-flash` (e.g., "when GA'd on Vertex AI us-central1, run the calibration golden set; if pass rate within 2pp of the 2.5 baseline, swap").
- Must update `DECISIONS.md` at repo root to include a line linking to ADR 0014.

**Verification command (auditor will re-run).**

```bash
# File exists with required sections
test -f docs/decisions/0014-model-registry-gemini-2-5-flash-pin.md
for section in "## Context" "## Decision" "## Consequences" "## Alternatives Considered" "## Status"; do
  grep -q "$section" docs/decisions/0014-model-registry-gemini-2-5-flash-pin.md || echo "MISSING: $section"
done

# Status set to Accepted or Proposed
grep -E "^## Status$" -A 2 docs/decisions/0014-model-registry-gemini-2-5-flash-pin.md | grep -E "Accepted|Proposed"

# DECISIONS.md updated
grep -q "0014" DECISIONS.md || echo "MISSING: DECISIONS.md not updated"

# Markdown lints clean
pre-commit run markdownlint --files docs/decisions/0014-model-registry-gemini-2-5-flash-pin.md DECISIONS.md
```

**Forbidden shortcuts.**

- "Will write ADR later" placeholder.
- ADR that says "we deviated because we wanted to" — must cite a substantive constraint.
- Skipping `DECISIONS.md` update.
- Marking Status as `Deprecated` or `Superseded` (those imply something newer; that's not the case here).

**Required handoff evidence.**

- Full ADR content.
- Diff of `DECISIONS.md`.
- Output of all verification commands.

---

### C8 — Wire OTel collector `googlecloud` exporter for production

**Priority:** P1 | **Effort:** ~30 min | **Blocks:** Cloud Trace ingestion, production observability

**Why.** `config/otel-collector-config.yaml` has the Phoenix exporter (dev-mode) configured correctly per G8 in the audit, but the `googlecloud` exporter for production Cloud Trace is commented out. ADR 0006 (Google-native observability) mandates Cloud Trace as the production sink. Without this, any spans emitted from Cloud Run staging will be dropped, breaking the calibration-dashboard ingestion path scheduled for Phase 3.

**Files.**

- `config/otel-collector-config.yaml`
- Possibly: `terraform/otel-collector.tf` (if a new IAM binding is needed for the collector SA)

**Acceptance criteria.**

- `googlecloud` exporter is uncommented in `exporters:` block.
- Has `project: i-for-ai` set (or read from env var `GCP_PROJECT_ID` with default).
- Trace pipeline `service.pipelines.traces.exporters` includes both `phoenix` (dev) AND `googlecloud` (prod) — gated by env var or service-name routing.
- Metrics pipeline similarly wired (Cloud Monitoring).
- Sampling config: tail-based sampling (errors + slow spans always kept, success spans sampled at 10% per ADR 0006).
- File passes a syntactic validation:
  - YAML is valid.
  - The collector can dry-run-parse the config — `otelcol --config=config/otel-collector-config.yaml --dry-run` exits 0 if the collector binary is available; otherwise document that it wasn't available and the YAML parse alone passed.
- The SA used by the collector must have `roles/cloudtrace.agent` and `roles/monitoring.metricWriter` — verify via gcloud IAM listing (note: if the SA doesn't exist yet, file a follow-up but at minimum document the requirement in a comment in the YAML).

**Verification command (auditor will re-run).**

```bash
# YAML is valid
python -c "import yaml; yaml.safe_load(open('config/otel-collector-config.yaml'))"
# Expected: no exception

# googlecloud exporter present
grep -E "^\s+googlecloud:" config/otel-collector-config.yaml
# Expected: at least 1 match

# googlecloud listed in trace pipeline
python -c "
import yaml
c = yaml.safe_load(open('config/otel-collector-config.yaml'))
traces = c['service']['pipelines']['traces']['exporters']
assert 'googlecloud' in traces, f'googlecloud not in trace exporters: {traces}'
print('PASS')
"
# Expected: PASS

# No commented-out exporter lines (those are dangerous)
grep -E "^#.*googlecloud" config/otel-collector-config.yaml && echo "WARN: googlecloud still has commented lines" || echo "PASS"
```

**Forbidden shortcuts.**

- Keeping the line commented but adding a TODO.
- Sending 100% of spans to Cloud Trace (cost blowup — must implement tail sampling).
- Hardcoding `project: my-project-id`. Must be `i-for-ai` or env-var.

**Required handoff evidence.**

- Diff of `config/otel-collector-config.yaml`.
- Output of the verification commands.
- If you added IAM, note the SA name + roles.

---

### C9 — CI workflow triggers on `phase/1`

**Priority:** P1 | **Effort:** ~20 min | **Blocks:** Continuous integration confidence

**Why.** `gh run list --branch phase/1` returns empty as of this audit despite the branch having ~10 commits. Either the workflows aren't configured to trigger on `phase/*` branches or there's a syntax issue in the `on:` block. Phase work must have CI feedback within ~5 minutes of each push, per `CLAUDE.md` discipline.

**Files.**

- `.github/workflows/*.yml` (all workflow files)

**Acceptance criteria.**

- Every workflow that runs tests/lints must include `phase/*` (or `phase/**`) in its `on.push.branches` and `on.pull_request.branches` arrays.
- Format example (do NOT just paste — read the file first):
  ```yaml
  on:
    push:
      branches: [main, 'phase/*']
    pull_request:
      branches: [main, 'phase/*']
  ```
- After updating, push an empty commit to `phase/1` and verify a run appears:
  ```bash
  git commit --allow-empty -m "ci(test): trigger CI on phase/1"
  git push origin phase/1
  sleep 30
  gh run list --branch phase/1 --limit 3
  ```
  Must show a run started within 60 seconds of push.
- The triggered run must complete successfully (exit conclusion `success`).

**Verification command (auditor will re-run).**

```bash
# Workflows reference phase/*
for wf in .github/workflows/*.yml; do
  grep -qE "phase/\*" "$wf" || echo "MISSING: $wf does not include phase/* trigger"
done
# Expected: empty output (or note workflow-by-workflow which are intentionally main-only)

# Latest run on phase/1 exists and succeeded
gh run list --branch phase/1 --limit 1 --json status,conclusion,databaseId
# Expected: a JSON entry with conclusion="success" (or in_progress)
```

**Forbidden shortcuts.**

- Adding the trigger to one workflow and not the others.
- Disabling workflows ("we'll re-enable on main merge").
- Using `[**]` as branch filter (too broad — could trigger on accident).

**Required handoff evidence.**

- Diff of each workflow file changed.
- Output of `gh run list --branch phase/1 --limit 3`.
- The commit SHA + run URL of the triggered CI run.

---

### C10 — Resolve ruff version drift + auto-fix C420

**Priority:** P2 | **Effort:** ~15 min | **Blocks:** Pre-commit hook trust

**Why.** Pre-commit pins `ruff` v0.6.9 (`.pre-commit-config.yaml`), but the venv has v0.15.13. The newer version finds 1 C420 violation in `atelier-core/tests/unit/test_model_registry.py:82` (dict-comprehension can be `dict.fromkeys`). The pinned hook misses it. Either:

- Bump the pin and fix the finding (preferred — newer ruff = stricter checks), or
- Bump the venv down (reverses the audit improvement; rejected).

**Files.**

- `.pre-commit-config.yaml`
- `atelier-core/tests/unit/test_model_registry.py:82`

**Acceptance criteria.**

- `.pre-commit-config.yaml` `ruff` rev bumped to latest stable on PyPI (verify with `pip index versions ruff` or `npm view` equivalent — at time of writing 0.15.x is current).
- `ruff check atelier-core/` reports 0 violations.
- `ruff format atelier-core/` reports 0 changes needed (run with `--check`).
- Run `pre-commit autoupdate` for OTHER hooks too — confirm any hook updated/no-changed is intentional. If any hook bump introduces new findings, fix them in the same commit.

**Verification command (auditor will re-run).**

```bash
# Pinned version is current
grep -E "rev:.*ruff" .pre-commit-config.yaml
# Expected: rev pointing at 0.15.x or later

# ruff check clean
.venv/bin/ruff check atelier-core/
# Expected: All checks passed.

# ruff format clean
.venv/bin/ruff format --check atelier-core/
# Expected: No changes needed.

# pre-commit run-all clean
pre-commit run --all-files
# Expected: all hooks pass
```

**Forbidden shortcuts.**

- Adding `# noqa: C420` to the test file.
- Pinning ruff to an older version that missed the finding (regression).
- Skipping `pre-commit autoupdate` and only bumping ruff.

**Required handoff evidence.**

- Diff of `.pre-commit-config.yaml`.
- Diff of `test_model_registry.py`.
- Output of the three ruff/pre-commit commands.

---

### C11 — Add `[tool.pytest.ini_options].pythonpath` to `pyproject.toml`

**Priority:** P2 | **Effort:** ~10 min | **Blocks:** Fresh-clone developer experience

**Why.** The audit found that pytest only runs cleanly when launched with `PYTHONPATH=atelier-core/src .venv/bin/pytest`. A fresh clone hitting `pytest` will fail with `ModuleNotFoundError`. This is a friction point that bites every new collaborator and every CI runner that doesn't manually set PYTHONPATH.

**Files.**

- `pyproject.toml` (root) — OR `atelier-core/pyproject.toml` depending on test discovery layout. Read both first.

**Acceptance criteria.**

- After change, `cd <worktree-root> && .venv/bin/pytest` works with no env-var preamble.
- Add (in the appropriate `pyproject.toml`):
  ```toml
  [tool.pytest.ini_options]
  pythonpath = ["atelier-core/src"]
  testpaths = ["atelier-core/tests"]
  addopts = "-q --strict-markers --strict-config"
  ```
  (Adjust pythonpath if `atelier-core/` is laid out differently — read the file first.)
- The change must not cause any existing test to fail.

**Verification command (auditor will re-run).**

```bash
# Run WITHOUT PYTHONPATH override
.venv/bin/pytest -q
# Expected: same or higher test count as baseline (87+)

# Configuration present
grep -A 3 "tool.pytest.ini_options" pyproject.toml atelier-core/pyproject.toml 2>/dev/null
# Expected: pythonpath block visible
```

**Forbidden shortcuts.**

- Adding a `conftest.py` at root that does `sys.path.insert` (works but is the wrong fix; pyproject is the canonical location).
- Setting `pythonpath = ["."]` (too broad).

**Required handoff evidence.**

- Diff of the touched `pyproject.toml`.
- Output of `.venv/bin/pytest -q` without PYTHONPATH.

---

### C12 — Update stale "75/75" references in docs

**Priority:** P2 | **Effort:** ~10 min | **Blocks:** Audit signal integrity

**Why.** Multiple docs (sprint state, brain checklist, README sections) claim "75/75 tests passing." After C5+C6, the count will be ≥98. Stale numbers in docs make every future audit waste time confirming whether the doc lags the code or the code regressed.

**Files.**

- Any file containing `75/75` or `75 tests` or similar.

**Acceptance criteria.**

- `grep -r "75/75" docs/ README.md atelier-core/README.md 2>/dev/null` returns empty.
- Where the number is replaced, use the **actual current count** at time of replacement (run `.venv/bin/pytest -q | tail -1` first).
- Bonus: replace the literal count with a reference to the live counter where possible, e.g., "see CI status badge" rather than a number that will rot again.

**Verification command (auditor will re-run).**

```bash
grep -rn "75/75\|75 tests" docs/ README.md atelier-core/README.md 2>/dev/null
# Expected: empty

# The replacement number matches reality
ACTUAL=$(PYTHONPATH=atelier-core/src .venv/bin/pytest -q 2>/dev/null | grep -oE "[0-9]+ passed" | head -1 | grep -oE "[0-9]+")
echo "Actual test count: $ACTUAL"
# Then spot-check that the docs reference this number (or a badge link).
```

**Forbidden shortcuts.**

- `sed -i 's|75/75|99/99|g'` without verifying the actual count.
- Removing the test-count claim entirely just to silence the grep (loses information value).

**Required handoff evidence.**

- List of files touched with the old/new substring per file.
- Output of the grep command.

---

### C13 — Populate `consensus/constitution-apple-grade/`

**Priority:** P2 | **Effort:** ~60 min | **Blocks:** Brand judge calibration depth

**Why.** Directory exists but is empty. The consensus directory spec (brain checklist Part 4 §6) calls for an Apple-grade design constitution: distilled principles from Apple HIG + Material Design + NN/g, with worked examples per principle. Without it, the Brand judge has only `DESIGN_PRINCIPLES_APPLE.md` (1.7KB) to anchor on — insufficient for the calibration golden set.

**Files.**

- `consensus/constitution-apple-grade/index.json` (new file — manifest)
- `consensus/constitution-apple-grade/00-clarity.md`
- `consensus/constitution-apple-grade/01-deference.md`
- `consensus/constitution-apple-grade/02-depth.md`
- `consensus/constitution-apple-grade/03-direct-manipulation.md`
- `consensus/constitution-apple-grade/04-feedback.md`
- (Optional, recommended) 5+ more files covering: consistency, user-control, aesthetic-integrity, metaphors, error-prevention.

**Acceptance criteria.**

- `index.json` is valid JSON with structure:
  ```json
  {
    "version": "1.0",
    "principles": [
      {"id": "00-clarity", "title": "Clarity", "file": "00-clarity.md", "weight": 0.20, "anchors": ["Apple HIG §1.1", "NN/g #1"]},
      ...
    ]
  }
  ```
- Each principle file (md) MUST contain:
  - Title (h1)
  - 1-paragraph definition citing the source (Apple HIG / Material / NN/g)
  - 3 "do" examples (with brief rationale)
  - 3 "don't" examples (with brief rationale)
  - 1 "edge case" section (when this principle conflicts with another, how to resolve)
- Sum of `weight` across principles in `index.json` MUST equal `1.0 ± 0.01`.
- All files pass `markdownlint`.
- Each citation must reference a real, verifiable section (do NOT invent HIG section numbers).

**Verification command (auditor will re-run).**

```bash
# Index is valid JSON with right structure
python -c "
import json, pathlib
data = json.load(open('consensus/constitution-apple-grade/index.json'))
assert 'principles' in data
total = sum(p['weight'] for p in data['principles'])
assert abs(total - 1.0) < 0.01, f'weights sum {total}'
for p in data['principles']:
    f = pathlib.Path('consensus/constitution-apple-grade') / p['file']
    assert f.exists(), f'missing {f}'
print('PASS')
"

# At least 5 principle files
ls consensus/constitution-apple-grade/*.md | wc -l
# Expected: >= 5

# Markdownlint
pre-commit run markdownlint --files consensus/constitution-apple-grade/*.md
```

**Forbidden shortcuts.**

- Inventing principle names not anchored to a published source.
- Lorem ipsum / placeholder content.
- 5 files with identical structure but different titles (must be substantively different).
- Skipping the "don't" examples — those are what the judge uses for rejection scoring.

**Required handoff evidence.**

- List of files created.
- `index.json` content.
- Markdownlint output.

---

### C14 — Verify Phoenix dev-mode flag is documented in onboarding

**Priority:** P2 | **Effort:** ~10 min | **Blocks:** Future-contributor confusion

**Why.** ADR 0006 mandates Phoenix is dev-only. The OTel collector config correctly routes Phoenix to dev pipeline. But no onboarding/README documents the env-var or flag that switches between dev and prod. New contributors will hit it via trial-and-error.

**Files.**

- `README.md` OR `docs/development.md` OR `atelier-core/README.md` (pick one; document in the most discoverable place).

**Acceptance criteria.**

- A section titled `## Local development observability` (or similar) exists with:
  - The env var name (e.g., `ATELIER_OBSERVABILITY_MODE=dev|prod`)
  - How to start Phoenix locally (Docker compose, port, etc.)
  - Why Phoenix is dev-only (cite ADR 0006).
- The section is linked from the root README's "Getting started" section if it lives elsewhere.

**Verification command (auditor will re-run).**

```bash
grep -E "ATELIER_OBSERVABILITY_MODE|phoenix" -r README.md docs/ atelier-core/README.md 2>/dev/null | head -5
# Expected: at least 1 match in a README/docs file
```

**Forbidden shortcuts.**

- Documentation that says "see the code" — must be self-contained.
- Hiding the doc in a deeply nested file.

**Required handoff evidence.**

- Filename + diff.

---

### C15 — Update STATUS.md "Next session first task" pointer

**Priority:** P2 | **Effort:** ~5 min (last step of session, after C1-C14 done) | **Blocks:** Next session restoration ritual

**Why.** `CLAUDE.md` daily ritual step 6: "Note tomorrow's first task in `docs/sprint/STATUS.md`." After remediation, the next session should know exactly where to pick up — likely Phase 1 next-wave items (F0023+ from the brain checklist).

**Files.**

- `docs/sprint/STATUS.md`

**Acceptance criteria.**

- File ends with a clearly delimited section:

  ```markdown
  ## Next session first task

  <one-line description of next unblocked feature, with its ID>

  Suggested model tier: <implementer-routine | implementer-novel | planner>
  Dependencies satisfied: yes
  ```

- The feature ID must exist in `features.json` with `passes=false`.

**Verification command (auditor will re-run).**

```bash
grep -A 4 "## Next session first task" docs/sprint/STATUS.md
# Expected: the section with a real feature ID

# That feature exists and is open
NEXT=$(grep -A 2 "## Next session first task" docs/sprint/STATUS.md | tail -1 | grep -oE "F[A0-9-]+")
jq --arg id "$NEXT" '.[] | select(.id == $id and .passes == false)' features.json
# Expected: a JSON object printed (not empty)
```

**Forbidden shortcuts.**

- "TBD" or "decide tomorrow."
- Pointing at a feature already passed.

**Required handoff evidence.**

- The "Next session first task" section content.

---

## 5. Dependencies and order of operations

Execute roughly in this order. Items in the same level may parallelize.

```
Level 1 (must run first, sequential):
  ├─ Pre-flight §3 (gate)
  ├─ C2 (sprint state baseline — other commits depend on STATUS.md being recent)

Level 2 (P0, can parallelize):
  ├─ C1 (features.json reconcile)
  ├─ C3 (axis_weights yaml)
  ├─ C4 (research-trust yaml)

Level 3 (P1, can parallelize among themselves):
  ├─ C5 (GitHub MCP) — new code, new tests
  ├─ C6 (TrajectoryRecorder) — new code, new tests
  ├─ C7 (ADR 0014) — docs only
  ├─ C8 (OTel exporter) — config only
  ├─ C9 (CI triggers) — must come last in this level so it can verify the run

Level 4 (P2, can parallelize):
  ├─ C10 (ruff bump)
  ├─ C11 (pytest pythonpath)
  ├─ C12 (stale 75/75 refs)
  ├─ C13 (constitution dir)
  ├─ C14 (Phoenix dev-mode doc)

Level 5 (must run last):
  └─ C15 (next-session pointer in STATUS.md)
```

**Subagent dispatch suggestion** (per `CLAUDE.md` Subagent dispatch defaults):

- Use **implementer-routine (Sonnet 4.6)** for: C2, C7, C10, C11, C12, C14, C15 (mechanical, well-spec'd).
- Use **implementer-novel (Opus 4.7)** for: C5, C6 (new code with non-trivial design — async, error handling, BQ integration).
- Use **planner (Opus 4.7)** for: C3, C4, C13 (require substantive judgment — weight calibration, trust tier curation, principle selection).
- Use **reviewer (Opus 4.7)** at the end of each level — must emit `"DONE"` token before progressing to next level. Three `"REJECTED"` cycles = surface non-convergence and escalate.

**Commit granularity.** One Conventional Commit per C-item (or per logical sub-component if a C-item is large). Examples:

- `feat(consensus): add axis_weights_heuristic.yaml (C3, FA-019, N15)`
- `feat(integrations): add GitHubMCPClient (C5, FA-004)`
- `chore(sprint): backfill STATUS/CHECKPOINTS for D1-D7 (C2)`
- `fix(state): reconcile features.json against phase/1 git log (C1)`
- `docs(adr): add 0014 model registry deviation (C7)`

---

## 6. Handoff protocol

When you believe all C-items are closed, **stop** and produce the handoff report. Do NOT push, do NOT request re-audit, do NOT claim done in chat — until the handoff is written.

### 6.1 Handoff artifact location

`/Users/danielmanzela/Professional Profile/Atelier/.worktrees/phase1-foundation/audit/executor-handoff.md`

### 6.2 Pre-execution stub (write this BEFORE starting work)

```markdown
# Executor Hand-off — Atelier Phase-1 Remediation

**Executor:** <agent name + model>
**Started:** <ISO 8601 timestamp>
**Plan:** <5 lines max — your execution order, which items you'll batch, any concerns up front>
**Skipping (with rationale):** <list of any C-items you propose to skip; if none, write "none">
```

### 6.3 Final handoff content (write this AFTER all work is done)

The report must have these sections, in this order:

1. **Executive summary** (≤200 words): what closed, what didn't, total commits, test-count delta, total compute spent.
2. **Per-item table** — one row per C1–C15:
   - ID | Status (`closed` / `partial` / `skipped` / `blocked`) | Commit SHA(s) | Verification command output (paste, not summarize) | Notes
3. **Gaps and known issues** — anything you discovered mid-work that isn't in the brief and needs an audit decision. Be honest; "honest negatives" is the entire point of this section.
4. **Drift from the brief** — any place you deviated from the spec, with rationale. Examples:
   - "Used `httpx` not `requests` for GitHub MCP" (good — matches existing deps)
   - "Skipped C13 because…" (acceptable only with rationale)
5. **Test count delta** — baseline → final, with the exact `pytest -q | tail -1` output.
6. **Mypy delta** — baseline → final.
7. **Pre-commit delta** — list any hook that started failing or stopped failing.
8. **Cost spent** — tokens consumed, $-equivalent (rough).
9. **What you would NOT bet your job on** — any C-item closed where you suspect the auditor will find a subtle problem.

### 6.4 Honest-negatives mandate

If you couldn't close a C-item, **say so**. The audit penalizes silent dropping ("we just skipped it") **far** more than honest reporting ("attempted, blocked by X, escalating"). The audit will detect dropped items via the verification commands anyway — claiming closure without evidence is the worst possible outcome for both of us.

### 6.5 Re-audit trigger

Once the handoff is written and pushed, signal re-audit by appending a line to `audit/executor-handoff.md`:

```
READY-FOR-AUDIT: 2026-05-21T<HH:MM>+05:30
```

The auditor will pick up from this signal. Re-audit consists of: re-running every §4 verification command with fresh output, cross-checking your handoff claims, and producing a `audit/re-audit-report-N.md` with a verdict per C-item.

### 6.6 What earns a "DONE" vs. "REJECTED" from the auditor

- **DONE per item** = verification command exits clean AND the required handoff evidence is present in your report.
- **REJECTED per item** = either the verification command fails OR the handoff omits required evidence OR fresh inspection reveals the implementation differs from claim.
- **Overall DONE** = every C1-C15 is per-item DONE AND no new gaps surfaced during re-audit.

Three consecutive overall-REJECTED cycles = surface non-convergence to the user (Ralph Loop). Do not loop more than 3 times.

---

## 7. Anti-patterns the auditor watches for

The auditor has seen these before in agent-executed remediation. **Each one fails the audit on detection.**

| Anti-pattern                                                   | Detection                                    | Why it fails                      |
| -------------------------------------------------------------- | -------------------------------------------- | --------------------------------- |
| Marking C-item closed without running its verification command | Re-running command fails                     | Iron Law                          |
| Adding `# noqa` / `# type: ignore` to silence lint/type errors | grep                                         | Bypasses the gate                 |
| Hardcoding values to pass tests                                | Reading the test + code                      | `<no_test_driven_slop>`           |
| Catching `Exception` and `pass`                                | grep                                         | `<no_silent_error_suppression>`   |
| Committing a real token or secret                              | `detect-secrets` hook + manual grep          | Hard rule                         |
| `pip install` without lockfile update                          | Checking `requirements.lock` mtime vs commit | `<lockfile_only_installs>`        |
| Editing upstream package code in `.venv/site-packages/`        | `git diff` shows venv churn                  | `<wrap_dont_fork>`                |
| `git push --force` to overwrite history                        | Reflog inspection                            | `<no_destructive_git>`            |
| Skipping pre-commit with `--no-verify`                         | Hook signature absence                       | Hard rule                         |
| Committing without Conventional Commits format                 | commitlint output                            | `<conventional_commits_required>` |
| Backdating commits to look like daily work                     | `git log --pretty=format:"%ai %s"`           | Audit transparency                |
| Removing tests that started failing                            | Test count drop without justification        | Regression masking                |
| Generating ADRs that don't cite real PRD sections              | Cross-referencing PRD                        | Hallucinated rationale            |
| `index.json` lists files that don't exist                      | File-existence loop                          | Spec gaming                       |

---

## 8. What "industry highest standards and best practices" means in this context

The user's original instruction included this phrase. Concretely, for Atelier on D7 of a 21-day sprint, it means:

1. **Spec-anchored development.** Every line of code traces to a PRD section, ADR, FA-feature, or audit finding. If you can't cite a source, don't write it.
2. **Compile-then-commit.** Static guarantees (mypy `--strict`, ruff, markdownlint) before runtime evidence (pytest, integration). Discipline > velocity.
3. **Failure trichotomy literacy.** Every error path classified as fail-loud / fail-soft / self-heal at design time, not patched in later.
4. **Observability-first.** Every span emitted carries the 15 mandatory attributes from `spans.py` — not "we'll add them later."
5. **Lockfile-only dependency hygiene.** Slopsquatting is a real and recent threat (LiteLLM March 2026). All new deps via lockfile + Snyk.
6. **Honest negatives over false positives.** The audit values "this didn't work, here's what's known" more than "shipped" claims that don't survive verification. Anthropic's Honesty Index for agent self-reports is a real benchmark; we will not lose points here.
7. **Idempotent / re-runnable everything.** Every script, every record, every commit must survive replay.
8. **Conventional Commits + ADRs as the audit trail.** A future operator reading `git log` + `docs/decisions/` must reconstruct every locked decision without asking.
9. **No premature abstraction.** Three similar lines beats a premature abstraction (per `CLAUDE.md` "Doing tasks"). Especially on D7 of 21.
10. **The PRD is canonical.** Mid-sprint changes require an ADR. Silent drift is the failure mode that kills sprints.

---

## 9. Auditor's calibration note

The auditor (this session) will re-audit using the same five-axis fan-out approach used in the original audit:

- **Agent A:** PRD/ADR compliance + critical gaps (G1-G17 closure deltas)
- **Agent B:** FA-features verification + new code review (C5, C6)
- **Agent C:** Foundation contracts (consensus/, agent_card.json, sprint state)
- **Agent D:** Code health (test counts, mypy, ruff, pre-commit, terraform, CI)
- **Agent E:** Cross-check (any anti-pattern from §7 detected; any handoff claim not corroborated)

The auditor's `audit/re-audit-report-N.md` will follow the same structure as `verification-report.md` and will mirror the verdict table format. Items that pass cleanly get ✅. Items that pass with concerns get 🟡 with a remediation sub-item. Items that fail get ❌ with the failing command output verbatim.

Re-audit budget: ~1 hour wall-clock per cycle. Three cycles max.

---

## 10. Final checklist (executor self-check before signaling READY-FOR-AUDIT)

Tick each box honestly. If any is unchecked, you are not ready.

- [ ] All 15 C-items have an entry in §6.3 per-item table — `closed`, `partial`, `skipped`, or `blocked`.
- [ ] Every `closed` item has its verification command output pasted in the table.
- [ ] No commit on `phase/1` was force-pushed or amended in a way that destroys history.
- [ ] `git log phase/1 --oneline | wc -l` is greater than the baseline by the number of items closed.
- [ ] `.venv/bin/pytest -q` exits clean AND the count is ≥ the baseline + new tests from C5 + C6.
- [ ] `pre-commit run --all-files` exits clean.
- [ ] `cd atelier-core && ../.venv/bin/mypy --strict src/atelier/` exits clean.
- [ ] `terraform -chdir=terraform validate` exits clean.
- [ ] `gh run list --branch phase/1 --limit 3` shows at least 1 `success` after the C9 trigger fix.
- [ ] No `--no-verify` flag was used on any commit (`git log --pretty=fuller phase/1 | grep -i "no-verify"` is empty).
- [ ] All new ADRs are listed in `DECISIONS.md`.
- [ ] `features.json` `passes=true` count matches the auditor's expectation (≥ 21).
- [ ] Sprint state files all dated 2026-05-21.
- [ ] `RESUME-HERE:` marker exists in `CHECKPOINTS.md`.
- [ ] Handoff artifact `audit/executor-handoff.md` is present, complete, and ends with `READY-FOR-AUDIT:` line.
- [ ] No secrets, API keys, or tokens committed (verified via `detect-secrets scan`).
- [ ] Honest-negatives section is populated (not empty, not "none — perfect run!").

---

## 11. Sign-off and accountability

This brief, the executor handoff, and the re-audit report together form the audit trail for Phase-1 remediation. They are checked into `audit/` and survive in git history. Any future operator can replay the audit cycle by reading these three artifacts in order.

**Author of this brief:** Auditor session (Claude Opus 4.7), 2026-05-21 D7.
**Authority chain:** PRD `2026-05-14-atelier-prd.md` → ADRs 0001-0013 → `CLAUDE.md` invariants → this brief.
**Sequence:** This brief → executor work → executor handoff → re-audit → DONE token OR REJECTED + next cycle.

The executor's name and model go in the handoff. Accountability is logged.

---

**End of brief.**
