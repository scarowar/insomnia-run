from pathlib import Path
import os
import re
import subprocess
from urllib.parse import parse_qsl

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
USER_MARKDOWN_FILES = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
ISSUE_TEMPLATE_FILES = sorted((ROOT / ".github" / "ISSUE_TEMPLATE").glob("*.yml"))


def user_facing_text() -> str:
    return "\n".join(
        path.read_text() for path in [*USER_MARKDOWN_FILES, *ISSUE_TEMPLATE_FILES]
    )


def test_docs_do_not_contain_stale_versions():
    text = user_facing_text()

    assert "v0.1.0" not in text
    assert "12.2.0" not in text


def test_docs_do_not_contain_internal_process_language():
    text = user_facing_text().lower()

    for phrase in [
        "conversation",
        "terraform-branch-deploy",
        "tbd",
        "north star",
        "best unofficial",
        "release-ready",
        "enterprise-ready",
        "audit-backed",
        "for now",
        "future work",
        "deferred",
    ]:
        assert phrase not in text


def test_docs_do_not_force_moving_major_action_ref():
    text = user_facing_text()

    assert not re.search(r"scarowar/insomnia-run@v0(?!\.)", text)
    assert "scarowar/insomnia-run@v0.2.0" in text


def test_migration_page_is_in_navigation():
    migration = (ROOT / "docs" / "migration.md").read_text()
    nav = (ROOT / "mkdocs.yml").read_text()

    assert "v0.1.x to v0.2.0" in migration
    assert "migration.md" in nav


def test_inso_config_auto_detection_is_documented():
    reference = (ROOT / "docs" / "reference" / "inputs.md").read_text()
    migration = (ROOT / "docs" / "migration.md").read_text()
    action = (ROOT / "action.yml").read_text()

    assert ".insorc" in reference
    assert ".insorc" in migration
    assert "config-file" not in action


def test_secret_workflow_jobs_check_out_project_files():
    text = (ROOT / "docs/guides/secrets.md").read_text()
    for block in re.findall(r"^```ya?ml[^\n]*\n(.*?)^```", text, re.M | re.S):
        document = yaml.safe_load(block)
        if not isinstance(document, dict) or "jobs" not in document:
            continue
        for name, job in document["jobs"].items():
            steps = job["steps"]
            action_index = next(
                i
                for i, s in enumerate(steps)
                if s.get("uses", "").startswith("scarowar/insomnia-run@")
            )
            assert any(
                s.get("uses", "").startswith("actions/checkout@")
                for s in steps[:action_index]
            ), name


def test_secret_encoding_example_preserves_literal_values(tmp_path):
    text = (ROOT / "docs/guides/secrets.md").read_text()
    block = re.findall(r"^```yaml[^\n]*\n(.*?)^```", text, re.M | re.S)[0]
    step = yaml.safe_load(block)[0]
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


def test_upstream_compatibility_accounts_for_every_action_input():
    action = yaml.safe_load((ROOT / "action.yml").read_text())
    text = (ROOT / "docs/reference/compatibility.md").read_text()
    assert set(action["inputs"]) <= set(re.findall(r"`([^`]+)`", text))
    assert "reference/compatibility.md" in (ROOT / "mkdocs.yml").read_text()


def test_installation_guidance_uses_uv_not_pip():
    text = user_facing_text().lower()

    assert "configure pip" not in text
    assert "uv 0.11.11" in text


@pytest.mark.parametrize(
    "path", USER_MARKDOWN_FILES, ids=lambda path: str(path.relative_to(ROOT))
)
def test_standalone_examples_explain_unreleased_candidate_reference(path):
    text = path.read_text()
    if "scarowar/insomnia-run@v0.2.0" not in text:
        return

    assert "unreleased" in text.lower(), path
    assert "tag does not exist" in text, path
    assert "replace `scarowar/insomnia-run@v0.2.0`" in text, path
    assert "reviewed full PR-head commit SHA" in text, path
    assert "40 hexadecimal characters" in text, path
    assert not re.search(r"scarowar/insomnia-run@[0-9a-f]{40}\b", text), path


@pytest.mark.parametrize(
    "path", USER_MARKDOWN_FILES, ids=lambda path: str(path.relative_to(ROOT))
)
def test_documented_yaml_is_valid_and_uses_explicit_export_paths(path):
    text = path.read_text()
    for block in re.findall(r"^```ya?ml[^\n]*\n(.*?)^```", text, re.M | re.S):
        document = yaml.safe_load(block)
        pending = [document]
        while pending:
            value = pending.pop()
            if isinstance(value, list):
                pending.extend(value)
            elif isinstance(value, dict):
                if "working-directory" in value:
                    assert value["working-directory"] != ".insomnia", path
                pending.extend(value.values())


def test_git_sync_and_export_paths_are_distinguished():
    getting_started = (ROOT / "docs/getting-started/index.md").read_text()
    reference = (ROOT / "docs/reference/inputs.md").read_text()
    for text in (getting_started, reference):
        assert "legacy Git Sync" in text
        assert ".insomnia/Workspace/" in text
        assert "repository root" in text
        assert "working-directory: ." in text
        assert "working-directory: insomnia-export.yaml" in text


def test_data_folders_is_a_common_comma_separated_input():
    reference = (ROOT / "docs/reference/inputs.md").read_text()
    common = reference.split("## Common\n", 1)[1].split("## Collection Only", 1)[0]
    assert re.search(r"\| `data-folders` \|.*comma-separated", common)
    assert "both collection and test" in reference
    assert 'data-folders: "./fixtures,./uploads"' in reference


def test_offline_troubleshooting_requires_exact_preinstalled_versions():
    troubleshooting = (ROOT / "docs/troubleshooting.md").read_text()
    installation = troubleshooting.split("## Inso Installation Fails", 1)[1].split(
        "## Inso Configuration Not Applied", 1
    )[0]
    assert "matches `inso-version` exactly" in installation
    assert 'inso-version: "13.3.1"' in installation
    assert "uv 0.11.11" in troubleshooting
    assert "UV_OFFLINE=true" in troubleshooting


def test_debug_guidance_requires_explicit_raw_output_and_warns_about_sharing():
    troubleshooting = (ROOT / "docs/troubleshooting.md").read_text()
    debug = troubleshooting.split("## Debug Mode", 1)[1].split("## Help", 1)[0]
    assert 'verbose: "true"' in debug
    assert 'include-raw-output: "true"' in debug
    assert 'pr-comment: "false"' in debug
    assert "secrets" in debug.lower()
    assert "artifacts" in debug.lower()
    assert "not streamed" in debug
    assert "verbose alone" in debug.lower()
    assert "--verbose" in debug
    assert "--include-raw-output" in debug
    assert "job summary" in debug


def test_empty_run_guidance_does_not_claim_successful_validation():
    for relative in ("docs/guides/collections.md", "docs/guides/test-suites.md"):
        text = (ROOT / relative).read_text()
        assert "No assertions executed" in text
        assert "not successful test validation" in text
    comparison = (ROOT / "docs/guides/test-suites.md").read_text()
    assert "| **Assertions** | Status codes |" not in comparison


@pytest.mark.parametrize(
    "relative", ["docs/reference/inputs.md", "docs/troubleshooting.md"]
)
def test_report_terms_distinguish_empty_skipped_and_synthetic_results(relative):
    text = (ROOT / relative).read_text()
    assert "Empty runs retain exit code `0`" in text
    assert "No Assertions Executed" in text
    assert "No assertions executed" in text
    assert "Skipped" in text
    assert "test results" in text
    assert "synthetic execution failures" in text
    assert "requests executed" not in text


def test_contributing_names_the_configured_formatter():
    contributing = (ROOT / "CONTRIBUTING.md").read_text()
    assert "Ruff" in contributing
    assert "ruff format" in contributing
    assert "Black" not in contributing


def test_release_guidance_records_owner_decisions_without_new_requirements():
    release = (ROOT / "RELEASE.md").read_text()
    assert "solo-maintainer" in release
    assert "Recruiting another maintainer is not a prerequisite" in release
    assert "Existing GitHub review rules remain unchanged" in release
    assert "ClusterFuzzLite is explicitly deferred by the owner" in release
    assert "not a false positive" in release
    assert "not proof of a present code defect" in release
    assert "nominate another eligible CODEOWNER" not in release
    assert "No merge, tag, or release is authorized" in release
