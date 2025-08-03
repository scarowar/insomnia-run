#!/bin/bash
set -euo pipefail

echo "--- 🚦 Starting Insomnia Action Execution ---"

# Debug log function
debug_log() {
	if [[ ${DEBUG:-false} == "true" ]]; then
		echo "::debug::🐞 \"$1\""
	fi
}

# Error log function
error_log() {
	echo "::error::❌ \"$1\""
}

# Info log function
info_log() {
	echo "::notice::ℹ️ \"$1\""
}

echo "::group::🔍 Validating Required Arguments and Environment Variables"

# Accept the full command string as a single argument
if [[ $# -lt 1 ]]; then
	error_log "Missing required argument: Inso CLI command string"
	exit 1
fi
INSO_CMD="$1"

# Validate GITHUB_OUTPUT
if [[ -z ${GITHUB_OUTPUT-} ]]; then
	error_log "GITHUB_OUTPUT environment variable is not set."
	exit 1
fi

echo "✅ All required arguments are set."
echo "INSO_CMD=${INSO_CMD}"
echo "GITHUB_OUTPUT=${GITHUB_OUTPUT}"
echo "::endgroup::"

echo "::group::🛠️ Running Inso CLI Command"
debug_log "Running command: ${INSO_CMD}"
echo "✅ Inso CLI command: ${INSO_CMD}"
echo "::endgroup::"

echo "::group::🚀 Executing Inso CLI"
set +e
# Parse the command string into an array for safer execution
# This avoids eval and potential command injection vulnerabilities
read -ra INSO_CMD_ARRAY <<<"${INSO_CMD}"
OUTPUT=$("${INSO_CMD_ARRAY[@]}" 2>&1)
EXIT_CODE=$?
set -e
if [[ ${EXIT_CODE} -ne 0 ]]; then
	error_log "Inso CLI exited with code ${EXIT_CODE}. See output for details."
else
	echo "✅ Inso CLI executed successfully."
fi
echo "::endgroup::"

echo "::group::📤 Exporting Outputs for GitHub Action"
# Output to GITHUB_OUTPUT for subsequent steps to use
# Use a unique delimiter to prevent accidental termination if output contains "EOF"
HEREDOC_DELIMITER="INSOMNIA_OUTPUT_END_$(date +%s)_$$"
{
	echo "output<<${HEREDOC_DELIMITER}"
	echo "${OUTPUT}"
	echo "${HEREDOC_DELIMITER}"
	echo "exit_code=${EXIT_CODE}"
	echo "command_ran=${INSO_CMD}"
	echo "identifier_ran="
} >>"${GITHUB_OUTPUT}"
echo "✅ Output and exit code exported to GITHUB_OUTPUT."
echo "::endgroup::"

info_log "✅ Inso CLI execution complete."

echo "--- 🏁 Insomnia Action Execution Complete ---"

# The script's own exit code will determine the step's success (0 for success, non-zero for failure)
exit 0
