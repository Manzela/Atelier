#!/usr/bin/env bash
# init.sh — One-time bootstrap for the Atelier sprint
# Per Anthropic's two-prompt harness pattern (Nov 2025): initializer agent runs once.
# Subsequent sessions never re-run this; they restore from features.json + claude-progress.txt.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ─── Colors ─────────────────────────────────────────────────────────────────
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
RESET="\033[0m"

log() { echo -e "${GREEN}[init]${RESET} $*"; }
warn() { echo -e "${YELLOW}[warn]${RESET} $*"; }
error() { echo -e "${RED}[error]${RESET} $*" >&2; }
fatal() {
  error "$*"
  exit 1
}

# ─── Banner ─────────────────────────────────────────────────────────────────
cat <<'BANNER'

   █████╗ ████████╗███████╗██╗     ██╗███████╗██████╗
  ██╔══██╗╚══██╔══╝██╔════╝██║     ██║██╔════╝██╔══██╗
  ███████║   ██║   █████╗  ██║     ██║█████╗  ██████╔╝
  ██╔══██║   ██║   ██╔══╝  ██║     ██║██╔══╝  ██╔══██╗
  ██║  ██║   ██║   ███████╗███████╗██║███████╗██║  ██║
  ╚═╝  ╚═╝   ╚═╝   ╚══════╝╚══════╝╚═╝╚══════╝╚═╝  ╚═╝

  Autonomous Design Agent — Sprint Bootstrap
  github.com/Manzela/atelier

BANNER

# ─── 1. Verify prerequisites ────────────────────────────────────────────────
log "Verifying prerequisites..."

check_cmd() {
  local cmd="$1"
  local install_hint="$2"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    fatal "Missing required command: $cmd. Install: $install_hint"
  fi
  log "  ✓ $cmd ($(command -v "$cmd"))"
}

check_cmd python3 "brew install python@3.11 OR pyenv install 3.11.9"
check_cmd node "brew install node@20 OR nvm install"
check_cmd npm "ships with node"
check_cmd git "brew install git"
check_cmd gh "brew install gh"
check_cmd docker "https://docs.docker.com/get-docker/"
check_cmd gcloud "brew install --cask google-cloud-sdk"

# Python version check
PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ "$PY_VER" != "3.11" && "$PY_VER" != "3.12" ]]; then
  fatal "Python 3.11+ required (found $PY_VER). Run: pyenv install 3.11.9 && pyenv local 3.11.9"
fi
log "  ✓ Python $PY_VER"

# Node version check
NODE_MAJOR="$(node -v | sed 's/v//' | cut -d. -f1)"
if [[ "$NODE_MAJOR" -lt 20 ]]; then
  fatal "Node 20+ required (found $(node -v)). Run: nvm install"
fi
log "  ✓ Node $(node -v)"

# ─── 2. GitHub auth ─────────────────────────────────────────────────────────
log "Verifying GitHub auth..."
if ! gh auth status >/dev/null 2>&1; then
  fatal "gh CLI not authenticated. Run: gh auth login"
fi
GH_USER="$(gh api user --jq .login)"
log "  ✓ Authenticated as @$GH_USER"

# ─── 3. GCP auth ────────────────────────────────────────────────────────────
log "Verifying GCP auth..."
if ! gcloud auth application-default print-access-token >/dev/null 2>&1; then
  warn "ADC not set. Will need: gcloud auth application-default login"
  warn "(Skipping for bootstrap — required for actual Vertex AI calls.)"
else
  GCP_PROJECT="$(gcloud config get-value project 2>/dev/null || echo 'unset')"
  log "  ✓ ADC set; project=$GCP_PROJECT"
fi

# ─── 4. Pre-commit hooks ────────────────────────────────────────────────────
log "Installing pre-commit hooks..."
if ! command -v pre-commit >/dev/null 2>&1; then
  log "  Installing pre-commit via pip..."
  python3 -m pip install --user pre-commit
fi
pre-commit install
pre-commit install --hook-type commit-msg # for commitlint
pre-commit install --hook-type pre-push   # for pytest-fast
log "  ✓ pre-commit hooks installed (run-on-commit + commit-msg + pre-push)"

# ─── 5. Python dependencies ─────────────────────────────────────────────────
log "Installing Python dependencies..."
if [[ ! -f requirements.lock ]]; then
  warn "  requirements.lock not found — generating from requirements.in (D1 of sprint)"
  warn "  For now, installing minimum bootstrap deps:"
  python3 -m pip install --user pre-commit ruff mypy pytest detect-secrets
else
  python3 -m pip install -r requirements.lock
fi
log "  ✓ Python deps installed"

# ─── 6. Node dependencies ───────────────────────────────────────────────────
log "Installing Node dependencies..."
if [[ -f package-lock.json ]]; then
  npm ci
else
  warn "  package-lock.json not found — running npm install (D1 of sprint)"
  npm install
fi
log "  ✓ Node deps installed"

# ─── 7. Sprint state ────────────────────────────────────────────────────────
log "Verifying sprint state files..."
for f in CLAUDE.md DECISIONS.md REJECTED.md features.json claude-progress.txt; do
  if [[ ! -f "$f" ]]; then
    fatal "Missing sprint state file: $f. This file should be committed to the repo."
  fi
  log "  ✓ $f present"
done

# ─── 8. Worktree base check ─────────────────────────────────────────────────
log "Checking worktree state..."
mkdir -p .worktrees
if [[ ! -e .worktrees/.gitkeep ]]; then
  touch .worktrees/.gitkeep
fi
log "  ✓ .worktrees/ ready (gitignored)"

# ─── 9. Vertex AI quota reminder ────────────────────────────────────────────
echo ""
warn "Pending user-manual actions (see PRD §23):"
warn "  P-1: File Vertex AI quota request: Gemini 3.1 Pro provisioned throughput"
warn "  P-2: File Agent Engine session-write quota increase"
warn "  P-3: Activate Tier 1 models in Vertex AI Model Garden (Haiku 4.5, Gemini 3.1 Pro,"
warn "       Gemini 3 Flash, Gemini 3 Flash-Lite, text-embedding-005, multimodal-embedding,"
warn "       Gemma 4 26B-A4B-it)"
warn "  P-4: Confirm Vertex AI Endpoints with Multi-Tuning is enabled"
warn "  P-5: Confirm Vertex AI Tuning Manager is enabled"
warn "  P-6: Read G4S 2026 official rulebook (publishes ~late May 2026)"
echo ""

# ─── 10. Done ───────────────────────────────────────────────────────────────
log "Bootstrap complete."
log ""
log "Next: review docs/sprint/STATUS.md for current sprint state."
log "Then: pick the next unblocked feature from features.json:"
log "      cat features.json | jq '.features[] | select(.passes == false) | .id' | head -5"
log ""
log "Sprint window: 2026-05-15 → 2026-06-04 (submission target 2026-06-03 noon)"
log "Build budget: \$5K Claude Opus 4.7 MAX via Vertex AI"
log ""
