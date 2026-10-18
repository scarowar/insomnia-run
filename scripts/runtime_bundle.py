"""Verify runtime identities and extract only bounded regular archive files."""

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import gzip
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
from typing import BinaryIO, Callable, Iterator
import zipfile
from urllib.parse import unquote, urlsplit


MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 10_000
MANIFEST_NAME = "manifest.json"
LOCK_NAME = "uv.lock"
REQUIREMENTS_NAME = "requirements.txt"


def runner_path(path: Path, runner_temp: Path) -> Path:
    root = runner_temp.resolve(strict=True)
    resolved = path.resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise ValueError("Installer-managed files must stay inside RUNNER_TEMP")
    return resolved


def require_digest(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", value):
        raise ValueError(
            "A trusted SHA-256 digest (64 hexadecimal characters) is required"
        )
    return value.lower()


@contextmanager
def regular_file(path: Path) -> Iterator[BinaryIO]:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
    )
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("Installer input must be a regular file")
        yield stream


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with regular_file(path) as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _member_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (
        not name
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in name
        or ":" in name
        or any(ord(char) < 32 or ord(char) == 127 for char in name)
        or path == PurePosixPath(".")
    ):
        raise ValueError("Unsafe archive member path")
    return path


def _write_member(stream: BinaryIO, destination: Path, size: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with destination.open("xb") as output:
        os.chmod(destination, 0o600)
        remaining = size
        while remaining:
            block = stream.read(min(remaining, 1024 * 1024))
            if not block:
                raise ValueError("Archive member is shorter than its declared size")
            output.write(block)
            remaining -= len(block)
        if stream.read(1):
            raise ValueError("Archive member exceeds its declared size")


def _extract_zip(
    archive: Path, target: Callable[[str, int, bool], Path], max_members: int
) -> None:
    with zipfile.ZipFile(archive) as source:
        for count, member in enumerate(source.infolist(), 1):
            if count > max_members:
                raise ValueError("Archive member limit exceeded")
            if member.is_dir() and member.filename in (".", "./"):
                continue
            mode = member.external_attr >> 16
            if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError(
                    "Archives may contain only directories and regular files"
                )
            output = target(member.filename, member.file_size, member.is_dir())
            if member.is_dir():
                output.mkdir(parents=True, exist_ok=True, mode=0o700)
            else:
                with source.open(member) as stream:
                    _write_member(stream, output, member.file_size)


def _extract_tar(
    archive: Path, target: Callable[[str, int, bool], Path], max_members: int
) -> None:
    with tarfile.open(archive, "r|*") as source:
        for count, member in enumerate(source, 1):
            if count > max_members:
                raise ValueError("Archive member limit exceeded")
            if member.isdir() and member.name in (".", "./"):
                continue
            if not member.isdir() and not member.isfile():
                raise ValueError(
                    "Archives may contain only directories and regular files"
                )
            if member.sparse is not None:
                raise ValueError("Sparse archive members are not supported")
            output = target(member.name, member.size, member.isdir())
            if member.isdir():
                output.mkdir(parents=True, exist_ok=True, mode=0o700)
                continue
            stream = source.extractfile(member)
            if stream is None:
                raise ValueError("Missing archive member data")
            with stream:
                _write_member(stream, output, member.size)


def _extract(archive: Path, root: Path, max_bytes: int, max_members: int) -> None:
    seen: dict[str, bool] = {}
    total = 0

    def target(name: str, size: int, directory: bool) -> Path:
        nonlocal total
        path = _member_path(name)
        key = path.as_posix().casefold()
        if key in seen:
            raise ValueError("Duplicate archive member path")
        if any(
            seen.get(parent.as_posix().casefold()) is False for parent in path.parents
        ):
            raise ValueError("Archive file conflicts with a directory")
        if not directory and any(item.startswith(key + "/") for item in seen):
            raise ValueError("Archive file conflicts with a directory")
        seen[key] = directory
        total += size
        if size < 0 or total > max_bytes:
            raise ValueError("Archive size or member limit exceeded")
        return root.joinpath(*path.parts)

    if zipfile.is_zipfile(archive):
        _extract_zip(archive, target, max_members)
    else:
        _extract_tar(archive, target, max_members)


def extract_verified(
    archive: Path,
    checksum: str,
    destination: Path,
    *,
    max_bytes: int = MAX_ARCHIVE_BYTES,
    max_members: int = MAX_ARCHIVE_MEMBERS,
) -> None:
    """Hash a private snapshot, then atomically expose its validated contents."""
    checksum = require_digest(checksum)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Extraction destination must not exist")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".insomnia-verify-", dir=destination.parent
    ) as scratch:
        private = Path(scratch)
        snapshot = private / "archive"
        digest = hashlib.sha256()
        size = 0
        with regular_file(archive) as source, snapshot.open("xb") as output:
            os.chmod(snapshot, 0o600)
            for block in iter(lambda: source.read(1024 * 1024), b""):
                size += len(block)
                if size > max_bytes:
                    raise ValueError("Archive size limit exceeded")
                digest.update(block)
                output.write(block)
        if digest.hexdigest() != checksum:
            raise ValueError("Archive failed SHA-256 verification")
        extracted = private / "contents"
        extracted.mkdir(mode=0o700)
        _extract(snapshot, extracted, max_bytes, max_members)
        if destination.exists() or destination.is_symlink():
            raise ValueError("Extraction destination must not exist")
        extracted.rename(destination)


def source_digest(project: Path) -> str:
    paths = [project / "pyproject.toml"]
    source_paths = list((project / "src").rglob("*"))
    if any(path.is_symlink() for path in source_paths):
        raise ValueError("Source identity must not include symlinks")
    paths.extend(
        path
        for path in source_paths
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    )
    digest = hashlib.sha256()
    for path in sorted(paths):
        if any(
            parent.is_symlink()
            for parent in (path, *path.parents)
            if parent.is_relative_to(project)
        ):
            raise ValueError("Source identity must not include symlinks")
        relative = path.relative_to(project).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate runtime manifest key")
        result[key] = value
    return result


@dataclass(frozen=True)
class VerifiedBundle:
    root: Path
    requirements: Path
    application: Path


def _load_manifest(root: Path) -> dict:
    manifest_path = root / MANIFEST_NAME
    if manifest_path.stat().st_size > 1024 * 1024:
        raise ValueError("Runtime manifest is too large")
    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object
    )
    expected = {
        "schema_version",
        "source_sha256",
        "lock_sha256",
        "python_tag",
        "platform",
        "application",
        "files",
    }
    if (
        not isinstance(manifest, dict)
        or set(manifest) != expected
        or type(manifest["schema_version"]) is not int
        or manifest["schema_version"] != 1
    ):
        raise ValueError("Unsupported runtime manifest schema")
    return manifest


def _verify_bundle_files(root: Path, files: dict) -> None:
    if not isinstance(files, dict) or not files or len(files) > MAX_ARCHIVE_MEMBERS:
        raise ValueError("Invalid runtime bundle file manifest")
    actual = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }
    if any(path.is_symlink() for path in root.rglob("*")):
        raise ValueError("Runtime bundle must not contain symlinks")
    if actual != set(files) | {MANIFEST_NAME}:
        raise ValueError("Runtime bundle contains missing or unlisted files")
    for name, digest in files.items():
        path = _member_path(name)
        if path.as_posix() != name or (
            name != REQUIREMENTS_NAME
            and (
                len(path.parts) != 2
                or path.parts[0] != "wheels"
                or not name.endswith(".whl")
            )
        ):
            raise ValueError("Unexpected runtime bundle file")
        if not isinstance(digest, str) or sha256_file(root / name) != require_digest(
            digest
        ):
            raise ValueError("Runtime bundle file failed SHA-256 verification")


def _wheel_hashes(files: dict) -> dict[tuple[str, str], str]:
    wheels = {}
    for name in files:
        if name.endswith(".whl"):
            parts = PurePosixPath(name).name.split("-")
            if len(parts) not in (5, 6):
                raise ValueError("Invalid wheel filename")
            key = (re.sub(r"[-_.]+", "-", parts[0]).lower(), parts[1])
            if key in wheels:
                raise ValueError("Duplicate runtime wheel package")
            wheels[key] = files[name]
    return wheels


def _requirement_hashes(requirements: Path) -> dict[tuple[str, str], str]:
    entries = {}
    for line in requirements.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(
            r"([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9][A-Za-z0-9.!+_-]*) --hash=sha256:([a-f0-9]{64})",
            line,
        )
        if not match:
            raise ValueError(
                "Runtime requirements must be exact hashed wheel requirements"
            )
        key = (re.sub(r"[-_.]+", "-", match[1]).lower(), match[2])
        if key in entries:
            raise ValueError("Duplicate runtime requirement")
        entries[key] = match[3]
    return entries


def verify_bundle(
    root: Path, project: Path, python_tag: str, platform_tag: str
) -> VerifiedBundle:
    manifest = _load_manifest(root)
    if manifest["source_sha256"] != source_digest(project) or manifest[
        "lock_sha256"
    ] != sha256_file(project / LOCK_NAME):
        raise ValueError("Runtime bundle source/lock identity mismatch")
    if manifest["python_tag"] != python_tag or manifest["platform"] != platform_tag:
        raise ValueError("Runtime bundle Python/platform identity mismatch")
    files = manifest["files"]
    _verify_bundle_files(root, files)
    application = manifest["application"]
    if (
        not isinstance(application, str)
        or application not in files
        or not application.startswith("wheels/insomnia_run-")
    ):
        raise ValueError("Runtime bundle application wheel is missing")
    requirements = root / REQUIREMENTS_NAME
    if REQUIREMENTS_NAME not in files or requirements.stat().st_size > 1024 * 1024:
        raise ValueError("Runtime bundle requirements are missing or too large")
    wheels = _wheel_hashes(files)
    if _requirement_hashes(requirements) != wheels:
        raise ValueError("Runtime requirements do not match the wheelhouse")
    return VerifiedBundle(root, requirements, root / application)


def _select_locked_wheel(requirement, lock: dict, supported: dict) -> tuple[str, dict]:
    from packaging.utils import canonicalize_name, parse_wheel_filename

    if requirement.url or requirement.extras or len(requirement.specifier) != 1:
        raise ValueError("Bundle dependencies must use exact registry wheel versions")
    specifier = next(iter(requirement.specifier))
    if specifier.operator != "==" or "*" in specifier.version:
        raise ValueError("Bundle dependencies must use exact registry wheel versions")
    packages = [
        package
        for package in lock["package"]
        if canonicalize_name(package["name"]) == canonicalize_name(requirement.name)
        and package["version"] == specifier.version
    ]
    if len(packages) != 1:
        raise ValueError(
            "Runtime dependency does not match exactly one lockfile package"
        )
    candidates = []
    for wheel in packages[0].get("wheels", []):
        filename = unquote(PurePosixPath(urlsplit(wheel["url"]).path).name)
        name, version, _, tags = parse_wheel_filename(filename)
        ranks = [supported[tag] for tag in tags if tag in supported]
        if (
            ranks
            and name == canonicalize_name(requirement.name)
            and str(version) == specifier.version
        ):
            candidates.append((min(ranks), filename, wheel))
    if not candidates:
        raise ValueError(
            "Locked runtime dependency has no wheel for the build platform"
        )
    _, filename, selected = min(candidates, key=lambda item: (item[0], item[1]))
    return filename, selected


def build_bundle(project: Path, output: Path, *, uv: str = "uv") -> Path:
    """Build a native wheelhouse from the frozen runtime dependency selection."""
    import tomllib
    from packaging.requirements import Requirement
    from packaging.tags import sys_tags
    from packaging.utils import parse_wheel_filename
    from install_runtime import download_archive

    project = project.resolve(strict=True)
    source_hash = source_digest(project)
    lock_hash = sha256_file(project / LOCK_NAME)
    lock = tomllib.loads((project / LOCK_NAME).read_text(encoding="utf-8"))
    environment = dict(os.environ, UV_PYTHON_DOWNLOADS="never")
    for name in (
        "INSOMNIA_RUN_DOWNLOAD_TOKEN",
        "INPUT_DOWNLOAD_TOKEN",
        "INSO_DOWNLOAD_TOKEN",
    ):
        environment.pop(name, None)
    selection = subprocess.run(
        [
            uv,
            "export",
            "--frozen",
            "--no-dev",
            "--no-emit-project",
            "--no-hashes",
            "--no-annotate",
            "--no-header",
            "--format",
            REQUIREMENTS_NAME,
            "--project",
            str(project),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    ).stdout
    supported = {tag: rank for rank, tag in enumerate(sys_tags())}
    with tempfile.TemporaryDirectory(prefix="insomnia-bundle-build-") as scratch:
        root = Path(scratch)
        wheels = root / "wheels"
        wheels.mkdir(mode=0o700)
        for line in selection.splitlines():
            if not line.strip():
                continue
            requirement = Requirement(line)
            if requirement.marker and not requirement.marker.evaluate():
                continue
            filename, selected = _select_locked_wheel(requirement, lock, supported)
            wheel_path = wheels / filename
            if PurePosixPath(filename).name != filename or "\\" in filename:
                raise ValueError("Invalid locked wheel filename")
            download_archive(selected["url"], wheel_path)
            if sha256_file(wheel_path) != require_digest(
                selected["hash"].removeprefix("sha256:")
            ):
                raise ValueError("Locked dependency wheel failed SHA-256 verification")
        build_dir = root / "application"
        subprocess.run(
            [
                uv,
                "build",
                "--wheel",
                "--project",
                str(project),
                "--out-dir",
                str(build_dir),
                "--python",
                sys.executable,
                "--no-python-downloads",
            ],
            check=True,
            env=environment,
        )
        application_wheels = list(build_dir.glob("insomnia_run-*.whl"))
        if len(application_wheels) != 1:
            raise ValueError("Bundle build must produce exactly one application wheel")
        application = wheels / application_wheels[0].name
        shutil.copyfile(application_wheels[0], application)
        requirements = []
        for wheel in sorted(wheels.iterdir()):
            name, version, _, _ = parse_wheel_filename(wheel.name)
            requirements.append(
                f"{name}=={version} --hash=sha256:{sha256_file(wheel)}\n"
            )
        (root / REQUIREMENTS_NAME).write_text("".join(requirements), encoding="utf-8")
        files = {
            path.relative_to(root).as_posix(): sha256_file(path)
            for path in [root / REQUIREMENTS_NAME, *sorted(wheels.iterdir())]
        }
        manifest = {
            "schema_version": 1,
            "source_sha256": source_hash,
            "lock_sha256": lock_hash,
            "python_tag": sys.implementation.cache_tag,
            "platform": sysconfig.get_platform(),
            "application": application.relative_to(root).as_posix(),
            "files": files,
        }
        (root / MANIFEST_NAME).write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        # The build scratch directory is not itself a payload member.
        shutil.rmtree(build_dir)
        verify_bundle(
            root, project, sys.implementation.cache_tag, sysconfig.get_platform()
        )
        output.mkdir(parents=True, exist_ok=True)
        filename = f"insomnia-run-runtime-{sys.implementation.cache_tag}-{sysconfig.get_platform()}.tar.gz"
        destination = output / filename
        with (
            destination.open("xb") as stream,
            gzip.GzipFile(
                filename="", mode="wb", fileobj=stream, mtime=0
            ) as compressed,
            tarfile.open(fileobj=compressed, mode="w") as archive,
        ):
            for name in sorted([MANIFEST_NAME, *files]):
                path = root / name
                member = tarfile.TarInfo(name)
                member.size = path.stat().st_size
                member.mode = 0o600
                with path.open("rb") as source:
                    archive.addfile(member, source)
        return destination
