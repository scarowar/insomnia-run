"""Validate reviewed download metadata and the bootstrapped Python interpreter.

Bootstrap itself uses uv and the local manifest without requiring host Python.
The metadata comes from uv 0.13.1, commit
62faed3351cfee2121b3c28b937b1f4b93233a93, in
crates/uv-python-managed/download-metadata.json. Asset digests were also checked
against the python-build-standalone 20261013 release.
"""

import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys
import sysconfig
from typing import Any


DOWNLOADS = {
    "cpython-3.14.8-linux-x86_64-gnu": "x86_64-unknown-linux-gnu",
    "cpython-3.14.8-darwin-x86_64-none": "x86_64-apple-darwin",
    "cpython-3.14.8-darwin-aarch64-none": "aarch64-apple-darwin",
}
TARGETS = {key.replace("-darwin-", "-macos-") for key in DOWNLOADS}
MANIFEST = Path(__file__).resolve().parents[1] / "python-downloads.json"


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate download metadata key")
        result[key] = value
    return result


def load_manifest(path: Path) -> dict[str, dict[str, Any]]:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("Python manifest must be a regular file")
        content = stream.read(65537)
    if len(content) > 65536:
        raise ValueError("Python manifest exceeds 64 KiB")
    entries = json.loads(content.decode("utf-8"), object_pairs_hook=_unique_object)
    if not isinstance(entries, dict) or entries.keys() != DOWNLOADS.keys():
        raise ValueError("Python manifest must contain exactly the reviewed targets")
    for key, triple in DOWNLOADS.items():
        _, _, system, arch, libc = key.split("-")
        expected = {
            "name": "cpython",
            "arch": {"family": arch, "variant": None},
            "os": system,
            "libc": libc,
            "major": 3,
            "minor": 14,
            "patch": 8,
            "prerelease": "",
            "variant": None,
            "build": "20261013",
            "url": (
                "https://github.com/astral-sh/python-build-standalone/releases/download/"
                f"20261013/cpython-3.14.8%2B20261013-{triple}-install_only_stripped.tar.gz"
            ),
        }
        entry = entries[key]
        if not isinstance(entry, dict) or entry.keys() != expected.keys() | {"sha256"}:
            raise ValueError("Python download is not a reviewed entry")
        digest = entry["sha256"]
        if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("Every reviewed Python build requires a SHA-256 digest")
        if any(type(entry[name]) is not int for name in ("major", "minor", "patch")):
            raise ValueError("Invalid reviewed Python version")
        if any(entry[name] != value for name, value in expected.items()):
            raise ValueError("Python download does not match the reviewed build")
    return entries


def verify_interpreter(install_dir: Path, target: str) -> Path:
    if target not in TARGETS:
        raise ValueError("Python target is not reviewed")
    root = install_dir.resolve(strict=True)
    target_root = root / target
    expected = (target_root / "bin/python3.14").resolve(strict=True)
    actual = Path(sys.executable).resolve(strict=True)
    if not expected.is_relative_to(target_root) or actual != expected:
        raise ValueError(
            "Python executable is outside the selected managed installation"
        )
    if (
        sys.implementation.name != "cpython"
        or tuple(sys.version_info) != (3, 14, 8, "final", 0)
        or sysconfig.get_config_var("Py_GIL_DISABLED")
    ):
        raise ValueError("Managed Python must be standard CPython 3.14.8")
    return actual


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=TARGETS, required=True)
    parser.add_argument("--install-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        load_manifest(MANIFEST)
        print(verify_interpreter(args.install_dir, args.target))
    except (OSError, ValueError):
        parser.exit(1, "Managed Python verification failed.\n")


if __name__ == "__main__":
    main()
