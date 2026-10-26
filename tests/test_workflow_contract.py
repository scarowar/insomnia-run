from pathlib import Path
import os
import re
import shlex
import subprocess
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted(
    path
    for pattern in ("*.yml", "*.yaml")
    for path in (ROOT / ".github" / "workflows").glob(pattern)
)
ACTION_FILES = [ROOT / "action.yml"]
CODEOWNERS = ROOT / ".github" / "CODEOWNERS"
PRE_COMMIT_CONFIG = ROOT / ".pre-commit-config.yaml"
ACTION_REF_RE = re.compile(r"@[0-9a-f]{40}$")
PR_CONCURRENCY_GROUP = "${{ github.workflow }}-${{ github.event_name }}-${{ github.event.pull_request.number || github.ref }}"


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text())


def workflow_on(workflow: dict):
    return workflow.get("on", workflow.get(True))


def uses_references(path: Path):
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        stripped = line.strip()
        if not stripped.startswith("uses: "):
            continue
        value = stripped.removeprefix("uses: ").split("#", 1)[0].strip()
        yield line_number, value


def workflow_steps():
    for path in WORKFLOWS:
        workflow = load_yaml(path)
        for job_name, job in workflow.get("jobs", {}).items():
            for step in job.get("steps", []):
                yield path, job_name, step


def test_privileged_pull_request_target_is_not_used():
    for path in WORKFLOWS:
        assert "pull_request_target" not in path.read_text(), path


def test_repository_has_codeowners():
    assert CODEOWNERS.read_text().strip() == "* @scarowar"


def test_release_security_workflows_exist():
    workflows = {path.name for path in WORKFLOWS}

    assert "security.yml" in workflows
    assert "codeql.yml" in workflows
    assert "dependency-review.yml" in workflows
    assert "scorecards.yml" in workflows


def test_third_party_actions_are_pinned_to_sha():
    for path in [*WORKFLOWS, *ACTION_FILES]:
        for line_number, ref in uses_references(path):
            if ref.startswith("./"):
                continue
            assert ACTION_REF_RE.search(ref), f"{path}:{line_number} uses {ref}"


def test_production_workflow_template_requires_reviewed_commit_pins():
    document = (ROOT / "docs/guides/secrets.md").read_text()
    examples = [
        yaml.safe_load(block)
        for block in re.findall(r"```yaml\n(.*?)\n```", document, re.DOTALL)
    ]
    production = next(
        example["jobs"]["production"]
        for example in examples
        if isinstance(example, dict) and "production" in example.get("jobs", {})
    )
    for step in production["steps"]:
        if "uses" in step:
            reference = step["uses"].replace("REVIEWED_RELEASE_SHA", "f" * 40)
            assert ACTION_REF_RE.search(reference), step["uses"]


def test_jobs_start_with_harden_runner_and_have_timeouts():
    for path in WORKFLOWS:
        workflow = load_yaml(path)
        for job_name, job in workflow.get("jobs", {}).items():
            steps = job.get("steps", [])
            if not steps:
                continue
            assert job.get("timeout-minutes"), f"{path}:{job_name} missing timeout"
            assert job["timeout-minutes"] <= 25, f"{path}:{job_name} timeout too high"
            if path.name == "e2e-test.yml" and job_name == "test-container":
                # Hosted container jobs cannot run the host-level security agent.
                assert re.fullmatch(
                    r"python:[^@]+@sha256:[0-9a-f]{64}", job["container"]["image"]
                )
                assert "options" not in job["container"]
                assert job.get("permissions", workflow["permissions"]) == {
                    "contents": "read"
                }
                continue
            assert (
                steps[0].get("uses", "").startswith("step-security/harden-runner@")
            ), f"{path}:{job_name} does not start with Harden-Runner"


def test_workflows_define_top_level_permissions():
    for path in WORKFLOWS:
        workflow = load_yaml(path)

        assert workflow.get("permissions"), f"{path} missing top-level permissions"


def test_checkout_does_not_persist_credentials():
    for path, job_name, step in workflow_steps():
        if not step.get("uses", "").startswith("actions/checkout@"):
            continue

        assert step.get("with", {}).get("persist-credentials") is False, (
            f"{path}:{job_name} checkout persists credentials"
        )


def test_setup_uv_pins_installed_uv_version():
    for path, job_name, step in workflow_steps():
        if not step.get("uses", "").startswith("astral-sh/setup-uv@"):
            continue

        assert step.get("with", {}).get("version") == "0.13.1", (
            f"{path}:{job_name} setup-uv does not pin uv version"
        )
        assert step["with"].get("checksum"), f"{path}:{job_name} uv digest missing"


def test_ci_checks_lockfile_freshness_before_installing():
    workflow = load_yaml(ROOT / ".github/workflows/ci.yml")
    steps = workflow["jobs"]["lint"]["steps"]
    check_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("run") == "uv lock --check"
    )
    install_index = next(
        index for index, step in enumerate(steps) if "uv sync" in step.get("run", "")
    )
    assert check_index < install_index


def test_release_validation_rejects_stale_project_metadata(tmp_path):
    workflow = load_yaml(ROOT / ".github/workflows/release-validation.yml")
    install = next(
        step["run"]
        for step in workflow["jobs"]["validate"]["steps"]
        if "uv sync" in step.get("run", "")
    )
    command = shlex.split(
        next(
            line.strip()
            for line in install.splitlines()
            if line.strip().startswith("uv sync ")
        )
    )
    binary = os.environ.get("INSOMNIA_RUN_UV_BINARY", "uv")
    command[0] = binary
    command.extend(["--offline", "--no-config", "--python", sys.executable])
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("UV_")
    }
    environment.update(
        UV_PROJECT_ENVIRONMENT=str(tmp_path / "environment"),
        UV_PYTHON_DOWNLOADS="never",
    )
    project = tmp_path / "pyproject.toml"
    project.write_text(
        '[project]\nname = "lock-freshness-probe"\nversion = "0.0.0"\nrequires-python = ">=3.10"\n'
    )
    subprocess.run(
        [binary, "lock", "--offline", "--no-config", "--python", sys.executable],
        cwd=tmp_path,
        env=environment,
        check=True,
        capture_output=True,
    )
    lock = (tmp_path / "uv.lock").read_bytes()
    fresh = subprocess.run(
        command, cwd=tmp_path, env=environment, capture_output=True, text=True
    )
    assert fresh.returncode == 0, fresh.stderr
    project.write_text(
        project.read_text().replace('version = "0.0.0"', 'version = "0.0.1"')
    )
    stale = subprocess.run(
        command, cwd=tmp_path, env=environment, capture_output=True, text=True
    )
    assert stale.returncode != 0, "Release validation accepted a stale lockfile"
    assert (tmp_path / "uv.lock").read_bytes() == lock


def test_release_validation_checks_locked_metadata_before_building():
    workflow = load_yaml(ROOT / ".github/workflows/release-validation.yml")
    commands = [
        line.strip()
        for step in workflow["jobs"]["validate"]["steps"]
        for line in step.get("run", "").splitlines()
    ]
    sync = next(
        index
        for index, command in enumerate(commands)
        if command.startswith("uv sync ")
    )
    build = next(
        index
        for index, command in enumerate(commands)
        if command.startswith("uv build ")
    )
    assert sync < build


def test_pull_request_workflows_cancel_superseded_runs():
    for path in WORKFLOWS:
        workflow = load_yaml(path)
        triggers = workflow_on(workflow)
        has_pull_request = (
            triggers == "pull_request"
            or (isinstance(triggers, list) and "pull_request" in triggers)
            or (isinstance(triggers, dict) and "pull_request" in triggers)
        )
        if not has_pull_request:
            continue

        concurrency = workflow.get("concurrency")
        assert concurrency, f"{path} missing concurrency"
        assert concurrency["group"] == PR_CONCURRENCY_GROUP
        assert concurrency["cancel-in-progress"] is True


def test_expensive_bot_prs_are_cost_controlled():
    codeql = load_yaml(ROOT / ".github" / "workflows" / "codeql.yml")
    dependency_review = load_yaml(
        ROOT / ".github" / "workflows" / "dependency-review.yml"
    )
    e2e = load_yaml(ROOT / ".github" / "workflows" / "e2e-test.yml")
    security = load_yaml(ROOT / ".github" / "workflows" / "security.yml")

    assert "github.actor != 'dependabot[bot]'" in codeql["jobs"]["analyze"]["if"]
    assert "github.actor != 'pre-commit-ci[bot]'" in codeql["jobs"]["analyze"]["if"]
    assert dependency_review["jobs"]["dependency-review"]["if"] == (
        "github.actor != 'pre-commit-ci[bot]'"
    )

    for job in e2e["jobs"].values():
        assert "github.actor != 'dependabot[bot]'" in job["if"]
        assert "github.actor != 'pre-commit-ci[bot]'" in job["if"]

    assert (
        "github.actor != 'pre-commit-ci[bot]'"
        in security["jobs"]["deterministic-security"]["if"]
    )


def test_e2e_jobs_use_local_api_fixtures():
    e2e = load_yaml(ROOT / ".github" / "workflows" / "e2e-test.yml")

    for job_name, job in e2e["jobs"].items():
        step_names = {step.get("name") for step in job.get("steps", [])}
        assert "Start local API fixture" in step_names, (
            f"{job_name} does not start the deterministic API fixture"
        )

    fixture_text = "\n".join(
        path.read_text() for path in (ROOT / "tests" / "fixtures").glob("*.yaml")
    )
    assert "jsonplaceholder.typicode.com" not in fixture_text
    assert "httpbin.org" not in fixture_text


def test_e2e_checks_the_verified_binary_against_the_compatibility_suite():
    workflow = load_yaml(ROOT / ".github/workflows/e2e-test.yml")
    steps = workflow["jobs"]["test-test-command"]["steps"]
    compatibility = next(
        step
        for step in steps
        if "tests/test_inso_compatibility.py" in step.get("run", "")
    )
    assert (
        compatibility["env"]["INSOMNIA_RUN_INSO_BINARY"]
        == "${{ runner.temp }}/insomnia-run-inso/bin/inso"
    )
    assert "--no-build --no-install-project" in compatibility["run"]
    assert "--require-hashes" in compatibility["run"]
    assert "uv run --frozen --no-sync --no-build pytest" in compatibility["run"]
    assert (
        '--basetemp "${RUNNER_TEMP}/insomnia-run-compat-tests"' in compatibility["run"]
    )


def test_docs_deploy_runs_only_for_docs_surface_changes():
    workflow = load_yaml(ROOT / ".github" / "workflows" / "docs.yml")
    paths = workflow_on(workflow)["push"]["paths"]

    assert ".github/workflows/docs.yml" in paths
    assert "docs/**" in paths
    assert "overrides/**" in paths
    assert "mkdocs.yml" in paths
    assert "pyproject.toml" in paths
    assert "uv.lock" in paths


def test_pre_commit_ci_runs_fast_hygiene_only():
    config = load_yaml(PRE_COMMIT_CONFIG)
    ci_config = config["ci"]

    assert ci_config["autoupdate_schedule"] == "weekly"
    assert ci_config["autofix_commit_msg"] == "style: apply pre-commit fixes"
    assert ci_config["autoupdate_commit_msg"] == "chore: update pre-commit hooks"
    assert {
        "gitleaks",
        "bandit",
        "actionlint",
        "gitlint",
        "pip-audit",
        "zizmor",
    } <= set(ci_config["skip"])


def test_dependency_review_blocks_low_severity_and_above():
    workflow = load_yaml(ROOT / ".github" / "workflows" / "dependency-review.yml")
    steps = workflow["jobs"]["dependency-review"]["steps"]
    dependency_review = next(
        step for step in steps if "dependency-review-action" in step.get("uses", "")
    )

    assert dependency_review["with"]["fail-on-severity"] == "low"


def test_dependabot_updates_have_cooldown():
    config = load_yaml(ROOT / ".github" / "dependabot.yml")

    for update in config["updates"]:
        assert update["cooldown"]["default-days"] >= 7


def test_dependabot_updates_the_uv_lockfile_ecosystem():
    config = load_yaml(ROOT / ".github" / "dependabot.yml")
    ecosystems = {entry["package-ecosystem"]: entry for entry in config["updates"]}

    assert "pip" not in ecosystems
    assert ecosystems["uv"]["directory"] == "/"
    assert ecosystems["uv"]["allow"] == [{"dependency-type": "all"}]
    assert ecosystems["github-actions"]["directory"] == "/"


def test_security_workflow_runs_deterministic_scanners():
    workflow = load_yaml(ROOT / ".github" / "workflows" / "security.yml")
    steps_text = "\n".join(
        step.get("run", "")
        for step in workflow["jobs"]["deterministic-security"]["steps"]
    )

    assert "uv run --frozen --no-sync --no-build pip-audit --strict" in steps_text
    assert (
        "uv run --frozen --no-sync --no-build bandit -r src/insomnia_run" in steps_text
    )
    assert "uv run --frozen --no-sync --no-build zizmor --offline ." in steps_text
    assert (
        "uv run --frozen --no-sync --no-build cyclonedx-py environment .venv"
        in steps_text
    )


def test_automatic_sonar_analysis_has_no_conflicting_ci_scanner():
    assert (ROOT / ".sonarcloud.properties").is_file()
    for _, _, step in workflow_steps():
        assert "sonarqube-scan-action" not in step.get("uses", "")


def test_ci_enforces_coverage_independently_of_automatic_analysis():
    ci = load_yaml(ROOT / ".github/workflows/ci.yml")
    commands = "\n".join(s.get("run", "") for s in ci["jobs"]["test"]["steps"])
    assert "--cov-fail-under=95" in commands
    assert '--basetemp "${RUNNER_TEMP}/insomnia-run-unit-tests"' in commands
    assert "pytest -q" in commands
