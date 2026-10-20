"""Verify release identity, build distributions, and recover an unpublished draft.

Publication requires enabled immutable releases and Administration: read access
to verify the setting. Builds and dry-runs do not require that access.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import sysconfig
import tempfile
from urllib.parse import quote


SIGNER_FINGERPRINT = "31B08FE8A3D1BDC6EB69EAE1D18E27CC6E3E2D56"
REPOSITORY = "scarowar/insomnia-run"
RULESET_ID = 7137745
TAG = re.compile(r"v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", re.ASCII)
COMMIT_PATTERN = r"[a-f0-9]{40}"
PROJECT_FILE = "pyproject.toml"
SBOM_SUFFIX = ".cyclonedx.json"


class NotFound(Exception):
    """A GitHub resource does not exist (not an authentication failure)."""


def gh_api(path, method="GET", data=None, upload=None):
    command = ["gh", "api", "--method", method, path]
    if upload:
        command.extend(
            [
                "--header",
                "Content-Type: application/octet-stream",
                "--input",
                str(upload),
            ]
        )
    elif data is not None:
        command.extend(["--input", "-"])
    elif "/assets/" in path:
        command.extend(["--header", "Accept: application/octet-stream"])
    elif path.endswith("per_page=100"):
        command.extend(["--paginate", "--slurp"])
    try:
        result = subprocess.run(
            command,
            input=json.dumps(data).encode() if data is not None else None,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as error:
        if b"(HTTP 404)" in (error.stderr or b""):
            raise NotFound(path) from error
        raise
    if "/assets/" in path and method == "GET":
        return result.stdout
    if not result.stdout:
        return None
    return json.loads(result.stdout)


def validate_signature(status: str) -> None:
    signatures = [
        line.split()
        for line in status.splitlines()
        if line.startswith("[GNUPG:] VALIDSIG ")
    ]
    if not signatures or any(
        len(fields) < 12 or fields[-1].upper() != SIGNER_FINGERPRINT
        for fields in signatures
    ):
        raise ValueError(
            "Release tag signer does not match the trusted primary fingerprint"
        )


def validate_checks(checks: list, statuses: list, required: dict) -> None:
    if not required:
        raise ValueError("Release requires nonempty protected-branch checks")
    for name, app_id in required.items():
        matches = [
            check
            for check in checks
            if check["name"] == name and check.get("app", {}).get("id") == app_id
        ]
        if matches:
            latest = max(matches, key=lambda check: check.get("id", 0))
            success = latest.get("conclusion") == "success"
        else:
            candidates = [status for status in statuses if status["context"] == name]
            latest = max(candidates, key=lambda status: status.get("id", 0), default={})
            success = (
                app_id == 68672
                and latest.get("creator", {}).get("login") == "pre-commit-ci[bot]"
                and latest.get("state") == "success"
            )
        if not success:
            raise ValueError(
                f"Required release check is missing or unsuccessful: {name}"
            )


def git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def require_clean_tracked_tree(root: Path) -> None:
    if git(
        root,
        "status",
        "--porcelain",
        "--untracked-files=no",
        "--ignore-submodules=none",
    ):
        raise ValueError(
            "Release source must not contain tracked working-tree or index changes"
        )
    untracked = git(
        root,
        "ls-files",
        "--others",
        "-z",
        "--",
        "src",
        PROJECT_FILE,
        "uv.lock",
        "uv.toml",
        ".python-version",
        "README.md",
        "LICENSE",
    )
    if any(
        name and "__pycache__" not in Path(name).parts and Path(name).suffix != ".pyc"
        for name in untracked.split("\0")
    ):
        raise ValueError(
            "Release source must not contain untracked package or build inputs"
        )


def tested_commit(root: Path, commit: str) -> str:
    pages = gh_api(f"repos/{REPOSITORY}/commits/{commit}/pulls?per_page=100")
    for pr in (pr for page in pages for pr in page):
        if (
            pr.get("merged_at")
            and pr.get("merge_commit_sha") == commit
            and pr.get("base", {}).get("ref") == "main"
        ):
            head = pr["head"]["sha"]
            if not re.fullmatch(COMMIT_PATTERN, head):
                continue
            git(root, "fetch", "--no-tags", "origin", head)
            if git(
                root, "rev-parse", "--verify", "--end-of-options", f"{commit}^{{tree}}"
            ) == git(
                root, "rev-parse", "--verify", "--end-of-options", f"{head}^{{tree}}"
            ):
                return head
    raise ValueError("Release must match the tested tree of a merged main-branch PR")


def verify(root: Path, tag: str, commit: str) -> None:
    if not re.fullmatch(COMMIT_PATTERN, commit):
        raise ValueError("An exact tested commit SHA is required")
    require_clean_tracked_tree(root)
    if not TAG.fullmatch(tag):
        raise ValueError("Release tag must be an immutable vMAJOR.MINOR.PATCH tag")
    import tomllib

    project = tomllib.loads((root / PROJECT_FILE).read_text(encoding="utf-8"))
    if project["project"]["version"] != tag.removeprefix("v"):
        raise ValueError("Release tag and project version differ")
    tag_ref = f"refs/tags/{tag}"
    if (
        git(root, "rev-parse", "--verify", "--end-of-options", "HEAD") != commit
        or git(
            root, "rev-parse", "--verify", "--end-of-options", f"{tag_ref}^{{commit}}"
        )
        != commit
    ):
        raise ValueError("Tag, checkout, and tested commit must agree")
    git(root, "merge-base", "--is-ancestor", commit, "refs/remotes/origin/main")
    signature = subprocess.run(
        ["git", "verify-tag", "--raw", "--", tag_ref],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    validate_signature(signature.stderr)
    tested = tested_commit(root, commit)
    ruleset = gh_api(f"repos/{REPOSITORY}/rulesets/{RULESET_ID}")
    required = {
        check["context"]: check["integration_id"]
        for rule in ruleset["rules"]
        if rule["type"] == "required_status_checks"
        for check in rule["parameters"]["required_status_checks"]
    }
    check_pages = gh_api(f"repos/{REPOSITORY}/commits/{tested}/check-runs?per_page=100")
    status_pages = gh_api(f"repos/{REPOSITORY}/commits/{tested}/statuses?per_page=100")
    validate_checks(
        [check for page in check_pages for check in page["check_runs"]],
        [status for page in status_pages for status in page],
        required,
    )


def asset_paths(directory: Path) -> list[Path]:
    paths = sorted(directory.iterdir())
    if not paths:
        raise ValueError("Release has no assets")
    for path in paths:
        if (
            path.is_symlink()
            or not path.is_file()
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", path.name)
        ):
            raise ValueError("Release assets must have safe names and be regular files")
    return paths


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def write_checksums(directory: Path) -> None:
    paths = [path for path in asset_paths(directory) if path.name != "SHA256SUMS"]
    contents = "".join(f"{digest(path)}  {path.name}\n" for path in paths)
    (directory / "SHA256SUMS").write_text(contents, encoding="ascii")


def bundle_platform(bundle: Path, project: Path, wheel: Path) -> str:
    from runtime_bundle import extract_verified, verify_bundle

    with tempfile.TemporaryDirectory(prefix="insomnia-release-verify-") as scratch:
        extracted = Path(scratch) / "contents"
        extract_verified(bundle, digest(bundle), extracted)
        manifest = json.loads((extracted / "manifest.json").read_text(encoding="utf-8"))
        platform = manifest["platform"]
        verified = verify_bundle(extracted, project, "cpython-314", platform)
        if digest(verified.application) != digest(wheel):
            raise ValueError("Runtime application wheel differs from the release wheel")
        if platform == "linux-x86_64":
            return "linux-x86_64"
        if platform.startswith("macosx-") and platform.endswith("-x86_64"):
            return "macos-x86_64"
        if platform.startswith("macosx-") and platform.endswith("-arm64"):
            return "macos-arm64"
        raise ValueError("Unexpected runtime bundle platform")


def validate_asset_set(directory: Path, tag: str, project: Path | None = None) -> None:
    if not TAG.fullmatch(tag):
        raise ValueError("Invalid release tag")
    version = tag.removeprefix("v")
    paths = asset_paths(directory)
    wheel = f"insomnia_run-{version}-py3-none-any.whl"
    source = f"insomnia_run-{version}.tar.gz"
    bundles = [
        path
        for path in paths
        if path.name != source and path.name.endswith((".tar.gz", ".zip"))
    ]
    expected = (
        {wheel, source, "SHA256SUMS"}
        | {path.name for path in bundles}
        | {path.name + SBOM_SUFFIX for path in bundles}
    )
    if len(bundles) != 3 or {path.name for path in paths} != expected:
        raise ValueError(
            "Release assets are not complete: distributions, three native bundles, SBOMs, and checksums are required"
        )
    actual_sums = "".join(
        f"{digest(path)}  {path.name}\n" for path in paths if path.name != "SHA256SUMS"
    )
    if (directory / "SHA256SUMS").read_text(encoding="ascii") != actual_sums:
        raise ValueError("Release asset checksums differ")
    if project is None:
        raise ValueError("Release bundle verification requires the source project")
    platforms = set()
    for bundle in bundles:
        family = bundle_platform(bundle, project, directory / wheel)
        if family in platforms:
            raise ValueError("Duplicate runtime bundle platform")
        platforms.add(family)
        sbom = json.loads(
            (directory / (bundle.name + SBOM_SUFFIX)).read_text(encoding="utf-8")
        )
        component = sbom.get("metadata", {}).get("component", {})
        if (
            sbom.get("bomFormat") != "CycloneDX"
            or component.get("name") != "insomnia-run"
            or component.get("version") != version
        ):
            raise ValueError("Runtime SBOM project identity differs")


def verify_remote_asset(
    api, endpoint: str, asset_id: int, path: Path, *, uploaded: bool = False
) -> None:
    actual = api(f"{endpoint}/assets/{asset_id}")
    if hashlib.sha256(actual).hexdigest() != digest(path):
        reason = (
            "Uploaded asset failed verification"
            if uploaded
            else "Existing draft asset conflicts"
        )
        raise ValueError(f"{reason}: {path.name}")


def require_immutable_releases(repository: str, api=gh_api) -> None:
    try:
        settings = api(f"repos/{repository}/immutable-releases")
    except (NotFound, OSError, ValueError, subprocess.SubprocessError):
        raise ValueError(
            "Cannot verify immutable releases; publication is blocked. "
            "Reading the setting requires Administration: read access."
        ) from None
    if not isinstance(settings, dict) or settings.get("enabled") is not True:
        raise ValueError("Immutable releases must be enabled before publication.")


def existing_draft(api, endpoint: str, tag: str):
    # The tag endpoint exposes published releases, not recoverable drafts.
    matches = [
        candidate
        for page in api(f"{endpoint}?per_page=100")
        for candidate in page
        if candidate.get("tag_name") == tag
    ]
    if any(candidate.get("draft") is not True for candidate in matches):
        raise ValueError("Refusing to modify a published release")
    if len(matches) > 1:
        raise ValueError("Multiple drafts exist for the release tag")
    return matches[0] if matches else None


def publish_assets(
    repository: str,
    tag: str,
    commit: str,
    directory: Path,
    api=gh_api,
    *,
    dry_run: bool = False,
) -> list[str]:
    if (
        not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
        or not TAG.fullmatch(tag)
        or not re.fullmatch(COMMIT_PATTERN, commit)
    ):
        raise ValueError("Invalid release repository, tag, or commit")
    paths = asset_paths(directory)
    if dry_run:
        return [path.name for path in paths]
    require_immutable_releases(repository, api)
    endpoint = f"repos/{repository}/releases"
    release = existing_draft(api, endpoint, tag)
    if release is None:
        release = api(
            endpoint,
            method="POST",
            data={
                "tag_name": tag,
                "target_commitish": commit,
                "name": tag,
                "draft": True,
            },
        )
    if not release["draft"]:
        raise ValueError("Refusing to modify a published release")
    if release["target_commitish"] != commit:
        raise ValueError("Existing draft target conflicts with the tested commit")
    # Fetch all asset pages: the embedded assets field is not a complete inventory.
    pages = api(f"{endpoint}/{release['id']}/assets?per_page=100")
    assets = [asset for page in pages for asset in page]
    if len({asset["name"] for asset in assets}) != len(assets):
        raise ValueError("Existing draft contains duplicate assets")
    by_name = {asset["name"]: asset for asset in assets}
    if set(by_name) - {path.name for path in paths}:
        raise ValueError("Existing draft contains unexpected assets")
    for path in paths:
        if path.name in by_name:
            verify_remote_asset(api, endpoint, by_name[path.name]["id"], path)
    for path in paths:
        if path.name not in by_name:
            asset = api(
                f"https://uploads.github.com/{endpoint}/{release['id']}/assets?name={quote(path.name)}",
                method="POST",
                upload=path,
            )
            verify_remote_asset(api, endpoint, asset["id"], path, uploaded=True)
    require_immutable_releases(repository, api)
    api(f"{endpoint}/{release['id']}", method="PATCH", data={"draft": False})
    return [path.name for path in paths]


def build(root: Path, output: Path, *, bundle_only: bool = False) -> None:
    require_clean_tracked_tree(root)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Build output must be empty")
    output.mkdir(parents=True, exist_ok=True)
    os.environ["SOURCE_DATE_EPOCH"] = git(root, "show", "-s", "--format=%ct", "HEAD")
    if not bundle_only:
        subprocess.run(["uv", "build", "--out-dir", str(output)], cwd=root, check=True)
    # Kept in the installer module so producer and verifier share one identity format.
    from runtime_bundle import build_bundle, extract_verified, verify_bundle

    bundle = build_bundle(root, output)
    with tempfile.TemporaryDirectory(prefix="insomnia-release-sbom-") as scratch:
        extracted = Path(scratch) / "contents"
        extract_verified(bundle, digest(bundle), extracted)
        verified = verify_bundle(
            extracted, root, sys.implementation.cache_tag, sysconfig.get_platform()
        )
        environment = Path(scratch) / "runtime"
        subprocess.run(
            [
                "uv",
                "venv",
                "--no-project",
                "--no-python-downloads",
                "--python",
                sys.executable,
                str(environment),
            ],
            cwd=root,
            check=True,
        )
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(environment / "bin/python"),
                "--no-index",
                "--no-build",
                "--no-deps",
                "--require-hashes",
                "--find-links",
                str(extracted / "wheels"),
                "-r",
                str(verified.requirements),
            ],
            cwd=root,
            check=True,
        )
        subprocess.run(
            [
                "uv",
                "run",
                "--frozen",
                "--no-sync",
                "cyclonedx-py",
                "environment",
                str(environment),
                "--pyproject",
                str(root / PROJECT_FILE),
                "--output-reproducible",
                "--of",
                "JSON",
                "-o",
                str(output / (bundle.name + SBOM_SUFFIX)),
            ],
            cwd=root,
            check=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("verify", "build", "checksums", "validate", "publish")
    )
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--directory", type=Path, default=Path("release-assets"))
    parser.add_argument("--tag", default="")
    parser.add_argument("--commit", default="")
    parser.add_argument("--bundle-only", action="store_true")
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Publish a verified complete draft; otherwise only list local assets",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "verify":
        verify(root, args.tag, args.commit)
    elif args.command == "build":
        build(root, args.directory.resolve(), bundle_only=args.bundle_only)
    elif args.command == "checksums":
        write_checksums(args.directory)
    elif args.command == "validate":
        validate_asset_set(args.directory, args.tag, root)
    else:
        validate_asset_set(args.directory, args.tag, root)
        if args.publish:
            verify(root, args.tag, args.commit)
        print(
            json.dumps(
                publish_assets(
                    REPOSITORY,
                    args.tag,
                    args.commit,
                    args.directory,
                    dry_run=not args.publish,
                )
            )
        )


if __name__ == "__main__":
    main()
