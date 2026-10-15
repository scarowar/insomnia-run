"""Resolve and verify official release digests before extracting Inso archives."""

import argparse
import hashlib
import json
from pathlib import Path
import re


def expected_checksum(asset: str, manifest: Path, metadata: Path | None) -> str:
    checksum = json.loads(manifest.read_text(encoding="utf-8")).get(asset, "")
    if not checksum and metadata:
        release = json.loads(metadata.read_text(encoding="utf-8"))
        for item in release.get("assets", []):
            if item.get("name") == asset:
                digest = item.get("digest") or ""
                if digest.startswith("sha256:"):
                    checksum = digest.removeprefix("sha256:")
                break
        if not checksum:
            raise ValueError(
                "The official release has no SHA-256 digest for this asset"
            )
    if checksum and not re.fullmatch(r"[a-f0-9]{64}", checksum):
        raise ValueError("Invalid SHA-256 digest in release metadata")
    return checksum


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
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "inso-checksums.json",
    )
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    try:
        checksum = expected_checksum(args.asset, args.manifest, args.metadata)
        if args.archive:
            verify_archive(args.archive, checksum)
        else:
            print(checksum)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Inso integrity check failed: {error}\n")


if __name__ == "__main__":
    main()
