"""Scope-key format + CEL condition helper for Vertex Memory Bank ACL-on-read.

Spec section 20.4: every memory write carries a scope key of the form
    f"{project_id}/{phase}/{user_or_agent_id}"
Reads are enforced server-side by IAM Conditions that evaluate
``request.attribute['memoryScope'] == resource.attribute['memoryScope']``.

This module is the single source of truth for the scope-key format
and the matching CEL expression.

Failure trichotomy:
- Malformed scope key -> fail-loud (raises ValueError; never silently
  default to a wildcard, which would leak across tenants).
- IAM CEL evaluation failure on read -> fail-soft (caller receives
  empty result + structured warning log; does NOT raise --- Vertex
  treats this as "no memories matched", which is the correct
  semantics for ACL-on-read).
"""

from __future__ import annotations

from dataclasses import dataclass

_SEPARATOR = "/"
_EXPECTED_PARTS = 3


@dataclass(frozen=True, slots=True)
class MemoryScopeKey:
    """Three-part scope key: project / phase / user-or-agent identifier."""

    project_id: str
    phase: str
    actor_id: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("project_id", self.project_id),
            ("phase", self.phase),
            ("actor_id", self.actor_id),
        ):
            if not value or _SEPARATOR in value:
                msg = (
                    f"MemoryScopeKey.{field_name} must be non-empty and "
                    f"must not contain {_SEPARATOR!r}; got {value!r}"
                )
                raise ValueError(msg)

    def encode(self) -> str:
        """Encode to the canonical wire format: project/phase/actor."""
        return f"{self.project_id}{_SEPARATOR}{self.phase}{_SEPARATOR}{self.actor_id}"

    @classmethod
    def decode(cls, encoded: str) -> MemoryScopeKey:
        """Decode from wire format; raises ValueError if malformed."""
        parts = encoded.split(_SEPARATOR)
        if len(parts) != _EXPECTED_PARTS:
            msg = (
                f"scope key must have exactly {_EXPECTED_PARTS} parts; "
                f"got {len(parts)} from {encoded!r}"
            )
            raise ValueError(msg)
        return cls(project_id=parts[0], phase=parts[1], actor_id=parts[2])


CEL_ACL_ON_READ_CONDITION: str = (
    'request.attribute["aiplatform.googleapis.com/memoryScope"] == '
    'resource.attribute["aiplatform.googleapis.com/memoryScope"]'
)
"""CEL expression bound to the IAM Condition on the Memory Bank read role.

Applied via ``gcloud iam policies create-binding`` with --condition; see
infra/iam/atelier-memory-scope-acl.json for the full condition object.
"""
