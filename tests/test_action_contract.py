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
    action_text = ACTION_YAML.read_text()

    assert "astral-sh/setup-uv" not in action_text
    assert "uv pip install" not in action_text
    assert "uv" not in action_text
    assert "python3 -m venv" in action_text
    assert 'VENV="${RUNNER_TEMP}/insomnia-run-venv"' in action_text
    assert '"${VENV}/bin/python" -m pip install' in action_text


def test_action_installs_inso_from_official_release_assets():
    action = load_action()
    action_text = ACTION_YAML.read_text()
    detect_step = step_by_name(action, "🔍 Detect preinstalled Inso")
    install_step = step_by_name(action, "🧰 Install Inso CLI")
    verify_step = step_by_name(action, "✅ Verify Inso CLI")

    assert "command -v inso" in detect_step["run"]
    assert install_step["if"] == "steps.detect-inso.outputs.needs-setup == 'true'"
    assert install_step["env"]["INSO_VERSION"] == "${{ inputs.inso-version }}"
    assert "Kong/setup-inso" not in action_text
    assert "core%40${INSO_VERSION}" in install_step["run"]
    assert "inso-linux-x64-${INSO_VERSION}.tar.xz" in install_step["run"]
    # Upstream publishes no checksum manifest; known versions must verify
    # against the pinned digest.
    assert "EXPECTED_SHA256" in install_step["run"]
    assert "sha256sum" in install_step["run"]
    assert "x86_64" in install_step["run"]  # x64-only: no arm64 assets upstream
    assert "aarch64" not in install_step["run"]
    assert "curl -sSL --fail --retry 3" in install_step["run"]
    assert "${RUNNER_TEMP}/inso" in install_step["run"]
    assert "sudo mv" not in action_text
    assert "inso --version" in verify_step["run"]
    assert "version mismatch" in verify_step["run"]


def test_action_defaults_to_inso_13_2_0():
    action = load_action()

    assert action["inputs"]["inso-version"]["default"] == "13.2.0"


def test_action_does_not_echo_full_command():
    action_text = ACTION_YAML.read_text()

    assert 'echo "Executing:' not in action_text
    assert "::group::Running Insomnia" in action_text


def test_action_supports_idempotent_pr_comments_with_comment_tag():
    action = load_action()
    comment_step = step_by_name(action, "💬 Post PR Comment")

    assert action["inputs"]["pr-comment"]["default"] == "true"
    assert action["inputs"]["comment-tag"]["default"] == "insomnia-run-report"
    assert comment_step["if"] == (
        "inputs.pr-comment == 'true' && github.event_name == 'pull_request'"
    )
    assert comment_step["with"]["comment-tag"] == "${{ inputs.comment-tag }}"
    assert comment_step["with"]["body"] == "${{ steps.run-cli.outputs.markdown }}"


def test_action_generates_junit_report_file():
    action = load_action()
    action_text = ACTION_YAML.read_text()

    assert action["inputs"]["junit-output"]["default"] == ""
    assert action["outputs"]["junit-path"]["value"] == ("${{ steps.run-cli.outputs.junit-path }}")
    assert 'CMD+=(--junit-output "$JUNIT_PATH")' in action_text
    assert "junit-path=$JUNIT_PATH" in action_text


def test_action_upload_report_is_opt_in():
    action = load_action()
    upload_step = step_by_name(action, "📦 Upload report artifact")

    assert action["inputs"]["upload-report"]["default"] == "false"
    assert action["inputs"]["report-artifact-name"]["default"] == "insomnia-run-report"
    assert upload_step["if"] == "inputs.upload-report == 'true'"
    assert "actions/upload-artifact@" in upload_step["uses"]


def test_action_keeps_inso_config_auto_detected():
    action = load_action()
    action_text = ACTION_YAML.read_text().lower()

    assert "config-file" not in action["inputs"]
    assert "insorc" not in action_text


def test_action_routes_run_scripts_through_env():
    action = load_action()

    for step in action["runs"]["steps"]:
        run = step.get("run")
        if run is None:
            continue
        assert "${{" not in run, f"step '{step.get('name')}' interpolates inside run"
        assert step.get("shell") == "bash"
