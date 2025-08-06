#!/bin/bash
set -euo pipefail

echo "--- 🚦 Starting Insomnia Action Execution ---"

debug_log() {
	if [[ ${DEBUG:-false} == "true" ]]; then
		echo "::debug::🐞 \"$1\""
	fi
}

error_log() {
	echo "::error::❌ \"$1\""
}

info_log() {
	echo "::notice::ℹ️ \"$1\""
}

echo "::group::🔍 Validating Required Arguments and Environment Variables"

if [[ $# -lt 1 ]]; then
	error_log "Missing required argument: Inso CLI command string"
	exit 1
fi
INSO_CMD="$1"

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
OUTPUT=$(bash -c "${INSO_CMD}" 2>&1)
EXIT_CODE=$?
set -e
if [[ ${EXIT_CODE} -ne 0 ]]; then
	error_log "Inso CLI exited with code ${EXIT_CODE}. See output for details."
else
	echo "✅ Inso CLI executed successfully."
fi
echo "::endgroup::"

echo "::group::📤 Exporting Outputs for GitHub Action"

HEREDOC_DELIMITER="INSOMNIA_OUTPUT_END_$(date +%s)_$$"
{
	echo "output<<${HEREDOC_DELIMITER}"
	echo "${OUTPUT}"
	echo "${HEREDOC_DELIMITER}"
	echo "exit_code=${EXIT_CODE}"
	echo "command_ran=${INSO_CMD}"
	echo "identifier_ran=${INPUT_IDENTIFIER_RAN:-}"
} >>"${GITHUB_OUTPUT}"
echo "✅ Output and exit code exported to GITHUB_OUTPUT."
echo "::endgroup::"

info_log "✅ Inso CLI execution complete."

echo "--- 🏁 Insomnia Action Execution Complete ---"

exit 0
