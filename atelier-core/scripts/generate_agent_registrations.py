"""Regenerate the Agent Gallery registration artifacts (AT-082).

Pure, offline: reads the committed A2A cards under ``agent_cards/`` and writes one
``<id>.registration.json`` per card under ``agent_cards/registration/``. No network
call, no GCP credentials. The CI drift-guard test asserts the on-disk artifacts
match a fresh run of this generator.

Usage:
    python scripts/generate_agent_registrations.py
"""

from __future__ import annotations

import logging

from atelier.orchestrator.agent_registration import generate_committed_registrations

logger = logging.getLogger(__name__)


def main() -> None:
    """Generate every registration payload and report what was written."""
    written = generate_committed_registrations()
    logger.info("Wrote %d registration payload(s):", len(written))
    for agent_id in sorted(written):
        logger.info("  %s", written[agent_id])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
