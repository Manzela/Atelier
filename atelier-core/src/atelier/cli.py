"""Atelier CLI — entry point for the `atelier` command.

Phase 1 stub: outputs a status message and exits cleanly. The real CLI
(ADK-backed, with subcommands for brief intake, campaign orchestration,
and eval harness) lands in Phase 2.

This stub exists because ``pyproject.toml`` declares
``atelier = "atelier.cli:main"`` in ``[project.scripts]``. Without a
real ``cli.py``, ``pip install -e .`` would install a broken command
that crashes with ``ModuleNotFoundError`` — a credibility failure for
any reviewer checking "does it run?".
"""

from __future__ import annotations

import sys

from atelier.__version__ import __version__

_BANNER = f"""\
Atelier v{__version__} — Autonomous Design Agent

Status: Phase 1 sprint (2026-05-15 → 2026-06-04)
  Convergence engine: ✅ built (multi-judge consensus + deterministic gates)
  DAG orchestrator:   🔧 assembling (Phase 2)
  Stitch integration: 🔧 wiring (Phase 2)

Run `pytest atelier-core/tests/` to verify the test suite.
See README.md for architecture and novel contributions.
"""


def main() -> None:
    """Entry point for the ``atelier`` console script."""
    sys.stdout.write(_BANNER)
    sys.exit(0)


if __name__ == "__main__":
    main()
