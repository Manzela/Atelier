"""Hermetic test infrastructure (PRD v2.2 AT-003).

This package is CI/test-only record/replay and determinism tooling. It never
fabricates a product render for users or judges (the live product is the only
generation path, per the operator no-demo-tier rule); it exists so the offline
test suite and ``make replay`` reproduce a genuine past run deterministically,
without network or production credentials.
"""
