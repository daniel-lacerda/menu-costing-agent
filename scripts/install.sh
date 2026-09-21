#!/usr/bin/env bash
# Installs Hermes Agent at the version this profile was built against and installs the profile
# as a named Hermes profile with a `sabor-da-maria` command. Idempotent.
set -euo pipefail

HERMES_COMMIT="6a627e6eb38e28ac421d5ad8df3f676e49d0c287"   # v0.21.3 (2026.9.14)
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERMES_SRC="${HOME}/.hermes/hermes-agent"

if ! command -v hermes >/dev/null 2>&1; then
    curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
    export PATH="${HOME}/.local/bin:${PATH}"
fi

if [ -d "${HERMES_SRC}/.git" ]; then
    git -C "${HERMES_SRC}" fetch -q origin
    git -C "${HERMES_SRC}" checkout -q "${HERMES_COMMIT}"
fi

hermes profile install "${REPO_DIR}/profile" --name sabor-da-maria --alias --yes
HERMES_HOME="${HOME}/.hermes/profiles/sabor-da-maria" hermes plugins enable menu_costing

# The bundled Langfuse plugin targets SDK v3 and declares no dependency; Hermes installs optional
# SDKs into its own environment with its managed uv, so do the same here.
"${HOME}/.hermes/bin/uv" pip install --quiet --python "${HERMES_SRC}/venv/bin/python" "langfuse>=3,<4"

cat <<MSG

Profile installed. Fill in the keys and start:
  cp "${REPO_DIR}/profile/.env.example" "${HOME}/.hermes/profiles/sabor-da-maria/.env"
  sabor-da-maria chat
MSG
