"""Atelier models package — canonical data contracts for the 8-node DAG.

All models follow these invariants (from architectural invariants + PRD §9):
    1. ``ConfigDict(frozen=True, extra='forbid')`` — immutable, no drift
    2. ``schema_version: int = 1`` — every model, never decreases, fields never dropped
    3. Pydantic v2 — ``model_dump_json()`` / ``model_validate_json()`` roundtrip

Import hierarchy (no circular deps):
    enums.py           → zero imports (leaf)
    brief_spec.py      → enums
    data_contracts.py  → enums, brief_spec (for type references only)
"""
