#!/usr/bin/env bash
# download_design2code.sh — Download the Design2Code dataset
# Dataset: https://github.com/SALT-NLP/Design2Code
# License: CC BY 4.0
# Size: ~2 GB (484 webpages with HTML + screenshots)
#
# Usage: ./scripts/eval/download_design2code.sh [DATA_DIR]

set -euo pipefail

DATA_DIR="${1:-atelier-eval/data/design2code}"

if [[ -d "$DATA_DIR" && -f "$DATA_DIR/manifest.json" ]]; then
  echo "✓ Design2Code already present at $DATA_DIR"
  exit 0
fi

mkdir -p "$DATA_DIR"

echo "Design2Code dataset download instructions:"
echo ""
echo "  Option A (GitHub):"
echo "    git clone --depth=1 https://github.com/SALT-NLP/Design2Code $DATA_DIR"
echo ""
echo "  Option B (HuggingFace):"
echo "    huggingface-cli download SALT-NLP/Design2Code --local-dir $DATA_DIR"
echo ""
echo "Dataset: 484 webpages, CC BY 4.0, ~2 GB"
echo "After download, verify: ls $DATA_DIR/manifest.json"

exit 0
