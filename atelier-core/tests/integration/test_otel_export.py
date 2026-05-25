from __future__ import annotations

from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_otel_collector_config_valid() -> None:
    with (_REPO_ROOT / "config" / "otel-collector-config.yaml").open() as f:
        data = yaml.safe_load(f)

    assert data["receivers"]["otlp"]["protocols"]["grpc"]["endpoint"] == "0.0.0.0:4317"
    assert data["processors"]["resource"]["attributes"][0]["value"] == "atelier"
    assert data["exporters"]["googlecloud"]["project"] == "atelier-build-2026"
