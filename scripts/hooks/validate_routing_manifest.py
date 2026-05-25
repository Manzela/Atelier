#!/usr/bin/env python3
"""Validate infra/routing/manifest.yaml against infra/routing/routing_manifest.schema.json.

Pre-commit hook — run with pass_filenames: false.
Exits 0 (pass) if the manifest is valid or not present.
Exits 1 (fail) if the manifest fails schema validation.
"""

import json
import sys

try:
    import jsonschema
    import yaml
except ImportError:
    print("SKIP: pyyaml or jsonschema not installed")
    sys.exit(0)

from pathlib import Path

manifest_path = Path("infra/routing/manifest.yaml")
schema_path = Path("infra/routing/routing_manifest.schema.json")

if not manifest_path.exists() or not schema_path.exists():
    print("SKIP: manifest or schema file not found")
    sys.exit(0)

manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
schema = json.loads(schema_path.read_text(encoding="utf-8"))

try:
    jsonschema.validate(instance=manifest, schema=schema)
    print("Routing manifest validates against schema OK")
except jsonschema.ValidationError as e:
    print(f"ERROR: Routing manifest fails schema validation: {e.message}")
    sys.exit(1)
