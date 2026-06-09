# Agent Gallery registration artifacts (AT-082)

These 18 `*.registration.json` files are the **operator-applied** payloads that
register each Atelier agent in the **Gemini Enterprise Agent Gallery**
(Discovery Engine `Agent` resources). They are generated 1:1 from the committed
A2A 0.3.0 agent cards in the parent directory
(`atelier-core/agent_cards/*.agent-card.json`) by a pure, offline transform:

```text
agent_cards/<id>.agent-card.json   ──build_registration_payload──▶   agent_cards/registration/<id>.registration.json
```

Source: `atelier.orchestrator.agent_registration` (no network, no GCP creds).
Regenerate with `python scripts/generate_agent_registrations.py`. A drift-guard
unit test (`tests/unit/test_agent_engine_deploy.py`) asserts the on-disk payloads
match a fresh generation and cover all 18 cards.

## What each payload is

The body of a Discovery Engine **`CreateAgent`** call. Fields prefixed with `_`
(`_target`, `_adkAgentDefinitionTemplate`, `_provenance`) are operator guidance /
provenance and are **not** part of the request body — strip them before POSTing.

| field                                | meaning                                                              |
| ------------------------------------ | -------------------------------------------------------------------- |
| `displayName`, `description`, `icon` | human-facing identity (from the card)                                |
| `a2aAgentDefinition.jsonAgentCard`   | the committed A2A card, inlined — the offline-derivable definition   |
| `authorizations`                     | the authorization resource(s) the agent calls under                  |
| `_target`                            | the `CreateAgent` parent + agentId an operator supplies at POST time |
| `_adkAgentDefinitionTemplate`        | the **alternative** ADK-backed definition (see below)                |
| `_provenance`                        | source card + skills, for the CI drift-guard                         |

## Two definition variants — pick one at POST time

`Agent.AgentDefinition` is a discriminated union; an `Agent` carries **exactly
one** of:

1. **`a2aAgentDefinition`** (emitted here, in the body). The committed A2A card
   _is_ the contract — no deployed resource is required to register. Use this
   when the agent is reachable at the card's `url` (the per-agent
   `.well-known/agents/<id>/agent-card.json` endpoint).

2. **`adkAgentDefinition.provisionedReasoningEngine.reasoningEngine`** (the
   `_adkAgentDefinitionTemplate` block). Preferred once the Agent Engine deploy
   has run — it binds the agent to the deployed reasoning-engine resource. To use
   this variant, replace `a2aAgentDefinition` with the contents of
   `_adkAgentDefinitionTemplate` and substitute the deployed reasoning-engine
   resource name (the output of `make deploy-agent-engine`).

> **Grounding note.** The `Assistant`/`engines` parent hierarchy is confirmed in
> the Discovery Engine API docs (context7). The exact `Agent` sub-resource field
> names (`a2aAgentDefinition.jsonAgentCard`,
> `adkAgentDefinition.provisionedReasoningEngine`) are newer than the indexed
> snapshot; verify them against the current `discoveryengine` API for your
> target version before POSTing. The offline transform is intentionally
> conservative: the source A2A card is the load-bearing payload, and every
> environment-specific value is a documented `${...}` placeholder.

## Operator steps (live, not run here)

These run against live GCP with operator credentials — they are **not** part of
the hermetic build:

1. **Deploy the root graph** (optional, for the ADK-backed variant):
   `make deploy-agent-engine` → prints the reasoning-engine resource name.
2. **Create / pick an Assistant** under your Discovery Engine app
   (`engines/{engine}/assistants/{assistant}`).
3. For each `<id>.registration.json`: strip the `_`-prefixed keys, substitute the
   `${...}` placeholders (`GOOGLE_CLOUD_PROJECT`, `LOCATION`, `ENGINE_ID`,
   `ASSISTANT_ID`, and — for the ADK variant — `REASONING_ENGINE_ID`,
   `AUTHORIZATION_ID`), then POST to `{parent}/agents`.

The `${...}` placeholders are the only environment-specific values; nothing in
these artifacts hardcodes a live project, engine, or resource.
