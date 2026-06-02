from pathlib import Path
import re

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
    assert "sonarqube.yml" in workflows
    assert "codeql.yml" in workflows
    assert "dependency-review.yml" in workflows
    assert "scorecards.yml" in workflows


def test_third_party_actions_are_pinned_to_sha():
    for path in [*WORKFLOWS, *ACTION_FILES]:
        for line_number, ref in uses_references(path):
            if ref.startswith("./"):
                continue
            assert ACTION_REF_RE.search(ref), f"{path}:{line_number} uses {ref}"


def test_jobs_start_with_harden_runner_and_have_timeouts():
    for path in WORKFLOWS:
        workflow = load_yaml(path)
        for job_name, job in workflow.get("jobs", {}).items():
            steps = job.get("steps", [])
            if not steps:
                continue
            assert job.get("timeout-minutes"), f"{path}:{job_name} missing timeout"
            assert job["timeout-minutes"] <= 25, f"{path}:{job_name} timeout too high"
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

        assert step.get("with", {}).get("version") == "0.11.11", (
            f"{path}:{job_name} setup-uv does not pin uv version"
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
    dependency_review = load_yaml(
        ROOT / ".github" / "workflows" / "dependency-review.yml"
    )
    e2e = load_yaml(ROOT / ".github" / "workflows" / "e2e-test.yml")
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
        "github.actor != 'pre-commit-ci[bot]'"
        in security["jobs"]["deterministic-security"]["if"]
    )
    assert "github.actor != 'dependabot[bot]'" in sonarqube["jobs"]["sonar"]["if"]
    assert "github.actor != 'pre-commit-ci[bot]'" in sonarqube["jobs"]["sonar"]["if"]
    assert (
        "github.event.pull_request.head.repo.full_name == github.repository"
        in sonarqube["jobs"]["sonar"]["if"]
    )


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


def test_security_workflow_runs_deterministic_scanners():
    workflow = load_yaml(ROOT / ".github" / "workflows" / "security.yml")
    steps_text = "\n".join(
        step.get("run", "")
        for step in workflow["jobs"]["deterministic-security"]["steps"]
    )

    assert "uv run pip-audit --strict" in steps_text
    assert "uv run bandit -r src/insomnia_run" in steps_text
    assert "uv run zizmor --offline ." in steps_text
    assert "uv run cyclonedx-py environment .venv" in steps_text


def test_sonarqube_waits_for_quality_gate():
    workflow = load_yaml(ROOT / ".github" / "workflows" / "sonarqube.yml")
    sonar_steps = workflow["jobs"]["sonar"]["steps"]
    scan_step = next(
        step for step in sonar_steps if "sonarqube-scan-action" in step.get("uses", "")
    )

    assert scan_step["env"]["SONAR_TOKEN"] == "${{ secrets.SONAR_TOKEN }}"
    assert "-Dsonar.host.url=https://sonarcloud.io" in scan_step["with"]["args"]
    assert "-Dsonar.organization=scarowar" in scan_step["with"]["args"]
    assert "-Dsonar.projectKey=scarowar_insomnia-run" in scan_step["with"]["args"]
    assert (
        "-Dsonar.python.coverage.reportPaths=coverage.xml" in scan_step["with"]["args"]
    )
    assert "-Dsonar.qualitygate.wait=true" in scan_step["with"]["args"]
    assert "--cov-report=xml:coverage.xml" in "\n".join(
        step.get("run", "") for step in sonar_steps
    )
