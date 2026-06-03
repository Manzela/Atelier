# 0026. OpenAPI schema is prod-gated — smoke-probe verifies route liveness, not schema exposure

**Status:** Accepted (2026-06-03)
**Date:** 2026-06-03
**Decision-makers:** Daniel Manzela
**Relates to:** resolves the conflict between AT-083 (live-prod smoke gate) and the S9 transport-hardening shipped in PR #76; references `atelier-core/src/atelier/api/app.py` (the gate) and `scripts/ci/smoke_probe.sh` (the probe).

## Context and problem statement

PR #76 (S9 hardening) gated FastAPI's interactive docs **and** the raw OpenAPI
schema behind the development flag:

```python
docs_url="/docs" if _is_dev else None,
openapi_url="/openapi.json" if _is_dev else None,
```

In a production build (`ATELIER_ENV=production`, baked into `deploy/Dockerfile.api`),
`GET /openapi.json` therefore returns `404`. This is deliberate: the schema
publishes the full route, parameter, and model surface of a paid, authenticated
API — an information-disclosure aid to an attacker with no benefit to a legitimate
end user (the dashboard talks to the typed client, and A2A consumers discover
capability through the agent card, not the OpenAPI document).

This directly contradicts two pre-existing checks written before the hardening:

- **AT-083 acceptance** required `GET /openapi.json` to list `/v1/generate`,
  `/v1/replay`, `/v1/dream`.
- **`scripts/ci/smoke_probe.sh`** asserted `/openapi.json` → `200` and that it
  contained those three routes.

Both would now fail the live deploy gate against a correctly-hardened production
service. The conflict is genuine: the smoke probe used "the schema advertises the
routes" as a proxy for "the routes are live," and the hardening removes the schema.

## Decision

Keep the hardening. **The OpenAPI schema stays gated (404) in production.** Replace
the schema-exposure proxy with a direct, honest liveness signal:

1. `smoke_probe.sh` asserts `/openapi.json` → **404** — i.e. it verifies the gate
   is _active_ (a positive security assertion), not merely tolerates its absence.
2. `/v1` route liveness **and** real convergence are verified by the **AT-110
   authenticated production-readiness walkthrough** — an authenticated
   `POST /v1/generate` followed by `GET /v1/replay/{session_id}` asserting
   `converged == true` with non-empty `tokens.json`. Exercising the routes proves
   they are served far more strongly than reading them off a schema.
3. Public capability discovery remains available unauthenticated via
   `GET /.well-known/agent-card.json` (A2A), which the probe already checks.

The AT-083 acceptance criterion is amended accordingly: the `/openapi.json`-lists-routes
clause is replaced by "`/openapi.json` is gated (404) in prod **and** the
authenticated generate→replay→converged path passes (AT-110)."

## Consequences

- **Positive:** the shipped production service exposes no machine-readable route
  surface; the smoke gate now fails _closed_ if the gating regresses (a future
  build that accidentally re-exposes `/openapi.json` turns the probe red).
- **Negative / accepted:** developers lose `/openapi.json` and `/docs` against a
  production host; they remain available in any non-production build
  (`ATELIER_ENV != production`), which is where schema exploration belongs.
- **Neutral:** no change to the API's actual routes or behavior — only to what is
  _advertised_ and what the gate _asserts_.
