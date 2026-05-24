# Phoenix Tracing Integration Guide

## Overview

Atelier uses **Arize Phoenix** for AI agent observability during
development and evaluation. In production, traces flow to **Google
Cloud Trace** via the OTel collector (`config/otel-collector-config.yaml`).

Phoenix is used in the development loop for:

- Tracing LLM calls (Gemini 2.5 Flash) through the pipeline
- Visualizing judge scoring distributions in the consensus agent
- Debugging trajectory recording and DPO pair extraction
- Monitoring token consumption and cost per surface

## Local development observability

### Why Phoenix is dev-only (ADR 0006)

Per [ADR 0006](../../docs/decisions/0006-google-native-stack.md), Atelier
uses a Google-native observability stack in production: Cloud Trace for
distributed tracing and Cloud Monitoring for metrics. Phoenix is excluded
from production because it would create a parallel trace sink that
diverges from the production pipeline, complicating incident response and
violating the single-source-of-truth principle for trace data.

### Environment variable: `ATELIER_OBSERVABILITY_MODE`

The `ATELIER_OBSERVABILITY_MODE` environment variable controls which
observability backend is active:

| Value           | Backend                         | Use case                            |
| --------------- | ------------------------------- | ----------------------------------- |
| `dev` (default) | Phoenix (Arize)                 | Local development, trace inspection |
| `prod`          | Google Cloud Trace + Monitoring | Staging and production on Cloud Run |

Set it in your shell or `.env` file:

```bash
# Local development (default — Phoenix)
export ATELIER_OBSERVABILITY_MODE=dev

# Production / staging (Cloud Trace)
export ATELIER_OBSERVABILITY_MODE=prod
```

The flag is read by `atelier.observability.get_observability_mode()` and
used to conditionally mount the Phoenix or Cloud Trace exporter in the
OTel pipeline. Unrecognized values emit a warning and fall back to `dev`.

### Phase-1 limitation

In Phase 1, the OTel collector pipeline (`config/otel-collector-config.yaml`)
statically includes BOTH Phoenix and Google Cloud exporters. The
`ATELIER_OBSERVABILITY_MODE` env var is read by `atelier.observability` but
does not yet control exporter selection — tracked as F0223 for Phase 2
wiring.

For Phase-1 testing: setting `MODE=prod` will not actually suppress Phoenix
traces; the collector will still forward to both backends. This is
operationally harmless (double-send overhead) but not the intended
production behavior.

### Starting Phoenix locally

```bash
# Option 1: pip install (lightweight)
pip install arize-phoenix
phoenix serve --port 6006

# Option 2: Docker (isolated)
docker run -d --name phoenix -p 6006:6006 arizephoenix/phoenix:latest
```

The Phoenix UI is available at `http://localhost:6006`.

## Architecture

```
Agent Pipeline
    │
    ├─[OTel SDK]──→ OTel Collector (config/otel-collector-config.yaml)
    │                   │
    │                   ├─→ Google Cloud Trace (production)
    │                   └─→ Phoenix (development)
    │
    └─[TrajectoryRecorder]──→ BigQuery (trajectory_records table)
```

## Setup (Development)

### 1. Install Phoenix

```bash
pip install arize-phoenix
```

### 2. Start the Phoenix server

```bash
phoenix serve --port 6006
```

The UI is available at `http://localhost:6006`.

### 3. Configure the OTel Collector for Development

The `config/otel-collector-config.yaml` includes a commented-out
development exporter. To enable Phoenix locally:

```yaml
exporters:
  otlp/phoenix:
    endpoint: 'http://localhost:4317'
    tls:
      insecure: true
```

Add the exporter to the traces pipeline:

```yaml
service:
  pipelines:
    traces:
      exporters: [otlp/phoenix]
```

### 4. Instrument the Agent

The agent automatically emits spans via the `TracerProtocol` interface.
In development, configure the tracer to point to the local collector:

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)

provider = TracerProvider()
exporter = OTLPSpanExporter(endpoint="http://localhost:4317", insecure=True)
provider.add_span_processor(BatchSpanProcessor(exporter))
trace.set_tracer_provider(provider)
```

## Key Spans

| Span Name                    | Module                             | Description                 |
| ---------------------------- | ---------------------------------- | --------------------------- |
| `atelier.trajectory.flush`   | `recorders/trajectory_recorder.py` | BQ streaming insert         |
| `atelier.consensus.evaluate` | `nodes/consensus.py`               | D-O-R-A-V composite scoring |
| `atelier.generator.generate` | `nodes/generator.py`               | UI artifact generation      |
| `atelier.gate.check`         | `nodes/gate.py`                    | Deterministic gate battery  |

## Production Setup

In production, traces flow to Google Cloud Trace via the
`googlecloud` exporter in the OTel collector. See
`config/otel-collector-config.yaml` for the full configuration.

The collector runs as a sidecar container in Cloud Run, configured
via the Terraform module in `infra/terraform/modules/cloud-run/`.

## PRD Reference

- §8 (Observability stack)
- §6.3 N3h (Trajectory Logger)

## ADR Reference

- ADR-0006: Google-native stack — BigQuery for telemetry
- ADR-0008: OTel collector with Google Cloud exporter
