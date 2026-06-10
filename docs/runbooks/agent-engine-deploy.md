# Agent Engine Deploy Runbook

End-to-end operator procedure for deploying Atelier to Vertex AI Agent Engine
and registering the 18 A2A agent cards in the Gemini Enterprise Agent Gallery,
so the native Scale > Deployments / Sessions / Memory and Optimize > Evaluation
/ Topology tabs populate in the Google Cloud Console.

Related documents: [`go-live.md`](go-live.md) (full production sequence),
[`rollback.md`](rollback.md) (recovery procedures).

Canonical coordinates: project `atelier-build-2026`, region `us-central1`.

---

## Prerequisites

### Tools

- `gcloud` CLI authenticated to `atelier-build-2026`:

  ```bash
  gcloud auth login
  gcloud auth application-default login
  gcloud config set project atelier-build-2026
  gcloud config set run/region us-central1
  ```

- Python 3.10 or 3.12 with `atelier-core` installed in `.venv`. Agent Engine
  requires one of these two versions; other minor versions are not supported by
  the Agent Engine sandbox.

  ```bash
  python --version   # must be 3.10.x or 3.12.x
  pip install -e "atelier-core/.[gcp,adk,dev]"
  ```

- The `google-adk` install must be on the `2.1.x` line (AT-002 pin). The deploy
  module's `validate_adk_pin()` gate enforces this and fails loud on any drift.

  ```bash
  python -c "import importlib.metadata; print(importlib.metadata.version('google-adk'))"
  # Expected: 2.1.x
  ```

### GCP APIs enabled (OPERATOR-GATED)

All API enablement requires live GCP credentials.

```bash
gcloud services enable \
  aiplatform.googleapis.com \
  storage.googleapis.com \
  --project=atelier-build-2026
```

Verify:

```bash
gcloud services list --enabled --project=atelier-build-2026 \
  --filter="name:(aiplatform.googleapis.com OR storage.googleapis.com)" \
  --format="value(name)"
```

Expected: both service names appear in the output.

### IAM roles required (OPERATOR-GATED)

| Task                         | Minimum role                                                             |
| ---------------------------- | ------------------------------------------------------------------------ |
| Agent Engine create / update | `roles/aiplatform.admin` on project `atelier-build-2026`                 |
| Staging bucket read/write    | `roles/storage.objectAdmin` on bucket `atelier-build-2026-agent-staging` |
| Agent Engine list / describe | `roles/aiplatform.viewer` (read-only verification)                       |

### Staging bucket (OPERATOR-GATED)

The deploy module uploads agent artifacts to a GCS staging bucket before the
Agent Engine runtime downloads and serves them. The bucket is referenced in
`agent_engine_deploy.py` as the default value for `ATELIER_STAGING_BUCKET`.

Create the bucket if it does not exist:

```bash
gcloud storage buckets create gs://atelier-build-2026-agent-staging \
  --project=atelier-build-2026 \
  --location=us-central1 \
  --uniform-bucket-level-access
```

Expected: `Creating gs://atelier-build-2026-agent-staging/...done.`

Skip if it already exists; `gsutil ls gs://atelier-build-2026-agent-staging`
confirms existence.

### Dependency requirements

`deployment_requirements()` in `atelier-core/src/atelier/agent_engine_deploy.py`
returns the four pinned packages that the Agent Engine sandbox must resolve:

```
google-adk>=2.1.0,<3
google-genai>=1.0,<3
google-cloud-aiplatform>=1.71,<2
pydantic>=2.6,<3
```

These are kept in lockstep with the AT-002 pins in `atelier-core/pyproject.toml`
and mirrored verbatim in `deploy/agent_engine_requirements.txt`. The sandbox
must resolve the same major versions as the verified build so the served agent
matches what was tested locally and in CI.

---

## Step 1: Pre-deploy verification (hermetic, no GCP)

Run the offline verification suite before touching the live project. This gate
is fully hermetic — no network, no GCP credentials required.

```bash
cd "$(git rev-parse --show-toplevel)"
make verify
```

Expected terminal output ends with:

```
[verify] OK - all enabled checks passed
```

A failure here means the local tree has a regression. Do not proceed to the live
deploy until `make verify` is clean.

---

## Step 2: Generate and confirm the 18 A2A agent-card artifacts

The 18 A2A agent cards committed under `atelier-core/agent_cards/` are the
registration artifacts the deploy step reads for the Agent Gallery. Confirm
they are current before deploying.

```bash
cd "$(git rev-parse --show-toplevel)"
python - <<'EOF'
from atelier.orchestrator.agent_cards import generate_committed_cards
written = generate_committed_cards()
print(f"Generated {len(written)} cards:")
for agent_id, path in sorted(written.items()):
    print(f"  {agent_id} -> {path.name}")
EOF
```

Expected: 18 lines, one per agent (planner, intake_brief_parser, 6 specialists,
5 D-O-R-A-V judges, 4 critics, fixer). Each card is written to
`atelier-core/agent_cards/{id}.agent-card.json`.

If the count is not 18 or a card generation error is logged, investigate the
agent registry before continuing — a missing card means the Gallery registration
will be incomplete.

---

## Step 3: Deploy to Vertex AI Agent Engine (OPERATOR-GATED)

This step calls `vertexai.agent_engines.create()` against live GCP. It requires
Application Default Credentials for `atelier-build-2026` and a live network
connection to the Vertex AI endpoint.

```bash
cd "$(git rev-parse --show-toplevel)"
export GOOGLE_CLOUD_PROJECT=atelier-build-2026
export GOOGLE_CLOUD_LOCATION=us-central1
make deploy-agent-engine
```

`make deploy-agent-engine` runs `deploy/preflight.sh` (named-reason readiness
probes) and then `deploy/agent_engine.sh`, which executes:

```bash
.venv/bin/python -m atelier.agent_engine_deploy
```

What `atelier.agent_engine_deploy` does:

1. Calls `validate_adk_pin()` — fails loud if `google-adk` is not `2.1.x`.
2. Calls `resolve_config()` — reads `GOOGLE_CLOUD_PROJECT`,
   `GOOGLE_CLOUD_LOCATION`, `ATELIER_AGENT_NAME` (default
   `atelier-root-engine`), `ATELIER_STAGING_BUCKET` (default
   `gs://atelier-build-2026-agent-staging`) from the environment.
3. Calls `build_agent_engine_app()` — the **hermetic** core (no network): builds
   the Atelier **root agent graph** via `build_root_agent()` and wraps it in
   `AdkApp(agent=root_agent, enable_tracing=True)`. ADK + Agent Engine deploy the
   root agent _and its reachable `sub_agents`_ as ONE app, so the deployed graph
   is the full coordinator, not a bare planner leaf:

   ```text
   atelier_root_coordinator (LlmAgent, root — no output_schema)
       ├─ brief_parser_llm        (LlmAgent leaf — output_schema=BriefSpec)
       ├─ DDLCSpecialistPipeline  (SequentialAgent of 6 specialists)
       ├─ QACritiquePanel         (ParallelAgent of 4 critics)
       └─ atelier_fixer           (LlmAgent leaf — output_schema=FixerDirective)
   ```

4. Calls `vertexai.init(project, location, staging_bucket)`.
5. Calls `vertexai.agent_engines.create(agent_engine=app,
display_name="atelier-root-engine", requirements=[...],
extra_packages=["."])` — uploads artifacts to the staging bucket and
   provisions the reasoning-engine resource.
6. Prints the resource name to stdout on success.

The split is deliberate: `build_agent_engine_app()` constructs the entire deploy
spec (root graph + `AdkApp` + create-kwargs) **without** calling `create()`, so
the whole configuration is unit-tested offline; `deploy_agent_engine()` is the
thin live wrapper that submits `app.app` to `create()`.

Expected terminal output (final lines):

```
[agent-engine] deploying planner: project=atelier-build-2026 location=us-central1
INFO  Deploying Atelier root graph to Agent Engine: project=atelier-build-2026 ... root=atelier_root_coordinator sub_agents=['brief_parser_llm', 'DDLCSpecialistPipeline', 'QACritiquePanel', 'atelier_fixer']
INFO  Agent Engine deploy complete. Resource name: projects/atelier-build-2026/locations/us-central1/reasoningEngines/<id>
[agent-engine] deployed resource_name=projects/atelier-build-2026/locations/us-central1/reasoningEngines/<id>
```

Record the resource name — it is needed in Step 4 and Step 5.

### Error handling

`deploy_agent_engine()` is fail-loud: any failure raises
`AgentEngineDeployError` and the shell wrapper exits non-zero. The deploy never
swallows errors silently. If the deploy fails:

1. Check the error message — the most common causes are a missing staging
   bucket, an expired ADC token, or a `google-adk` version drift.
2. For a version drift: reinstall the pinned ADK (`pip install -e "atelier-core/.[gcp,adk]"`)
   and retry.
3. For a bucket-not-found error: complete the staging bucket creation in the
   Prerequisites section and retry.
4. For persistent failures: see `rollback.md` Section 3.3.

---

## Step 4: Propagate the Agent Engine ID to Terraform and Cloud Run (OPERATOR-GATED)

Copy the resource name printed in Step 3 into `atelier-deploy/terraform/terraform.tfvars`
as `agent_engine_id`. Then re-apply Terraform so the Cloud Run service receives
the `AGENT_ENGINE_ID` environment variable that `resolve_config()` reads:

```bash
cd atelier-deploy/terraform
# Edit terraform.tfvars: set agent_engine_id = "<resource name from Step 3>"

terraform apply -var-file=terraform.tfvars
```

Expected: `Apply complete!` with the Cloud Run service revision updated.

After Terraform applies, the running Cloud Run service will expose
`agent_engine_id` in `/v1/platform/scale` (see Step 6 verification).

---

## Step 5: Agent Gallery registration — how the 18 cards register (OPERATOR-GATED)

The Gemini Enterprise Agent Gallery is populated through the Agent Engine
resource created in Step 3 and through explicit per-agent registration payloads
built from the 18 committed A2A cards.

### What the Agent Gallery uses

The Agent Gallery ingests three sources:

1. **The Agent Engine resource itself** (`atelier-root-engine`) — the
   `display_name` and `description` passed to `vertexai.agent_engines.create()`
   are indexed as the Gallery entry for the deployed root agent.

2. **The `/.well-known/agent-card.json` endpoint** on the live API — the Gallery
   crawls the well-known A2A discovery endpoint to enumerate the per-agent cards
   served at `https://atelier.autonomous-agent.dev/.well-known/agents/{id}/agent-card.json`.

3. **Explicit per-agent registration payloads** — the committed artifacts under
   `atelier-core/agent_cards/registration/`, one `<id>.registration.json` per
   card, are the `CreateAgent` request bodies an operator POSTs to register each
   agent as a Discovery Engine `Agent` resource under an Assistant
   (`engines/{engine}/assistants/{assistant}/agents`). These are produced offline
   by `atelier.orchestrator.agent_registration` — a pure card-in/payload-out
   transform, no network — and are regenerated with
   `python scripts/generate_agent_registrations.py`.

The 18 agent cards are served from the committed artifacts under
`atelier-core/agent_cards/` via the `app.py` lifespan loader. Each card carries
the standard A2A 0.3.0 schema (`name`, `description`, `version`,
`protocolVersion`, `url`, `provider`, `skills`, `protocols`,
`authentication`, `capabilities`).

### Posting the registration payloads (OPERATOR-GATED)

For the explicit-registration path, each `<id>.registration.json` is the
`CreateAgent` body. Before POSTing:

1. Strip the `_`-prefixed keys (`_target`, `_adkAgentDefinitionTemplate`,
   `_provenance`) — they are operator guidance / provenance, not request body.
2. Substitute the `${...}` placeholders (`GOOGLE_CLOUD_PROJECT`, `LOCATION`,
   `ENGINE_ID`, `ASSISTANT_ID`, and for the ADK-backed variant
   `REASONING_ENGINE_ID` from Step 3, `AUTHORIZATION_ID`).
3. Choose the definition variant: the emitted `a2aAgentDefinition` (the committed
   card inlined — no deployed resource needed), **or** swap in
   `_adkAgentDefinitionTemplate` and bind the Step 3 reasoning-engine resource
   (the preferred variant once the engine is deployed). The two are mutually
   exclusive — an `Agent` carries exactly one.
4. POST to `{parent}/agents`.

See `atelier-core/agent_cards/registration/README.md` for the full field map and
the grounding note on the `Agent.AgentDefinition` field names.

### Confirming Gallery registration (OPERATOR-GATED)

After the deploy and after the live API is serving (post Terraform apply and
Cloud Run revision traffic shift), confirm the Gallery entry is present in the
Google Cloud Console:

1. Navigate to Vertex AI > Agent Engine in the Cloud Console for project
   `atelier-build-2026`.
2. Confirm `atelier-root-engine` appears in the Deployments list with state
   `ACTIVE`.
3. Navigate to the Scale > Deployments tab for the resource — the Sessions and
   Memory sub-tabs populate once at least one session has been created against
   the live engine.
4. Navigate to Optimize > Evaluation — evaluation data populates after
   production-readiness runs complete (see `go-live.md` Step 6).
5. Navigate to Optimize > Topology — the static pipeline DAG (the 6 DDLC
   specialist nodes and their hand-off edges) is also available via
   `/v1/platform/topology` on the live API.

Note: the Scale > Sessions and Memory tabs and the Optimize > Evaluation tab
require at least one live session and one evaluation run respectively. They will
be empty until Step 6 verification (production-readiness) has been completed.

---

## Step 6: Verification (OPERATOR-GATED)

### 6.1 Confirm the Agent Engine is ACTIVE

```bash
gcloud ai reasoning-engines list \
  --project=atelier-build-2026 \
  --region=us-central1 \
  --filter="displayName=atelier-root-engine" \
  --format="table(name,displayName,state)"
```

Expected: one row with `state` = `ACTIVE`.

### 6.2 Confirm the resource name via /v1/platform/scale

After the Cloud Run service is updated with the `AGENT_ENGINE_ID` environment
variable (Step 4):

```bash
SVCURL=$(gcloud run services describe atelier-api \
  --region=us-central1 \
  --project=atelier-build-2026 \
  --format="value(status.url)")

curl -s "${SVCURL}/v1/platform/scale" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  | python -m json.tool | grep -A 5 '"deploy_config"'
```

Expected:

```json
"deploy_config": {
  "available": true,
  "project": "atelier-build-2026",
  "location": "us-central1",
  "display_name": "atelier-root-engine",
  ...
}
```

`available: true` confirms `resolve_config()` resolved successfully and the
`AGENT_ENGINE_ID` environment variable is present in the running service.

### 6.3 Confirm the 18 agent cards are reachable

```bash
curl -s "https://atelier.autonomous-agent.dev/.well-known/agent-card.json" \
  | python -m json.tool | grep '"name"'
```

Expected: the top-level card name for `atelier-root-engine`.

Spot-check one per-agent card:

```bash
curl -s "https://atelier.autonomous-agent.dev/.well-known/agents/planner/agent-card.json" \
  | python -m json.tool | grep '"protocolVersion"'
# Expected: "protocolVersion": "0.3.0"
```

### 6.4 Confirm /v1/platform/agents reports 18 agents

```bash
curl -s "${SVCURL}/v1/platform/agents" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  | python -m json.tool | grep '"count"'
# Expected: "count": 18
```

---

## Environment variable reference

| Variable                    | Default                                 | Effect                                                 |
| --------------------------- | --------------------------------------- | ------------------------------------------------------ |
| `GOOGLE_CLOUD_PROJECT`      | `atelier-build-2026`                    | GCP project for `vertexai.init` and the staging bucket |
| `GOOGLE_CLOUD_LOCATION`     | `us-central1`                           | Vertex AI region                                       |
| `ATELIER_AGENT_NAME`        | `atelier-root-engine`                   | `display_name` passed to `agent_engines.create`        |
| `ATELIER_AGENT_DESCRIPTION` | `Atelier hybrid-runtime planner agent`  | `description` passed to `agent_engines.create`         |
| `ATELIER_STAGING_BUCKET`    | `gs://atelier-build-2026-agent-staging` | GCS bucket for artifact upload during deploy           |

---

## Step summary

| #   | Step                                   | Command                                   | GCP credentials required | Reversible                       |
| --- | -------------------------------------- | ----------------------------------------- | ------------------------ | -------------------------------- |
| 0   | Prerequisites: APIs, IAM, bucket       | `gcloud services enable ...`              | yes                      | n/a                              |
| 1   | Pre-deploy hermetic verification       | `make verify`                             | no                       | yes                              |
| 2   | Generate/confirm 18 agent cards        | `python generate_committed_cards()`       | no                       | yes                              |
| 3   | Deploy to Agent Engine                 | `make deploy-agent-engine`                | yes                      | redeploy or see rollback.md §3.3 |
| 4   | Propagate Agent Engine ID to Terraform | `terraform apply`                         | yes                      | redeploy                         |
| 5   | Agent Gallery registration             | automatic on deploy + live API            | yes (live API)           | n/a                              |
| 6   | Verification                           | `gcloud ai reasoning-engines list` + curl | yes                      | n/a                              |

---

## Relation to the go-live sequence

This runbook covers Step 3 of [`go-live.md`](go-live.md) in full detail.
The go-live runbook references `make deploy-agent-engine` as a single line;
this document is the complete operator reference for that step, including the
prerequisites, the artifact generation, the Gallery registration mechanism, and
post-deploy verification. After completing the verification in Section 6 above,
return to `go-live.md` Step 4 to continue the full production sequence.
