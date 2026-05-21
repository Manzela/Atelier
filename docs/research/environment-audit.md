# Local Environment Audit Report

**Generated**: 2026-05-20 23:48 IDT
**Machine**: Daniel's MacBook Pro

---

## 1. Hardware & OS

| Property    | Value                                                        |
| ----------- | ------------------------------------------------------------ |
| **Machine** | Apple M2 Max (arm64)                                         |
| **RAM**     | 32 GB                                                        |
| **OS**      | macOS 26.5 (Tahoe, build 25F71)                              |
| **Disk**    | 926 GB total, **430 GB free** (3% used) — plenty of headroom |
| **Shell**   | zsh                                                          |

---

## 2. Development Toolchain

### Core Languages & Runtimes

| Tool                  | Version           | Notes                                  |
| --------------------- | ----------------- | -------------------------------------- |
| **Node.js**           | 22.20.0 (via NVM) | Single NVM version installed           |
| **npm**               | 10.9.3            |                                        |
| **Python (Homebrew)** | 3.14.4            | Active default via PATH                |
| **Python (System)**   | 3.9.6             | macOS bundled — aliased via `~/.zshrc` |
| **Go**                | 1.26.3            |                                        |
| **Ruby**              | 2.6.10            | System Ruby (arm64e, quite old)        |
| **Bun**               | 1.3.0             |                                        |
| **Java**              | ❌ Not installed  |                                        |
| **Rust**              | ❌ Not installed  |                                        |

### Build & Quality Tools

| Tool                  | Version                           |
| --------------------- | --------------------------------- |
| **Git**               | 2.50.1 (Apple Git-155)            |
| **Git LFS**           | Configured globally               |
| **Docker**            | 29.4.3 (Desktop running)          |
| **Terraform**         | 1.7.0                             |
| **gcloud SDK**        | 569.0.0 (alpha + beta)            |
| **gh (GitHub CLI)**   | Authenticated (keyring)           |
| **uv**                | 0.8.8                             |
| **ruff**              | 0.6.9                             |
| **mypy**              | ❌ Not installed globally         |
| **pre-commit**        | 4.6.0                             |
| **Prettier**          | via workspace `devDependencies`   |
| **shellcheck**        | via Homebrew                      |
| **yamllint**          | via Homebrew                      |
| **tmux**              | via Homebrew                      |
| **pandoc**            | via Homebrew                      |
| **typst**             | via Homebrew                      |
| **sops**              | via Homebrew (secrets encryption) |
| **age**               | via Homebrew (sops backend)       |
| **gitleaks**          | via Homebrew (secret scanning)    |
| **temporal**          | via Homebrew                      |
| **Homebrew formulas** | 93 total                          |

### AI / Agent CLI Tools

| Tool                    | Version                                   |
| ----------------------- | ----------------------------------------- |
| **Claude Code**         | 2.1.145 (Claude desktop app also running) |
| **Antigravity IDE**     | Running (Electron-based, current session) |
| **@google/gemini-cli**  | 0.42.0 (npm global)                       |
| **@github/copilot**     | 0.0.389 (npm global)                      |
| **@augmentcode/auggie** | 0.19.0 (npm global)                       |
| **firecrawl-cli**       | 1.17.0 (npm global)                       |
| **langfuse-cli**        | 0.0.8 (npm global)                        |
| **react-devtools**      | 7.0.1 (npm global)                        |

> [!NOTE]
> You are running a significant number of AI coding assistants simultaneously — Claude Code (multiple terminal sessions), Antigravity IDE, Copilot, Augment, Gemini CLI. This is heavy on context-switching and token spend.

---

## 3. Cloud Infrastructure

### Google Cloud Platform

| Property               | Value                                                        |
| ---------------------- | ------------------------------------------------------------ |
| **Active account**     | `manzela@tngshopper.com`                                     |
| **Service account**    | `github-dev-stg@i-for-ai.iam.gserviceaccount.com` (inactive) |
| **Active project**     | `i-for-ai`                                                   |
| **Compute region**     | `global`                                                     |
| **Total GCP projects** | 9 visible                                                    |

**GCP Projects on account:**

| Project ID                 | Name                         |
| -------------------------- | ---------------------------- |
| `i-for-ai`                 | i-for-AI (ACTIVE)            |
| `ai-project-424717`        | AI Project                   |
| `bulk-data-exports-453408` | Bulk-Data-Exports            |
| `globalproductdatabase`    | GlobalProductDatabase        |
| `gpdservice`               | GPDservice                   |
| `i-for-ai-1f78a`           | boostmobile                  |
| `il-website-348911`        | IL website                   |
| `gen-lang-client-*`        | Gemini default projects (×2) |

### GitHub

| Property              | Value                                                 |
| --------------------- | ----------------------------------------------------- |
| **Account**           | `Manzela`                                             |
| **Auth**              | Keyring-backed token                                  |
| **Token scopes**      | `admin:org`, `gist`, `repo`, `user`, `workflow`       |
| **Git identity**      | `Manzela <81286733+Manzela@users.noreply.github.com>` |
| **Credential helper** | `gh auth git-credential`                              |

> [!WARNING]
> **GitHub GITHUB_TOKEN env var is invalid.** The `GITHUB_PERSONAL_ACCESS_TOKEN` from `gh auth token` in `.zshrc` works, but there's a separate `GITHUB_TOKEN` in the environment that `gh auth status` reports as invalid. This likely causes issues for MCP servers and CI-adjacent tools that read `GITHUB_TOKEN` first. The keyring-backed Manzela account (inactive=false) is the fallback.

### SSH Keys

| Key                                | Purpose     |
| ---------------------------------- | ----------- |
| `~/.ssh/google_compute_engine.pub` | GCE SSH key |

> [!IMPORTANT]
> No personal SSH key for GitHub detected — all Git operations use HTTPS + `gh` credential helper. This is functional but worth noting.

---

## 4. Active Projects

### A. Atelier (Primary Workspace — `Professional Profile/Atelier`)

- **What**: Autonomous design agent for Google for Startups AI Agents Challenge 2026
- **Sprint**: 2026-05-15 → 2026-06-04 (3 weeks)
- **Repo**: [github.com/Manzela/atelier](https://github.com/Manzela/atelier)
- **Stack**: Python 3.11+ (pyproject.toml) + Node.js (npm workspaces) + TypeScript
- **`.python-version`**: `3.11.9` — explicit pin file present
- **`.nvmrc`**: `20.11.1` — current Node 22.20.0 is ahead of this pin
- **Subpackages**: `atelier-core`, `atelier-eval`, `atelier-dashboard`, `atelier-deploy`, `atelier-action`, `atelier-chrome-extension`, `atelier-figma-plugin`
- **Git branch**: `main` (clean working tree, no worktrees active)
- **Latest commit**: `c909dbf` — ADR absorptions + feature queuing
- **Python constraint**: `>=3.11,<3.13` — ⚠️ **system Python is 3.14.4, outside the supported range**
- **No active venv detected** — needs `python3.11` or `python3.12` venv creation

### B. AutonomousAgent (Active Research — `RX-Research Project/AutonomousAgent`)

- **What**: Hermes Agent deployment wrapper with self-RL pipeline
- **Repo**: [github.com/Manzela/AutonomousAgent](https://github.com/Manzela/AutonomousAgent)
- **Stack**: Python 3.11+ + Docker Compose + Terraform + uv
- **Git branch**: `main` (2 untracked files: compacted session doc + terraform plan)
- **Worktrees**: 3 active (`feat/framing-2-bolt-on`, `feat/phase-0a-h-plus`, `research/framing-1-moe-rl-spike`)
- **Has `.venv` and `.venv-test`** — proper venv isolation
- **`.venv` Python**: `3.12.11` ✅ (correct for `requires-python >= 3.11`)
- **Lock file**: `uv.lock` (574 lines) — uv-managed dependencies
- **Latest commit**: `287eee4` — CI polling smoke check fix
- **Submodule**: `hermes-agent` (git submodule)
- **Actively editing**: `docs/Compacted-sessions-20-05-2026.md` (cursor at line 575)

### C. Manzela Portfolio (`Professional Profile/Manzela`)

- **What**: Personal profile site + GitHub profile README
- **Stack**: Vanilla HTML (static site, GitHub Pages)
- **Has worktrees**: Yes
- **Key files**: `index.html` (74KB), `resume.json`, `llms.txt`, SEO files

### D. Other Projects in `Professional Profile/`

| Project                      | Type                                  |
| ---------------------------- | ------------------------------------- |
| `Antigravity-OS`             | Python — AI agent governance kernel   |
| `agent-dag-pipeline`         | Python — Multi-agent DAG with ADK     |
| `pipeline-observatory`       | Vanilla HTML — Architecture dashboard |
| `Elysium`                    | Vanilla HTML — Product case study     |
| `investordeck`               | Vite + TypeScript + Tailwind SPA      |
| `gemma4-vllm-deployment`     | Forensic runbook (docs-heavy)         |
| `Seller App` / `SellerApp-*` | Development/audit projects            |
| `Tasko-AI-Development`       | Development project                   |

### E. Developer Directory (Business/Production)

| Subdirectory                    | Purpose                                   |
| ------------------------------- | ----------------------------------------- |
| `PRODUCT`                       | TNG Shopper Pipeline (private production) |
| `GCP`                           | GCP infrastructure configs                |
| `Dashboard`                     | Analytics dashboard                       |
| `Pipeline`                      | Pipeline project                          |
| `TNG Customers`                 | Customer data                             |
| `TNG IDR (DEMO)`                | Demo environment                          |
| `Antigravity-OS-Installer V3.0` | OS installer                              |

---

## 5. Docker Infrastructure (Running)

### AutonomousAgent Docker Compose Stack (Up 9 hours)

| Service                | Image                                         | Status       |
| ---------------------- | --------------------------------------------- | ------------ |
| **hermes**             | `autonomousagent/hermes:0.1.0`                | Up (healthy) |
| **litellm-proxy**      | `ghcr.io/berriai/litellm:v1.84.0`             | Up (healthy) |
| **litellm-db**         | `postgres:16-alpine`                          | Up (healthy) |
| **phoenix**            | `arizephoenix/phoenix:latest`                 | Up           |
| **otel-collector**     | `otel/opentelemetry-collector-contrib:latest` | Up           |
| **github-mcp**         | `ghcr.io/github/github-mcp-server:latest`     | Up           |
| **shell-sandbox**      | `autonomousagent/shell-sandbox:0.1.0`         | Up           |
| **budget-watchdog**    | `autonomousagent/hermes:0.1.0`                | Up           |
| **escalation-watcher** | `autonomousagent/hermes:0.1.0`                | Up           |
| **snapshot-watchdog**  | `autonomousagent/hermes:0.1.0`                | Up           |

**Exposed ports:**

- `127.0.0.1:6006` → Phoenix observability UI
- `127.0.0.1:4317` → OTEL collector (gRPC)

### Orphaned GitHub MCP Containers

4 standalone `ghcr.io/github/github-mcp-server` containers running outside the compose stack (from various Claude Code sessions). These can be cleaned up.

### Docker Volumes

14 volumes total, spanning: `autonomous-agent`, `antigravity-os`, `demo`, `platform`, `tng-idr` stacks.

---

## 6. Running Terminal Sessions

| Shell                | Working Directory                     | Duration |
| -------------------- | ------------------------------------- | -------- |
| `claude`             | `Professional Profile`                | 23h 3m   |
| `Claude`             | `Professional Profile`                | 14h 2m   |
| `claude`             | `RX-Research Project/AutonomousAgent` | 9h 44m   |
| `claude -r ae44ed38` | `RX-Research Project/AutonomousAgent` | 5h 45m   |
| `claude`             | `RX-Research Project/AutonomousAgent` | 3h 25m   |
| `claude`             | `RX-Research Project/AutonomousAgent` | 3m       |

> [!WARNING]
> **6 concurrent Claude Code sessions** active across 2 workspaces. Combined with the Antigravity IDE session (this one), that's significant parallel AI agent activity. Watch for context conflicts and token burn.

---

## 7. MCP Servers Available (Antigravity IDE)

| Server                | Key Tools                                                             |
| --------------------- | --------------------------------------------------------------------- |
| **StitchMCP**         | Design system CRUD, screen generation/editing, variant generation     |
| **bigquery**          | SQL execution, dataset/table info, data insights                      |
| **cloudrun**          | Service deployment, project management                                |
| **github-mcp-server** | Full GitHub API (issues, PRs, repos, code search)                     |
| **notebooks**         | Jupyter notebook CRUD and execution                                   |
| **redis**             | Full Redis operations (hash, list, set, sorted set, streams, vectors) |
| **stitch**            | Duplicate of StitchMCP (screen code/image fetch added)                |
| **visualization**     | Chart rendering                                                       |
| **datacloud\_\***     | AlloyDB, BigQuery, Cloud SQL, Dataproc, Knowledge Catalog, Spanner    |

---

## 8. Identified Issues & Recommendations

### 🔴 Critical

| #   | Issue                                                                                     | Impact                                                                                                      |
| --- | ----------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| 1   | **Python version mismatch**: System Python is 3.14.4 but Atelier requires `>=3.11,<3.13`. | Atelier Python packages won't install properly under system Python. Need a 3.12.x venv.                     |
| 2   | **GITHUB_TOKEN is invalid** per `gh auth status`.                                         | MCP servers and tools reading `GITHUB_TOKEN` may silently fail. Fix: unset the invalid token or regenerate. |

### 🟡 Warnings

| #   | Issue                                                                                                                                               | Recommendation                                                                       |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| 3   | **6 Claude Code sessions + Antigravity IDE running simultaneously**                                                                                 | Token budget awareness — consolidate if possible.                                    |
| 4   | **4 orphaned GitHub MCP containers** outside the compose stack                                                                                      | Run `docker container prune` or manually stop them.                                  |
| 5   | **`.zshrc` has 4 duplicate `PATH` entries** for Antigravity and 2 duplicate `BUN_INSTALL` blocks — `$PATH` has **19+ directories**, many duplicated | Clean up `.zshrc` to prevent PATH pollution and shell startup slowdown.              |
| 6   | **mypy not installed globally** — Atelier's `CLAUDE.md` mandates `mypy --strict` on every Python commit                                             | Install mypy or ensure it's in project venvs.                                        |
| 7   | **No personal SSH key for GitHub**                                                                                                                  | HTTPS+gh works, but SSH is preferred for agent-heavy workflows.                      |
| 8   | **Terraform 1.7.0** is aging (current is ~1.12+)                                                                                                    | Upgrade if AutonomousAgent terraform configs require newer features.                 |
| 9   | **Atelier `.nvmrc` pins Node 20.11.1** but NVM has 22.20.0 active                                                                                   | May cause inconsistency if Atelier CI expects Node 20. Run `nvm use` inside Atelier. |
| 9   | **Ruby 2.6.10** is EOL (2022)                                                                                                                       | Only relevant if used — likely can ignore.                                           |

### 🟢 Good Practices Observed

| #   | Practice                                                                      |
| --- | ----------------------------------------------------------------------------- |
| ✅  | Git LFS configured globally                                                   |
| ✅  | `gitleaks` + `sops` + `age` for secret management                             |
| ✅  | pre-commit hooks configured in both main projects                             |
| ✅  | Docker Compose health checks on critical services                             |
| ✅  | Proper venv isolation in AutonomousAgent (`.venv`, `.venv-test`)              |
| ✅  | Conventional Commits + commitlint enforced                                    |
| ✅  | Structured project documentation (`CLAUDE.md`, `DECISIONS.md`, `REJECTED.md`) |
| ✅  | uv 0.8.8 available for fast dependency management                             |
| ✅  | Ample disk space (430 GB free)                                                |
| ✅  | OTEL + Phoenix observability stack running                                    |

---

## 9. Environment Summary

```
┌─────────────────────────────────────────────────────────────────┐
│  Apple M2 Max · 32 GB · macOS 26.5 · 430 GB free               │
├─────────────────────────────────────────────────────────────────┤
│  RUNTIMES: Node 22.20 · Python 3.14 · Go 1.26 · Bun 1.3       │
│  CLOUD:    GCP (i-for-ai) · GitHub (Manzela) · Docker 29.4     │
│  INFRA:    10-service Docker stack (Hermes + LiteLLM + Phoenix) │
│  AGENTS:   Claude Code ×6 · Antigravity IDE · Copilot · Auggie │
│  PROJECTS: Atelier (sprint) · AutonomousAgent (research)        │
│            Manzela Portfolio · TNG Pipeline (Developer/)        │
│  MCP:      17 servers (BigQuery, CloudRun, GitHub, Redis, etc.) │
└─────────────────────────────────────────────────────────────────┘
```
