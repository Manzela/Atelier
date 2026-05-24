#!/usr/bin/env bash
# download_web2code.sh — Download the Web2Code dataset
# Dataset: https://huggingface.co/datasets/MBZUAI/Web2Code
# License: Apache 2.0
# Size: ~500 MB (web page + code pairs)
#
# Usage: ./scripts/eval/download_web2code.sh [DATA_DIR]

set -euo pipefail

DATA_DIR="${1:-atelier-eval/data/web2code}"

if [[ -d "$DATA_DIR" && -f "$DATA_DIR/manifest.json" ]]; then
  echo "✓ Web2Code already present at $DATA_DIR"
  exit 0
fi

mkdir -p "$DATA_DIR"

echo "Web2Code dataset download instructions:"
echo ""
echo "  Option A (HuggingFace CLI):"
echo "    huggingface-cli download MBZUAI/Web2Code --local-dir $DATA_DIR"
echo ""
echo "  Option B (Python):"
echo "    python -c \"from datasets import load_dataset; ds = load_dataset('MBZUAI/Web2Code'); ds.save_to_disk('$DATA_DIR')\""
echo ""
echo "Dataset: web page + code pairs, Apache 2.0, ~500 MB"
echo "After download, verify: ls $DATA_DIR/manifest.json"

exit 0
