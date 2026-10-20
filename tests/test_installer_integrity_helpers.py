"""Installer trust boundaries, without GitHub or package index access."""

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from runtime_bundle import extract_verified, sha256_file, verify_bundle  # noqa: E402
from runtime_bundle import source_digest  # noqa: E402
from install_runtime import download_archive, install_runtime, token_origin  # noqa: E402
from verify_inso_release import expected_digest, install_inso, cache_identity  # noqa: E402
import install_runtime as runtime_installer  # noqa: E402
import verify_inso_release as inso_installer  # noqa: E402
from runtime_bundle import regular_file, require_digest, _write_member  # noqa: E402


@pytest.fixture(autouse=True)
def standalone_installer_environment(monkeypatch):
    monkeypatch.delenv("RUNNER_TEMP", raising=False)


def tar_archive(path, entries):
    with tarfile.open(path, "w:gz") as archive:
        for name, content in entries.items():
            member = tarfile.TarInfo(name)
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    return sha256_file(path)


def test_unbundled_inso_requires_explicit_trusted_digest(tmp_path):
    manifest = tmp_path / "checksums.json"
    manifest.write_text("{}")
    with pytest.raises(ValueError, match="inso-sha256"):
        expected_digest("inso-linux-x64-99.0.0.tar.xz", manifest)


def test_explicit_digest_cannot_override_bundled_release(tmp_path):
    manifest = tmp_path / "checksums.json"
    manifest.write_text(json.dumps({"asset": "a" * 64}))
    with pytest.raises(ValueError, match="conflicts"):
        expected_digest("asset", manifest, "b" * 64)
    assert expected_digest("asset", manifest, "a" * 64) == "a" * 64


def test_explicit_archive_is_checked_even_with_preinstalled_binary(tmp_path):
    archive = tmp_path / "inso.tar.gz"
    tar_archive(archive, {"inso": b"not executable"})
    installed = tmp_path / "existing-inso"
    installed.write_text("preinstalled")
    with pytest.raises(ValueError, match="SHA-256"):
        install_inso(archive, "a" * 64, tmp_path / "bin")
    assert installed.read_text() == "preinstalled"


@pytest.mark.parametrize(
    "name", ["../escape", "/escape", "a/../../b", "C:/file", "a\\b"]
)
def test_archive_path_traversal_never_creates_destination(tmp_path, name):
    archive = tmp_path / "archive.tar.gz"
    digest = tar_archive(archive, {name: b"bad"})
    with pytest.raises(ValueError):
        extract_verified(archive, digest, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_archive_rejects_symlinks_before_writing(tmp_path):
    archive = tmp_path / "archive.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        member = tarfile.TarInfo("escape")
        member.type = tarfile.SYMTYPE
        member.linkname = "../outside"
        stream.addfile(member)
    digest = sha256_file(archive)
    with pytest.raises(ValueError, match="regular files"):
        extract_verified(archive, digest, tmp_path / "output")


def test_verified_zip_has_private_files_and_rejects_existing_destination(tmp_path):
    archive = tmp_path / "archive.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("folder/data", "verified")
    destination = tmp_path / "output"
    digest = sha256_file(archive)
    extract_verified(archive, digest, destination)
    assert (destination / "folder/data").read_text() == "verified"
    assert destination.stat().st_mode & 0o777 == 0o700
    assert (destination / "folder/data").stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError, match="exist"):
        extract_verified(archive, digest, destination)


def test_archive_budget_and_duplicate_names_are_rejected(tmp_path):
    archive = tmp_path / "archive.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("a", b"12345")
    digest = sha256_file(archive)
    with pytest.raises(ValueError, match="size"):
        extract_verified(archive, digest, tmp_path / "output", max_bytes=4)
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("A", "one")
        stream.writestr("a", "two")
    digest = sha256_file(archive)
    with pytest.raises(ValueError, match="Duplicate"):
        extract_verified(archive, digest, tmp_path / "output")


@pytest.mark.parametrize(
    "origin",
    [
        "http://mirror.example",
        "https://u:p@mirror.example",
        "https://mirror.example/path",
        "https://mirror.example?x=1",
        "https://mirror.example/#frag",
    ],
)
def test_download_token_origin_rejects_ambiguous_or_insecure_values(origin):
    with pytest.raises(ValueError):
        token_origin(origin)


def test_offline_download_denies_network_before_opening(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("offline download attempted network access")

    monkeypatch.setattr("urllib.request.OpenerDirector.open", forbidden)
    with pytest.raises(ValueError, match="offline"):
        download_archive(
            "https://mirror.example/archive", tmp_path / "download", offline=True
        )


def test_local_download_works_offline_and_does_not_overwrite(tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"archive")
    destination = tmp_path / "copy"
    download_archive(str(source), destination, offline=True)
    assert destination.read_bytes() == b"archive"
    with pytest.raises(FileExistsError):
        download_archive(str(source), destination, offline=True)


def test_cache_identity_changes_with_digest_and_archive_identity():
    first = cache_identity("13.3.1", "linux-x64", "a" * 64, "https://mirror.example/a")
    assert first != cache_identity(
        "13.3.1", "linux-x64", "b" * 64, "https://mirror.example/a"
    )
    assert first != cache_identity(
        "13.3.1", "linux-x64", "a" * 64, "https://mirror.example/b"
    )
    assert "https:" not in first


def test_invalid_bundle_fails_before_uv_is_invoked(tmp_path, monkeypatch):
    archive = tmp_path / "bundle.tar.gz"
    digest = tar_archive(archive, {"manifest.json": b"{}"})
    real_run = subprocess.run

    def guarded(command, **kwargs):
        if command[0] == "uv":
            pytest.fail("unverified bundle invoked uv")
        return real_run(command, **kwargs)

    monkeypatch.setattr(subprocess, "run", guarded)
    with pytest.raises(ValueError):
        install_runtime(
            ROOT,
            tmp_path / "venv",
            "uv",
            bundle=str(archive),
            bundle_sha256=digest,
            offline=True,
        )


def test_missing_bundle_digest_is_rejected_without_venv(tmp_path):
    with pytest.raises(ValueError, match="runtime-bundle-sha256"):
        install_runtime(
            ROOT,
            tmp_path / "venv",
            "uv",
            bundle="https://mirror.example/bundle",
        )
    assert not (tmp_path / "venv").exists()


@pytest.fixture
def bundle_tree(tmp_path):
    project = tmp_path / "project"
    (project / "src/package").mkdir(parents=True)
    (project / "src/package/__init__.py").write_text("VALUE = 1\n")
    (project / "pyproject.toml").write_text(
        '[project]\nname="insomnia-run"\nversion="0.2.0"\n'
    )
    (project / "uv.lock").write_text("version = 1\n")
    root = tmp_path / "bundle"
    (root / "wheels").mkdir(parents=True)
    wheel = root / "wheels/insomnia_run-0.2.0-py3-none-any.whl"
    wheel.write_bytes(b"application-wheel")
    digest = sha256_file(wheel)
    (root / "requirements.txt").write_text(
        f"insomnia-run==0.2.0 --hash=sha256:{digest}\n"
    )
    manifest = {
        "schema_version": 1,
        "source_sha256": source_digest(project),
        "lock_sha256": sha256_file(project / "uv.lock"),
        "python_tag": "cpython-312",
        "platform": "linux-x86_64",
        "application": wheel.relative_to(root).as_posix(),
        "files": {
            "requirements.txt": sha256_file(root / "requirements.txt"),
            wheel.relative_to(root).as_posix(): digest,
        },
    }
    (root / "manifest.json").write_text(json.dumps(manifest))
    return root, project, manifest


def test_verified_bundle_projects_only_manifested_hashed_wheels(bundle_tree):
    root, project, _ = bundle_tree
    verified = verify_bundle(root, project, "cpython-312", "linux-x86_64")
    assert verified.application.name == "insomnia_run-0.2.0-py3-none-any.whl"
    assert verified.requirements.read_text().startswith(
        "insomnia-run==0.2.0 --hash=sha256:"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_sha256", "a" * 64),
        ("lock_sha256", "a" * 64),
        ("python_tag", "cpython-313"),
        ("platform", "macosx-14.0-arm64"),
        ("schema_version", True),
    ],
)
def test_bundle_rejects_wrong_identity(bundle_tree, field, value):
    root, project, manifest = bundle_tree
    manifest[field] = value
    (root / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        verify_bundle(root, project, "cpython-312", "linux-x86_64")


def test_bundle_rejects_unlisted_payload_and_changed_wheel(bundle_tree):
    root, project, _ = bundle_tree
    extra = root / "unlisted"
    extra.write_text("unapproved")
    with pytest.raises(ValueError, match="unlisted"):
        verify_bundle(root, project, "cpython-312", "linux-x86_64")
    extra.unlink()
    (root / "wheels/insomnia_run-0.2.0-py3-none-any.whl").write_bytes(b"modified")
    with pytest.raises(ValueError, match="SHA-256"):
        verify_bundle(root, project, "cpython-312", "linux-x86_64")


@pytest.mark.parametrize(
    "requirement",
    [
        "--index-url https://evil.example",
        "insomnia-run @ https://evil.example/a.whl",
        "insomnia-run==0.2.0",
        "-r elsewhere.txt",
        "insomnia-run==0.2.0 --hash=sha256:" + "a" * 64,
    ],
)
def test_bundle_rejects_unhashed_or_network_requirements(bundle_tree, requirement):
    root, project, manifest = bundle_tree
    (root / "requirements.txt").write_text(requirement + "\n")
    manifest["files"]["requirements.txt"] = sha256_file(root / "requirements.txt")
    (root / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="requirements"):
        verify_bundle(root, project, "cpython-312", "linux-x86_64")


def test_https_redirect_never_forwards_token_to_other_origin(tmp_path, monkeypatch):
    from urllib.error import HTTPError
    from email.message import Message

    requests = []
    token = "test-" + "download-credential"

    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            if len(requests) == 1:
                headers = Message()
                headers["Location"] = "https://cdn.example/archive"
                raise HTTPError(
                    request.full_url, 302, "redirect", headers, io.BytesIO()
                )
            return io.BytesIO(b"verified-archive")

    monkeypatch.setattr("install_runtime.build_opener", lambda handler: Opener())
    download_archive(
        "https://mirror.example/archive",
        tmp_path / "archive",
        token=token,
        origin="https://mirror.example",
        redirect_origins=("https://cdn.example",),
    )
    assert requests[0].get_header("Authorization") == "Bearer " + token
    assert requests[1].get_header("Authorization") is None
    assert (tmp_path / "archive").read_bytes() == b"verified-archive"


def test_https_redirect_rejects_downgrade_before_second_request(tmp_path, monkeypatch):
    from urllib.error import HTTPError
    from email.message import Message

    requests = []

    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            headers = Message()
            headers["Location"] = "http://mirror.example/insecure"
            raise HTTPError(request.full_url, 302, "redirect", headers, io.BytesIO())

    monkeypatch.setattr("install_runtime.build_opener", lambda handler: Opener())
    with pytest.raises(ValueError, match="HTTPS"):
        download_archive("https://mirror.example/archive", tmp_path / "archive")
    assert len(requests) == 1
    assert not (tmp_path / "archive").exists()


def test_source_install_defaults_to_frozen_sync_and_offline_denies_uv_network(
    tmp_path, monkeypatch
):
    commands = []
    token = "test-" + "download-credential"
    monkeypatch.setenv("INSOMNIA_RUN_DOWNLOAD_TOKEN", token)

    def run(command, **kwargs):
        commands.append((command, kwargs))
        if "build" in command:
            wheels = Path(command[command.index("--out-dir") + 1])
            wheels.mkdir()
            (wheels / "insomnia_run.whl").write_bytes(b"built")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", run)
    install_runtime(ROOT, tmp_path / "venv", "uv", offline=True)
    assert len(commands) == 4
    for command, kwargs in commands:
        assert command[:2] == ["uv", "--offline"]
        assert kwargs["env"]["UV_OFFLINE"] == "1"
        assert kwargs["env"]["UV_PYTHON_DOWNLOADS"] == "never"
        assert token not in json.dumps(kwargs["env"])
    sync = next(command for command, _ in commands if "sync" in command)
    assert all(
        flag in sync
        for flag in ["--frozen", "--no-dev", "--no-build", "--no-install-project"]
    )


def test_checksum_cli_rejects_missing_unbundled_digest_without_metadata_request(
    tmp_path,
):
    environment = dict(__import__("os").environ, RUNNER_TEMP=str(tmp_path))
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/verify_inso_release.py"),
            "--asset",
            "inso-linux-x64-99.0.0.tar.xz",
            "--archive-path",
            str(tmp_path / "archive"),
        ],
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "inso-sha256" in result.stderr
    assert "metadata" not in result.stderr


def test_verified_inso_archive_installs_single_executable(tmp_path):
    archive = tmp_path / "inso.tar.gz"
    digest = tar_archive(archive, {"package/inso": b"#!/bin/sh\nprintf '13.3.1\\n'\n"})
    binary = install_inso(archive, digest, tmp_path / "bin")
    result = subprocess.run(
        [str(binary), "--version"], capture_output=True, text=True, check=True
    )
    assert result.stdout == "13.3.1\n"
    assert binary.stat().st_mode & 0o777 == 0o700


def test_inso_archive_with_ambiguous_binary_does_not_overwrite_install(tmp_path):
    archive = tmp_path / "inso.tar.gz"
    digest = tar_archive(archive, {"a/inso": b"one", "b/inso": b"two"})
    destination = tmp_path / "bin"
    destination.mkdir()
    (destination / "inso").write_bytes(b"existing")
    with pytest.raises(ValueError, match="exactly one"):
        install_inso(archive, digest, destination)
    assert (destination / "inso").read_bytes() == b"existing"


def test_bundle_install_never_falls_back_to_source_or_index(
    bundle_tree, tmp_path, monkeypatch
):
    import sysconfig

    root, project, manifest = bundle_tree
    manifest["python_tag"] = sys.implementation.cache_tag
    manifest["platform"] = sysconfig.get_platform()
    (root / "manifest.json").write_text(json.dumps(manifest))
    archive = tmp_path / "runtime.tar.gz"
    digest = tar_archive(
        archive,
        {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        },
    )
    commands = []
    real_run = subprocess.run

    def run(command, **kwargs):
        if command[0] != "uv":
            return real_run(command, **kwargs)
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", run)
    install_runtime(
        project,
        tmp_path / "venv",
        "uv",
        bundle=str(archive),
        bundle_sha256=digest,
        offline=True,
    )
    assert len(commands) == 2
    assert commands[0][2] == "venv"
    install = commands[1]
    assert all(
        flag in install
        for flag in [
            "--offline",
            "--no-index",
            "--no-build",
            "--require-hashes",
            "--find-links",
        ]
    )
    assert not any("sync" in command or "build" in command for command in commands)


@pytest.mark.parametrize("directory", [False, True])
def test_source_identity_rejects_symlink_sources(tmp_path, directory):
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    (project / "pyproject.toml").write_text("[project]")
    external = tmp_path / "external.py"
    if directory:
        external.mkdir()
        (external / "module.py").write_text("VALUE = 1")
    else:
        external.write_text("VALUE = 1")
    (project / "src/module.py").symlink_to(external)
    with pytest.raises(ValueError, match="symlink"):
        source_digest(project)


def test_local_fifo_is_rejected_without_waiting_for_writer(tmp_path):
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    code = "import sys; from pathlib import Path; sys.path.insert(0, 'scripts'); from runtime_bundle import sha256_file; sha256_file(Path(sys.argv[1]))"
    result = subprocess.run(
        [sys.executable, "-c", code, str(fifo)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=1,
    )
    assert result.returncode != 0
    assert "regular file" in result.stderr


@pytest.mark.parametrize(
    "url",
    [
        "https://mirror.example:0/a",
        "https://mirror.example:99999/a",
        "https://mirror.example/a\n",
        "https://mirror.example/a\\b",
        "https://mirror.example/a#fragment",
    ],
)
def test_https_download_rejects_invalid_urls_before_network(tmp_path, url, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid URL reached network")

    monkeypatch.setattr("install_runtime.build_opener", forbidden)
    with pytest.raises(ValueError):
        download_archive(url, tmp_path / "archive")


@pytest.mark.parametrize("value", ["", "a", "g" * 64, None, 123])
def test_digest_format_is_required(value):
    with pytest.raises(ValueError, match="SHA-256"):
        require_digest(value)


@pytest.mark.parametrize(
    "members", [{"a": b"file", "a/b": b"child"}, {"a/b": b"child", "a": b"file"}]
)
def test_archive_rejects_file_directory_collisions(tmp_path, members):
    archive = tmp_path / "archive.tar.gz"
    digest = tar_archive(archive, members)
    with pytest.raises(ValueError, match="conflicts"):
        extract_verified(archive, digest, tmp_path / "out")


def test_member_size_must_match_declared_bytes(tmp_path):
    short_stream = io.BytesIO(b"one")
    with pytest.raises(ValueError, match="shorter"):
        _write_member(short_stream, tmp_path / "short", 4)
    long_stream = io.BytesIO(b"longer")
    with pytest.raises(ValueError, match="exceeds"):
        _write_member(long_stream, tmp_path / "long", 3)


def test_archive_member_count_limit(tmp_path):
    archive = tmp_path / "archive.tar.gz"
    digest = tar_archive(archive, {"a": b"one", "b": b"two"})
    with pytest.raises(ValueError, match="member limit"):
        extract_verified(archive, digest, tmp_path / "out", max_members=1)


@pytest.mark.parametrize("archive_type", ["tar", "zip"])
@pytest.mark.parametrize("max_members", [0, 1, 2, 3])
def test_archive_member_budget_counts_ignored_root_entries(
    tmp_path, archive_type, max_members
):
    archive = tmp_path / "archive"
    if archive_type == "tar":
        with tarfile.open(archive, "w:gz") as output:
            for name in (".", "./"):
                member = tarfile.TarInfo(name)
                member.type = tarfile.DIRTYPE
                output.addfile(member)
            member = tarfile.TarInfo("inso")
            member.size = 1
            output.addfile(member, io.BytesIO(b"x"))
    else:
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("./", "")
            with pytest.warns(UserWarning, match="Duplicate name"):
                output.writestr("./", "")
            output.writestr("inso", "x")
    destination = tmp_path / "out"
    digest = sha256_file(archive)
    if max_members < 3:
        with pytest.raises(ValueError, match="member limit"):
            extract_verified(archive, digest, destination, max_members=max_members)
        assert not destination.exists()
        assert list(tmp_path.iterdir()) == [archive]
    else:
        extract_verified(archive, digest, destination, max_members=max_members)
        assert (destination / "inso").read_bytes() == b"x"


def test_download_size_limit_cleans_up_without_publishing(tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"too large")
    with pytest.raises(ValueError, match="size limit"):
        download_archive(str(source), tmp_path / "out", max_bytes=1)
    assert not (tmp_path / "out").exists()
    assert not list(tmp_path.glob(".insomnia-download-*"))


@pytest.mark.parametrize(
    "token,origin", [("value", ""), ("bad\nvalue", "https://mirror.example")]
)
def test_download_rejects_unscoped_or_invalid_tokens(tmp_path, token, origin):
    with pytest.raises(ValueError, match="download-token-origin"):
        download_archive(
            "https://mirror.example/a", tmp_path / "out", token=token, origin=origin
        )


def test_installer_refuses_symlink_destination(tmp_path):
    external = tmp_path / "external"
    external.mkdir()
    destination = tmp_path / "bin"
    destination.symlink_to(external)
    with pytest.raises(ValueError, match="symlink"):
        install_inso(tmp_path / "unused", "a" * 64, destination)


def test_inso_cli_cache_identity_and_successful_local_install(
    tmp_path, monkeypatch, capsys
):
    archive = tmp_path / "source.tar.gz"
    digest = tar_archive(archive, {"inso": b"executable"})
    args = [
        "verify_inso_release.py",
        "--asset",
        "inso-linux-x64-99.0.0.tar.xz",
        "--inso-sha256",
        digest,
        "--inso-archive",
        str(archive),
        "--archive-path",
        str(tmp_path / "cached"),
        "--install-dir",
        str(tmp_path / "bin"),
        "--offline-install",
    ]
    monkeypatch.setattr(sys, "argv", args + ["--cache-key"])
    inso_installer.main()
    assert capsys.readouterr().out.startswith("insomnia-run-inso-v2-")
    monkeypatch.setattr(sys, "argv", args)
    inso_installer.main()
    assert (tmp_path / "bin/inso").read_bytes() == b"executable"


def test_inso_cli_requires_explicit_custom_archive_digest(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_inso_release.py",
            "--asset",
            "inso-linux-x64-13.3.1.tar.xz",
            "--inso-archive",
            str(tmp_path / "source"),
            "--archive-path",
            str(tmp_path / "cached"),
        ],
    )
    with pytest.raises(SystemExit) as error:
        inso_installer.main()
    assert error.value.code == 1
    assert "custom inso-archive" in capsys.readouterr().err


def test_runtime_cli_reports_failure_without_private_path_or_token(
    tmp_path, monkeypatch, capsys
):
    private = "sensitive-" + "location"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "install_runtime.py",
            "--project",
            str(tmp_path),
            "--venv",
            str(tmp_path / private),
            "--runtime-bundle",
            private,
        ],
    )
    with pytest.raises(SystemExit) as error:
        runtime_installer.main()
    assert error.value.code == 1
    assert private not in capsys.readouterr().err


def test_fifo_is_not_a_regular_installer_input(tmp_path):
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    file_context = regular_file(fifo)
    with pytest.raises(ValueError, match="regular file"):
        with file_context:
            pytest.fail("FIFO was accepted")


@pytest.mark.parametrize("archive_type", ["zip", "tar"])
def test_archive_supports_regular_directories_and_root_marker(tmp_path, archive_type):
    archive = tmp_path / "archive"
    if archive_type == "zip":
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("./", "")
            output.writestr("folder/", "")
            output.writestr("folder/data", "content")
    else:
        with tarfile.open(archive, "w:gz") as output:
            for name in (".", "folder"):
                member = tarfile.TarInfo(name)
                member.type = tarfile.DIRTYPE
                output.addfile(member)
            member = tarfile.TarInfo("folder/data")
            member.size = 7
            output.addfile(member, io.BytesIO(b"content"))
    extract_verified(archive, sha256_file(archive), tmp_path / "out")
    assert (tmp_path / "out/folder/data").read_text() == "content"


def test_zip_symlink_is_rejected(tmp_path):
    archive = tmp_path / "archive.zip"
    with zipfile.ZipFile(archive, "w") as output:
        member = zipfile.ZipInfo("link")
        member.create_system = 3
        member.external_attr = 0o120777 << 16
        output.writestr(member, "outside")
    digest = sha256_file(archive)
    with pytest.raises(ValueError, match="regular files"):
        extract_verified(archive, digest, tmp_path / "out")


@pytest.mark.parametrize(
    "mutation,diagnostic",
    [
        ("duplicate-key", "Duplicate runtime manifest"),
        ("large-manifest", "manifest is too large"),
        ("empty-files", "file manifest"),
        ("symlink", "symlink"),
        ("unexpected-file", "Unexpected"),
        ("missing-application", "application wheel"),
        ("missing-requirements", "requirements"),
        ("invalid-wheel", "wheel filename"),
        ("duplicate-wheel", "Duplicate runtime wheel"),
        ("duplicate-requirement", "Duplicate runtime requirement"),
        ("comment", None),
    ],
)
def test_bundle_content_policy_rejections(bundle_tree, mutation, diagnostic):
    root, project, manifest = bundle_tree
    manifest_path = root / "manifest.json"
    if mutation == "duplicate-key":
        manifest_path.write_text('{"schema_version":1,"schema_version":1}')
    elif mutation == "large-manifest":
        manifest_path.write_text(" " * (1024 * 1024 + 1))
    else:
        if mutation == "empty-files":
            manifest["files"] = {}
        elif mutation == "symlink":
            (root / "link").symlink_to(root / "requirements.txt")
        elif mutation == "unexpected-file":
            (root / "extra").write_text("payload")
            manifest["files"]["extra"] = sha256_file(root / "extra")
        elif mutation == "missing-application":
            manifest["application"] = "wheels/missing.whl"
        elif mutation == "missing-requirements":
            (root / "requirements.txt").unlink()
            del manifest["files"]["requirements.txt"]
        elif mutation in ("invalid-wheel", "duplicate-wheel"):
            name = (
                "wheels/invalid.whl"
                if mutation == "invalid-wheel"
                else "wheels/insomnia_run-0.2.0-cp312-none-any.whl"
            )
            (root / name).write_bytes(b"wheel")
            manifest["files"][name] = sha256_file(root / name)
        elif mutation in ("duplicate-requirement", "comment"):
            requirements = root / "requirements.txt"
            content = requirements.read_text()
            requirements.write_text(
                content
                + (
                    content
                    if mutation == "duplicate-requirement"
                    else "\n# wheels only\n"
                )
            )
            manifest["files"]["requirements.txt"] = sha256_file(requirements)
        manifest_path.write_text(json.dumps(manifest))
    if diagnostic:
        with pytest.raises(ValueError, match=diagnostic):
            verify_bundle(root, project, "cpython-312", "linux-x86_64")
    else:
        assert verify_bundle(root, project, "cpython-312", "linux-x86_64")


def test_inso_refuses_existing_symlink_binary(tmp_path):
    archive = tmp_path / "archive"
    digest = tar_archive(archive, {"inso": b"binary"})
    destination = tmp_path / "bin"
    destination.mkdir()
    existing = tmp_path / "existing"
    existing.write_bytes(b"unchanged")
    (destination / "inso").symlink_to(existing)
    with pytest.raises(ValueError, match="symlink"):
        install_inso(archive, digest, destination)
    assert existing.read_bytes() == b"unchanged"


def test_inso_cli_verify_only_and_runner_temp_scope(tmp_path, monkeypatch):
    archive = tmp_path / "archive"
    archive.write_bytes(b"verified")
    args = [
        "verify_inso_release.py",
        "--asset",
        "inso-linux-x64-99.0.0.tar.xz",
        "--archive-path",
        str(archive),
        "--inso-sha256",
        sha256_file(archive),
        "--offline-install",
    ]
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setattr(sys, "argv", args)
    inso_installer.main()
    archive.write_bytes(b"tampered")
    with pytest.raises(SystemExit):
        inso_installer.main()


def test_runtime_cli_confines_environment_to_runner_temp(tmp_path, monkeypatch):
    root = tmp_path / "runner"
    root.mkdir()
    monkeypatch.setenv("RUNNER_TEMP", str(root))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "install_runtime.py",
            "--project",
            str(ROOT),
            "--venv",
            str(tmp_path / "outside"),
        ],
    )
    with pytest.raises(SystemExit) as error:
        runtime_installer.main()
    assert error.value.code == 1


@pytest.mark.skipif(
    sys.version_info < (3, 11), reason="Release bundle builds require Python 3.11+"
)
@pytest.mark.parametrize(
    "fault",
    [
        None,
        "hash",
        "no-wheel",
        "unlocked",
        "unpinned",
        "url",
        "extras",
        "wildcard",
        "no-application",
    ],
)
def test_bundle_builder_and_installer_share_verified_manifest(
    tmp_path, monkeypatch, fault
):
    import runtime_bundle
    import sysconfig

    project = tmp_path / "project"
    (project / "src/insomnia_run").mkdir(parents=True)
    (project / "src/insomnia_run/__init__.py").write_text("")
    (project / "pyproject.toml").write_text(
        '[project]\nname="insomnia-run"\nversion="0.2.0"\n'
    )
    wheel = tmp_path / "dependency-1.0-py3-none-any.whl"
    wheel.write_bytes(b"locked dependency")
    digest = "a" * 64 if fault == "hash" else sha256_file(wheel)
    version = "2.0" if fault == "unlocked" else "1.0"
    wheel_entries = (
        ""
        if fault == "no-wheel"
        else f'{{url="https://files.pythonhosted.org/{wheel.name}",hash="sha256:{digest}"}}'
    )
    lock = f'[[package]]\nname = "dependency"\nversion = "{version}"\nwheels = [{wheel_entries}]\n'
    (project / "uv.lock").write_text(lock)

    def run(command, **kwargs):
        if "export" in command:
            requirement = {
                "unpinned": "dependency>=1.0",
                "url": "dependency @ https://example.org/dependency.whl",
                "extras": "dependency[extra]==1.0",
                "wildcard": "dependency==1.*",
            }.get(fault, "dependency==1.0")
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=requirement + "\nconditional==1.0; sys_platform == 'absent'\n",
            )
        directory = Path(command[command.index("--out-dir") + 1])
        directory.mkdir()
        if fault != "no-application":
            (directory / "insomnia_run-0.2.0-py3-none-any.whl").write_bytes(
                b"application"
            )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(
        "install_runtime.download_archive",
        lambda url, destination, **kwargs: destination.write_bytes(wheel.read_bytes()),
    )
    if fault:
        with pytest.raises(ValueError):
            runtime_bundle.build_bundle(project, tmp_path / "dist")
        return
    bundle = runtime_bundle.build_bundle(project, tmp_path / "dist")
    second = runtime_bundle.build_bundle(project, tmp_path / "second-dist")
    assert sha256_file(bundle) == sha256_file(second)
    extracted = tmp_path / "extracted"
    extract_verified(bundle, sha256_file(bundle), extracted)
    verified = verify_bundle(
        extracted, project, sys.implementation.cache_tag, sysconfig.get_platform()
    )
    assert verified.application.read_bytes() == b"application"
    assert "dependency==1.0 --hash=sha256:" in verified.requirements.read_text()
