"""Install an Inso binary only from an explicitly verified release archive."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tarfile
import tempfile
import zipfile

from install_runtime import download_archive
from runtime_bundle import extract_verified, require_digest, runner_path


def expected_digest(asset: str, manifest: Path, supplied: str = "") -> str:
    checksums = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(checksums, dict):
        raise ValueError("Invalid bundled SHA-256 manifest")
    bundled = checksums.get(asset, "")
    if not isinstance(bundled, str) or not isinstance(supplied, str):
        raise ValueError("Invalid SHA-256 digest")
    bundled = require_digest(bundled) if bundled else ""
    explicit = require_digest(supplied) if supplied else ""
    if bundled and explicit and bundled != explicit:
        raise ValueError("inso-sha256 conflicts with the bundled release digest")
    if not (bundled or explicit):
        raise ValueError(
            "Unbundled Inso releases require an explicit trusted inso-sha256"
        )
    return bundled or explicit


def cache_identity(version: str, platform: str, digest: str, archive: str = "") -> str:
    identity = json.dumps(
        [version, platform, require_digest(digest), archive], separators=(",", ":")
    )
    return "insomnia-run-inso-v2-" + hashlib.sha256(identity.encode()).hexdigest()


def install_inso(archive: Path, digest: str, destination: Path) -> Path:
    # Explicit archives always take precedence over preinstalled executables.
    if destination.is_symlink():
        raise ValueError("Inso destination must not be a symlink")
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix=".inso-", dir=destination) as scratch:
        extracted = Path(scratch) / "contents"
        extract_verified(archive, digest, extracted)
        binaries = list(extracted.rglob("inso"))
        binaries = [path for path in binaries if path.is_file()]
        if len(binaries) != 1:
            raise ValueError("Verified archive must contain exactly one inso binary")
        staged = Path(scratch) / "inso"
        shutil.copyfile(binaries[0], staged)
        staged.chmod(0o700)
        target = destination / "inso"
        if target.is_symlink():
            raise ValueError("Inso destination must not be a symlink")
        os.replace(staged, target)
        return target


def _check_runner_paths(archive_path: Path, install_dir: Path | None) -> None:
    if os.environ.get("RUNNER_TEMP"):
        root = Path(os.environ["RUNNER_TEMP"])
        runner_path(archive_path, root)
        if install_dir:
            runner_path(install_dir, root)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", required=True)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "inso-checksums.json",
    )
    parser.add_argument("--inso-sha256", default="")
    parser.add_argument("--inso-archive", default="")
    parser.add_argument("--archive-path", type=Path, required=True)
    parser.add_argument("--install-dir", type=Path)
    parser.add_argument("--download-token-origin", default="")
    parser.add_argument("--offline-install", action="store_true")
    parser.add_argument("--cache-key", action="store_true")
    args = parser.parse_args()
    try:
        match = re.fullmatch(
            r"inso-(linux-x64|macos)-(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)\.(?:tar\.xz|zip)",
            args.asset,
        )
        if not match:
            raise ValueError("Invalid Inso release asset name")
        _check_runner_paths(args.archive_path, args.install_dir)
        digest = expected_digest(args.asset, args.manifest, args.inso_sha256)
        if args.inso_archive and not args.inso_sha256:
            raise ValueError("A custom inso-archive requires explicit inso-sha256")
        if args.cache_key:
            print(cache_identity(match[2], match[1], digest, args.inso_archive))
            return
        location = (
            args.inso_archive
            or f"https://github.com/Kong/insomnia/releases/download/core%40{match[2]}/{args.asset}"
        )
        if not args.archive_path.exists():
            download_archive(
                location,
                args.archive_path,
                token=os.environ.get("INSOMNIA_RUN_DOWNLOAD_TOKEN", ""),
                origin=args.download_token_origin,
                offline=args.offline_install,
            )
        if args.install_dir:
            install_inso(args.archive_path, digest, args.install_dir)
        else:
            from runtime_bundle import sha256_file

            if sha256_file(args.archive_path) != digest:
                raise ValueError("Inso archive failed SHA-256 verification")
    except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile) as error:
        reason = str(error) if isinstance(error, ValueError) else type(error).__name__
        parser.exit(1, f"Inso installation failed: {reason}\n")


if __name__ == "__main__":
    main()
