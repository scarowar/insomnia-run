import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def release():
    return load_script("build_release")


def test_preparation_only_changes_local_version_files(tmp_path, monkeypatch):
    prepare = load_script("prepare_release")
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(prepare.subprocess, "run", run)
    prepare.prepare(tmp_path, dry_run=True)
    command = calls[-1]
    assert command[:5] == ["uv", "run", "--frozen", "--no-sync", "semantic-release"]
    assert "--noop" in command
    assert command.index("--noop") < command.index("version")
    for flag in (
        "--no-commit",
        "--no-tag",
        "--no-push",
        "--no-vcs-release",
        "--skip-build",
    ):
        assert flag in command
    assert all("push" not in args[:2] for args in calls)


def test_preparation_refuses_dirty_tree(tmp_path, monkeypatch):
    prepare = load_script("prepare_release")
    run = Mock(
        return_value=subprocess.CompletedProcess([], 0, stdout=" M action.yml\n")
    )
    monkeypatch.setattr(prepare.subprocess, "run", run)
    with pytest.raises(ValueError, match="clean"):
        prepare.prepare(tmp_path)
    assert run.call_count == 1


def test_preparation_supplies_version_locations_without_repo_configuration(
    tmp_path, monkeypatch
):
    prepare = load_script("prepare_release")
    configuration = []
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if "semantic-release" in args:
            configuration.append(Path(args[args.index("--config") + 1]).read_text())
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(prepare.subprocess, "run", run)
    prepare.prepare(tmp_path)
    assert '"pyproject.toml:project.version"' in configuration[0]
    assert "major_on_zero = false" in configuration[0]
    assert calls[-1] == ["uv", "lock", "--offline"]


def test_locked_semantic_release_configuration_dry_run(tmp_path):
    binary = os.environ.get("INSOMNIA_RELEASE_TOOL_BINARY")
    if not binary:
        pytest.skip(
            "Set INSOMNIA_RELEASE_TOOL_BINARY to the locked semantic-release executable"
        )
    prepare = load_script("prepare_release")
    config = tmp_path / "release.toml"
    config.write_text(prepare.CONFIG)
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"GH_TOKEN", "GITHUB_TOKEN"}
    }
    result = subprocess.run(
        [binary, "--config", str(config), "--noop", "version", "--print"],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    import re

    assert re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+\s*", result.stdout)


@pytest.mark.parametrize(
    "alternate_version", [None, "9.8.7"], ids=["current", "changed"]
)
def test_runtime_sbom_command_keeps_root_project_identity(tmp_path, alternate_version):
    import json
    import shutil

    if sys.version_info < (3, 11):
        pytest.skip("Release tooling runs on Python 3.14; tomllib requires 3.11")
    import tomllib

    project_file = ROOT / "pyproject.toml"
    project = tomllib.loads(project_file.read_text())
    if alternate_version:
        project_file = tmp_path / "pyproject.toml"
        project_file.write_text(
            f'[project]\nname = "{project["project"]["name"]}"\nversion = "{alternate_version}"\n'
        )
    binary = shutil.which("cyclonedx-py") or str(ROOT / ".venv/bin/cyclonedx-py")
    if not Path(binary).is_file():
        pytest.skip("Runtime SBOM generation requires the locked dev tools")
    output = tmp_path / "bom.json"
    subprocess.run(
        [
            binary,
            "environment",
            str(ROOT / ".venv"),
            "--pyproject",
            str(project_file),
            "--output-reproducible",
            "--of",
            "JSON",
            "-o",
            str(output),
        ],
        check=True,
        capture_output=True,
    )
    bom = json.loads(output.read_text())
    assert bom["bomFormat"] == "CycloneDX"
    assert bom["metadata"]["component"]["name"] == "insomnia-run"
    expected = tomllib.loads(project_file.read_text())["project"]["version"]
    assert bom["metadata"]["component"]["version"] == expected


def test_manifest_hashes_every_asset_and_is_stable(release, tmp_path):
    (tmp_path / "insomnia_run-0.2.0.whl").write_bytes(b"wheel")
    (tmp_path / "insomnia_run-0.2.0.tar.gz").write_bytes(b"source")
    release.write_checksums(tmp_path)
    first = (tmp_path / "SHA256SUMS").read_bytes()
    release.write_checksums(tmp_path)
    assert (tmp_path / "SHA256SUMS").read_bytes() == first
    assert "insomnia_run-0.2.0.whl" in first.decode()
    assert "SHA256SUMS" not in first.decode()


def test_manifest_refuses_symlinks(release, tmp_path):
    (tmp_path / "bad.whl").symlink_to("/etc/passwd")
    with pytest.raises(ValueError, match="regular"):
        release.write_checksums(tmp_path)


def test_recovery_uploads_only_missing_assets_and_publishes_last(release, tmp_path):
    wheel = tmp_path / "package.whl"
    wheel.write_bytes(b"wheel")
    sums = tmp_path / "SHA256SUMS"
    sums.write_bytes(b"checksums")
    events = []
    existing = {
        "id": 7,
        "tag_name": "v0.2.0",
        "draft": True,
        "target_commitish": "a" * 40,
        "assets": [{"name": "package.whl", "id": 9}],
    }

    def api(path, method="GET", data=None, upload=None):
        events.append((path, method, data, upload))
        if path.endswith("/immutable-releases"):
            return {"enabled": True}
        if path.endswith("/releases?per_page=100"):
            return [[existing]]
        if path.endswith("/assets/9"):
            return b"wheel"
        if path.endswith("assets?per_page=100"):
            return [existing["assets"]]
        if upload:
            return {"id": 10}
        if path.endswith("/assets/10"):
            return b"checksums"
        return {}

    release.publish_assets("owner/repo", "v0.2.0", "a" * 40, tmp_path, api)
    uploads = [event for event in events if event[3]]
    assert [event[3].name for event in uploads] == ["SHA256SUMS"]
    assert events[0][0] == "repos/owner/repo/immutable-releases"
    assert events[-2][0] == "repos/owner/repo/immutable-releases"
    assert events[-1][1:3] == ("PATCH", {"draft": False})


@pytest.mark.parametrize("response_lost", [False, True])
def test_interrupted_upload_reuses_draft_from_paginated_release_inventory(
    release, tmp_path, response_lost
):
    (tmp_path / "package.whl").write_bytes(b"wheel")
    (tmp_path / "SHA256SUMS").write_bytes(b"checksums")
    unrelated = {"id": 99, "tag_name": "v0.9.0", "draft": True, "assets": []}
    drafts = {99: unrelated}
    contents = {}
    uploads = []
    interrupted = False
    endpoint = "repos/owner/repo/releases"

    def api(path, method="GET", data=None, upload=None):
        nonlocal interrupted
        if path == "repos/owner/repo/immutable-releases" and method == "GET":
            return {"enabled": True}
        if path == endpoint + "?per_page=100":
            return [[{"tag_name": "v0.1.0", "draft": False}], list(drafts.values())]
        if path == endpoint + "/tags/v0.2.0":
            # GitHub's tag endpoint does not expose unpublished drafts.
            raise release.NotFound()
        if path == endpoint and method == "POST":
            draft = {"id": len(drafts) + 6, **data, "assets": []}
            drafts[draft["id"]] = draft
            return draft
        for release_id, draft in drafts.items():
            if (
                path == f"{endpoint}/{release_id}/assets?per_page=100"
                and method == "GET"
            ):
                return [list(draft["assets"])]
            if (
                upload
                and method == "POST"
                and path
                == f"https://uploads.github.com/{endpoint}/{release_id}/assets?name={upload.name}"
            ):
                uploads.append(upload.name)
                interrupt = upload.name == "package.whl" and not interrupted
                if interrupt and not response_lost:
                    interrupted = True
                    raise OSError("interrupted upload")
                asset_id = len(contents) + 10
                contents[asset_id] = upload.read_bytes()
                draft["assets"].append({"id": asset_id, "name": upload.name})
                if interrupt:
                    interrupted = True
                    raise OSError("interrupted upload")
                return {"id": asset_id}
            if path == f"{endpoint}/{release_id}" and method == "PATCH":
                draft.update(data)
                return draft
        if path in {f"{endpoint}/assets/{key}" for key in contents} and method == "GET":
            return contents[int(path.rsplit("/", 1)[1])]
        pytest.fail(f"Unexpected release API request: {method} {path}")

    with pytest.raises(OSError, match="interrupted"):
        release.publish_assets("owner/repo", "v0.2.0", "a" * 40, tmp_path, api)
    release.publish_assets("owner/repo", "v0.2.0", "a" * 40, tmp_path, api)
    assert len(drafts) == 2
    assert drafts[99] is unrelated
    assert unrelated == {"id": 99, "tag_name": "v0.9.0", "draft": True, "assets": []}
    assert drafts[7]["draft"] is False
    expected = ["SHA256SUMS", "package.whl"] + (
        [] if response_lost else ["package.whl"]
    )
    assert uploads == expected
    assert {asset["name"] for asset in drafts[7]["assets"]} == {
        "SHA256SUMS",
        "package.whl",
    }


@pytest.mark.parametrize("published", [False, True])
def test_ambiguous_or_published_release_inventory_is_never_modified(
    release, tmp_path, published
):
    (tmp_path / "package.whl").write_bytes(b"wheel")
    candidates = [
        {"id": 7, "tag_name": "v0.2.0", "draft": True},
        {"id": 8, "tag_name": "v0.2.0", "draft": not published},
    ]
    events = []

    def api(path, method="GET", data=None, upload=None):
        events.append(method)
        if path.endswith("/immutable-releases"):
            return {"enabled": True}
        if path.endswith("/releases?per_page=100"):
            return [[candidates[0]], [candidates[1]]]
        if "/tags/" in path:
            raise release.NotFound()
        pytest.fail("Ambiguous or published release caused an API mutation")

    with pytest.raises(ValueError, match="Multiple drafts|published"):
        release.publish_assets("owner/repo", "v0.2.0", "a" * 40, tmp_path, api)
    assert events == ["GET", "GET"]


def test_recovered_draft_target_must_match_before_asset_mutation(release, tmp_path):
    (tmp_path / "package.whl").write_bytes(b"wheel")
    api = Mock(
        side_effect=[
            {"enabled": True},
            [
                [
                    {
                        "id": 7,
                        "tag_name": "v0.2.0",
                        "draft": True,
                        "target_commitish": "b" * 40,
                    }
                ]
            ],
        ]
    )
    with pytest.raises(ValueError, match="target conflicts"):
        release.publish_assets("owner/repo", "v0.2.0", "a" * 40, tmp_path, api)
    assert all(not call.kwargs for call in api.call_args_list)


def test_release_inventory_permission_error_never_creates_a_draft(release, tmp_path):
    (tmp_path / "package.whl").write_bytes(b"wheel")
    api = Mock(
        side_effect=[
            {"enabled": True},
            subprocess.CalledProcessError(1, ["gh", "api"], stderr=b"HTTP 403"),
        ]
    )
    with pytest.raises(subprocess.CalledProcessError):
        release.publish_assets("owner/repo", "v0.2.0", "a" * 40, tmp_path, api)
    assert all(not call.kwargs for call in api.call_args_list)


@pytest.mark.parametrize(
    "draft,content", [(False, b"wheel"), (True, b"other"), (True, b"")]
)
def test_published_or_conflicting_assets_are_never_changed(
    release, tmp_path, draft, content
):
    (tmp_path / "package.whl").write_bytes(b"wheel")
    events = []

    def api(path, method="GET", data=None, upload=None):
        events.append(method)
        if path.endswith("/immutable-releases"):
            return {"enabled": True}
        if path.endswith("/releases?per_page=100"):
            return [
                [
                    {
                        "id": 7,
                        "tag_name": "v0.2.0",
                        "draft": draft,
                        "target_commitish": "a" * 40,
                        "assets": [{"name": "package.whl", "id": 9}],
                    }
                ]
            ]
        if path.endswith("assets?per_page=100"):
            return [[{"name": "package.whl", "id": 9}]]
        return content

    with pytest.raises(ValueError, match="published|conflict"):
        release.publish_assets("owner/repo", "v0.2.0", "a" * 40, tmp_path, api)
    assert events == (["GET", "GET"] if not draft else ["GET", "GET", "GET", "GET"])


def test_dry_run_never_creates_or_uploads_release(release, tmp_path):
    (tmp_path / "package.whl").write_bytes(b"wheel")
    api = Mock()
    result = release.publish_assets(
        "owner/repo", "v0.2.0", "a" * 40, tmp_path, api, dry_run=True
    )
    assert result == ["package.whl"]
    api.assert_not_called()


@pytest.mark.parametrize(
    "settings",
    [
        {"enabled": False, "enforced_by_owner": False},
        {},
        {"enabled": 1},
        {"enabled": "true"},
        None,
        [],
    ],
)
def test_immutable_setting_must_be_boolean_true_before_any_release_mutation(
    release, tmp_path, settings
):
    (tmp_path / "package.whl").write_bytes(b"wheel")
    api = Mock(return_value=settings)
    with pytest.raises(ValueError, match="Immutable releases"):
        release.publish_assets("owner/repo", "v0.2.0", "a" * 40, tmp_path, api)
    api.assert_called_once_with("repos/owner/repo/immutable-releases")


@pytest.mark.parametrize(
    "error",
    [
        subprocess.CalledProcessError(1, ["gh", "api"], stderr=b"HTTP 403"),
        OSError("network unavailable"),
        ValueError("malformed API JSON"),
    ],
)
def test_unreadable_immutable_setting_fails_closed_with_permission_guidance(
    release, tmp_path, error
):
    (tmp_path / "package.whl").write_bytes(b"wheel")
    api = Mock(side_effect=error)
    with pytest.raises(ValueError, match="Administration: read"):
        release.publish_assets("owner/repo", "v0.2.0", "a" * 40, tmp_path, api)
    api.assert_called_once_with("repos/owner/repo/immutable-releases")


def test_immutable_not_found_is_not_interpreted_as_missing_draft(release, tmp_path):
    (tmp_path / "package.whl").write_bytes(b"wheel")
    api = Mock(side_effect=release.NotFound())
    with pytest.raises(ValueError, match="Administration: read"):
        release.publish_assets("owner/repo", "v0.2.0", "a" * 40, tmp_path, api)
    api.assert_called_once_with("repos/owner/repo/immutable-releases")


def test_missing_draft_is_created_before_upload_and_not_published_on_failure(
    release, tmp_path
):
    (tmp_path / "package.whl").write_bytes(b"wheel")
    events = []

    def api(path, method="GET", data=None, upload=None):
        events.append((method, data))
        if path.endswith("/immutable-releases"):
            return {"enabled": True}
        if path.endswith("/releases?per_page=100"):
            return [[]]
        if path.endswith("assets?per_page=100"):
            return [[]]
        if upload:
            raise OSError("interrupted upload")
        return {"id": 7, "assets": [], "draft": True, "target_commitish": "a" * 40}

    with pytest.raises(OSError):
        release.publish_assets("owner/repo", "v0.2.0", "a" * 40, tmp_path, api)
    assert events[2][1]["draft"] is True
    assert not any(method == "PATCH" for method, _ in events)


def test_signed_tag_validation_requires_exact_primary_identity(release):
    trusted = release.SIGNER_FINGERPRINT
    release.validate_signature(
        f"[GNUPG:] VALIDSIG {'B' * 40} 2026-10-16 1 0 4 0 22 8 00 {trusted}"
    )
    with pytest.raises(ValueError, match="signer"):
        release.validate_signature(
            f"[GNUPG:] VALIDSIG {'C' * 40} 2026-10-16 1 0 4 0 22 8 00 {'D' * 40}"
        )
    with pytest.raises(ValueError, match="signer"):
        release.validate_signature("")


def test_required_checks_require_success_from_expected_apps(release):
    checks = [{"name": "Lint", "conclusion": "success", "app": {"id": 15368}}]
    release.validate_checks(checks, [], {"Lint": 15368})
    checks[0]["app"]["id"] = 999
    with pytest.raises(ValueError, match="Lint"):
        release.validate_checks(checks, [], {"Lint": 15368})
    with pytest.raises(ValueError, match="missing"):
        release.validate_checks([], [], {"missing": 15368})
    with pytest.raises(ValueError, match="nonempty"):
        release.validate_checks([], [], {})
    statuses = [
        {
            "id": 1,
            "context": "pre-commit.ci - pr",
            "state": "success",
            "creator": {"login": "pre-commit-ci[bot]"},
        }
    ]
    release.validate_checks([], statuses, {"pre-commit.ci - pr": 68672})


def test_release_workflow_is_manual_and_has_no_unconditional_publish():
    import yaml

    workflow = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())
    triggers = workflow.get("on", workflow.get(True))
    assert set(triggers) == {"workflow_dispatch"}
    assert triggers["workflow_dispatch"]["inputs"]["publish"]["default"] is False
    assert workflow["concurrency"]["cancel-in-progress"] is False
    assert workflow["jobs"]["publish"]["if"] == "inputs.publish"
    assert "if" not in workflow["jobs"]["assemble"]
    assert "id-token" not in workflow["permissions"]


@pytest.mark.parametrize(
    "selected,dispatch,allowed",
    [
        ("a" * 40, "a" * 40, True),
        ("a" * 40, "b" * 40, False),
        ("", "a" * 40, False),
        ("a" * 40, "", False),
        ("", "", False),
        ("main", "main", False),
        ("A" * 40, "A" * 40, False),
        ("a" * 40 + "\n", "a" * 40 + "\n", False),
        ("a" * 39 + ";", "a" * 39 + ";", False),
    ],
)
def test_release_dispatch_guard_runs_before_checkout(selected, dispatch, allowed):
    import yaml

    workflow = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())
    jobs = workflow["jobs"]
    verify = jobs["verify"]
    assert "github.ref == 'refs/heads/main'" in verify["if"]
    assert "github.repository == 'scarowar/insomnia-run'" in verify["if"]
    steps = verify["steps"]
    guards = [step for step in steps if "WORKFLOW_SHA" in step.get("env", {})]
    assert len(guards) == 1
    guard = guards[0]
    assert guard["env"]["WORKFLOW_SHA"] == "${{ github.sha }}"
    assert guard["env"]["RELEASE_COMMIT"] == "${{ inputs.commit }}"
    checkout = next(
        step for step in steps if step.get("uses", "").startswith("actions/checkout@")
    )
    assert steps.index(guard) < steps.index(checkout)
    assert jobs["build"]["needs"] == "verify"
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", guard["run"]],
        env={**os.environ, "RELEASE_COMMIT": selected, "WORKFLOW_SHA": dispatch},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == (0 if allowed else 1)
    if not allowed:
        assert "workflow dispatch SHA" in result.stdout + result.stderr


@pytest.fixture
def release_checkout(tmp_path, release, monkeypatch):
    root = tmp_path / "checkout"
    root.mkdir()
    environment = {
        **os.environ,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
    }

    def git(*args):
        return subprocess.run(
            [
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "tag.gpgsign=false",
                "-C",
                str(root),
                *args,
            ],
            env=environment,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    git("init", "-q")
    git("config", "user.name", "Release fixture")
    git("config", "user.email", "release@example.invalid")
    (root / "pyproject.toml").write_text('[project]\nversion = "0.2.0"\n')
    (root / "source.py").write_text("VALUE = 1\n")
    git("add", ".")
    git("commit", "-qm", "Create release fixture")
    commit = git("rev-parse", "HEAD")
    git("tag", "v0.2.0")
    git("update-ref", "refs/remotes/origin/main", commit)
    real_run = subprocess.run
    signature = f"[GNUPG:] VALIDSIG {'B' * 40} 2026-10-16 1 0 4 0 22 8 00 {release.SIGNER_FINGERPRINT}"

    def run(args, **kwargs):
        if args[:2] == ["git", "verify-tag"]:
            assert args == [
                "git",
                "verify-tag",
                "--raw",
                "--",
                "refs/tags/v0.2.0",
            ]
            return subprocess.CompletedProcess(args, 0, stderr=signature)
        if args[0] != "git":
            pytest.fail("Release must reject dirty source before running build tools")
        return real_run(args, **kwargs)

    monkeypatch.setattr(release.subprocess, "run", run)
    monkeypatch.setattr(release, "tested_commit", Mock(return_value=commit))
    api = Mock(
        side_effect=[
            {
                "rules": [
                    {
                        "type": "required_status_checks",
                        "parameters": {
                            "required_status_checks": [
                                {"context": "Test", "integration_id": 1}
                            ]
                        },
                    }
                ]
            },
            [
                {
                    "check_runs": [
                        {"name": "Test", "conclusion": "success", "app": {"id": 1}}
                    ]
                }
            ],
            [[]],
        ]
    )
    monkeypatch.setattr(release, "gh_api", api)
    return root, git, commit, api


def dirty_release_source(root, git, mutation):
    path = root / "source.py"
    if mutation in ("modified", "staged", "staged-and-modified"):
        path.write_text("VALUE = 2\n")
        if mutation != "modified":
            git("add", "source.py")
        if mutation == "staged-and-modified":
            path.write_text("VALUE = 3\n")
    elif mutation in ("deleted", "staged-delete"):
        path.unlink()
        if mutation == "staged-delete":
            git("add", "-u")
    else:
        git("mv", "source.py", "renamed.py")


@pytest.mark.skipif(sys.version_info < (3, 11), reason="Release requires tomllib")
@pytest.mark.parametrize("tag_matches", [True, False])
def test_release_uses_tag_namespace_despite_conflicting_ref(
    release, release_checkout, tag_matches
):
    root, git, commit, _ = release_checkout
    other = git("commit-tree", "HEAD^{tree}", "-p", "HEAD", "-m", "Other commit")
    git("update-ref", "refs/tags/v0.2.0", commit if tag_matches else other)
    git("update-ref", "refs/v0.2.0", other if tag_matches else commit)
    if tag_matches:
        release.verify(root, "v0.2.0", commit)
    else:
        with pytest.raises(ValueError, match="must agree"):
            release.verify(root, "v0.2.0", commit)


@pytest.mark.parametrize(
    "mutation",
    [
        "modified",
        "staged",
        "staged-and-modified",
        "deleted",
        "staged-delete",
        "renamed",
    ],
)
@pytest.mark.parametrize("operation", ["verify", "build"])
def test_release_refuses_tracked_changes_before_identity_or_build(
    release, release_checkout, operation, mutation, monkeypatch
):
    root, git, commit, api = release_checkout
    dirty_release_source(root, git, mutation)
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import runtime_bundle

    identity = Mock(side_effect=AssertionError("Dirty source reached bundle identity"))
    monkeypatch.setattr(runtime_bundle, "source_digest", identity)
    output = root / "release-assets"
    if operation == "verify":
        release_operation = release.verify
        arguments = (root, "v0.2.0", commit)
    else:
        release_operation = release.build
        arguments = (root, output)
    with pytest.raises(ValueError, match="tracked"):
        release_operation(*arguments)
    identity.assert_not_called()
    api.assert_not_called()
    release.tested_commit.assert_not_called()
    assert not output.exists()


@pytest.mark.parametrize("ignored", [False, True])
@pytest.mark.parametrize(
    "relative",
    [
        "src/insomnia_run/untracked.py",
        "src/insomnia_run/data.json",
        "src/insomnia_run/name with\na newline.py",
        "pyproject.toml",
        "uv.lock",
        "uv.toml",
        ".python-version",
        "README.md",
        "LICENSE",
    ],
)
def test_release_rejects_untracked_and_ignored_build_inputs(
    release, release_checkout, relative, ignored
):
    root, git, _, api = release_checkout
    if relative == "pyproject.toml":
        git("rm", "--cached", "pyproject.toml")
    if ignored:
        pattern = "/src/" if relative.startswith("src/") else "/" + relative
        (root / ".gitignore").write_text(pattern + "\n")
        git("add", ".gitignore")
    if ignored or relative == "pyproject.toml":
        git("commit", "-qm", "Prepare untracked build input fixture")
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("untracked build input\n")
    assert git("status", "--porcelain", "--untracked-files=no") == ""
    if ignored:
        assert git("check-ignore", "--", relative)

    with pytest.raises(ValueError, match="untracked package or build inputs"):
        release.require_clean_tracked_tree(root)

    api.assert_not_called()


@pytest.mark.parametrize("ignored", [False, True])
@pytest.mark.parametrize(
    "relative",
    [
        "release-assets/package.whl",
        "src/insomnia_run/__pycache__/cached.cpython-312.pyc",
        "src/insomnia_run/cached.pyc",
    ],
)
def test_release_allows_generated_assets_and_excluded_bytecode(
    release, release_checkout, relative, ignored
):
    root, git, _, _ = release_checkout
    if ignored:
        (root / ".gitignore").write_text("/release-assets/\n__pycache__/\n*.pyc\n")
        git("add", ".gitignore")
        git("commit", "-qm", "Ignore generated release fixture files")
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"generated")
    if ignored:
        assert git("check-ignore", "--", relative)

    release.require_clean_tracked_tree(root)


def test_release_verifier_allows_untracked_generated_assets(release, release_checkout):
    if sys.version_info < (3, 11):
        pytest.skip("Release tooling requires Python 3.11 or later")
    root, _, commit, api = release_checkout
    (root / "release-assets").mkdir()
    (root / "release-assets/package.whl").write_bytes(b"generated")
    release.verify(root, "v0.2.0", commit)
    assert api.call_count == 3


def test_release_build_allows_untracked_assets_before_bundle_identity(
    release, release_checkout, monkeypatch
):
    root, _, _, _ = release_checkout
    (root / "generated.txt").write_text("untracked")
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import runtime_bundle

    build = Mock(side_effect=RuntimeError("reached clean build"))
    monkeypatch.setattr(runtime_bundle, "build_bundle", build)
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    with pytest.raises(RuntimeError, match="reached clean build"):
        release.build(root, root / "release-assets", bundle_only=True)
    build.assert_called_once()


def test_release_metadata_requires_tag_version_and_commit_identity(release, tmp_path):
    if sys.version_info < (3, 11):
        pytest.skip("Release tooling runs on Python 3.14; tomllib requires 3.11")
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.2.0"\n')
    release.validate_version(tmp_path, "v0.2.0")
    with pytest.raises(ValueError, match="version"):
        release.validate_version(tmp_path, "v0.3.0")
    with pytest.raises(ValueError, match="tag"):
        release.validate_version(tmp_path, "v0.2.0;evil")


def test_gh_client_does_not_treat_permission_error_as_absent(release, monkeypatch):
    def run(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0], stderr=b"HTTP 403")

    monkeypatch.setattr(release.subprocess, "run", run)
    with pytest.raises(subprocess.CalledProcessError):
        release.gh_api("repos/owner/repo/releases/tags/v0.2.0")


def test_release_rejects_unexpected_existing_assets(release, tmp_path):
    (tmp_path / "package.whl").write_bytes(b"wheel")
    api = Mock(
        side_effect=[
            {"enabled": True},
            [
                [
                    {
                        "id": 7,
                        "tag_name": "v0.2.0",
                        "draft": True,
                        "target_commitish": "a" * 40,
                    }
                ]
            ],
            [[{"name": "old.exe", "id": 9}]],
        ]
    )
    with pytest.raises(ValueError, match="unexpected"):
        release.publish_assets("owner/repo", "v0.2.0", "a" * 40, tmp_path, api)
    assert api.call_count == 3


def test_failed_latest_check_cannot_be_hidden_by_older_success(release):
    checks = [
        {"id": 1, "name": "Lint", "conclusion": "success", "app": {"id": 15368}},
        {"id": 2, "name": "Lint", "conclusion": "failure", "app": {"id": 15368}},
    ]
    with pytest.raises(ValueError, match="Lint"):
        release.validate_checks(checks, [], {"Lint": 15368})


def test_pr_only_checks_require_merged_identical_tree(release, tmp_path, monkeypatch):
    commit = "a" * 40
    head = "b" * 40
    calls = []

    def api(path):
        calls.append(path)
        if "/pulls?" in path:
            return [
                [
                    {
                        "merged_at": "2026-10-16",
                        "merge_commit_sha": commit,
                        "base": {"ref": "main"},
                        "head": {"sha": head},
                    }
                ]
            ]
        if "/check-runs?" in path:
            return [
                {
                    "check_runs": [
                        {"name": "Lint", "conclusion": "success", "app": {"id": 15368}}
                    ]
                }
            ]
        return [[]]

    monkeypatch.setattr(release, "gh_api", api)
    monkeypatch.setattr(release, "git", lambda *args: "same-tree")
    assert release.tested_commit(tmp_path, commit) == head
    monkeypatch.setattr(release, "git", lambda root, *args: args[-1])
    with pytest.raises(ValueError, match="tested"):
        release.tested_commit(tmp_path, commit)


def test_incomplete_release_assets_are_rejected(release, tmp_path):
    (tmp_path / "package.whl").write_bytes(b"wheel")
    with pytest.raises(ValueError, match="complete"):
        release.validate_asset_set(tmp_path, "v0.2.0")


def test_corrupt_uploaded_asset_leaves_draft_unpublished(release, tmp_path):
    (tmp_path / "package.whl").write_bytes(b"wheel")
    api = Mock(
        side_effect=[
            {"enabled": True},
            [[]],
            {"id": 7, "draft": True, "target_commitish": "a" * 40},
            [[]],
            {"id": 9},
            b"corrupt",
        ]
    )
    with pytest.raises(ValueError, match="verification"):
        release.publish_assets("owner/repo", "v0.2.0", "a" * 40, tmp_path, api)
    assert not any(call.kwargs.get("method") == "PATCH" for call in api.call_args_list)


def test_github_api_uses_binary_asset_response_and_only_maps_404(release, monkeypatch):
    run = Mock(return_value=subprocess.CompletedProcess([], 0, stdout=b"binary-wheel"))
    monkeypatch.setattr(release.subprocess, "run", run)
    assert release.gh_api("repos/owner/repo/releases/assets/9") == b"binary-wheel"
    assert "Accept: application/octet-stream" in run.call_args.args[0]
    run.side_effect = subprocess.CalledProcessError(
        1, [], stderr=b"gh: Not Found (HTTP 404)"
    )
    with pytest.raises(release.NotFound):
        release.gh_api("repos/owner/repo/releases/tags/v0.2.0")


def test_github_api_sends_json_and_upload_bytes_without_shell(
    release, tmp_path, monkeypatch
):
    run = Mock(return_value=subprocess.CompletedProcess([], 0, stdout=b'{"id": 1}'))
    monkeypatch.setattr(release.subprocess, "run", run)
    assert release.gh_api(
        "repos/owner/repo/releases", method="POST", data={"draft": True}
    ) == {"id": 1}
    assert run.call_args.kwargs["input"] == b'{"draft": true}'
    release.gh_api(
        "https://uploads.github.com/repos/owner/repo/releases/1/assets?name=a.whl",
        method="POST",
        upload=tmp_path / "a.whl",
    )
    assert str(tmp_path / "a.whl") in run.call_args.args[0]
    release.gh_api("repos/owner/repo/releases/1/assets?per_page=100")
    assert "--paginate" in run.call_args.args[0]
    run.return_value = subprocess.CompletedProcess([], 0, stdout=b"")
    assert (
        release.gh_api(
            "repos/owner/repo/releases/1", method="PATCH", data={"draft": False}
        )
        is None
    )


@pytest.mark.parametrize("kind", ["directory", "unsafe-name", "empty"])
def test_invalid_local_asset_inputs(release, tmp_path, kind):
    if kind == "directory":
        (tmp_path / "directory").mkdir()
    elif kind == "unsafe-name":
        (tmp_path / "bad\nname.whl").write_bytes(b"wheel")
    with pytest.raises(ValueError, match="assets"):
        release.asset_paths(tmp_path)


@pytest.mark.parametrize(
    "repository,tag,commit",
    [
        ("owner/repo/extra", "v0.2.0", "a" * 40),
        ("owner/repo", "latest", "a" * 40),
        ("owner/repo", "v0.2.0", "main"),
    ],
)
def test_publisher_rejects_untrusted_identity_before_network(
    release, tmp_path, repository, tag, commit
):
    api = Mock()
    with pytest.raises(ValueError, match="Invalid"):
        release.publish_assets(repository, tag, commit, tmp_path, api)
    api.assert_not_called()


def test_verifier_checks_exact_signed_tree_and_required_results(
    release, tmp_path, monkeypatch
):
    if sys.version_info < (3, 11):
        pytest.skip("Release tooling requires Python 3.11 or later")
    commit = "a" * 40
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.2.0"\n')
    monkeypatch.setattr(
        release,
        "git",
        lambda root, *args: "" if args[0] in {"status", "ls-files"} else commit,
    )
    monkeypatch.setattr(release, "tested_commit", lambda *args: "b" * 40)
    status = f"[GNUPG:] VALIDSIG {'B' * 40} 2026-10-16 1 0 4 0 22 8 00 {release.SIGNER_FINGERPRINT}"
    monkeypatch.setattr(
        release.subprocess,
        "run",
        Mock(return_value=subprocess.CompletedProcess([], 0, stderr=status)),
    )
    api = Mock(
        side_effect=[
            {
                "rules": [
                    {
                        "type": "required_status_checks",
                        "parameters": {
                            "required_status_checks": [
                                {"context": "Lint", "integration_id": 15368}
                            ]
                        },
                    }
                ]
            },
            [
                {
                    "check_runs": [
                        {"name": "Lint", "conclusion": "success", "app": {"id": 15368}}
                    ]
                }
            ],
            [[]],
        ]
    )
    monkeypatch.setattr(release, "gh_api", api)
    release.verify(tmp_path, "v0.2.0", commit)
    assert "/" + "b" * 40 + "/" in api.call_args_list[-1].args[0]
    with pytest.raises(ValueError, match="exact"):
        release.verify(tmp_path, "v0.2.0", "main")
    monkeypatch.setattr(
        release,
        "git",
        lambda root, *args: "" if args[0] in {"status", "ls-files"} else "c" * 40,
    )
    with pytest.raises(ValueError, match="agree"):
        release.verify(tmp_path, "v0.2.0", commit)


def test_git_uses_argument_vector(release, tmp_path, monkeypatch):
    run = Mock(return_value=subprocess.CompletedProcess([], 0, stdout="tree\n"))
    monkeypatch.setattr(release.subprocess, "run", run)
    assert release.git(tmp_path, "rev-parse", "HEAD") == "tree"
    assert run.call_args.args[0] == ["git", "rev-parse", "HEAD"]


def test_runtime_bundle_build_contract(release, tmp_path, monkeypatch):
    from types import SimpleNamespace
    import sysconfig

    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import runtime_bundle

    output = tmp_path / "assets"
    archive = output / "runtime.tar.gz"

    def build_bundle(root, directory):
        assert root == tmp_path
        assert directory == output
        archive.write_bytes(b"verified-by-installer-module")
        return archive

    monkeypatch.setattr(runtime_bundle, "build_bundle", build_bundle, raising=False)
    extract = Mock()
    verify = Mock(
        return_value=SimpleNamespace(requirements=tmp_path / "requirements.txt")
    )
    monkeypatch.setattr(runtime_bundle, "extract_verified", extract)
    monkeypatch.setattr(runtime_bundle, "verify_bundle", verify)
    monkeypatch.setattr(
        release,
        "git",
        lambda root, *args: "" if args[0] in {"status", "ls-files"} else "1700000000",
    )
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    run = Mock()
    monkeypatch.setattr(release.subprocess, "run", run)
    release.build(tmp_path, output)
    assert run.call_args_list[0].args[0] == ["uv", "build", "--out-dir", str(output)]
    assert "environment" in run.call_args.args[0]
    assert "--pyproject" in run.call_args.args[0]
    installs = [call.args[0] for call in run.call_args_list if "pip" in call.args[0]]
    assert len(installs) == 1
    for flag in ("--no-index", "--no-build", "--no-deps", "--require-hashes"):
        assert flag in installs[0]
    assert verify.call_args.args[2:] == (
        sys.implementation.cache_tag,
        sysconfig.get_platform(),
    )
    assert os.environ["SOURCE_DATE_EPOCH"] == "1700000000"
    assert extract.call_count == 1
    with pytest.raises(ValueError, match="empty"):
        release.build(tmp_path, output)


@pytest.mark.parametrize(
    "command", ["verify", "build", "checksums", "validate", "publish"]
)
def test_cli_routes_without_implicit_publication(
    release, tmp_path, monkeypatch, command
):
    mocks = {
        name: Mock(return_value=[])
        for name in (
            "verify",
            "build",
            "write_checksums",
            "validate_asset_set",
            "publish_assets",
        )
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(release, name, mock)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_release.py",
            command,
            "--root",
            str(tmp_path),
            "--directory",
            str(tmp_path),
            "--tag",
            "v0.2.0",
            "--commit",
            "a" * 40,
        ],
    )
    release.main()
    if command == "publish":
        assert mocks["publish_assets"].call_args.kwargs["dry_run"] is True
        mocks["verify"].assert_not_called()
    else:
        mocks["publish_assets"].assert_not_called()


def test_cli_explicit_publication_reverifies_commit(release, tmp_path, monkeypatch):
    validate = Mock()
    verify = Mock()
    publish = Mock(return_value=[])
    monkeypatch.setattr(release, "validate_asset_set", validate)
    monkeypatch.setattr(release, "verify", verify)
    monkeypatch.setattr(release, "publish_assets", publish)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_release.py",
            "publish",
            "--publish",
            "--root",
            str(tmp_path),
            "--directory",
            str(tmp_path),
            "--tag",
            "v0.2.0",
            "--commit",
            "a" * 40,
        ],
    )
    release.main()
    verify.assert_called_once_with(tmp_path, "v0.2.0", "a" * 40)
    assert publish.call_args.kwargs["dry_run"] is False


def test_prepare_cli_defaults_to_no_remote_operations(tmp_path, monkeypatch, capsys):
    prepare = load_script("prepare_release")
    operation = Mock()
    monkeypatch.setattr(prepare, "prepare", operation)
    monkeypatch.setattr(
        sys, "argv", ["prepare_release.py", "--root", str(tmp_path), "--dry-run"]
    )
    prepare.main()
    operation.assert_called_once_with(tmp_path, dry_run=True)
    assert "before committing" in capsys.readouterr().out


def test_complete_local_asset_set_is_checked_without_publication(
    release, tmp_path, monkeypatch
):
    import hashlib
    import io
    import json
    import tarfile

    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import runtime_bundle

    project = tmp_path / "project"
    project.mkdir()
    (project / "src").mkdir()
    (project / "pyproject.toml").write_text(
        '[project]\nname = "insomnia-run"\nversion = "0.2.0"\n'
    )
    (project / "uv.lock").write_text("version = 1\n")
    output = tmp_path / "output"
    output.mkdir()
    wheel_name = "insomnia_run-0.2.0-py3-none-any.whl"
    wheel = b"fixture-wheel"
    (output / wheel_name).write_bytes(wheel)
    (output / "insomnia_run-0.2.0.tar.gz").write_bytes(b"fixture-source")
    for platform in ("linux-x86_64", "macosx-10.13-x86_64", "macosx-11.0-arm64"):
        bundle = output / f"runtime-{platform}.tar.gz"
        requirements = f"insomnia-run==0.2.0 --hash=sha256:{hashlib.sha256(wheel).hexdigest()}\n".encode()
        files = {f"wheels/{wheel_name}": wheel, "requirements.txt": requirements}
        manifest = {
            "schema_version": 1,
            "source_sha256": runtime_bundle.source_digest(project),
            "lock_sha256": runtime_bundle.sha256_file(project / "uv.lock"),
            "python_tag": "cpython-314",
            "platform": platform,
            "application": f"wheels/{wheel_name}",
            "files": {
                name: hashlib.sha256(content).hexdigest()
                for name, content in files.items()
            },
        }
        files["manifest.json"] = json.dumps(manifest).encode()
        with tarfile.open(bundle, "w:gz") as archive:
            for name, content in files.items():
                member = tarfile.TarInfo(name)
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
        (output / (bundle.name + ".cyclonedx.json")).write_text(
            json.dumps(
                {
                    "bomFormat": "CycloneDX",
                    "metadata": {
                        "component": {"name": "insomnia-run", "version": "0.2.0"}
                    },
                }
            )
        )
    release.write_checksums(output)
    release.validate_asset_set(output, "v0.2.0", project)
    (output / wheel_name).write_bytes(b"different-wheel")
    release.write_checksums(output)
    with pytest.raises(ValueError, match="wheel"):
        release.validate_asset_set(output, "v0.2.0", project)
