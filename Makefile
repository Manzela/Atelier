# Atelier build and verification Makefile (PRD v2.2 AT-004).
#
# Lanes (each cd's to the right subproject and interpreter; the lane stops
# non-zero on the first failing check):
#
#   make verify    Offline hermetic gate: deps + mypy --strict + tests + lint.
#                  A clean clone runs `make verify` to green with no prod
#                  credentials and no live model/tool calls (hermeticity is
#                  hardened by AT-003). Exits non-zero on the first failure.
#   make preflight Named-reason GCP / deploy-readiness probes (G7/G9/G11 +
#                  chromium + brief-parse + model-id GA). Live GCP probes are
#                  delegated to the Gemini CLI in practice (see deploy/preflight.sh).
#   make replay    Deterministic replay of a recorded real production trajectory
#                  (AT-003). Offline cold-clone viewing of a genuine past run.
#
# Checks that depend on not-yet-landed features SKIP LOUDLY (never silently) and
# name the owning AT-feature, so `make verify` stays green and grows as they land.
#
# Path variables are quoted in every recipe: the checkout path may contain spaces.

SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

ROOT := $(CURDIR)
CORE := atelier-core
DASH := atelier-dashboard
VENV := $(ROOT)/.venv
PY   := $(VENV)/bin/python
UV   := $(shell command -v uv 2>/dev/null)

.PHONY: help verify preflight replay deploy-agent-engine \
        _deps verify-types verify-tests verify-lint verify-dashboard verify-eval \
        verify-token-roundtrip

help:
	@echo "Atelier make targets (PRD v2.2 AT-004):"
	@echo "  make verify    - offline hermetic gate: deps + mypy --strict + tests + lint"
	@echo "  make preflight - named-reason GCP / deploy-readiness probes"
	@echo "  make replay    - deterministic replay of a recorded trajectory (AT-003)"
	@echo "  make deploy-agent-engine - deploy planner to Vertex Agent Engine (AT-082, operator-gated)"

# ---- verify -----------------------------------------------------------------
verify: _deps verify-types verify-tests verify-lint verify-dashboard verify-tokens verify-token-roundtrip verify-eval
	@echo "[verify] OK - all enabled checks passed"

_deps:
	@echo "[verify:deps] sync pinned deps into .venv (google-adk + dev extra)"
ifeq ($(UV),)
	@test -d "$(VENV)" || python3 -m venv "$(VENV)"
	@"$(PY)" -m pip install --quiet --disable-pip-version-check -r "$(CORE)/requirements.lock"
	@"$(PY)" -m pip install --quiet --disable-pip-version-check -e "$(CORE)[dev]"
else
	@test -d "$(VENV)" || "$(UV)" venv "$(VENV)" --python 3.11
	@"$(UV)" pip install --python "$(PY)" --quiet -r "$(CORE)/requirements.lock"
	@"$(UV)" pip install --python "$(PY)" --quiet -e "$(CORE)[dev]"
endif

verify-types: _deps
	@echo "[verify:types] mypy --strict $(CORE)/src"
	@"$(PY)" -m mypy "$(CORE)/src"

verify-tests: _deps
	@echo "[verify:tests] offline pytest (unit + AT-003 record/replay + AT-020 specialist pipeline)"
	@cd "$(CORE)" && "$(PY)" -m pytest tests/unit tests/integration/test_record_replay_determinism.py tests/integration/test_specialist_pipeline.py tests/integration/test_critique_panel_pipeline.py -q -p no:cacheprovider
	@echo "[verify:tests] NOTE the full section-16 golden-path integration grows as E1-E4 land"

verify-lint:
	@echo "[verify:lint] markdownlint (per PRD AT-004; ruff/format are enforced by pre-commit + CI)"
	@if command -v markdownlint >/dev/null 2>&1; then \
	   markdownlint '**/*.md' --ignore node_modules; \
	 else echo "[verify:lint] SKIP markdownlint - not on PATH (covered by pre-commit / CI)"; fi

verify-dashboard:
	@if [ -f "$(DASH)/tsconfig.json" ]; then \
	   echo "[verify:dashboard] tsc --noEmit"; cd "$(DASH)" && npx --no-install tsc --noEmit; \
	 else echo "[verify:dashboard] SKIP - no $(DASH)/tsconfig.json yet (lands with the Next.js dashboard adoption)"; fi

verify-tokens:
	@if [ -d node_modules/style-dictionary ]; then \
	   echo "[verify:tokens] style-dictionary build (DTCG -> CSS/Tailwind/Swift/Kotlin)"; \
	   npm run build:tokens >/dev/null && \
	   for f in design-tokens/build/css/variables.css design-tokens/build/tailwind/tokens.js \
	            design-tokens/build/swift/AtelierTokens.swift design-tokens/build/kotlin/AtelierTokens.kt; do \
	     test -s "$$f" || { echo "[verify:tokens] FAIL missing/empty $$f"; exit 1; }; \
	   done; \
	   echo "[verify:tokens] OK - 4 platform outputs produced"; \
	 else echo "[verify:tokens] SKIP - style-dictionary not installed (run npm ci; covered by the CI tokens job)"; fi

verify-token-roundtrip:
	@if [ -d node_modules/style-dictionary ]; then \
	   echo "[verify:token-roundtrip] AT-052 propagation proof (sentinel -> CSS/Tailwind/Swift/Kotlin)"; \
	   node scripts/verify-token-roundtrip.mjs; \
	 else echo "[verify:token-roundtrip] SKIP - style-dictionary not installed (run npm ci; covered by CI tokens job)"; fi

verify-eval: _deps
	@echo "[verify:eval] deterministic offline eval gate (AT-100): real gates score GOOD HTML, REJECT garbage, regression-sensitive, zero live calls"
	@cd "$(CORE)" && "$(PY)" -m pytest tests/eval/test_agent_evaluator.py -q -p no:cacheprovider
	@echo "[verify:eval] OK"

# ---- replay -----------------------------------------------------------------
replay: _deps
	@echo "[replay] deterministic record/replay harness (AT-003): 3x byte-identical canonical trajectory, zero live calls"
	@cd "$(CORE)" && "$(PY)" -m pytest tests/integration/test_record_replay_determinism.py -q -p no:cacheprovider
	@echo "[replay] NOTE a recorded REAL production trajectory replaces the golden fixture once the operator captures one"

# ---- preflight --------------------------------------------------------------
preflight:
	@echo "[preflight] named-reason GCP / deploy-readiness probes"
	@bash deploy/preflight.sh

# ---- deploy -----------------------------------------------------------------
deploy-agent-engine: preflight
	@echo "[deploy] Vertex AI Agent Engine (AT-082) - operator-gated, requires GCP creds"
	@bash deploy/agent_engine.sh
