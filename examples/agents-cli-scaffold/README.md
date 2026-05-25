# agents-cli Scaffold Example

This directory demonstrates how Atelier integrates with Google's
[`agents-cli`](https://cloud.google.com/products/agent-development-kit) toolchain for scaffolding,
evaluation, and deployment.

## Prerequisites

```bash
# Install agents-cli (alpha — pin version for stability)
uvx google-agents-cli@latest setup

# Verify installation
agents-cli --version
```

## Round-Trip Workflow

### 1. Scaffold a new agent project

```bash
agents-cli create my-atelier-agent --prototype --yes
cd my-atelier-agent
```

### 2. Wire Atelier's ADK agent

Replace the generated `agent.py` with Atelier's agent definition.
See [`agent.py`](./agent.py) for a minimal example.

### 3. Configure the agent manifest

See [`agent.yaml`](./agent.yaml) for the Atelier-compatible configuration.

### 4. Local playground

```bash
agents-cli playground
# Opens http://localhost:8000 with the Agent Dev UI
```

### 5. Run evaluation

```bash
agents-cli eval run \
  --eval-set atelier-core/tests/eval/golden_set.json \
  --agent ./agent.py
```

### 6. Deploy to Cloud Run

```bash
agents-cli deploy \
  --project=atelier-build-2026 \
  --target=cloud_run \
  --service=atelier-api-staging \
  --region=us-central1
```

## File Structure

```
examples/agents-cli-scaffold/
├── README.md          # This file
├── agent.py           # Minimal Atelier agent definition
└── agent.yaml         # Agent manifest for agents-cli
```

## Notes

- `agents-cli` is currently in **alpha**. Pin the version in CI to avoid breaking changes.
- Atelier uses its own Terraform-based deployment (`atelier-deploy/`) for production.
  `agents-cli deploy` is a convenience wrapper for rapid prototyping.
- The `agent.yaml` format may change between `agents-cli` versions.
