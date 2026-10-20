import hashlib
import io
import os
from pathlib import Path
import shutil
import sys
import tarfile
from urllib.error import HTTPError

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import install_runtime
import verify_inso_release
import runtime_bundle


@pytest.mark.parametrize("mode", [0o770, 0o777])
@pytest.mark.parametrize("operation", ["download", "install"])
@pytest.mark.parametrize("existing_destination", [False, True])
def test_managed_directory_rejects_other_writers(
    tmp_path, monkeypatch, mode, operation, existing_destination
):
    shared = tmp_path / "shared"
    shared.mkdir()
    shared.chmod(mode)
    if existing_destination:
        monkeypatch.setenv("RUNNER_TEMP", str(shared))
    destination = shared if existing_destination else shared / "managed"
    archive = tmp_path / "source.tar"
    with tarfile.open(archive, "w") as output:
        member = tarfile.TarInfo("inso")
        member.size = 7
        output.addfile(member, io.BytesIO(b"trusted"))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="directory"):
        if operation == "download":
            install_runtime.download_archive(
                str(archive), destination / "archive", expected_sha256=digest
            )
        else:
            verify_inso_release.install_inso(archive, digest, destination)

    assert not (destination / "archive").exists()
    assert not (destination / "inso").exists()
    if not existing_destination:
        assert not destination.exists()


def test_download_rejects_foreign_owned_parent_before_network(tmp_path, monkeypatch):
    shared = tmp_path / "foreign"
    shared.mkdir(mode=0o755)
    identity = shared.stat()
    original = os.fstat

    def foreign_owner(descriptor):
        value = original(descriptor)
        if (value.st_dev, value.st_ino) == (identity.st_dev, identity.st_ino):
            fields = list(value)
            fields[4] = os.getuid() + 10001
            return os.stat_result(fields)
        return value

    monkeypatch.setattr(os, "fstat", foreign_owner)
    monkeypatch.setattr(
        install_runtime,
        "build_opener",
        lambda *args: pytest.fail("Unsafe parent reached network setup"),
    )
    with pytest.raises(ValueError, match="directory"):
        install_runtime.download_archive(
            "https://mirror.example/archive", shared / "archive"
        )
    assert list(shared.iterdir()) == []


def test_owner_directory_under_system_temp_accepts_verified_download(tmp_path):
    parent = tmp_path / "owned"
    parent.mkdir(mode=0o755)
    source = tmp_path / "source"
    source.write_bytes(b"trusted")

    install_runtime.download_archive(
        str(source),
        parent / "archive",
        expected_sha256=hashlib.sha256(b"trusted").hexdigest(),
    )

    assert (parent / "archive").read_bytes() == b"trusted"


def test_arbitrary_sticky_runner_temp_is_not_a_system_anchor(tmp_path, monkeypatch):
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    runner_temp.chmod(0o1777)
    monkeypatch.setenv("RUNNER_TEMP", str(runner_temp))
    source = tmp_path / "source"
    source.write_bytes(b"trusted")

    with pytest.raises(ValueError, match="directory"):
        install_runtime.download_archive(str(source), runner_temp / "archive")

    assert list(runner_temp.iterdir()) == []


def test_darwin_system_tmp_alias_accepts_owned_download(tmp_path, monkeypatch):
    user_temp = tmp_path / "user-temp"
    user_temp.mkdir()
    monkeypatch.delenv("RUNNER_TEMP", raising=False)
    monkeypatch.setattr(runtime_bundle.sys, "platform", "darwin")
    monkeypatch.setattr(runtime_bundle.tempfile, "gettempdir", lambda: str(user_temp))
    source = tmp_path / "source"
    source.write_bytes(b"trusted")

    with runtime_bundle.tempfile.TemporaryDirectory(dir="/tmp") as directory:
        destination = Path(directory) / "archive"
        install_runtime.download_archive(str(source), destination)
        assert destination.read_bytes() == b"trusted"


def test_foreign_nonsticky_system_anchor_is_rejected(tmp_path, monkeypatch):
    anchor = tmp_path / "system-temp"
    anchor.mkdir()
    identity = anchor.stat()
    original = os.fstat

    def foreign_owner(descriptor):
        value = original(descriptor)
        if (value.st_dev, value.st_ino) == (identity.st_dev, identity.st_ino):
            fields = list(value)
            fields[4] = os.getuid() + 10001
            return os.stat_result(fields)
        return value

    monkeypatch.delenv("RUNNER_TEMP", raising=False)
    monkeypatch.setattr(runtime_bundle.tempfile, "gettempdir", lambda: str(anchor))
    monkeypatch.setattr(os, "fstat", foreign_owner)
    source = tmp_path / "source"
    source.write_bytes(b"trusted")

    with pytest.raises(ValueError, match="directory"):
        install_runtime.download_archive(str(source), anchor / "archive")

    assert list(anchor.iterdir()) == []


def test_redirect_requires_explicit_destination_before_connection(
    tmp_path, monkeypatch
):
    requests = []

    class Opener:
        def open(self, request, timeout):
            requests.append(request.full_url)
            if len(requests) == 1:
                raise HTTPError(
                    request.full_url,
                    302,
                    "Found",
                    {"Location": "https://internal.example/archive"},
                    io.BytesIO(),
                )
            return io.BytesIO(b"archive")

    monkeypatch.setattr(install_runtime, "build_opener", lambda handler: Opener())
    with pytest.raises(ValueError, match="origin"):
        install_runtime.download_archive(
            "https://mirror.example/archive", tmp_path / "out"
        )
    assert requests == ["https://mirror.example/archive"]
    assert not (tmp_path / "out").exists()


def test_failed_cache_replacement_preserves_original(tmp_path, monkeypatch):
    cached = tmp_path / "archive"
    cached.write_bytes(b"original corrupt cache")
    source = tmp_path / "replacement"
    source.write_bytes(b"invalid replacement")
    monkeypatch.setattr(verify_inso_release, "expected_digest", lambda *args: "a" * 64)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_inso_release.py",
            "--asset",
            "inso-linux-x64-13.3.1.tar.xz",
            "--archive-path",
            str(cached),
            "--inso-archive",
            str(source),
            "--inso-sha256",
            "a" * 64,
        ],
    )
    with pytest.raises(SystemExit):
        verify_inso_release.main()
    assert cached.read_bytes() == b"original corrupt cache"


def test_cache_parent_swap_cannot_delete_outside_file(tmp_path, monkeypatch):
    runner = tmp_path / "runner"
    parent = runner / "cache"
    parent.mkdir(parents=True)
    cached = parent / "archive"
    cached.write_bytes(b"corrupt cache")
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "archive"
    sentinel.write_bytes(b"outside sentinel")
    original_hash = verify_inso_release.sha256_file

    def hash_then_swap(*args, **kwargs):
        digest = original_hash(*args, **kwargs)
        parent.rename(runner / "previous")
        parent.symlink_to(outside, target_is_directory=True)
        return digest

    def stop(*args, **kwargs):
        raise ValueError("stop before network")

    monkeypatch.setenv("RUNNER_TEMP", str(runner))
    monkeypatch.setattr(verify_inso_release, "sha256_file", hash_then_swap)
    monkeypatch.setattr(verify_inso_release, "expected_digest", lambda *args: "a" * 64)
    monkeypatch.setattr(verify_inso_release, "download_archive", stop)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_inso_release.py",
            "--asset",
            "inso-linux-x64-13.3.1.tar.xz",
            "--archive-path",
            str(cached),
        ],
    )
    with pytest.raises(SystemExit):
        verify_inso_release.main()
    assert sentinel.read_bytes() == b"outside sentinel"


def test_download_parent_swap_never_publishes_outside(tmp_path, monkeypatch):
    parent = tmp_path / "downloads"
    parent.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    original_copy = install_runtime._copy_download
    source = tmp_path / "source"
    source.write_bytes(b"archive")

    def copy_then_swap(*args, **kwargs):
        original_copy(*args, **kwargs)
        shutil.copytree(parent, outside, dirs_exist_ok=True)
        parent.rename(tmp_path / "original")
        parent.symlink_to(outside, target_is_directory=True)

    monkeypatch.setattr(install_runtime, "_copy_download", copy_then_swap)
    with pytest.raises((ValueError, OSError)):
        install_runtime.download_archive(str(source), parent / "archive")
    assert not (outside / "archive").exists()


@pytest.mark.parametrize("script", ["install_runtime.py", "verify_inso_release.py"])
def test_installer_rejects_redundant_authority_options(script, tmp_path):
    import subprocess

    option = "--python" if script == "install_runtime.py" else "--manifest"
    args = (
        ["--project", str(tmp_path), "--venv", str(tmp_path / "venv")]
        if script == "install_runtime.py"
        else [
            "--asset",
            "inso-linux-x64-13.3.1.tar.xz",
            "--archive-path",
            str(tmp_path / "archive"),
        ]
    )
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "scripts" / script),
            *args,
            option,
            str(tmp_path / "untrusted"),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


@pytest.mark.parametrize("kind", ["symlink", "fifo", "oversized"])
def test_checksum_manifest_requires_bounded_regular_file(tmp_path, kind):
    manifest = tmp_path / "manifest"
    if kind == "symlink":
        source = tmp_path / "source"
        source.write_text('{"asset": "' + "a" * 64 + '"}')
        manifest.symlink_to(source)
    elif kind == "fifo":
        os.mkfifo(manifest)
    else:
        manifest.write_bytes(b" " * (64 * 1024) + b"{}")
    with pytest.raises((ValueError, OSError)):
        verify_inso_release.expected_digest("asset", manifest, "a" * 64)


def test_install_parent_swap_cannot_replace_outside_binary(tmp_path, monkeypatch):
    archive = tmp_path / "source.tar"
    with tarfile.open(archive, "w") as output:
        member = tarfile.TarInfo("inso")
        member.size = 3
        output.addfile(member, io.BytesIO(b"new"))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    destination = tmp_path / "bin"
    destination.mkdir()
    (destination / "inso").write_bytes(b"previous")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "inso").write_bytes(b"outside sentinel")
    extract = verify_inso_release.extract_verified

    def extract_then_swap(*args, **kwargs):
        extract(*args, **kwargs)
        extracted = args[2]
        shutil.copytree(extracted.parent, outside / extracted.parent.name)
        destination.rename(tmp_path / "original")
        destination.symlink_to(outside, target_is_directory=True)

    monkeypatch.setattr(verify_inso_release, "extract_verified", extract_then_swap)
    with pytest.raises((ValueError, OSError)):
        verify_inso_release.install_inso(archive, digest, destination)
    assert (outside / "inso").read_bytes() == b"outside sentinel"
    assert (tmp_path / "original/inso").read_bytes() == b"previous"


@pytest.mark.parametrize(
    "origin",
    [
        "http://mirror.example",
        "https://*.example",
        "https://host/path",
        "https://host/",
        "https://host?query",
        "https://host#fragment",
        "https://user:pass@host",
        "https://host\n",
        "",
    ],
)
def test_redirect_origin_validation_precedes_network(tmp_path, monkeypatch, origin):
    monkeypatch.setattr(
        install_runtime,
        "build_opener",
        lambda *args: pytest.fail("invalid origin reached network setup"),
    )
    with pytest.raises(ValueError):
        install_runtime.download_archive(
            "https://mirror.example/archive",
            tmp_path / "out",
            redirect_origins=(origin,),
        )


@pytest.mark.parametrize(
    "initial,redirect,origins,allowed",
    [
        (
            "https://github.com/archive",
            "https://release-assets.githubusercontent.com/a",
            (),
            True,
        ),
        (
            "https://api.github.com/archive",
            "https://release-assets.githubusercontent.com/a",
            (),
            True,
        ),
        (
            "https://github.com:444/archive",
            "https://release-assets.githubusercontent.com/a",
            (),
            False,
        ),
        (
            "https://mirror.example/archive",
            "https://release-assets.githubusercontent.com/a",
            (),
            False,
        ),
        (
            "https://mirror.example/archive",
            "https://cdn.internal.example:444/a",
            ("https://cdn.internal.example:444",),
            True,
        ),
        ("https://mirror.example/archive", "/another", (), True),
        ("https://mirror.example/archive", "https://mirror.example:444/a", (), False),
    ],
)
def test_redirect_policy_and_auth_are_independent(
    tmp_path,
    monkeypatch,
    initial,
    redirect,
    origins,
    allowed,
):
    from urllib.parse import urljoin, urlsplit

    requests = []
    credential = "test-download-credential"
    token_origin = "https://" + urlsplit(initial).netloc

    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            if len(requests) == 1:
                raise HTTPError(
                    request.full_url, 302, "Found", {"Location": redirect}, io.BytesIO()
                )
            return io.BytesIO(b"archive")

    monkeypatch.setattr(install_runtime, "build_opener", lambda handler: Opener())
    kwargs = dict(token=credential, origin=token_origin, redirect_origins=origins)
    if allowed:
        install_runtime.download_archive(initial, tmp_path / "out", **kwargs)
        assert (tmp_path / "out").read_bytes() == b"archive"
        assert len(requests) == 2
        same = urlsplit(urljoin(initial, redirect)).netloc == urlsplit(initial).netloc
        assert requests[1].get_header("Authorization") == (
            "Bearer " + credential if same else None
        )
    else:
        with pytest.raises(ValueError, match="origin"):
            install_runtime.download_archive(initial, tmp_path / "out", **kwargs)
        assert len(requests) == 1
        assert not (tmp_path / "out").exists()


def test_redirect_chain_cannot_extend_allowed_origins(tmp_path, monkeypatch):
    requests = []

    class Opener:
        def open(self, request, timeout):
            requests.append(request.full_url)
            target = (
                "https://github.com/download"
                if len(requests) == 1
                else "https://release-assets.githubusercontent.com/archive"
            )
            raise HTTPError(
                request.full_url, 302, "Found", {"Location": target}, io.BytesIO()
            )

    monkeypatch.setattr(install_runtime, "build_opener", lambda handler: Opener())
    with pytest.raises(ValueError, match="origin"):
        install_runtime.download_archive(
            "https://mirror.example/archive",
            tmp_path / "out",
            redirect_origins=("https://github.com",),
        )
    assert requests == ["https://mirror.example/archive", "https://github.com/download"]


def test_offline_rejects_before_network_setup_with_allowed_origins(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        install_runtime,
        "build_opener",
        lambda *args: pytest.fail("offline network"),
    )
    with pytest.raises(ValueError, match="offline"):
        install_runtime.download_archive(
            "https://mirror.example/archive",
            tmp_path / "out",
            redirect_origins=("https://cdn.example",),
            offline=True,
        )
