"""Reviewed Python bootstrap metadata and post-install identity checks."""

import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import runpy
import shutil
import subprocess
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import managed_python  # noqa: E402


REVIEWED = {
    "cpython-3.14.8-linux-x86_64-gnu": (
        "x86_64-unknown-linux-gnu",
        "d8faa1b588506b9e3e5a3f57807bb056d534a1641a6b10d15b6ea3f0b413b960",
    ),
    "cpython-3.14.8-darwin-x86_64-none": (
        "x86_64-apple-darwin",
        "f0137337ecf6234b30c9c955219dae2d71e1a00387c4d204d6c6929e24bf9a90",
    ),
    "cpython-3.14.8-darwin-aarch64-none": (
        "aarch64-apple-darwin",
        "994adadc202c5df0b4570192cc9a70e3f2c131e512f4a125c56efa8562f44b28",
    ),
}


def test_manifest_contains_only_reviewed_builds():
    entries = managed_python.load_manifest(ROOT / "python-downloads.json")
    assert entries.keys() == REVIEWED.keys()
    for key, (triple, digest) in REVIEWED.items():
        assert entries[key]["sha256"] == digest
        assert entries[key]["url"] == (
            "https://github.com/astral-sh/python-build-standalone/releases/download/"
            f"20261013/cpython-3.14.8%2B20261013-{triple}-install_only_stripped.tar.gz"
        )


def test_manifest_checksum_matches_pre_python_bootstrap_pin():
    assert hashlib.sha256(
        (ROOT / "python-downloads.json").read_bytes()
    ).hexdigest() == (
        "542bf79edef9770b216e379066743f256dda36f1374c60106e7d30d9ac1c86a8"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("sha256", None),
        ("sha256", ""),
        ("sha256", "a" * 63),
        ("sha256", "g" * 64),
        ("major", True),
        ("patch", 9),
        ("variant", "freethreaded"),
        ("prerelease", "rc1"),
        ("build", "20261014"),
        ("arch", {"family": "x86_64", "variant": "v3"}),
        ("url", "https://mirror.example/python.tar.gz"),
    ],
)
def test_manifest_rejects_unreviewed_entry(tmp_path, field, value):
    data = json.loads((ROOT / "python-downloads.json").read_text())
    data["cpython-3.14.8-linux-x86_64-gnu"][field] = value
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="reviewed"):
        managed_python.load_manifest(path)


@pytest.mark.parametrize("change", ["missing", "extra", "missing-hash", "extra-field"])
def test_manifest_rejects_incomplete_or_expanded_catalog(tmp_path, change):
    data = json.loads((ROOT / "python-downloads.json").read_text())
    key = "cpython-3.14.8-linux-x86_64-gnu"
    if change == "missing":
        del data[key]
    elif change == "extra":
        data["cpython-3.15.0-linux-x86_64-gnu"] = copy.deepcopy(data[key])
    elif change == "missing-hash":
        del data[key]["sha256"]
    else:
        data[key]["extra"] = "unexpected"
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="reviewed"):
        managed_python.load_manifest(path)


@pytest.mark.parametrize("content", ["[]", "null", "{}", "not json"])
def test_manifest_rejects_invalid_documents(tmp_path, content):
    path = tmp_path / "metadata.json"
    path.write_text(content)
    with pytest.raises(ValueError):
        managed_python.load_manifest(path)


def test_manifest_rejects_non_object_entry(tmp_path):
    data = json.loads((ROOT / "python-downloads.json").read_text())
    data["cpython-3.14.8-linux-x86_64-gnu"] = None
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="reviewed"):
        managed_python.load_manifest(path)


def test_manifest_rejects_duplicate_json_keys(tmp_path):
    path = tmp_path / "metadata.json"
    content = (ROOT / "python-downloads.json").read_text()
    path.write_text(content.replace('"patch": 8,', '"patch": 9, "patch": 8,', 1))
    with pytest.raises(ValueError, match="Duplicate"):
        managed_python.load_manifest(path)


def installed_python(tmp_path, monkeypatch):
    key = "cpython-3.14.8-linux-x86_64-gnu"
    executable = tmp_path / key / "bin" / "python3.14"
    executable.parent.mkdir(parents=True)
    executable.touch()
    monkeypatch.setattr(managed_python.sys, "executable", str(executable))
    monkeypatch.setattr(managed_python.sys, "version_info", (3, 14, 8, "final", 0))
    monkeypatch.setattr(managed_python.sysconfig, "get_config_var", lambda name: 0)
    return key, executable


def test_verify_running_interpreter_checks_exact_installation(tmp_path, monkeypatch):
    key, executable = installed_python(tmp_path, monkeypatch)
    assert managed_python.verify_interpreter(tmp_path, key) == executable.resolve()


@pytest.mark.parametrize(
    "version", [(3, 14, 7, "final", 0), (3, 14, 8, "candidate", 1)]
)
def test_verify_interpreter_rejects_wrong_version(tmp_path, monkeypatch, version):
    key, _ = installed_python(tmp_path, monkeypatch)
    monkeypatch.setattr(managed_python.sys, "version_info", version)
    with pytest.raises(ValueError, match="CPython 3.14.8"):
        managed_python.verify_interpreter(tmp_path, key)


def test_verify_interpreter_rejects_freethreaded_build(tmp_path, monkeypatch):
    key, _ = installed_python(tmp_path, monkeypatch)
    monkeypatch.setattr(managed_python.sysconfig, "get_config_var", lambda name: 1)
    with pytest.raises(ValueError, match="CPython 3.14.8"):
        managed_python.verify_interpreter(tmp_path, key)


def test_verify_interpreter_rejects_other_implementation(tmp_path, monkeypatch):
    key, _ = installed_python(tmp_path, monkeypatch)
    monkeypatch.setattr(managed_python.sys.implementation, "name", "pypy")
    with pytest.raises(ValueError, match="CPython 3.14.8"):
        managed_python.verify_interpreter(tmp_path, key)


@pytest.mark.parametrize("arch", ["x86_64", "aarch64"])
def test_macos_uses_canonical_installation_directory(tmp_path, monkeypatch, arch):
    key = f"cpython-3.14.8-macos-{arch}-none"
    executable = tmp_path / key / "bin/python3.14"
    executable.parent.mkdir(parents=True)
    executable.touch()
    monkeypatch.setattr(managed_python.sys, "executable", str(executable))
    monkeypatch.setattr(managed_python.sys, "version_info", (3, 14, 8, "final", 0))
    monkeypatch.setattr(managed_python.sysconfig, "get_config_var", lambda name: 0)
    assert managed_python.verify_interpreter(tmp_path, key) == executable.resolve()


def test_verify_interpreter_rejects_different_installation(tmp_path, monkeypatch):
    key, _ = installed_python(tmp_path, monkeypatch)
    other = tmp_path / "other-python"
    other.touch()
    monkeypatch.setattr(managed_python.sys, "executable", str(other))
    with pytest.raises(ValueError, match="installation"):
        managed_python.verify_interpreter(tmp_path, key)


def test_verify_interpreter_rejects_symlink_escape(tmp_path, monkeypatch):
    key, executable = installed_python(tmp_path, monkeypatch)
    outside = tmp_path / "outside"
    outside.touch()
    executable.unlink()
    executable.symlink_to(outside)
    with pytest.raises(ValueError, match="installation"):
        managed_python.verify_interpreter(tmp_path, key)


def test_verify_interpreter_rejects_unknown_target(tmp_path):
    with pytest.raises(ValueError, match="reviewed"):
        managed_python.verify_interpreter(tmp_path, "../../outside")


def test_cli_failure_is_nonzero_without_traceback(tmp_path):
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/managed_python.py"),
            "--manifest",
            str(tmp_path / "missing.json"),
            "--target",
            "cpython-3.14.8-linux-x86_64-gnu",
            "--install-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    assert "Managed Python verification failed" in completed.stderr
    assert "Traceback" not in completed.stderr


def test_cli_success_prints_only_verified_path(tmp_path, monkeypatch, capsys):
    key, executable = installed_python(tmp_path, monkeypatch)
    monkeypatch.setattr(
        sys,
        "argv",
        ["managed_python.py", "--target", key, "--install-dir", str(tmp_path)],
    )
    managed_python.main()
    assert capsys.readouterr().out.strip() == str(executable.resolve())


def test_cli_failure_is_bounded(tmp_path, monkeypatch, capsys):
    key, _ = installed_python(tmp_path, monkeypatch)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "managed_python.py",
            "--manifest",
            str(tmp_path / "missing\n::error::injected"),
            "--target",
            key,
            "--install-dir",
            str(tmp_path),
        ],
    )
    with pytest.raises(SystemExit) as error:
        managed_python.main()
    assert error.value.code == 1
    assert capsys.readouterr().err == "Managed Python verification failed.\n"


def test_script_entry_point(tmp_path, monkeypatch, capsys):
    key, executable = installed_python(tmp_path, monkeypatch)
    monkeypatch.setattr(
        sys,
        "argv",
        ["managed_python.py", "--target", key, "--install-dir", str(tmp_path)],
    )
    runpy.run_path(str(ROOT / "scripts/managed_python.py"), run_name="__main__")
    assert capsys.readouterr().out.strip() == str(executable.resolve())


@pytest.fixture
def uv_binary():
    binary = os.environ.get("INSOMNIA_RUN_UV_BINARY")
    if not binary:
        pytest.skip("Set INSOMNIA_RUN_UV_BINARY to test verified uv 0.13.1")
    completed = subprocess.run(
        [binary, "--version"], capture_output=True, text=True, check=True
    )
    assert completed.stdout.split()[1] == "0.13.1"
    return binary


def uv_catalog(binary, manifest):
    return subprocess.run(
        [
            binary,
            "python",
            "list",
            "--only-downloads",
            "--all-platforms",
            "--all-arches",
            "--output-format",
            "json",
            "--no-config",
            "--offline",
            "--python-downloads-json-url",
            str(manifest),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )


def test_real_uv_catalog_has_only_reviewed_canonical_keys(uv_binary):
    completed = uv_catalog(uv_binary, ROOT / "python-downloads.json")
    assert completed.returncode == 0, completed.stderr
    entries = json.loads(completed.stdout)
    assert {entry["key"] for entry in entries} == managed_python.TARGETS


def test_real_uv_does_not_fallback_to_builtin_catalog(uv_binary, tmp_path):
    manifest = tmp_path / "empty.json"
    manifest.write_text("{}")
    completed = uv_catalog(uv_binary, manifest)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == []


def test_real_uv_optional_hash_requires_our_preflight(uv_binary, tmp_path):
    data = json.loads((ROOT / "python-downloads.json").read_text())
    del data["cpython-3.14.8-linux-x86_64-gnu"]["sha256"]
    manifest = tmp_path / "no-hash.json"
    manifest.write_text(json.dumps(data))
    completed = uv_catalog(uv_binary, manifest)
    assert completed.returncode == 0, completed.stderr
    assert len(json.loads(completed.stdout)) == 3
    with pytest.raises(ValueError, match="reviewed"):
        managed_python.load_manifest(manifest)


def test_real_uv_invalid_hash_fails_without_catalog_fallback(uv_binary, tmp_path):
    data = json.loads((ROOT / "python-downloads.json").read_text())
    data["cpython-3.14.8-linux-x86_64-gnu"]["sha256"] = "invalid"
    manifest = tmp_path / "invalid-hash.json"
    manifest.write_text(json.dumps(data))
    completed = uv_catalog(uv_binary, manifest)
    assert completed.returncode != 0
    assert not completed.stdout


def test_real_uv_offline_install_cannot_fetch(uv_binary, tmp_path):
    completed = subprocess.run(
        [
            uv_binary,
            "python",
            "install",
            "cpython-3.14.8-linux-x86_64-gnu",
            "--python-downloads-json-url",
            str(ROOT / "python-downloads.json"),
            "--install-dir",
            str(tmp_path / "install"),
            "--no-bin",
            "--no-config",
            "--no-cache",
            "--offline",
            "--mirror",
            "https://127.0.0.1:9",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert completed.returncode != 0
    assert "network connectivity is disabled" in completed.stderr.lower()
    assert not (tmp_path / "install/cpython-3.14.8-linux-x86_64-gnu").exists()


@pytest.fixture
def action_python_step():
    action = yaml.safe_load((ROOT / "action.yml").read_text())
    return next(step for step in action["runs"]["steps"] if step.get("id") == "python")


def test_actual_action_manifest_pin_matches_file(action_python_step):
    digest = hashlib.sha256((ROOT / "python-downloads.json").read_bytes()).hexdigest()
    assert re.findall(r"\b[a-f0-9]{64}\b", action_python_step["run"]) == [digest]


@pytest.fixture
def bootstrap_environment(tmp_path):
    action = tmp_path / "action with spaces"
    (action / "scripts").mkdir(parents=True)
    shutil.copyfile(ROOT / "python-downloads.json", action / "python-downloads.json")
    shutil.copyfile(
        ROOT / "scripts/managed_python.py", action / "scripts/managed_python.py"
    )
    tools = tmp_path / "tools"
    tools.mkdir()
    for name in ("awk", "sha256sum", "shasum"):
        executable = shutil.which(name)
        if executable:
            (tools / name).symlink_to(executable)
    uv = tools / "uv"
    uv.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$UV_CALLS"\nexit 97\n')
    uv.chmod(0o700)
    environment = {"HOME": str(tmp_path / "home"), "LC_ALL": "C"}
    environment.update(
        ACTION_PATH=str(action),
        RUNNER_TEMP=str(tmp_path / "runner"),
        RUNNER_OS="Linux",
        RUNNER_ARCH="X64",
        PYTHON_VERSION="3.14.8",
        OFFLINE_INSTALL="false",
        GITHUB_OUTPUT=str(tmp_path / "output"),
        UV_CALLS=str(tmp_path / "uv-calls"),
        PATH=str(tools),
    )
    return environment


def run_action_bootstrap(step, environment, *, timeout=15):
    return subprocess.run(
        ["/bin/bash", "--noprofile", "--norc", "-c", step["run"]],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


PLATFORMS = [
    ("Linux", "X64", "cpython-3.14.8-linux-x86_64-gnu"),
    ("macOS", "X64", "cpython-3.14.8-macos-x86_64-none"),
    ("macOS", "ARM64", "cpython-3.14.8-macos-aarch64-none"),
]


@pytest.mark.parametrize("system,arch,target", PLATFORMS)
@pytest.mark.parametrize("change", ["missing-hash", "null-hash", "malformed"])
def test_actual_action_rejects_changed_manifest_before_uv(
    action_python_step, bootstrap_environment, system, arch, target, change
):
    environment = bootstrap_environment
    environment.update(RUNNER_OS=system, RUNNER_ARCH=arch)
    manifest = Path(environment["ACTION_PATH"]) / "python-downloads.json"
    metadata = json.loads(manifest.read_text())
    entry = metadata[target.replace("-macos-", "-darwin-")]
    if change == "missing-hash":
        del entry["sha256"]
    else:
        entry["sha256"] = None
    manifest.write_text("{" if change == "malformed" else json.dumps(metadata))
    completed = run_action_bootstrap(action_python_step, environment)
    assert completed.returncode == 1, completed.stderr
    assert "manifest verification failed" in completed.stdout.lower()
    assert not Path(environment["UV_CALLS"]).exists()
    assert not Path(environment["GITHUB_OUTPUT"]).exists()


@pytest.mark.parametrize("system,arch,target", PLATFORMS)
def test_actual_action_uses_canonical_target_and_private_manifest(
    action_python_step, bootstrap_environment, system, arch, target
):
    environment = bootstrap_environment
    environment.update(RUNNER_OS=system, RUNNER_ARCH=arch)
    completed = run_action_bootstrap(action_python_step, environment)
    assert completed.returncode == 97, completed.stderr
    args = Path(environment["UV_CALLS"]).read_text().splitlines()
    assert args[:3] == ["python", "install", target]
    assert args[args.index("--python-downloads-json-url") + 1] == str(
        Path(environment["ACTION_PATH"]) / "python-downloads.json"
    )
    assert "--no-bin" in args


def test_online_action_rechecks_archive_instead_of_reusing_installation(
    action_python_step, bootstrap_environment
):
    completed = run_action_bootstrap(action_python_step, bootstrap_environment)
    assert completed.returncode == 97, completed.stderr
    args = Path(bootstrap_environment["UV_CALLS"]).read_text().splitlines()
    assert "--reinstall" in args, "Online bootstrap must verify the reviewed archive"
    assert "--no-config" in args, "Caller uv configuration must not alter bootstrap"


@pytest.fixture
def real_uv_bootstrap_environment(bootstrap_environment, uv_binary):
    system = "macOS" if sys.platform == "darwin" else "Linux"
    arch = {
        "arm64": "ARM64",
        "aarch64": "ARM64",
        "x86_64": "X64",
        "amd64": "X64",
    }.get(platform.machine().lower())
    if sys.platform not in ("linux", "darwin") or (system, arch) not in {
        (os_name, architecture) for os_name, architecture, _ in PLATFORMS
    }:
        pytest.skip("No reviewed Python build for this host")
    environment = bootstrap_environment
    environment.update(RUNNER_OS=system, RUNNER_ARCH=arch)
    uv = Path(environment["PATH"]) / "uv"
    uv.unlink()
    uv.symlink_to(Path(uv_binary).resolve())
    assert not (uv.parent / "python3").exists()
    return environment


def test_actual_action_offline_missing_python_cannot_fetch(
    action_python_step, real_uv_bootstrap_environment
):
    environment = real_uv_bootstrap_environment
    environment["OFFLINE_INSTALL"] = "true"
    completed = run_action_bootstrap(action_python_step, environment)
    assert completed.returncode != 0
    diagnostic = (completed.stdout + completed.stderr).lower()
    assert "offline" in diagnostic or "network connectivity is disabled" in diagnostic
    assert not Path(environment["GITHUB_OUTPUT"]).exists()


def test_actual_action_real_uv_without_host_python(
    action_python_step, real_uv_bootstrap_environment
):
    if os.environ.get("INSOMNIA_RUN_TEST_PYTHON_DOWNLOADS") != "1":
        pytest.skip(
            "Set INSOMNIA_RUN_TEST_PYTHON_DOWNLOADS=1 for a fresh real bootstrap"
        )
    environment = real_uv_bootstrap_environment
    completed = run_action_bootstrap(action_python_step, environment, timeout=180)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    target = next(
        key
        for os_name, architecture, key in PLATFORMS
        if (os_name, architecture)
        == (environment["RUNNER_OS"], environment["RUNNER_ARCH"])
    )
    expected = (
        Path(environment["RUNNER_TEMP"])
        / "insomnia-run-python"
        / target
        / "bin/python3.14"
    )
    assert (
        Path(environment["GITHUB_OUTPUT"]).read_text().strip()
        == f"executable={expected}"
    )
    environment["OFFLINE_INSTALL"] = "true"
    Path(environment["GITHUB_OUTPUT"]).unlink()
    completed = run_action_bootstrap(action_python_step, environment)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert (
        Path(environment["GITHUB_OUTPUT"]).read_text().strip()
        == f"executable={expected}"
    )
