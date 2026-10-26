from importlib.metadata import version
import os
from pathlib import Path
import re
import shlex
import subprocess
from urllib.parse import parse_qsl

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_FILES = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
ACTION = yaml.safe_load((ROOT / "action.yml").read_text())


def yaml_examples(path):
    for block in re.findall(
        r"^```ya?ml[^\n]*\n(.*?)^```", path.read_text(), re.M | re.S
    ):
        yield yaml.safe_load(block)


def mappings(document):
    pending = [document]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            yield value
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)


def action_steps(path):
    for document in yaml_examples(path):
        for step in mappings(document):
            if "uses" in step:
                yield step


@pytest.mark.parametrize("path", MARKDOWN_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_workflow_examples_use_pinned_actions(path):
    for step in action_steps(path):
        # Instantiate the documented release-SHA parameter before validating the template.
        action = step["uses"].replace("REVIEWED_RELEASE_SHA", "f" * 40)
        if action.startswith("./"):
            continue
        name, reference = action.rsplit("@", 1)
        if name == "scarowar/insomnia-run":
            assert reference == f"v{version('insomnia-run')}" or re.fullmatch(
                r"[0-9a-f]{40}", reference
            ), action
        else:
            assert re.fullmatch(r"[0-9a-f]{40}", reference), action
        if name == "actions/checkout":
            assert step.get("with", {}).get("persist-credentials") is False


@pytest.mark.parametrize("path", MARKDOWN_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_action_examples_use_valid_inputs(path):
    required = {key for key, value in ACTION["inputs"].items() if value.get("required")}
    for step in action_steps(path):
        if not step["uses"].startswith("scarowar/insomnia-run@"):
            continue
        inputs = step.get("with", {})
        assert set(inputs) <= set(ACTION["inputs"]), inputs
        assert required <= set(inputs), inputs
        assert inputs["command"] in {"collection", "test"}
        assert inputs["working-directory"] != ".insomnia"


def test_reference_accounts_for_every_action_input():
    reference = (ROOT / "docs/reference/compatibility.md").read_text()
    assert set(ACTION["inputs"]) <= set(re.findall(r"`([^`]+)`", reference))
    assert "reference/compatibility.md" in (ROOT / "mkdocs.yml").read_text()


def test_secret_workflow_jobs_check_out_project_files():
    for document in yaml_examples(ROOT / "docs/guides/secrets.md"):
        if not isinstance(document, dict) or "jobs" not in document:
            continue
        for name, job in document["jobs"].items():
            steps = job["steps"]
            action_index = next(
                i
                for i, step in enumerate(steps)
                if step.get("uses", "").startswith("scarowar/insomnia-run@")
            )
            assert any(
                step.get("uses", "").startswith("actions/checkout@")
                for step in steps[:action_index]
            ), name


def test_secret_encoding_example_preserves_literal_values(tmp_path):
    step = next(
        step
        for document in yaml_examples(ROOT / "docs/guides/secrets.md")
        for step in mappings(document)
        if step.get("id") == "inso-secrets"
    )
    output = tmp_path / "outputs"
    values = {
        "API_KEY": "key+with&reserved%2F\ncharacters",
        "AUTH_TOKEN": "token value",
    }
    result = subprocess.run(
        ["bash", "-euc", step["run"]],
        env={**os.environ, **values, "GITHUB_OUTPUT": str(output)},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert dict(parse_qsl(output.read_text().replace("\n", "&"))) == values
    assert all(value not in result.stdout for value in values.values())
    assert all(line.startswith("::add-mask::") for line in result.stdout.splitlines())
    masks = [
        line.removeprefix("::add-mask::")
        .replace("%0D", "\r")
        .replace("%0A", "\n")
        .replace("%25", "%")
        for line in result.stdout.splitlines()
    ]
    assert masks == [line.split("=", 1)[1] for line in output.read_text().splitlines()]


def test_debug_example_requires_private_raw_output_opt_in():
    examples = [
        example
        for document in yaml_examples(ROOT / "docs/troubleshooting.md")
        for example in mappings(document)
        if example.get("verbose") == "true"
    ]
    assert examples
    for example in examples:
        assert example["include-raw-output"] == "true"
        assert example["pr-comment"] == "false"
        assert example["upload-artifact"] == "false"


def test_development_setup_installs_commit_message_and_pre_commit_hooks():
    instructions = (ROOT / "CONTRIBUTING.md").read_text()
    commands = [
        shlex.split(line)
        for block in re.findall(r"^```sh\n(.*?)^```", instructions, re.M | re.S)
        for line in block.splitlines()
    ]
    install = next(
        command
        for command in commands
        if "pre-commit" in command and "install" in command
    )
    hook_types = {
        install[i + 1] for i, value in enumerate(install) if value == "--hook-type"
    }
    assert hook_types == {"pre-commit", "commit-msg"}
