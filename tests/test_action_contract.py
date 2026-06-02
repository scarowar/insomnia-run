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


def test_action_does_not_install_uv_at_runtime():
    action = ACTION_YAML.read_text()

    assert "astral-sh/setup-uv" not in action
    assert "uv pip install" not in action
    assert "python3 -m venv" in action
    assert "GITHUB_PATH" not in action
    assert (
        'INSOMNIA_RUN_BIN="${RUNNER_TEMP}/insomnia-run-venv/bin/insomnia-run"' in action
    )


def test_action_uses_official_inso_setup_without_manual_download():
    action = load_action()
    action_text = ACTION_YAML.read_text()
    detect_step = step_by_name(action, "Detect Inso CLI")
    setup_step = step_by_name(action, "Setup Inso CLI")

    assert "command -v inso" in detect_step["run"]
    assert setup_step["if"] == "steps.detect-inso.outputs.found != 'true'"
    assert (
        setup_step["uses"] == "Kong/setup-inso@33b1006a5c2ae15364fc18146ec900b7db3c675e"
    )
    assert setup_step["with"]["inso-version"] == "${{ inputs.inso-version }}"
    assert "install-inso" not in action["inputs"]
    assert "curl -sL" not in action_text
    assert "sudo mv" not in action_text


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
    assert 'JUNIT_FILE="${RUNNER_TEMP}/insomnia-run-junit.xml"' in action_text
    assert 'CMD+=(--junit-output "$JUNIT_FILE")' in action_text
    assert "junit-file=$JUNIT_FILE" in action_text


def test_action_keeps_inso_config_auto_detected():
    action = load_action()

    assert "config-file" not in action["inputs"]
    assert "insorc" not in ACTION_YAML.read_text().lower()
