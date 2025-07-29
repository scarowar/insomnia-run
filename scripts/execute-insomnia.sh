#!/bin/bash
set -euo pipefail

echo "--- 🚦 Starting Insomnia Action Execution ---"

# Debug log function
debug_log() {
  if [[ "${DEBUG:-false}" == "true" ]]; then
    echo "::debug::🐞 $1"
  fi
}

# Error log function
error_log() {
  echo "::error::❌ $1"
}

# Info log function
info_log() {
  echo "::notice::ℹ️ $1"
}

echo "::group::🔍 Validating Required Arguments and Environment Variables"

# Accept the full command string as a single argument
if [ $# -lt 1 ]; then error_log "Missing required argument: Inso CLI command string"; exit 1; fi
INSO_CMD="$1"

# Validate GITHUB_OUTPUT
if [ -z "${GITHUB_OUTPUT:-}" ]; then error_log "GITHUB_OUTPUT environment variable is not set."; exit 1; fi

echo "✅ All required arguments are set."
echo "INSO_CMD=$INSO_CMD"
echo "GITHUB_OUTPUT=$GITHUB_OUTPUT"
echo "::endgroup::"

echo "::group::🔒 Masking Secrets (if any)"
if [ -n "${SECRETS_JSON:-}" ]; then
  MASKED=$(python3 -c 'import os, json; secrets=json.loads(os.environ["SECRETS_JSON"]); print("\n".join(secrets.values()))')
  while IFS= read -r secret; do
    if [ -n "$secret" ]; then
      echo "::add-mask::$secret"
    fi
  done <<< "$MASKED"
  echo "✅ All provided secrets masked."
else
  echo "ℹ️ No secrets provided to mask."
fi
echo "::endgroup::"

echo "::group::🛠️ Running Inso CLI Command"
debug_log "Running command: $INSO_CMD"
echo "✅ Inso CLI command: $INSO_CMD"
echo "::endgroup::"

echo "::group::🚀 Executing Inso CLI"
set +e
OUTPUT=$(eval "$INSO_CMD" 2>&1)
EXIT_CODE=$?
set -e
if [ $EXIT_CODE -ne 0 ]; then
  error_log "Inso CLI exited with code $EXIT_CODE. See output for details."
else
  echo "✅ Inso CLI executed successfully."
fi
echo "::endgroup::"

echo "::group::📤 Exporting Outputs for GitHub Action"
# Output to GITHUB_OUTPUT for subsequent steps to use
{
  echo "output<<EOF"
  echo "$OUTPUT"
  echo "EOF"
  echo "exit_code=$EXIT_CODE"
  echo "command_ran=$INSO_CMD"
  echo "identifier_ran="
} >> "$GITHUB_OUTPUT"
echo "✅ Output and exit code exported to GITHUB_OUTPUT."
echo "::endgroup::"

info_log "✅ Inso CLI execution complete."

echo "--- 🏁 Insomnia Action Execution Complete ---"

# The script's own exit code will determine the step's success (0 for success, non-zero for failure)
exit 0