#!/usr/bin/env bash
# Runs the evaluation suite inside the Hermes environment against this repo's profile.
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERMES_SRC="${HERMES_SRC:-$HOME/.hermes/hermes-agent}"
cd "$REPO_DIR/evals"
HERMES_HOME="${HERMES_HOME:-$REPO_DIR/profile}" PYTHONPATH="$HERMES_SRC" \
    "$HERMES_SRC/venv/bin/python" run_suite.py "$@"
