"""Exercise the configured hooks with the already-installed pinned Gitleaks."""

import os
from pathlib import Path
import shlex
import shutil
import sqlite3
import subprocess
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def secret_repository(tmp_path):
    store_module = pytest.importorskip(
        "pre_commit.store", reason="Secret scanning requires installed pre-commit"
    )
    config = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text())
    scanner = next(
        repo
        for repo in config["repos"]
        if repo["repo"] == "https://github.com/gitleaks/gitleaks"
    )
    cache = Path(store_module.Store.get_default_directory())
    database = cache / "db.db"
    if not database.is_file():
        pytest.skip("The pinned Gitleaks pre-commit environment is not installed")
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
        row = connection.execute(
            "SELECT path FROM repos WHERE repo = ? AND ref = ?",
            (scanner["repo"], scanner["rev"]),
        ).fetchone()
    if not row or not any(
        path.is_file() and os.access(path, os.X_OK)
        for path in Path(row[0]).glob("golangenv-*/bin/gitleaks")
    ):
        pytest.skip("The pinned Gitleaks pre-commit environment is not installed")

    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GIT_", "GITLEAKS_")) and key != "SKIP"
    }
    env.update(
        PRE_COMMIT_HOME=str(cache),
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_NAME="Scanner regression",
        GIT_AUTHOR_EMAIL="scanner@example.invalid",
        GIT_COMMITTER_NAME="Scanner regression",
        GIT_COMMITTER_EMAIL="scanner@example.invalid",
    )

    def git(*args):
        return subprocess.run(
            ["git", "-c", "core.hooksPath=" + os.devnull, *args],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
        )

    git("init", "--quiet")
    (tmp_path / ".pre-commit-config.yaml").write_text(
        yaml.safe_dump({"repos": [scanner]})
    )
    shutil.copyfile(ROOT / ".gitleaksignore", tmp_path / ".gitleaksignore")
    (tmp_path / "example.txt").write_text("A harmless scanner fixture.\n")
    git("add", ".")
    git("-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "Clean fixture")

    def scan(*args, cwd=tmp_path):
        return subprocess.run(
            [sys.executable, "-m", "pre_commit", "run", *args],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )

    return tmp_path, git, scan


def ci_scanner_args():
    workflow = yaml.safe_load((ROOT / ".github/workflows/security.yml").read_text())
    for step in workflow["jobs"]["deterministic-security"]["steps"]:
        for line in step.get("run", "").splitlines():
            args = shlex.split(line)
            if "pre-commit" in args and any(a.startswith("gitleaks") for a in args):
                index = args.index("pre-commit")
                assert args[:index] == [
                    "uv",
                    "run",
                    "--frozen",
                    "--no-sync",
                    "--no-build",
                ]
                assert args[index + 1] == "run"
                return args[index + 2 :]
    pytest.fail("The security workflow must invoke the configured secret scanner")


def write_synthetic_key(path):
    # Assemble a non-issued test token so this test's source is not itself a leak.
    token = "ghp_" + "aB3dE6gH9jK2mN5pQ8sT1vW4yZ7cF0iL3oR6"
    path.write_text(f'github_token = "{token}"\n')
    return token


def assert_redacted_detection(result, token, rule="github-pat"):
    output = result.stdout + result.stderr
    if token in output:
        pytest.fail("The secret scanner exposed the synthetic token", pytrace=False)
    if result.returncode != 1 or rule not in output or "REDACTED" not in output:
        pytest.fail("Expected a redacted secret finding:\n" + output, pytrace=False)


@pytest.mark.parametrize("line_number", [461, 470, 471])
def test_historical_fixture_exceptions_do_not_hide_new_findings(
    secret_repository, line_number
):
    root, git, scan = secret_repository
    path = root / "tests/test_runner.py"
    path.parent.mkdir()
    token = "abcdef" + "123456"
    path.write_text("\n" * (line_number - 1) + f"X-Api-Key: {token}\n")
    git("add", ".")
    git("-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "Reintroduced fixture")

    assert_redacted_detection(scan(*ci_scanner_args()), token, rule="generic-api-key")


def test_ci_detects_committed_secret_with_clean_index(secret_repository):
    root, git, scan = secret_repository
    token = write_synthetic_key(root / "committed-key.txt")
    git("add", ".")
    git("-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "Synthetic key")
    assert git("status", "--porcelain").stdout == ""

    assert_redacted_detection(scan(*ci_scanner_args()), token)


def test_ci_checkout_detects_a_secret_deleted_before_the_current_tree(
    secret_repository,
):
    root, git, scan = secret_repository
    key_file = root / "removed-key.txt"
    token = write_synthetic_key(key_file)
    git("add", ".")
    git("-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "Synthetic key")
    git("rm", "--quiet", key_file.name)
    git("-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "Remove key")
    assert git("status", "--porcelain").stdout == ""

    workflow = yaml.safe_load((ROOT / ".github/workflows/security.yml").read_text())
    checkout = next(
        step
        for step in workflow["jobs"]["deterministic-security"]["steps"]
        if step.get("uses", "").startswith("actions/checkout@")
    )
    depth = checkout.get("with", {}).get("fetch-depth", 1)
    checkout_dir = root / "workflow-checkout"
    args = ["clone", "--quiet"]
    if depth:
        args += ["--depth", str(depth)]
    git(*args, root.as_uri(), str(checkout_dir))
    assert not (checkout_dir / key_file.name).exists()

    assert_redacted_detection(scan(*ci_scanner_args(), cwd=checkout_dir), token)


def test_ci_accepts_clean_repository(secret_repository):
    _, git, scan = secret_repository
    assert git("status", "--porcelain").stdout == ""

    result = scan(*ci_scanner_args())

    assert result.returncode == 0, result.stdout + result.stderr


def test_local_hook_scans_only_staged_changes(secret_repository):
    root, git, scan = secret_repository
    token = write_synthetic_key(root / "committed-key.txt")
    git("add", ".")
    git("-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "Synthetic key")
    (root / "example.txt").write_text("Another harmless change.\n")
    git("add", "example.txt")

    result = scan("gitleaks", "--hook-stage", "pre-commit")

    assert result.returncode == 0, result.stdout + result.stderr
    write_synthetic_key(root / "staged-key.txt")
    git("add", "staged-key.txt")
    assert_redacted_detection(scan("gitleaks", "--hook-stage", "pre-commit"), token)
