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

# The official installer clones the repository; without the checkout there is nothing to pin.
if [ ! -d "${HERMES_SRC}/.git" ]; then
    echo "${HERMES_SRC} is not a git checkout; cannot pin Hermes to ${HERMES_COMMIT}" >&2
    exit 1
fi
git -C "${HERMES_SRC}" fetch -q origin
git -C "${HERMES_SRC}" checkout -q "${HERMES_COMMIT}"
# The official installer resolves dependencies for whatever commit it cloned; the pinned
# commit may declare different ones.
"${HOME}/.hermes/bin/uv" pip install --quiet --python "${HERMES_SRC}/venv/bin/python" -e "${HERMES_SRC}"

# A second run updates the installed profile in place: distribution files and config are
# replaced, while sessions, memories and .env are kept.
if hermes profile list 2>/dev/null | grep -q "sabor-da-maria"; then
    hermes profile update sabor-da-maria --force-config --yes
else
    hermes profile install "${REPO_DIR}/profile" --name sabor-da-maria --alias --yes
fi
# config.yaml already lists the plugin as enabled; this command is what installs its
# dependencies (openpyxl, pydantic, pyyaml) into the Hermes environment.
HERMES_HOME="${HOME}/.hermes/profiles/sabor-da-maria" hermes plugins enable menu_costing

# The bundled Langfuse plugin declares no dependency on the SDK. Hermes installs optional SDKs
# into its own environment with its managed uv; v4 is the SDK current Langfuse organizations accept.
# The Anthropic SDK is for the evaluation suite's judge, which runs in the same environment.
"${HOME}/.hermes/bin/uv" pip install --quiet --python "${HERMES_SRC}/venv/bin/python" \
    "langfuse>=4,<5" "anthropic>=1,<2"

cat <<MSG

Profile installed. Fill in the keys and start:
  cp "${REPO_DIR}/profile/.env.example" "${HOME}/.hermes/profiles/sabor-da-maria/.env"
  sabor-da-maria chat
MSG
