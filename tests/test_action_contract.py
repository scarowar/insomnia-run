"""Public metadata and executable bootstrap contracts of the composite action."""

import os
from pathlib import Path
import re
import subprocess

import pytest
import yaml


ACTION_YAML = Path(__file__).resolve().parents[1] / "action.yml"


def load_action():
    return yaml.safe_load(ACTION_YAML.read_text())


def step_by_name(action, name):
    return next(step for step in action["runs"]["steps"] if step.get("name") == name)


def run_step(step, tmp_path, **overrides):
    env = {
        **os.environ,
        **{key: str(value) for key, value in step.get("env", {}).items()},
        "GITHUB_OUTPUT": str(tmp_path / "output"),
        "HOME": str(tmp_path),
    }
    env.update(overrides)
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-euo", "pipefail", "-c", step["run"]],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def executable(tmp_path, name, script):
    path = tmp_path / name
    path.write_text("#!/bin/bash\n" + script)
    path.chmod(0o755)
    return path


def test_external_actions_are_pinned_to_immutable_commits():
    for step in load_action()["runs"]["steps"]:
        if "uses" in step:
            assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", step["uses"])


def test_shell_inputs_are_passed_through_environment_not_inline_expressions():
    for step in load_action()["runs"]["steps"]:
        if "run" in step:
            assert "${{" not in step["run"]


def test_uv_bootstrap_version_matches_the_first_party_build_backend():
    action = load_action()
    setup = step_by_name(action, "Setup uv")
    check = step_by_name(action, "Check uv")
    version = str(setup["with"]["version"])

    assert check["env"]["INSOMNIA_RUN_UV_VERSION"] == version
    assert (
        f'"uv_build=={version}"' in (ACTION_YAML.parent / "pyproject.toml").read_text()
    )
    assert setup["with"].get("checksum")
    assert "github-com-token" in setup["with"]["github-token"]
    assert "inputs.github-token" not in setup["with"]["github-token"]
    assert "github.server_url == 'https://github.com'" in setup["with"]["github-token"]
    assert "offline-install" in setup["with"]["enable-cache"]
    for untrusted_event in ("issue_comment", "pull_request_target"):
        assert untrusted_event in setup["with"]["save-cache"]


@pytest.mark.parametrize("offline", ["TRUE", "False", "", "typo"])
def test_invalid_offline_setting_fails_before_bootstrap(tmp_path, offline):
    result = run_step(
        step_by_name(load_action(), "Check uv"),
        tmp_path,
        OFFLINE_INSTALL=offline,
        PYTHON_VERSION="system",
    )
    assert result.returncode != 0
    assert "offline-install must be true or false" in result.stdout
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("matching", [True, False])
@pytest.mark.parametrize("offline", ["true", "false"])
def test_uv_bootstrap_uses_exact_preinstalled_version_or_fails_offline(
    tmp_path, matching, offline
):
    step = step_by_name(load_action(), "Check uv")
    wanted = step["env"]["INSOMNIA_RUN_UV_VERSION"]
    executable(tmp_path, "uv", f"printf 'uv {wanted if matching else '0.0.1'}\\n'\n")

    result = run_step(
        step,
        tmp_path,
        PATH=f"{tmp_path}:{os.environ['PATH']}",
        OFFLINE_INSTALL=offline,
        PYTHON_VERSION="system",
        RUNNER_OS="Linux",
        RUNNER_ARCH="X64",
    )

    if offline == "true" and not matching:
        assert result.returncode != 0
        assert not (tmp_path / "output").exists()
    else:
        assert result.returncode == 0, result.stderr
        assert (
            tmp_path / "output"
        ).read_text().strip() == f"needs-setup={str(not matching).lower()}"


@pytest.mark.parametrize("version", ["13.3.1", "13.3.1-beta.1"])
def test_inso_version_validation_accepts_release_identifiers(tmp_path, version):
    step = step_by_name(load_action(), "Validate Inso Version")
    assert run_step(step, tmp_path, INSO_VERSION=version).returncode == 0


@pytest.mark.parametrize(
    "version",
    ["latest", "13.3", "../13.3.1", "13.3.1\n::error::FORGED", "$(touch FORGED)"],
)
def test_inso_version_validation_rejects_untrusted_paths_without_echoing_them(
    tmp_path, version
):
    result = run_step(
        step_by_name(load_action(), "Validate Inso Version"),
        tmp_path,
        INSO_VERSION=version,
    )
    assert result.returncode != 0
    assert "FORGED" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "installed,found", [("13.3.1", True), ("13.2.0", False), ("unknown", False)]
)
def test_preinstalled_inso_must_match_the_requested_version(tmp_path, installed, found):
    executable(tmp_path, "inso", f"printf '{installed}\\n'\n")
    result = run_step(
        step_by_name(load_action(), "Detect Inso CLI"),
        tmp_path,
        PATH=f"{tmp_path}:{os.environ['PATH']}",
        INSO_VERSION="13.3.1",
        INSO_ARCHIVE="",
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "output").read_text().strip() == f"found={str(found).lower()}"


def test_explicit_archive_is_verified_even_when_inso_is_preinstalled(tmp_path):
    probe = tmp_path / "probe"
    executable(tmp_path, "inso", f"touch '{probe}'\nprintf '13.3.1\\n'\n")
    result = run_step(
        step_by_name(load_action(), "Detect Inso CLI"),
        tmp_path,
        PATH=f"{tmp_path}:{os.environ['PATH']}",
        INSO_VERSION="13.3.1",
        INSO_ARCHIVE="/mirror/inso.tar.xz",
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "output").read_text().strip() == "found=false"
    assert not probe.exists()


@pytest.mark.parametrize(
    "version,exit_code,succeeds",
    [
        ("13.3.1", 0, True),
        ("13.2.0", 0, False),
        ("unknown", 0, False),
        ("13.3.1", 1, False),
    ],
)
def test_installed_inso_is_rechecked_before_running_collections(
    tmp_path, version, exit_code, succeeds
):
    executable(tmp_path, "inso", f"printf '{version}\\n'\nexit {exit_code}\n")
    result = run_step(
        step_by_name(load_action(), "Verify Inso CLI"),
        tmp_path,
        PATH=f"{tmp_path}:{os.environ['PATH']}",
        INSO_VERSION="13.3.1",
        USE_INSTALLED_INSO="false",
    )
    assert (result.returncode == 0) is succeeds


def test_installer_preserves_archive_digest_and_separate_token_inputs():
    action = load_action()
    install = step_by_name(action, "Install Inso CLI")
    assert install["env"]["INSO_SHA256"] == "${{ inputs.inso-sha256 }}"
    assert install["env"]["INSO_ARCHIVE"] == "${{ inputs.inso-archive }}"
    assert install["env"]["CUSTOM_DOWNLOAD_TOKEN"] == "${{ inputs.download-token }}"
    assert (
        install["env"]["CUSTOM_DOWNLOAD_ORIGIN"]
        == "${{ inputs.download-token-origin }}"
    )
    assert "inputs.github-token" not in install["env"]["PUBLIC_DOWNLOAD_TOKEN"]
    assert "inputs.github-com-token" in install["env"]["PUBLIC_DOWNLOAD_TOKEN"]
    for step in action["runs"]["steps"]:
        if step.get("uses", "").startswith("actions/cache/"):
            assert "inputs.offline-install != 'true'" in step["if"]
            assert step["with"]["key"] == "${{ steps.inso-identity.outputs.key }}"
            assert "restore-keys" not in step["with"]


def test_runtime_install_supports_explicit_bundle_and_offline_inputs():
    step = step_by_name(load_action(), "Install insomnia-run")
    for key, name in {
        "RUNTIME_BUNDLE": "runtime-bundle",
        "RUNTIME_BUNDLE_SHA256": "runtime-bundle-sha256",
        "OFFLINE_INSTALL": "offline-install",
    }.items():
        assert step["env"][key] == "${{ inputs." + name + " }}"
    assert step["env"]["ACTION_PATH"] == "${{ github.action_path }}"


def test_action_exposes_report_files_counts_and_comment_state():
    outputs = load_action()["outputs"]
    report_outputs = [
        "report-directory",
        "json-file",
        "raw-file",
        "json-output-omitted",
        "total",
        "passed",
        "failed",
        "skipped",
        "requests",
        "run-error",
        "markdown",
        "json-output",
        "junit-file",
        "exit-code",
    ]
    for name in report_outputs:
        assert outputs[name]["value"] == "${{ steps.run-cli.outputs." + name + " }}"
    for name in ("comment-id", "comment-status"):
        assert outputs[name]["value"] == "${{ steps.comment.outputs." + name + " }}"


def test_publication_preserves_failure_policy_after_other_step_failures():
    action = load_action()
    final = step_by_name(action, "Check for Failures")
    assert "!cancelled()" in final["if"]
    assert final["env"]["EXIT_CODE"] == "${{ steps.run-cli.outputs.exit-code }}"
    assert final["env"]["FAIL_ON_ERROR"] == "${{ inputs.fail-on-error }}"
    upload = step_by_name(action, "Upload report artifact")
    assert "inputs.upload-artifact == 'true'" in upload["if"]
    assert upload["with"]["path"] == "${{ steps.run-cli.outputs.report-directory }}"
    assert upload["with"]["retention-days"] == "${{ inputs.artifact-retention-days }}"


def test_comment_adapter_receives_explicit_target_and_scoped_identity():
    comment = step_by_name(load_action(), "Post PR Comment")
    assert comment["env"]["ACTION_COMMENT_ENABLED"] == "${{ inputs.pr-comment }}"
    assert (
        comment["env"]["ACTION_COMMENT_NUMBER"] == "${{ inputs.comment-issue-number }}"
    )
    assert (
        comment["env"]["ACTION_COMMENT_TOKEN"]
        == "${{ inputs.github-token || github.token }}"
    )
    assert comment["env"]["ACTION_COMMENT_TAG"] == "${{ inputs.comment-tag }}"
    assert comment["env"]["ACTION_COMMENT_MATRIX"] == "${{ toJSON(matrix) }}"


def test_defaults_keep_sensitive_data_and_optional_install_modes_disabled():
    inputs = load_action()["inputs"]
    for name in ("include-raw-output", "upload-artifact", "offline-install"):
        assert inputs[name]["default"] == "false"
    for name in ("junit-report", "cache-inso", "progress", "annotations"):
        assert inputs[name]["default"] == "true"
    assert inputs["python-version"]["default"] == "system"
    for name in (
        "runtime-bundle",
        "runtime-bundle-sha256",
        "inso-archive",
        "inso-sha256",
        "capture-response-headers",
    ):
        assert inputs[name].get("default", "") == ""


def test_inso_config_is_auto_detected_without_global_path_modification():
    action = load_action()
    assert "config-file" not in action["inputs"]
    assert "install-inso" not in action["inputs"]
    assert "GITHUB_PATH" not in ACTION_YAML.read_text()
    assert "Kong/setup-inso" not in ACTION_YAML.read_text()
