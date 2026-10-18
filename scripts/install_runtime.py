"""Install the frozen source runtime or an explicitly verified wheel bundle."""

import argparse
from contextlib import closing
import os
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import tarfile
from typing import BinaryIO
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile

from runtime_bundle import (
    MAX_ARCHIVE_BYTES,
    extract_verified,
    regular_file,
    require_digest,
    runner_path,
    verify_bundle,
)


def _https_url(value: str):
    if (
        not value
        or any(ord(char) <= 32 or ord(char) == 127 for char in value)
        or "\\" in value
    ):
        raise ValueError("Downloads require an unambiguous HTTPS URL")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError("Downloads require an unambiguous HTTPS URL")
    try:
        port = parsed.port if parsed.port is not None else 443
        if port == 0:
            raise ValueError("Invalid HTTPS download port")
    except ValueError as error:
        raise ValueError("Invalid HTTPS download port") from error
    return parsed, (parsed.hostname.lower(), port)


def token_origin(value: str) -> tuple[str, int]:
    parsed, origin = _https_url(value)
    if parsed.path not in ("", "/") or parsed.query:
        raise ValueError("Download token origin must not include a path or query")
    return origin


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _copy_download(source: BinaryIO, output: BinaryIO, max_bytes: int) -> None:
    total = 0
    for block in iter(lambda: source.read(1024 * 1024), b""):
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
    return urljoin(current, location)


def _download_https(
    location: str,
    output: BinaryIO,
    token: str,
    allowed_origin: tuple[str, int] | None,
    max_bytes: int,
) -> None:
    opener = build_opener(_NoRedirect())
    current = location
    for attempt in range(6):
        _, current_origin = _https_url(current)
        headers = {
            "User-Agent": "insomnia-run-installer",
            "Accept": "application/octet-stream",
        }
        if token and current_origin == allowed_origin:
            headers["Authorization"] = "Bearer " + token
        try:
            response = opener.open(Request(current, headers=headers), timeout=60)
        except HTTPError as error:
            current = _redirect_location(error, current, attempt)
            continue
        except URLError:
            raise ValueError("Archive download failed; check network access") from None
        with closing(response):
            _copy_download(response, output, max_bytes)
        break


def download_archive(
    location: str,
    destination: Path,
    *,
    token: str = "",
    origin: str = "",
    offline: bool = False,
    max_bytes: int = MAX_ARCHIVE_BYTES,
) -> None:
    """Copy a local archive or fetch HTTPS with origin-scoped authentication."""
    if token and (
        not origin or any(ord(char) < 32 or ord(char) == 127 for char in token)
    ):
        raise ValueError(
            "A valid download-token-origin is required for a download token"
        )
    allowed_origin = token_origin(origin) if origin else None
    parsed = urlsplit(location)
    if parsed.scheme:
        _https_url(location)
        if offline:
            raise ValueError("Installer network access is disabled by offline-install")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Download destination already exists")
    with tempfile.TemporaryDirectory(
        prefix=".insomnia-download-", dir=destination.parent
    ) as scratch:
        staged = Path(scratch) / "archive"
        with staged.open("xb") as output:
            os.chmod(staged, 0o600)
            if not parsed.scheme:
                with regular_file(Path(location)) as source:
                    _copy_download(source, output, max_bytes)
            else:
                _download_https(location, output, token, allowed_origin, max_bytes)
        # Hard linking is an atomic no-clobber publication on the same filesystem.
        os.link(staged, destination)


def _child_environment(offline: bool) -> dict[str, str]:
    environment = dict(os.environ)
    for name in (
        "INSOMNIA_RUN_DOWNLOAD_TOKEN",
        "INPUT_DOWNLOAD_TOKEN",
        "INSO_DOWNLOAD_TOKEN",
    ):
        environment.pop(name, None)
    environment["UV_PYTHON_DOWNLOADS"] = "never"
    if offline:
        environment["UV_OFFLINE"] = "1"
    return environment


def install_runtime(
    project: Path,
    venv: Path,
    python: str,
    uv: str,
    *,
    bundle: str = "",
    bundle_sha256: str = "",
    token: str = "",
    origin: str = "",
    offline: bool = False,
) -> None:
    if bool(bundle) != bool(bundle_sha256):
        raise ValueError(
            "runtime-bundle and runtime-bundle-sha256 must be provided together"
        )
    if venv.exists() or venv.is_symlink():
        raise ValueError("Runtime virtual environment destination must not exist")
    environment = _child_environment(offline)
    prefix = [uv] + (["--offline"] if offline else [])

    def run(arguments, *, extra_environment=None):
        subprocess.run(
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
                bundle, archive, token=token, origin=origin, offline=offline
            )
            extracted = root / "verified"
            extract_verified(archive, bundle_sha256, extracted)
            identity = subprocess.run(
                [
                    python,
                    "-I",
                    "-S",
                    "-c",
                    "import json,sys,sysconfig; print(json.dumps([sys.implementation.cache_tag,sysconfig.get_platform()]))",
                ],
                env=environment,
                text=True,
                capture_output=True,
                check=True,
            )
            python_tag, platform_tag = json.loads(identity.stdout)
            verified = verify_bundle(extracted, project, python_tag, platform_tag)
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
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--runtime-bundle", default="")
    parser.add_argument("--runtime-bundle-sha256", default="")
    parser.add_argument("--download-token-origin", default="")
    parser.add_argument("--offline-install", action="store_true")
    args = parser.parse_args()
    try:
        if os.environ.get("RUNNER_TEMP"):
            runner_path(args.venv, Path(os.environ["RUNNER_TEMP"]))
        install_runtime(
            args.project,
            args.venv,
            args.python,
            args.uv,
            bundle=args.runtime_bundle,
            bundle_sha256=args.runtime_bundle_sha256,
            token=os.environ.get("INSOMNIA_RUN_DOWNLOAD_TOKEN", ""),
            origin=args.download_token_origin,
            offline=args.offline_install,
        )
    except (
        OSError,
        ValueError,
        subprocess.SubprocessError,
        tarfile.TarError,
        zipfile.BadZipFile,
    ) as error:
        parser.exit(
            1,
            f"Runtime installation failed: {type(error).__name__}. Check installer inputs and provisioned materials.\n",
        )


if __name__ == "__main__":
    main()
