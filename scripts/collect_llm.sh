#!/usr/bin/env bash
# Pull UC-040 JSONL files from UBELIX into the evaluation checkout.
set -euo pipefail

: "${UBELIX_LLM_SOURCE:?Set UBELIX_LLM_SOURCE to user@host:/path/to/checkout/data/interim/llm}"
cd "$(dirname "${BASH_SOURCE[0]}")/.."
destination=${LLM_COLLECT_DIR:-data/interim/llm}
mkdir -p "$destination"
rsync -av --include='*/' --include='*.jsonl' --exclude='*' -- \
    "${UBELIX_LLM_SOURCE%/}/" "$destination/"
