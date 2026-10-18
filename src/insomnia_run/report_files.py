"""Restricted report destinations and private, atomically written files."""

import os
import secrets
import tempfile
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

_CONTROL_FILES = (
    "GITHUB_OUTPUT",
    "GITHUB_ENV",
    "GITHUB_PATH",
    "GITHUB_STEP_SUMMARY",
    "GITHUB_STATE",
    "GITHUB_EVENT_PATH",
)


def _same_destination(first: Path, second: Path) -> bool:
    if first.resolve() == second.resolve():
        return True
    return first.exists() and second.exists() and first.samefile(second)


def validate_destination(
    path: str | Path,
    *,
    environ: Mapping[str, str] | None = None,
    other_paths: Iterable[str | Path] = (),
) -> Path:
    environment = os.environ if environ is None else environ
    if not str(path) or any(ord(char) < 32 or ord(char) == 127 for char in str(path)):
        raise ValueError(
            "Report destination must be a nonempty path without control characters."
        )
    destination = Path(os.path.abspath(path))
    try:
        resolved = destination.resolve()
        if destination.is_dir():
            raise ValueError("Report destination must name a file, not a directory.")
        if any(_same_destination(destination, Path(other)) for other in other_paths):
            raise ValueError("Report destinations must not collide.")
        if environment.get("GITHUB_ACTIONS", "").lower() == "true":
            roots = [
                Path(environment[name]).resolve()
                for name in ("GITHUB_WORKSPACE", "RUNNER_TEMP")
                if environment.get(name)
            ]
            if not any(resolved != root and root in resolved.parents for root in roots):
                raise ValueError(
                    "Report destination must be below the workspace or runner temp directory."
                )
            if any(
                _same_destination(destination, Path(environment[name]))
                for name in _CONTROL_FILES
                if environment.get(name)
            ):
                raise ValueError(
                    "Report destination must not overwrite a GitHub control file."
                )
    except (OSError, RuntimeError) as error:
        raise ValueError("Report destination cannot be safely resolved.") from error
    return resolved


def _open_parent(destination: Path, restricted: bool) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY
    if not restricted:
        destination.parent.mkdir(parents=True, exist_ok=True)
        return os.open(destination.parent, flags)
    # Pin each component so a symlink swap cannot redirect a later file operation.
    flags |= os.O_NOFOLLOW
    descriptor = os.open(destination.anchor, flags)
    try:
        for part in destination.parent.parts[1:]:
            try:
                child = os.open(part, flags, dir_fd=descriptor)
            except FileNotFoundError:
                os.mkdir(part, mode=0o700, dir_fd=descriptor)
                child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def write_report_file(
    path: str | Path,
    text: str,
    *,
    environ: Mapping[str, str] | None = None,
    other_paths: Iterable[str | Path] = (),
) -> Path:
    environment = os.environ if environ is None else environ
    others = tuple(other_paths)
    destination = validate_destination(path, environ=environment, other_paths=others)
    parent = _open_parent(
        destination, environment.get("GITHUB_ACTIONS", "").lower() == "true"
    )
    temporary = ".insomnia-report-" + secrets.token_hex(12)
    try:
        descriptor = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=parent
        )
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        validate_destination(destination, environ=environment, other_paths=others)
        if not os.path.samestat(os.fstat(parent), destination.parent.stat()):
            raise ValueError("Report destination parent changed during writing.")
        os.replace(temporary, destination.name, src_dir_fd=parent, dst_dir_fd=parent)
    finally:
        try:
            os.unlink(temporary, dir_fd=parent)
        except FileNotFoundError:
            pass
        finally:
            os.close(parent)
    return destination


@contextmanager
def private_capture_directory(*, parent: Path | None = None) -> Iterator[Path]:
    with tempfile.TemporaryDirectory(
        prefix="insomnia-private-", dir=parent
    ) as directory:
        path = Path(directory)
        path.chmod(0o700)
        yield path
