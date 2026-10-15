"""Resolve and verify official release digests before extracting Inso archives."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re


def release_checksum(asset: str, metadata: Path) -> str:
    release = json.loads(metadata.read_text(encoding="utf-8"))
    for item in release.get("assets", []):
        if item.get("name") == asset:
            digest = item.get("digest") or ""
            if digest.startswith("sha256:"):
                return digest.removeprefix("sha256:")
            break
    raise ValueError("The official release has no SHA-256 digest for this asset")


def expected_checksum(asset: str, manifest: Path, metadata: Path | None) -> str:
    checksum = json.loads(manifest.read_text(encoding="utf-8")).get(asset, "")
    if not checksum and metadata:
        checksum = release_checksum(asset, metadata)
    if checksum and not re.fullmatch(r"[a-f0-9]{64}", checksum):
        raise ValueError("Invalid SHA-256 digest in release metadata")
    return checksum


def release_paths(asset: str, runner_temp: Path) -> tuple[Path, Path]:
    match = re.fullmatch(
        r"inso-(?:linux-x64|macos)-([0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?)"
        r"\.(?:tar\.xz|zip)",
        asset,
    )
    if not match:
        raise ValueError("Invalid Inso release asset name")
    root = runner_temp.resolve(strict=True)
    metadata = (root / "insomnia-run-release.json").resolve()
    archive = (root / "insomnia-run-download" / match[1] / asset).resolve()
    if not metadata.is_relative_to(root) or not archive.is_relative_to(root):
        raise ValueError("Release files must stay inside RUNNER_TEMP")
    return metadata, archive


def verify_archive(archive: Path, checksum: str) -> None:
    if not checksum:
        raise ValueError("A trusted SHA-256 digest is required")
    digest = hashlib.sha256()
    with archive.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != checksum:
        raise ValueError("Inso archive failed SHA-256 verification")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asset")
    parser.add_argument("--metadata", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    try:
        metadata, archive = release_paths(args.asset, Path(os.environ["RUNNER_TEMP"]))
        manifest = Path(__file__).resolve().parents[1] / "inso-checksums.json"
        checksum = expected_checksum(
            args.asset, manifest, metadata if args.metadata else None
        )
        if args.verify:
            verify_archive(archive, checksum)
        else:
            print(checksum)
    except (KeyError, OSError, ValueError) as error:
        parser.exit(1, f"Inso integrity check failed: {error}\n")


if __name__ == "__main__":
    main()
