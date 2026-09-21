#!/usr/bin/env bash
# Runs a simulated consultation inside the Hermes environment against this repo's profile.
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERMES_SRC="${HERMES_SRC:-$HOME/.hermes/hermes-agent}"
HERMES_HOME="${HERMES_HOME:-$REPO_DIR/profile}" PYTHONPATH="$HERMES_SRC" \
    "$HERMES_SRC/venv/bin/python" "$REPO_DIR/evals/converse.py" "${1:-$REPO_DIR/evals/scenarios/sem-forno.yaml}"
