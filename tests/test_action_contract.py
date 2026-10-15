from pathlib import Path

import yaml


ACTION_YAML = Path(__file__).resolve().parents[1] / "action.yml"


def load_action():
    return yaml.safe_load(ACTION_YAML.read_text())


def step_by_name(action, name):
    for step in action["runs"]["steps"]:
        if step.get("name") == name:
            return step
    raise AssertionError(f"Missing action step: {name}")


def test_action_bootstraps_uv_from_the_pinned_toolchain():
    action = ACTION_YAML.read_text()

    assert "astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b" in action
    assert "uv pip install --no-build --no-deps --no-index" in action
    assert (
        "uv sync --frozen --no-dev --no-build --no-install-project --project" in action
    )
    assert "python3 -m venv" not in action
    assert (
        'INSOMNIA_RUN_BIN="${RUNNER_TEMP}/insomnia-run-venv/bin/insomnia-run"' in action
    )


def test_action_installs_inso_from_official_release_assets():
    action = load_action()
    action_text = ACTION_YAML.read_text()
    validate_step = step_by_name(action, "Validate Inso Version")
    detect_step = step_by_name(action, "Detect Inso CLI")
    install_step = step_by_name(action, "Install Inso CLI")

    assert validate_step["env"]["INSO_VERSION"] == "${{ inputs.inso-version }}"
    assert "Invalid Inso CLI version" in validate_step["run"]
    assert "command -v inso" in detect_step["run"]
    assert 'mkdir -p "${HOME}/.cache/pkg"' in detect_step["run"]
    assert detect_step["env"]["INSO_VERSION"] == "${{ inputs.inso-version }}"
    assert "BASH_REMATCH" in detect_step["run"]
    assert "does not match requested version" in detect_step["run"]
    assert install_step["if"] == "steps.detect-inso.outputs.found != 'true'"
    assert install_step["env"]["INSO_VERSION"] == "${{ inputs.inso-version }}"
    assert "install-inso" not in action["inputs"]
    assert "Kong/setup-inso" not in action_text
    assert "core%40${INSO_VERSION}" in install_step["run"]
    assert "inso-${platform}-${INSO_VERSION}.${archive}" in install_step["run"]
    assert (
        "curl --proto '=https' --proto-redir '=https' -fsSL --retry 3 --retry-all-errors"
        in install_step["run"]
    )
    assert 'mkdir -p "${HOME}/.cache/pkg"' in install_step["run"]
    assert "${RUNNER_TEMP}/insomnia-run-inso/bin" in install_step["run"]
    assert "GITHUB_PATH" not in action_text
    assert "sudo mv" not in action_text

    verify_step = step_by_name(action, "Verify Inso CLI")
    assert 'mkdir -p "${HOME}/.cache/pkg"' in verify_step["run"]
    assert verify_step["env"]["INSO_VERSION"] == "${{ inputs.inso-version }}"
    assert "version mismatch" in verify_step["run"]


def test_action_bootstraps_uv_with_lockfile_and_rate_limit_safeguards():
    action = load_action()
    check_step = step_by_name(action, "Check uv")
    setup_step = step_by_name(action, "Setup uv")
    install_step = step_by_name(action, "Install insomnia-run")

    assert check_step["env"]["INSOMNIA_RUN_UV_VERSION"] == "0.11.11"
    assert "command -v uv" in check_step["run"]
    assert "uv --version" in check_step["run"]
    assert "needs-setup=${needs_setup}" in check_step["run"]

    assert setup_step["if"] == "steps.check-uv.outputs.needs-setup == 'true'"
    assert setup_step["uses"] == (
        "astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b"
    )
    assert setup_step["with"]["version"] == "0.11.11"
    assert setup_step["with"]["working-directory"] == "${{ github.action_path }}"
    assert (
        "github.server_url == 'https://github.com'"
        in setup_step["with"]["github-token"]
    )
    assert "inputs.github-token" in setup_step["with"]["github-token"]
    assert "github.token" in setup_step["with"]["github-token"]
    assert "github.event_name != 'issue_comment'" in setup_step["with"]["save-cache"]
    assert (
        "github.event_name != 'pull_request_target'" in setup_step["with"]["save-cache"]
    )

    assert install_step["env"]["ACTION_PATH"] == "${{ github.action_path }}"
    assert (
        install_step["env"]["INSOMNIA_RUN_VENV"]
        == "${{ runner.temp }}/insomnia-run-venv"
    )
    assert (
        'uv venv --no-project --no-python-downloads --python "$python_path"'
        in install_step["run"]
    )
    assert 'UV_PROJECT_ENVIRONMENT="${INSOMNIA_RUN_VENV}"' in install_step["run"]
    assert (
        'uv sync --frozen --no-dev --no-build --no-install-project --project "${ACTION_PATH}"'
        in install_step["run"]
    )
    assert 'uv build --wheel --project "${ACTION_PATH}"' in install_step["run"]
    assert "uv pip install --no-build --no-deps --no-index" in install_step["run"]


def test_action_defaults_to_latest_verified_inso_release():
    action = load_action()

    assert action["inputs"]["inso-version"]["default"] == "13.3.1"


def test_action_does_not_echo_full_command():
    action = ACTION_YAML.read_text()

    assert 'echo "Executing: ${CMD[*]}"' not in action
    assert "Executing insomnia-run for command" in action


def test_action_supports_explicit_comment_targeting():
    action = load_action()
    comment_step = step_by_name(action, "Post PR Comment")

    assert "comment-issue-number" in action["inputs"]
    assert comment_step["if"] == (
        "inputs.pr-comment == 'true' && "
        "(github.event_name == 'pull_request' || inputs.comment-issue-number != '')"
    )
    assert (
        comment_step["with"]["issue-number"]
        == "${{ inputs.comment-issue-number || github.event.pull_request.number }}"
    )


def test_action_generates_junit_report_file():
    action = load_action()
    action_text = ACTION_YAML.read_text()

    assert action["inputs"]["junit-report"]["default"] == "true"
    assert "junit-output-file" in action["inputs"]
    assert action["outputs"]["junit-file"]["value"] == (
        "${{ steps.run-cli.outputs.junit-file }}"
    )
    assert 'JUNIT_FILE="${REPORT_DIR}/junit.xml"' in action_text
    assert 'CMD+=(--junit-output "$JUNIT_FILE")' in action_text
    assert "junit-file=$JUNIT_FILE" in action_text


def test_action_keeps_inso_config_auto_detected():
    action = load_action()

    assert "config-file" not in action["inputs"]
    assert "insorc" not in ACTION_YAML.read_text().lower()
