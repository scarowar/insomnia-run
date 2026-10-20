import hashlib
import io
from pathlib import Path
import sys
import tarfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import install_runtime
import runtime_bundle
import verify_inso_release


@pytest.mark.parametrize("operation", ["download", "install"])
@pytest.mark.parametrize("mode", [0o700, 0o1777])
def test_custom_tmpdir_does_not_grant_public_directory_trust(
    tmp_path, monkeypatch, operation, mode
):
    custom = tmp_path / "custom-temp"
    custom.mkdir()
    custom.chmod(mode)
    monkeypatch.delenv("RUNNER_TEMP", raising=False)
    monkeypatch.setenv("TMPDIR", str(custom))
    monkeypatch.setattr(runtime_bundle.tempfile, "tempdir", None)
    archive = tmp_path / "source.tar"
    with tarfile.open(archive, "w") as output:
        member = tarfile.TarInfo("inso")
        member.size = 7
        output.addfile(member, io.BytesIO(b"trusted"))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    destination = custom / "managed"

    def install():
        if operation == "download":
            install_runtime.download_archive(
                str(archive), destination / "archive", expected_sha256=digest
            )
            return (destination / "archive").read_bytes()
        binary = verify_inso_release.install_inso(archive, digest, destination)
        return binary.read_bytes()

    if mode == 0o1777:
        with pytest.raises(ValueError, match="directory"):
            install()
        assert not destination.exists()
    else:
        assert install() == (
            archive.read_bytes() if operation == "download" else b"trusted"
        )


@pytest.mark.parametrize("anchor", ["/tmp", "/var/tmp"])
def test_standard_temp_anchor_accepts_private_download(anchor):
    with runtime_bundle.tempfile.TemporaryDirectory(dir=anchor) as directory:
        parent = Path(directory)
        source = parent / "source"
        source.write_bytes(b"trusted")
        install_runtime.download_archive(
            str(source),
            parent / "archive",
            expected_sha256=hashlib.sha256(b"trusted").hexdigest(),
        )
        assert (parent / "archive").read_bytes() == b"trusted"
