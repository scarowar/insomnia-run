"""Install the frozen source runtime or an explicitly verified wheel bundle."""

import argparse
from contextlib import closing, contextmanager, nullcontext
import os
from pathlib import Path
import secrets
import signal
import stat
import subprocess  # nosec B404 # installation invokes uv with argument vectors
import sys
import sysconfig
import tempfile
import tarfile
import time
from typing import BinaryIO, Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile

from runtime_bundle import (
    MAX_ARCHIVE_BYTES,
    extract_verified,
    regular_file,
    open_directory,
    require_directory_identity,
    require_digest,
    runner_path,
    verify_bundle,
    sha256_file,
    tool_environment,
)


_INVALID_DOWNLOAD_URL = "Downloads require an unambiguous HTTPS URL"
_DOWNLOAD_DEADLINE_SECONDS = 300


def _split_url(value: str):
    try:
        return urlsplit(value)
    except ValueError:
        raise ValueError(_INVALID_DOWNLOAD_URL) from None


def _https_url(value: str):
    if (
        not value
        or any(ord(char) <= 32 or ord(char) == 127 for char in value)
        or "\\" in value
    ):
        raise ValueError(_INVALID_DOWNLOAD_URL)
    parsed = _split_url(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError(_INVALID_DOWNLOAD_URL)
    try:
        port = parsed.port if parsed.port is not None else 443
        if port == 0:
            raise ValueError("Invalid HTTPS download port")
    except ValueError as error:
        raise ValueError("Invalid HTTPS download port") from error
    return parsed, (parsed.hostname.lower(), port)


def token_origin(value: str) -> tuple[str, int]:
    parsed, origin = _https_url(value)
    if parsed.path not in ("", "/") or parsed.query or "*" in parsed.hostname:
        raise ValueError("Download token origin must not include a path or query")
    return origin


def download_origin(value: str) -> tuple[str, int]:
    parsed, origin = _https_url(value)
    if parsed.path or parsed.query or "*" in parsed.hostname:
        raise ValueError("Download origin must be an exact HTTPS origin")
    return origin


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _remaining_download_time(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ValueError("Archive download exceeded its total time limit")
    return remaining


def _copy_download(
    source: BinaryIO, output: BinaryIO, max_bytes: int, *, deadline: float | None = None
) -> None:
    total = 0
    read = getattr(source, "read1", source.read)
    while True:
        if deadline is not None:
            _remaining_download_time(deadline)
        block = read(1024 * 1024)
        if deadline is not None:
            _remaining_download_time(deadline)
        if not block:
            break
        total += len(block)
        if total > max_bytes:
            raise ValueError("Download size limit exceeded")
        output.write(block)


def _redirect_location(error: HTTPError, current: str, attempt: int) -> str:
    if error.code not in (301, 302, 303, 307, 308):
        error.close()
        raise ValueError(
            f"Archive download failed (HTTP {error.code}); not retried"
        ) from None
    location = error.headers.get("Location")
    error.close()
    if not location or attempt == 5:
        raise ValueError("Invalid or excessive archive redirects") from None
    try:
        return urljoin(current, location)
    except ValueError:
        raise ValueError(_INVALID_DOWNLOAD_URL) from None


@contextmanager
def _download_deadline() -> Iterator[float]:
    started = time.monotonic()
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_delay, previous_interval = signal.getitimer(signal.ITIMER_REAL)
    duration = (
        min(_DOWNLOAD_DEADLINE_SECONDS, previous_delay)
        if previous_delay
        else _DOWNLOAD_DEADLINE_SECONDS
    )

    def expired(signum, frame):
        raise ValueError("Archive download exceeded its total time limit")

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, duration)
    try:
        yield started + duration
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_delay:
            remaining = max(0.000001, previous_delay - (time.monotonic() - started))
            signal.setitimer(signal.ITIMER_REAL, remaining, previous_interval)


def _download_https(
    location: str,
    output: BinaryIO,
    token: str,
    allowed_origin: tuple[str, int] | None,
    max_bytes: int,
    download_origins: tuple[str, ...] = (),
) -> None:
    with _download_deadline() as deadline:
        _download_https_transfer(
            location,
            output,
            token,
            allowed_origin,
            max_bytes,
            download_origins,
            deadline=deadline,
        )


def _download_https_transfer(
    location: str,
    output: BinaryIO,
    token: str,
    allowed_origin: tuple[str, int] | None,
    max_bytes: int,
    download_origins: tuple[str, ...] = (),
    *,
    deadline: float,
) -> None:
    permitted = {
        ("github.com", 443),
        ("api.github.com", 443),
        ("release-assets.githubusercontent.com", 443),
        *(download_origin(value) for value in download_origins),
    }
    if _https_url(location)[1] not in permitted:
        raise ValueError("Archive download origin is not permitted")
    if token and allowed_origin not in permitted:
        raise ValueError("Download token origin is not permitted")
    opener = build_opener(_NoRedirect())
    current = location
    for attempt in range(6):
        request = _download_request(current, permitted, token, allowed_origin)
        try:
            response = opener.open(
                request, timeout=min(60, _remaining_download_time(deadline))
            )
        except HTTPError as error:
            current = _redirect_location(error, current, attempt)
            continue
        except URLError:
            raise ValueError("Archive download failed; check network access") from None
        with closing(response):
            if response.status != 200:
                raise ValueError(
                    f"Archive download requires HTTP 200 (received {response.status})"
                )
            _copy_download(response, output, max_bytes, deadline=deadline)
        break


def _download_request(
    current: str,
    permitted: set[tuple[str, int]],
    token: str,
    allowed_origin: tuple[str, int] | None,
) -> Request:
    parsed, current_origin = _https_url(current)
    for host, port in permitted:
        if (host, port) == current_origin:
            break
    else:
        raise ValueError("Archive redirect origin is not permitted")
    authority = f"[{host}]" if ":" in host else host
    if port != 443:
        authority += f":{port}"
    headers = {
        "User-Agent": "insomnia-run-installer",
        "Accept": "application/octet-stream",
    }
    if token and current_origin == allowed_origin:
        headers["Authorization"] = "Bearer " + token
    return Request(
        urlunsplit(("https", authority, parsed.path, parsed.query, "")), headers=headers
    )


def _check_download_destination(destination: Path, parent: int, replace: bool) -> None:
    try:
        existing = os.stat(destination.name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return
    if not replace:
        raise FileExistsError("Download destination already exists")
    if not stat.S_ISREG(existing.st_mode):
        raise ValueError("Cached archive must be a regular file")


def _download_token_origin(token: str, origin: str) -> tuple[str, int] | None:
    if token and (
        not origin or any(ord(char) < 32 or ord(char) == 127 for char in token)
    ):
        raise ValueError(
            "A valid download-token-origin is required for a download token"
        )
    return token_origin(origin) if origin else None


def _copy_archive_source(
    location: str,
    output: BinaryIO,
    *,
    token: str,
    allowed_origin: tuple[str, int] | None,
    max_bytes: int,
    download_origins: tuple[str, ...],
) -> None:
    if _split_url(location).scheme:
        _download_https(
            location, output, token, allowed_origin, max_bytes, download_origins
        )
    else:
        with regular_file(Path(location)) as source:
            _copy_download(source, output, max_bytes)


def _publish_download(
    staged: Path, destination: Path, parent: int, *, expected_sha256: str, replace: bool
) -> None:
    if expected_sha256 and sha256_file(staged, dir_fd=parent) != expected_sha256:
        raise ValueError("Inso archive failed SHA-256 verification")
    require_directory_identity(destination.parent, parent)
    if replace:
        os.replace(staged, destination.name, src_dir_fd=parent, dst_dir_fd=parent)
    else:
        os.link(
            staged,
            destination.name,
            src_dir_fd=parent,
            dst_dir_fd=parent,
            follow_symlinks=False,
        )


def download_archive(
    location: str,
    destination: Path,
    *,
    token: str = "",
    origin: str = "",
    offline: bool = False,
    max_bytes: int = MAX_ARCHIVE_BYTES,
    download_origins: tuple[str, ...] = (),
    expected_sha256: str = "",
    replace: bool = False,
    dir_fd: int | None = None,
) -> None:
    """Copy a local archive or fetch HTTPS with origin-scoped authentication."""
    allowed_origin = _download_token_origin(token, origin)
    for value in download_origins:
        download_origin(value)
    if expected_sha256:
        expected_sha256 = require_digest(expected_sha256)
    if replace and not expected_sha256:
        raise ValueError("Replacing a cached archive requires a trusted digest")
    parsed = _split_url(location)
    if parsed.scheme:
        _https_url(location)
    if parsed.scheme and offline:
        raise ValueError("Installer network access is disabled by offline-install")
    with (
        open_directory(destination.parent, create=True)
        if dir_fd is None
        else nullcontext(dir_fd)
    ) as parent:
        _check_download_destination(destination, parent, replace)
        staged = Path(".insomnia-download-" + secrets.token_hex(12))
        descriptor = os.open(
            staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=parent
        )
        try:
            with os.fdopen(descriptor, "wb") as output:
                os.fchmod(output.fileno(), 0o600)
                _copy_archive_source(
                    location,
                    output,
                    token=token,
                    allowed_origin=allowed_origin,
                    max_bytes=max_bytes,
                    download_origins=download_origins,
                )
                output.flush()
                os.fsync(output.fileno())
            _publish_download(
                staged,
                destination,
                parent,
                expected_sha256=expected_sha256,
                replace=replace,
            )
        finally:
            try:
                os.unlink(staged, dir_fd=parent)
            except FileNotFoundError:
                pass


def install_runtime(
    project: Path,
    venv: Path,
    uv: str,
    *,
    bundle: str = "",
    bundle_sha256: str = "",
    token: str = "",
    origin: str = "",
    offline: bool = False,
    download_origins: tuple[str, ...] = (),
) -> None:
    python = sys.executable
    if bool(bundle) != bool(bundle_sha256):
        raise ValueError(
            "runtime-bundle and runtime-bundle-sha256 must be provided together"
        )
    if venv.exists() or venv.is_symlink():
        raise ValueError("Runtime virtual environment destination must not exist")
    environment = tool_environment(offline=offline)
    prefix = [uv] + (["--offline"] if offline else [])

    def run(arguments, *, extra_environment=None):
        subprocess.run(  # nosec B603 # fixed uv operations, isolated validated destinations
            prefix + arguments,
            env={**environment, **(extra_environment or {})},
            check=True,
        )

    with tempfile.TemporaryDirectory(prefix="insomnia-runtime-") as scratch:
        root = Path(scratch)
        verified = None
        if bundle:
            require_digest(bundle_sha256)
            archive = root / "bundle"
            download_archive(
                bundle,
                archive,
                token=token,
                origin=origin,
                offline=offline,
                download_origins=download_origins,
            )
            extracted = root / "verified"
            extract_verified(archive, bundle_sha256, extracted)
            verified = verify_bundle(
                extracted,
                project,
                sys.implementation.cache_tag,
                sysconfig.get_platform(),
                uv=uv,
            )
        run(
            [
                "venv",
                "--no-project",
                "--no-python-downloads",
                "--python",
                python,
                str(venv),
            ]
        )
        interpreter = str(venv / "bin" / "python")
        if verified:
            run(
                [
                    "pip",
                    "install",
                    "--no-index",
                    "--no-build",
                    "--require-hashes",
                    "--find-links",
                    str(verified.root / "wheels"),
                    "--python",
                    interpreter,
                    "--requirement",
                    str(verified.requirements),
                ]
            )
        else:
            wheels = root / "wheels"
            run(
                [
                    "build",
                    "--wheel",
                    "--project",
                    str(project),
                    "--out-dir",
                    str(wheels),
                    "--python",
                    python,
                    "--no-python-downloads",
                ]
            )
            run(
                [
                    "sync",
                    "--frozen",
                    "--no-dev",
                    "--no-build",
                    "--no-install-project",
                    "--project",
                    str(project),
                    "--python",
                    python,
                    "--no-python-downloads",
                ],
                extra_environment={"UV_PROJECT_ENVIRONMENT": str(venv)},
            )
            built = list(wheels.glob("*.whl"))
            if len(built) != 1:
                raise ValueError(
                    "Source build must produce exactly one application wheel"
                )
            run(
                [
                    "pip",
                    "install",
                    "--no-build",
                    "--no-deps",
                    "--no-index",
                    "--python",
                    interpreter,
                    str(built[0]),
                ]
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--venv", type=Path, required=True)
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--runtime-bundle", default="")
    parser.add_argument("--runtime-bundle-sha256", default="")
    parser.add_argument("--download-token-origin", default="")
    parser.add_argument("--download-origin", action="append", default=[])
    parser.add_argument("--offline-install", action="store_true")
    args = parser.parse_args()
    try:
        if os.environ.get("RUNNER_TEMP"):
            runner_path(args.venv, Path(os.environ["RUNNER_TEMP"]))
        install_runtime(
            args.project,
            args.venv,
            args.uv,
            bundle=args.runtime_bundle,
            bundle_sha256=args.runtime_bundle_sha256,
            token=os.environ.get("INSOMNIA_RUN_DOWNLOAD_TOKEN", ""),
            origin=args.download_token_origin,
            offline=args.offline_install,
            download_origins=tuple(args.download_origin),
        )
    except (
        OSError,
        ValueError,
        subprocess.SubprocessError,
        tarfile.TarError,
        zipfile.BadZipFile,
    ) as error:
        diagnostic = (
            str(error) if isinstance(error, ValueError) else type(error).__name__
        )
        parser.exit(
            1,
            f"Runtime installation failed: {diagnostic}. Check installer inputs and provisioned materials.\n",
        )


if __name__ == "__main__":
    main()
