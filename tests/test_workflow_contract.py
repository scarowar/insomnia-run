import re
from pathlib import Path

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
E2E_WORKFLOW = ROOT / ".github" / "workflows" / "e2e-test.yml"
ACTION_REF_RE = re.compile(r"@[0-9a-f]{40}$")
SHA_WITH_VERSION_COMMENT_RE = re.compile(r"@[0-9a-f]{40}\s+#\s+\S+")
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
        yield line_number, stripped


def workflow_steps():
    for path in WORKFLOWS:
        workflow = load_yaml(path)
        for job_name, job in workflow.get("jobs", {}).items():
            for step in job.get("steps", []):
                yield path, job_name, step


def run_blocks():
    for path in [*WORKFLOWS, *ACTION_FILES]:
        document = load_yaml(path)
        jobs = document.get("jobs") or {"action": document.get("runs", {})}
        for job_name, job in jobs.items():
            for step in job.get("steps", []):
                run = step.get("run")
                if run is not None:
                    yield path, job_name, step.get("name"), run


def test_privileged_pull_request_target_is_not_used():
    for path in WORKFLOWS:
        assert "pull_request_target" not in path.read_text(), path


def test_repository_has_codeowners():
    assert CODEOWNERS.read_text().strip() == "* @scarowar"


def test_release_security_workflows_exist():
    workflows = {path.name for path in WORKFLOWS}

    assert "security.yml" in workflows
    assert "sonarqube.yml" in workflows
    assert "codeql.yml" in workflows
    assert "dependency-review.yml" in workflows
    assert "scorecards.yml" in workflows


def test_third_party_actions_are_pinned_to_sha_with_version_comment():
    for path in [*WORKFLOWS, *ACTION_FILES]:
        for line_number, line in uses_references(path):
            ref = line.removeprefix("uses: ")
            if ref.startswith("./"):
                continue
            value = ref.split("#", 1)[0].strip()
            assert ACTION_REF_RE.search(value), f"{path}:{line_number} uses {value}"
            assert SHA_WITH_VERSION_COMMENT_RE.search(line), (
                f"{path}:{line_number} missing version comment: {line}"
            )


def test_jobs_start_with_harden_runner_and_have_timeouts():
    for path in WORKFLOWS:
        workflow = load_yaml(path)
        for job_name, job in workflow.get("jobs", {}).items():
            steps = job.get("steps", [])
            if not steps:
                continue
            assert job.get("timeout-minutes"), f"{path}:{job_name} missing timeout"
            assert job["timeout-minutes"] <= 25, f"{path}:{job_name} timeout too high"
            assert steps[0].get("uses", "").startswith("step-security/harden-runner@"), (
                f"{path}:{job_name} does not start with Harden-Runner"
            )


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

        version = step.get("with", {}).get("version")
        assert version and re.fullmatch(r"\d+\.\d+\.\d+", str(version)), (
            f"{path}:{job_name} setup-uv does not pin an exact uv version"
        )


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
    dependency_review = load_yaml(ROOT / ".github" / "workflows" / "dependency-review.yml")
    e2e = load_yaml(E2E_WORKFLOW)
    security = load_yaml(ROOT / ".github" / "workflows" / "security.yml")
    sonarqube = load_yaml(ROOT / ".github" / "workflows" / "sonarqube.yml")

    assert "github.actor != 'dependabot[bot]'" in codeql["jobs"]["analyze"]["if"]
    assert "github.actor != 'pre-commit-ci[bot]'" in codeql["jobs"]["analyze"]["if"]
    assert dependency_review["jobs"]["dependency-review"]["if"] == (
        "github.actor != 'pre-commit-ci[bot]'"
    )

    for job in e2e["jobs"].values():
        assert "github.actor != 'dependabot[bot]'" in job["if"]
        assert "github.actor != 'pre-commit-ci[bot]'" in job["if"]

    assert (
        "github.actor != 'pre-commit-ci[bot]'" in security["jobs"]["deterministic-security"]["if"]
    )

    # SonarQube is dispatch-only; bots can never trigger it.
    assert "pull_request" not in workflow_on(sonarqube)


def test_docs_deploy_runs_only_for_docs_surface_changes():
    workflow = load_yaml(ROOT / ".github" / "workflows" / "docs.yml")
    paths = workflow_on(workflow)["push"]["paths"]

    assert ".github/workflows/docs.yml" in paths
    assert "docs/**" in paths
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


def test_security_workflow_runs_deterministic_scanners():
    workflow = load_yaml(ROOT / ".github" / "workflows" / "security.yml")
    job = workflow["jobs"]["deterministic-security"]
    steps_text = "\n".join(step.get("run", "") for step in job["steps"])

    assert "uv run pip-audit --strict" in steps_text
    assert "uv run bandit -c pyproject.toml -r src/insomnia_run" in steps_text
    assert "uv run zizmor --offline ." in steps_text
    assert "uv run cyclonedx-py environment .venv" in steps_text

    upload = next(
        step for step in job["steps"] if step.get("uses", "").startswith("actions/upload-artifact@")
    )
    assert upload["with"]["name"] == "cyclonedx-sbom"
    assert upload["with"]["retention-days"] == 14


def test_security_workflow_triggers_and_permissions():
    workflow = load_yaml(ROOT / ".github" / "workflows" / "security.yml")
    triggers = workflow_on(workflow)

    assert "schedule" in triggers
    assert "workflow_dispatch" in triggers
    assert "pull_request" not in triggers
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["jobs"]["deterministic-security"]["permissions"] == {"contents": "read"}


def test_sonarqube_is_dispatch_only_and_gated_on_token():
    workflow = load_yaml(ROOT / ".github" / "workflows" / "sonarqube.yml")
    triggers = workflow_on(workflow)

    assert "workflow_dispatch" in triggers
    assert "push" not in triggers
    assert "pull_request" not in triggers

    job = workflow["jobs"]["sonar"]
    assert job["env"]["SONAR_TOKEN"] == "${{ secrets.SONAR_TOKEN }}"
    scan_step = next(
        step for step in job["steps"] if "sonarqube-scan-action" in step.get("uses", "")
    )

    assert scan_step["if"] == "env.SONAR_TOKEN != ''"
    for expected in (
        "-Dsonar.host.url=https://sonarcloud.io",
        "-Dsonar.organization=scarowar",
        "-Dsonar.projectKey=scarowar_insomnia-run",
        "-Dsonar.python.coverage.reportPaths=coverage.xml",
        "-Dsonar.qualitygate.wait=true",
    ):
        assert expected in scan_step["with"]["args"]

    assert "--cov-report=xml:coverage.xml" in "\n".join(
        step.get("run", "") for step in job["steps"]
    )


def test_workflows_and_action_route_run_scripts_through_env():
    for path, job_name, step_name, run in run_blocks():
        assert "${{" not in run, f"{path}:{job_name}/{step_name} interpolates in run"


def test_e2e_runs_only_against_the_local_mock_api():
    text = E2E_WORKFLOW.read_text()

    assert "tests/mock_api.py" in text
    assert "jsonplaceholder.typicode.com" not in text
    assert "httpbin.org" not in text

    for fixture in sorted((ROOT / "tests" / "fixtures").glob("*.yaml")):
        for line in fixture.read_text().splitlines():
            if line.strip().startswith("url:"):
                target = line.split("url:", 1)[1].strip()
                assert target.startswith("http://127.0.0.1"), (
                    f"{fixture.name}: {target} is not the local mock API"
                )


def test_e2e_declares_pr_comment_false_and_read_only_permissions():
    workflow = load_yaml(E2E_WORKFLOW)

    assert workflow["permissions"] == {"contents": "read"}
    for job_name, job in workflow["jobs"].items():
        assert job["permissions"] == {"contents": "read"}, job_name
        for step in job["steps"]:
            if step.get("uses") == "./":
                assert step["with"].get("pr-comment") == "false", job_name


def test_e2e_collection_job_runs_on_x64_only():
    """Upstream publishes no arm64 inso assets; e2e must not claim arm support."""
    workflow = yaml.safe_load(E2E_WORKFLOW.read_text())
    job = workflow["jobs"]["collection-run"]
    runs_on = job["runs-on"]
    assert runs_on == "ubuntu-latest"
    assert "matrix" not in job


def test_e2e_asserts_junit_report_outputs():
    workflow = load_yaml(E2E_WORKFLOW)
    steps = workflow["jobs"]["outputs-junit"]["steps"]
    failing = next(step for step in steps if step.get("id") == "failing")
    assertions = next(
        step
        for step in steps
        if step.get("name") == "Assert failing-run outputs and JUnit contents"
    )["run"]

    assert failing["with"]["pr-comment"] == "false"
    assert "junit-output" in failing["with"]
    assert "${{ runner.temp }}" in failing["with"]["junit-output"]
    assert "<failure" in assertions
    assert "junit-path" in assertions
