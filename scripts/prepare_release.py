"""Prepare version files after `uv sync --group release`; review and sign separately."""

import argparse
from pathlib import Path
import subprocess
import tempfile


CONFIG = """[semantic_release]
version_toml = ["pyproject.toml:project.version"]
major_on_zero = false
allow_zero_version = true
build_command = ""

[semantic_release.branches.local]
match = ".*"
prerelease = false
"""


def prepare(root: Path, *, dry_run: bool = False) -> None:
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    if status.stdout.strip():
        raise ValueError("Release preparation requires a clean working tree")
    with tempfile.TemporaryDirectory(prefix="insomnia-release-config-") as scratch:
        config = Path(scratch) / "release.toml"
        config.write_text(CONFIG, encoding="utf-8")
        command = [
            "uv",
            "run",
            "--frozen",
            "--no-sync",
            "semantic-release",
            "--config",
            str(config),
        ]
        if dry_run:
            command.append("--noop")
        command.extend(
            [
                "version",
                "--no-commit",
                "--no-tag",
                "--no-push",
                "--no-vcs-release",
                "--skip-build",
            ]
        )
        subprocess.run(command, cwd=root, check=True)
    if not dry_run:
        subprocess.run(["uv", "lock", "--offline"], cwd=root, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    prepare(args.root.resolve(), dry_run=args.dry_run)
    print(
        "Review the version, lockfile, and changelog changes before committing or signing a tag."
    )


if __name__ == "__main__":
    main()
