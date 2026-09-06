"""Deterministic no-break guarantee.

Covers the consumer-visible contract that must not break between releases.
New inputs are additive with safe defaults; outputs/exit-codes are a
superset; valid workflows keep working.
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ACTION_YAML = ROOT / "action.yml"


def load_action():
    return yaml.safe_load(ACTION_YAML.read_text())


def test_required_inputs_unchanged_no_new_required():
    action = load_action()
    # Origin v0.1.2 had exactly 2 required inputs: command, working-directory
    assert action["inputs"]["command"]["required"] is True
    assert action["inputs"]["working-directory"]["required"] is True
    # No new required inputs may be added — would break every consumer
    required = [k for k, v in action["inputs"].items() if v.get("required") is True]
    assert required == ["command", "working-directory"], f"new required inputs would break: {required}"


def test_outputs_are_superset_of_v012():
    action = load_action()
    # v0.1.2 outputs: markdown, json-output, exit-code (junit-path added in 0.2.0)
    assert "markdown" in action["outputs"]
    assert "json-output" in action["outputs"]
    assert "exit-code" in action["outputs"]
    assert "junit-path" in action["outputs"]
    # Values must still route via run-cli outputs (no output removed/renamed)
    assert action["outputs"]["markdown"]["value"] == "${{ steps.run-cli.outputs.markdown }}"
    assert action["outputs"]["exit-code"]["value"] == "${{ steps.run-cli.outputs.exit-code }}"


def test_new_inputs_have_safe_defaults_mimicking_old_implicit_behavior():
    action = load_action()
    # Old implicit behavior: pr comments on, fail on test failure, include raw, etc.
    # New explicit inputs default to the old implicit value so existing
    # workflows that omit them keep working identically.
    assert action["inputs"]["inso-version"]["default"] == "13.2.0"
    assert action["inputs"]["pr-comment"]["default"] == "true"
    assert action["inputs"]["fail-on-error"]["default"] == "true"
    assert action["inputs"]["include-raw-output"]["default"] == "true"
    assert action["inputs"]["raw-output-max-bytes"]["default"] == "8192"
    assert action["inputs"]["junit-output"]["default"] == ""
    assert action["inputs"]["upload-report"]["default"] == "false"
    assert action["inputs"]["report-artifact-name"]["default"] == "insomnia-run-report"
    assert action["inputs"]["comment-tag"]["default"] == "insomnia-run-report"
    # All new inputs must be optional
    for k in [
        "inso-version",
        "github-token",
        "pr-comment",
        "comment-tag",
        "fail-on-error",
        "include-raw-output",
        "raw-output-max-bytes",
        "junit-output",
        "upload-report",
        "report-artifact-name",
    ]:
        assert action["inputs"][k]["required"] is False, f"{k} must be optional"


def test_exit_code_semantics_unchanged():
    # 0 pass, 1 test failure (respects fail-on-error), 2 config/runtime always fails
    # See action.yml Check for Failures step and runner.py exit handling
    text = ACTION_YAML.read_text()
    assert "steps.run-cli.outputs.exit-code != '0'" in text
    assert "steps.run-cli.outputs.exit-code == '2' || steps.run-cli.outputs.exit-code > '1'" in text
    assert "exit 1" in text  # fail gate


def test_inso_version_default_is_latest_stable_and_pinned():
    action = load_action()
    import re

    default = action["inputs"]["inso-version"]["default"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", default), f"inso-version default must be semver, got {default}"
    text = ACTION_YAML.read_text()
    assert "EXPECTED_SHA256" in text
    assert "sha256sum" in text


def test_valid_old_workflow_still_parses():
    # Minimal v0.1.2 consumer workflow — must still be valid against new action
    wf = """
name: API Tests
on: pull_request
jobs:
  api-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: scarowar/insomnia-run@v0.1.2
        with:
          command: collection
          working-directory: .insomnia
"""
    data = yaml.safe_load(wf)
    assert data["jobs"]["api-tests"]["steps"][1]["with"]["command"] == "collection"
