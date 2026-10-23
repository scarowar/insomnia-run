"""Install an Inso binary only from an explicitly verified release archive."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import tarfile
import tempfile
import zipfile

from install_runtime import download_archive
from runtime_bundle import (
    extract_verified,
    require_digest,
    runner_path,
    sha256_file,
    open_directory,
    regular_file,
    require_directory_identity,
)

MANIFEST = Path(__file__).resolve().parents[1] / "inso-checksums.json"


def expected_digest(asset: str, manifest: Path, supplied: str = "") -> str:
    with regular_file(manifest) as stream:
        contents = stream.read(64 * 1024 + 1)
    if len(contents) > 64 * 1024:
        raise ValueError("Bundled SHA-256 manifest is too large")
    checksums = json.loads(contents)
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
    return "insomnia-run-inso-v3-" + hashlib.sha256(identity.encode()).hexdigest()


def install_inso(
    archive: Path,
    digest: str,
    destination: Path,
    *,
    archive_dir_fd: int | None = None,
) -> Path:
    # Explicit archives always take precedence over preinstalled executables.
    if destination.is_symlink():
        raise ValueError("Inso destination must not be a symlink")
    with (
        open_directory(destination, create=True) as parent,
        tempfile.TemporaryDirectory(prefix=".inso-") as scratch,
    ):
        extracted = Path(scratch) / "contents"
        extract_verified(archive, digest, extracted, archive_dir_fd=archive_dir_fd)
        binaries = list(extracted.rglob("inso"))
        binaries = [path for path in binaries if path.is_file()]
        if len(binaries) != 1:
            raise ValueError("Verified archive must contain exactly one inso binary")
        target = destination / "inso"
        try:
            existing = os.stat("inso", dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        if existing is not None and not stat.S_ISREG(existing.st_mode):
            raise ValueError("Inso destination must be a regular file, not a symlink")
        staged = ".inso-" + secrets.token_hex(12)
        descriptor = os.open(
            staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o700, dir_fd=parent
        )
        try:
            with (
                os.fdopen(descriptor, "wb") as output,
                regular_file(binaries[0]) as source,
            ):
                os.fchmod(output.fileno(), 0o700)
                shutil.copyfileobj(source, output)
                output.flush()
                os.fsync(output.fileno())
            require_directory_identity(destination, parent)
            os.replace(staged, "inso", src_dir_fd=parent, dst_dir_fd=parent)
        finally:
            try:
                os.unlink(staged, dir_fd=parent)
            except FileNotFoundError:
                pass
        return target


def _check_runner_paths(archive_path: Path, install_dir: Path | None) -> None:
    if os.environ.get("RUNNER_TEMP"):
        root = Path(os.environ["RUNNER_TEMP"])
        runner_path(archive_path, root)
        if install_dir:
            runner_path(install_dir, root)


def _install_cached_release(
    args: argparse.Namespace, location: str, digest: str
) -> None:
    with open_directory(args.cache_directory, create=True) as parent:
        archive = Path("archive")
        try:
            cached = sha256_file(archive, dir_fd=parent)
        except FileNotFoundError:
            cached = None
        if cached != digest:
            if cached is not None and args.offline_install:
                raise ValueError("Inso archive failed SHA-256 verification")
            download_archive(
                location,
                args.cache_directory / "archive",
                token=os.environ.get("INSOMNIA_RUN_DOWNLOAD_TOKEN", ""),
                origin=args.download_token_origin,
                offline=args.offline_install,
                download_origins=tuple(args.download_origin),
                expected_sha256=digest,
                replace=cached is not None,
                dir_fd=parent,
            )
        require_directory_identity(args.cache_directory, parent)
        if args.install_dir:
            install_inso(archive, digest, args.install_dir, archive_dir_fd=parent)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", required=True)
    parser.add_argument("--inso-sha256", default="")
    parser.add_argument("--inso-archive", default="")
    parser.add_argument("--cache-directory", type=Path, required=True)
    parser.add_argument("--install-dir", type=Path)
    parser.add_argument("--download-token-origin", default="")
    parser.add_argument("--download-origin", action="append", default=[])
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
        _check_runner_paths(args.cache_directory, args.install_dir)
        digest = expected_digest(args.asset, MANIFEST, args.inso_sha256)
        if args.inso_archive and not args.inso_sha256:
            raise ValueError("A custom inso-archive requires explicit inso-sha256")
        if args.cache_key:
            print(cache_identity(match[2], match[1], digest, args.inso_archive))
            return
        location = (
            args.inso_archive
            or f"https://github.com/Kong/insomnia/releases/download/core%40{match[2]}/{args.asset}"
        )
        _install_cached_release(args, location, digest)
    except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile) as error:
        reason = str(error) if isinstance(error, ValueError) else type(error).__name__
        parser.exit(1, f"Inso installation failed: {reason}\n")


if __name__ == "__main__":
    main()
