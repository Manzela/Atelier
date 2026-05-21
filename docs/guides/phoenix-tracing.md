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
    endpoint: "http://localhost:4317"
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

| Span Name | Module | Description |
|-----------|--------|-------------|
| `atelier.trajectory.flush` | `recorders/trajectory_recorder.py` | BQ streaming insert |
| `atelier.consensus.evaluate` | `nodes/consensus.py` | D-O-R-A-V composite scoring |
| `atelier.generator.generate` | `nodes/generator.py` | UI artifact generation |
| `atelier.gate.check` | `nodes/gate.py` | Deterministic gate battery |

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
