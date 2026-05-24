# 0029. Memory Scope-Key Format

**Status:** Accepted
**Date:** 2026-05-21
**Decision-makers:** Daniel Manzela (Principal Architect), Atelier sprint

## Context

The Vertex AI Memory Bank backend requires scope-keyed namespacing to enforce Virtual Context Isolation. Without a canonical key format, each backend could invent its own encoding, creating inconsistencies and scope-leak risks.

## Decision

Adopt a 3-part scope key format: `{project_id}/{phase}/{actor_id}`.

- `MemoryScopeKey` frozen dataclass in `atelier.memory.scope` is the single source of truth.
- `encode()` produces the wire format; `decode()` round-trips with ValueError on malformed input.
- IAM Conditions use a CEL expression comparing `request.attribute["memoryScope"]` to `resource.attribute["memoryScope"]` for server-side enforcement.

### Wire format

```
atelier-build-2026/phase-1/tenant-a
atelier-build-2026/phase-2/agent-router
```

### Failure contract

- Malformed scope key (empty part, contains separator) -> fail-loud (`ValueError`)
- IAM CEL evaluation failure on read -> fail-soft (returns `[]`, logs warning)
- Never default to a wildcard scope on error — this would leak across tenants.

## Consequences

### Positive

- Single canonical format for all memory tiers (semantic + procedural).
- Server-side enforcement via IAM CEL — defense in depth, not application-only.
- `encode()`/`decode()` round-trip is unit-testable without GCP access.

### Negative

- 3-part format may be insufficient if we need sub-project scoping. Mitigation: extend to 4+ parts in a future ADR if needed, with backwards-compatible decode.

## References

- Spec section 20.4 (scope-keyed namespacing)
- Implementation: `atelier-core/src/atelier/memory/scope.py`
- IAM condition: `infra/iam/atelier-memory-scope-acl.json`
