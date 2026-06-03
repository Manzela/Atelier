"""Per-tenant design-system record — AT-053 (persistent, auto-applied, enforced).

A :class:`DesignSystemRecord` is the durable, per-tenant design system that is
persisted at human sign-off (AT-031), auto-applied on the tenant's next run
(N2 source resolver), and *enforced* by the AT-012 zero-tolerance token-fidelity
gate (any off-system literal → REJECT). This is the "enforced, not merely
applied" USP versus tools that only seed a system as a soft prior.

V1 scope (PRD §12 / AT-053): there is exactly ONE design system per tenant. The
codebase-onboarding learner and multi-system-per-tenant are V2; this model
intentionally has no slot for either (a tenant key, not a system key).

The model follows the repo data-contract invariants (frozen, ``extra='forbid'``,
``schema_version``) so it round-trips ``model_dump_json()`` ↔
``model_validate_json()`` for both Firestore documents and Vertex Memory Bank
content blobs.

PRD Reference: §12 E? (AT-053), §9 (data contracts), §20 (memory).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DesignSystemRecord(BaseModel):
    """The persisted design system for one tenant (one system per tenant, V1).

    Attributes:
        tenant_id: Identity Platform tenant partition key — the primary key.
            There is exactly one current record per tenant (V1 scope).
        run_id: The run that produced/last-edited this system (provenance).
        tokens: Flat ``{token_name: value}`` design-token map (the same shape
            carried by ``ProjectContext.design_tokens``). This is the authorized
            token set the AT-012 gate enforces against.
        constitution: Optional brand constitution / non-negotiable rules string
            surfaced to the generator and to the human reviewer.
        applicable_standards: Domain standards (e.g. WCAG rows) carried alongside
            the tokens; a list of small JSON-safe dicts.
        created_at: UTC timestamp the record was written.
        firestore_doc_path: The Firestore document path when persisted online
            (``tenants/{tenant_id}/design_systems/{run_id}``); ``None`` offline.
        schema_version: Forward-compat version marker (never decreases).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tenant_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    tokens: dict[str, Any] = Field(default_factory=dict)
    constitution: str | None = None
    applicable_standards: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    firestore_doc_path: str | None = None
    schema_version: int = 1

    def authorized_token_values(self) -> set[str]:
        """Return the set of authorized token display VALUES (for gate fidelity).

        The AT-012 token-fidelity gate compares a rendered surface's literal
        token values against this set: any value not in it is an off-system
        literal and is REJECTed. Values are coerced to display strings the same
        way the A2UI surface builder coerces them (lists → comma-joined), so the
        comparison is apples-to-apples with the rendered ``/tokens`` rows.

        Metadata keys (``_``-prefixed, e.g. ``_source``) are excluded — they are
        intake bookkeeping, not brand tokens.
        """
        values: set[str] = set()
        for name, value in self.tokens.items():
            if name.startswith("_"):
                continue
            values.add(_coerce_display(value))
        return values

    def to_memory_content(self) -> str:
        """Serialize to a JSON string for Vertex Memory Bank ``add_memory`` content.

        Vertex Memory Bank stores opaque text content; we store the full record
        as canonical JSON so the read path can reconstruct the system losslessly
        via :meth:`from_memory_content`. ``mode="json"`` makes ``created_at``
        ISO-8601 and keeps the blob deterministic.
        """
        return self.model_dump_json()

    @classmethod
    def from_memory_content(cls, content: str) -> DesignSystemRecord:
        """Reconstruct a record from a Vertex Memory Bank / file JSON blob."""
        return cls.model_validate_json(content)

    def to_firestore_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict for a Firestore document write."""
        data: dict[str, Any] = self.model_dump(mode="json")
        return data

    @classmethod
    def from_firestore_dict(cls, data: dict[str, Any]) -> DesignSystemRecord:
        """Reconstruct a record from a Firestore document snapshot dict."""
        return cls.model_validate(data)


def _coerce_display(value: Any) -> str:
    """Coerce a token value to the same display string the A2UI surface emits.

    Mirrors ``atelier.a2ui.surface._coerce_token_value`` so the gate's authorized
    value set matches the rendered ``/tokens`` row values byte-for-byte. Kept as a
    small local (not an import) so this model has no dependency on the a2ui layer.
    """
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def serialize_priors(record: DesignSystemRecord) -> list[str]:
    """Render a persisted system as N2 memory-bank prior strings (auto-apply).

    These strings are consumed downstream by the generator anchor (they appear in
    ``ProjectContext.memory_bank_priors``), so run #2 inherits run #1's system
    with no re-specification. The format is intentionally human- and model-
    readable (one fact per line); the structured enforcement set is carried
    separately on ``ProjectContext.persisted_design_tokens``.
    """
    priors: list[str] = [f"Persisted design system for tenant {record.tenant_id} (AT-053)."]
    # One line per token so the generator can ground every literal it emits.
    token_lines = [
        f"Token {name} = {_coerce_display(value)}"
        for name, value in record.tokens.items()
        if not name.startswith("_")
    ]
    if token_lines:
        priors.append("Persisted tokens (authorized set): " + "; ".join(token_lines))
    if record.constitution:
        priors.append(f"Constitution: {record.constitution}")
    if record.applicable_standards:
        priors.append("Applicable standards: " + json.dumps(record.applicable_standards))
    return priors


__all__ = ["DesignSystemRecord", "serialize_priors"]
